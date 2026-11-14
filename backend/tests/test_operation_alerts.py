"""The platform checks itself and tells the people who run it (D-109): what it looks for, one
email when something new is wrong, a reminder while it stays wrong, one more when all is clear.

Requirements: OPS-006, SEC-001
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from app.core.email import EmailSendError
from app.main import create_app
from app.modules.exports.models import ExportJob
from app.modules.operations import service as operations
from app.modules.operations.models import OperationAlert
from app.modules.recordings.worker_dispatch import check_operations
from tests import test_export_jobs, test_telephony
from tests.conftest import Api, build_settings, make_project, make_user, read_outbox

pytestmark = pytest.mark.db

audio = test_telephony.audio
world = test_telephony.world
w = test_export_jobs.w


class Unreachable:
    def ping(self) -> None:
        raise ConnectionError("no answer")


def subjects(outbox: Path) -> list[str]:
    return [
        next(line[9:] for line in m.splitlines() if line.startswith("Subject: "))
        for m in read_outbox(outbox)
    ]


def failed_export(db: Any, project: Any, user: Any) -> ExportJob:
    job = ExportJob(
        project_id=project.id,
        requested_by=user.id,
        content="audio",
        scope="approved",
        table_format="csv",
        state="FAILED",
        file_name="audio.zip",
        finished_at=datetime.now(UTC),
    )
    db.add(job)
    db.commit()
    return job


def test_something_new_is_emailed_once_repeated_while_wrong_and_cleared(
    migrated_db: str, outbox: Path
) -> None:
    app = create_app(
        build_settings(
            database_url=migrated_db,
            email_file_dir=str(outbox),
            alert_email="ops@example.org, lead@example.org",
        )
    )
    with app.state.session_factory() as db:
        project = make_project(db, "ALERTS")
        admin = make_user(db, "sa@example.org", ["SUPER_ADMIN"])
        # Nothing wrong: nothing kept, nobody told.
        assert check_operations(app) is None
        assert db.scalars(select(OperationAlert)).all() == []
        assert read_outbox(outbox) == []

        # An export fails: both addresses get one message that says what and where to look.
        job = failed_export(db, project, admin)
        assert check_operations(app) == "problems"
        first = read_outbox(outbox)
        assert len(first) == 2
        assert {m.split("To: ")[1].splitlines()[0] for m in first} == {
            "ops@example.org",
            "lead@example.org",
        }
        assert subjects(outbox)[0] == "[Conversation Collection] 1 thing needs attention"
        assert "- 1 export failed in the last 24 hours. (since " in first[0]
        assert "/status" in first[0]
        assert "OPERATIONS_RUNBOOK.md" in first[0]
        # The same thing still wrong, even more of it: no second message.
        failed_export(db, project, admin)
        assert check_operations(app) is None
        assert len(read_outbox(outbox)) == 2
        db.expire_all()
        row = db.scalar(select(OperationAlert).where(OperationAlert.code == "EXPORTS_FAILED"))
        assert (row.active, row.count, row.summary) == (
            True,
            2,
            "2 exports failed in the last 24 hours.",
        )

        # Something else goes wrong: a message at once, naming everything that is wrong.
        app.state.storage = Unreachable()
        assert check_operations(app) == "problems"
        assert subjects(outbox)[-1] == "[Conversation Collection] 2 things need attention"
        latest = read_outbox(outbox)[-1]
        assert "File storage does not answer" in latest
        assert "2 exports failed" in latest
        assert len(read_outbox(outbox)) == 4

        # Still wrong a day later: one reminder; not before.
        assert check_operations(app) is None
        db.execute(
            update(OperationAlert).values(last_emailed_at=datetime.now(UTC) - timedelta(hours=25))
        )
        db.commit()
        assert check_operations(app) == "problems"
        assert check_operations(app) is None
        assert len(read_outbox(outbox)) == 6

        # The Super Admin's status page shows the same.
        client = TestClient(app)
        api = Api(client)
        assert api.login("sa@example.org").status_code == 200
        status = api.get("/api/v1/system/status").json()
        assert status["alerts"]["email_configured"] is True
        assert status["alerts"]["recipients"] == 2
        assert [a["code"] for a in status["alerts"]["active"]] == [
            "EXPORTS_FAILED",
            "STORAGE_UNREACHABLE",
        ]
        assert status["alerts"]["active"][0]["count"] == 2

        # Everything is put right: one message says so, and then it is quiet.
        app.state.storage = None
        db.execute(update(ExportJob).values(state="EXPIRED"))
        db.commit()
        assert job.id is not None
        assert check_operations(app) == "all_clear"
        assert subjects(outbox)[-1] == "[Conversation Collection] All clear"
        assert "in order again" in read_outbox(outbox)[-1]
        assert check_operations(app) is None
        assert len(read_outbox(outbox)) == 8
        db.expire_all()
        rows = db.scalars(select(OperationAlert)).all()
        assert [r.active for r in rows] == [False, False]
        assert all(r.resolved_at is not None for r in rows)
        assert api.get("/api/v1/system/status").json()["alerts"]["active"] == []
        client.close()


def test_without_an_address_problems_are_on_the_status_page_only(
    migrated_db: str, outbox: Path
) -> None:
    app = create_app(build_settings(database_url=migrated_db, email_file_dir=str(outbox)))
    with app.state.session_factory() as db:
        failed_export(
            db, make_project(db, "QUIET"), make_user(db, "sa@example.org", ["SUPER_ADMIN"])
        )
        assert check_operations(app) is None
        assert read_outbox(outbox) == []
        client = TestClient(app)
        api = Api(client)
        api.login("sa@example.org")
        alerts = api.get("/api/v1/system/status").json()["alerts"]
        assert (alerts["email_configured"], alerts["recipients"]) == (False, 0)
        assert [a["code"] for a in alerts["active"]] == ["EXPORTS_FAILED"]
        client.close()


def test_a_message_that_cannot_be_sent_is_tried_again_and_one_process_reviews_at_a_time(
    migrated_db: str, outbox: Path
) -> None:
    app = create_app(
        build_settings(
            database_url=migrated_db, email_file_dir=str(outbox), alert_email="ops@example.org"
        )
    )
    working = app.state.email_sender

    class Broken:
        def send(self, message: Any) -> None:
            raise EmailSendError("mail server down")

    with app.state.session_factory() as db:
        failed_export(
            db, make_project(db, "RETRY"), make_user(db, "sa@example.org", ["SUPER_ADMIN"])
        )
        # Another process holds the review: this one leaves everything alone.
        with app.state.engine.connect() as other:
            other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": operations.LOCK_KEY})
            assert check_operations(app) is None
            assert db.scalars(select(OperationAlert)).all() == []
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": operations.LOCK_KEY})
        # The mail server is down: the problem is kept, nobody counts as told.
        app.state.email_sender = Broken()
        assert check_operations(app) is None
        db.expire_all()
        kept = db.scalar(select(OperationAlert))
        assert (kept.active, kept.last_emailed_at) == (True, None)
        # It works again: the message goes out with the next look.
        app.state.email_sender = working
        assert check_operations(app) == "problems"
        assert len(read_outbox(outbox)) == 1


def test_what_it_looks_for_in_recordings_and_calls(w: dict[str, Any]) -> None:
    db, settings = w["db"], w["app"].state.settings
    fine = {"storage": "ok", "redis": "ok"}
    assert operations.find_problems(db, settings, fine) == []
    # A recording whose processing failed, one that has waited far too long, and a phone call
    # whose recording a person must pick.
    db.execute(
        text("UPDATE recordings SET state = 'FAILED' WHERE task_id = :t"), {"t": w["ftf_task"]}
    )
    db.execute(
        text(
            "UPDATE recordings SET state = 'UPLOADED', updated_at = now() - interval '3 hours'"
            " WHERE task_id = :t"
        ),
        {"t": w["phone_task"]},
    )
    db.execute(text("UPDATE calls SET state = 'NEEDS_MATCH'"))
    db.commit()
    found = {p.code: p for p in operations.find_problems(db, settings, fine)}
    assert set(found) == {"RECORDINGS_FAILED", "RECORDINGS_STUCK", "CALLS_NEED_PERSON"}
    assert found["RECORDINGS_FAILED"].summary == "1 recording could not be processed."
    assert "waited for processing for over 60 minutes" in found["RECORDINGS_STUCK"].summary
    assert found["CALLS_NEED_PERSON"].count == 1
    # A recording only just uploaded is not "stuck": recovery has not had its time yet.
    db.execute(text("UPDATE recordings SET updated_at = now() WHERE state = 'UPLOADED'"))
    db.commit()
    assert "RECORDINGS_STUCK" not in {p.code for p in operations.find_problems(db, settings, fine)}
    # The parts the platform depends on.
    down = operations.find_problems(db, settings, {"storage": "error", "redis": "error"})
    assert {"STORAGE_UNREACHABLE", "REDIS_UNREACHABLE"} <= {p.code for p in down}
