"""Payments (D-137): rates per project, amounts for approved work only, approval days in India
time, one row per person and project, a spreadsheet with safe cells, and who may see it.

Requirements: ROLE-002, ROLE-003, ROLE-012, DASH-002, DASH-003, EXP-007, SEC-010
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.modules.audit.models import AuditLog
from app.modules.auth.models import User
from app.modules.participants.models import Participant
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task, TaskStatusHistory
from tests.conftest import Api, make_project, make_user

pytestmark = pytest.mark.db

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 11, 10)
MINUTE = 60_000


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), IST)


def _participant(db: Any, code: str, name: str) -> Participant:
    person = Participant(participant_code=code, display_label=name, language_code="hi")
    db.add(person)
    db.flush()
    return person


def _task(
    db: Any,
    project: Any,
    code: str,
    people: tuple[Participant, Participant],
    status: str,
    recordings: list[tuple[Any, int]],
    approved_at: datetime | None = None,
) -> None:
    """A task with finished recordings (oldest first: the last one is current), and the moment
    it was approved."""
    task = Task(
        task_code=code,
        project_id=project.id,
        recording_mode="FACE_TO_FACE",
        status=status,
        participant_a_id=people[0].id,
        participant_b_id=people[1].id,
    )
    db.add(task)
    db.flush()
    for i, (user, ms) in enumerate(recordings):
        rec = Recording(
            task_id=task.id,
            mode="FACE_TO_FACE",
            state="READY",
            created_by=user.id,
            native_sample_rate=16000,
            channel_count=1,
            channel_handling="mono as recorded",
            started_at=datetime(2026, 11, 1, tzinfo=UTC) + timedelta(hours=i),
        )
        db.add(rec)
        db.flush()
        db.add(
            AudioAsset(
                recording_id=rec.id,
                project_id=project.id,
                kind="FTF_DERIVED_PCM",
                version=1,
                storage_key=f"test/{rec.id}.wav",
                file_extension="wav",
                container="wav",
                codec="pcm_s16le",
                sample_format="s16",
                sample_rate=16000,
                bit_depth=16,
                channels=1,
                duration_ms=ms,
                size_bytes=ms * 32,
                sha256=uuid.uuid4().hex * 2,
                clip_count=0,
                clip_pct=0.0,
                silence_pct=0.0,
            )
        )
    if approved_at is not None:
        db.add(
            TaskStatusHistory(
                task_id=task.id,
                from_status="ADMIN_REVIEW",
                to_status="APPROVED",
                created_at=approved_at,
            )
        )
    db.commit()


@pytest.fixture
def pay(db: Any, new_api: Any) -> dict[str, Any]:
    """Two projects with their own rates (P2 has no participant rate) and approved work around
    the India-time day DAY:

    - P1 T900001 approved DAY 10:00: 10 min by mo (Asha, Bina)
    - P1 T900002 approved DAY-1 23:59 (DAY 18:29 UTC the day before): 5 min by mo2 (Asha, Bina)
    - P1 T900003 at Audio QC, not approved: 7 min by mo
    - P1 T900004 approved DAY 12:00, recorded twice: 20 min by mo replaced by 4 min by mo2
      (Asha, Chitra)
    - P2 T900005 approved DAY 00:00 (the day before in UTC): 200 s by mo (Bina, Chitra)
    - P2 T900006 approved DAY+1 00:00 (still DAY in UTC): 6 min by mo (Bina, Chitra)
    """
    p1, p2 = make_project(db, "PAYONE"), make_project(db, "PAYTWO")
    sa = make_user(db, "sa@example.org", ["SUPER_ADMIN"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[p1])
    mo = make_user(db, "mo@example.org", ["MODERATOR"], projects=[p1, p2])
    mo2 = make_user(db, "mo2@example.org", ["MODERATOR"], projects=[p1])
    make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[p1, p2])
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[p1, p2])
    # A name that a spreadsheet would run as a formula (D-088).
    db.execute(update(User).where(User.id == mo2.id).values(display_name="=Mona"))
    asha = _participant(db, "P900001", "Asha")
    bina = _participant(db, "P900002", "Bina")
    chitra = _participant(db, "P900003", "Chitra")
    day_before, day_after = DAY - timedelta(days=1), DAY + timedelta(days=1)
    _task(db, p1, "T900001", (asha, bina), "APPROVED", [(mo, 10 * MINUTE)], at(DAY, 10))
    _task(db, p1, "T900002", (asha, bina), "APPROVED", [(mo2, 5 * MINUTE)], at(day_before, 23, 59))
    _task(db, p1, "T900003", (asha, bina), "AUDIO_QC", [(mo, 7 * MINUTE)])
    _task(
        db,
        p1,
        "T900004",
        (asha, chitra),
        "APPROVED",
        [(mo, 20 * MINUTE), (mo2, 4 * MINUTE)],
        at(DAY, 12),
    )
    _task(db, p2, "T900005", (bina, chitra), "APPROVED", [(mo, 200_000)], at(DAY, 0))
    _task(db, p2, "T900006", (bina, chitra), "APPROVED", [(mo, 6 * MINUTE)], at(day_after, 0))

    def api(email: str) -> Api:
        a: Api = new_api()
        assert a.login(email).status_code == 200, email
        return a

    callers = {who: api(f"{who}@example.org") for who in ("sa", "pa", "mo", "qc", "cv")}
    rates = {p1.id: ("2.00", "1.00"), p2.id: ("3.35", None)}
    for pid, (moderator, participant) in rates.items():
        answer = callers["sa"].put(
            f"/api/v1/payments/rates/{pid}",
            json={"moderator_rate": moderator, "participant_rate": participant},
        )
        assert answer.status_code == 200, answer.text
    return {"db": db, "p1": p1, "p2": p2, "sa_user": sa, **callers}


def get(api: Api, who: str, **params: Any) -> Any:
    return api.get(f"/api/v1/payments/{who}", params=params)


def table(body: dict[str, Any], *keys: str) -> list[tuple[Any, ...]]:
    return [tuple(r[k] for k in keys) for r in body["rows"]]


def test_moderators_are_paid_on_approved_minutes_at_their_projects_rates(
    pay: dict[str, Any],
) -> None:
    one_day = {"date_from": DAY.isoformat(), "date_to": DAY.isoformat()}
    body = get(pay["sa"], "moderators", **one_day).json()
    # The task at Audio QC is not paid; the re-recorded one is paid once, on its current
    # recording, to the moderator who made it; DAY-1 23:59 and DAY+1 00:00 India time are out,
    # DAY 00:00 is in. 3.33 min x 3.35 = 11.1555 -> 11.16.
    assert table(
        body, "project_code", "name", "approved_tasks", "approved_minutes", "rate", "amount"
    ) == [
        ("PAYONE", "=Mona", 1, "4.00", "2.00", "8.00"),
        ("PAYONE", "mo", 1, "10.00", "2.00", "20.00"),
        ("PAYTWO", "mo", 1, "3.33", "3.35", "11.16"),
    ]
    assert body["totals"] == {
        "count": 3,
        "minutes": "17.33",
        "amount": "39.16",
        "minutes_without_rate": "0.00",
    }
    assert (body["date_from"], body["date_to"], body["timezone"]) == (
        DAY.isoformat(),
        DAY.isoformat(),
        "Asia/Kolkata",
    )

    # Without days: everything approved so far.
    every = get(pay["sa"], "moderators").json()
    assert table(every, "project_code", "name", "approved_tasks", "approved_minutes", "amount") == [
        ("PAYONE", "=Mona", 2, "9.00", "18.00"),
        ("PAYONE", "mo", 1, "10.00", "20.00"),
        ("PAYTWO", "mo", 2, "9.33", "31.26"),
    ]
    # One project, and a search by name.
    only = get(pay["sa"], "moderators", project_id=str(pay["p2"].id)).json()
    assert {r["project_code"] for r in only["rows"]} == {"PAYTWO"}
    found = get(pay["sa"], "moderators", search="MONA").json()
    assert table(found, "name") == [("=Mona",)]
    # Days the wrong way round.
    backwards = get(pay["sa"], "moderators", date_from="2026-11-11", date_to="2026-11-10")
    assert backwards.status_code == 422
    assert (backwards.json()["error"]["code"], backwards.json()["error"]["message"]) == (
        "VALIDATION_ERROR",
        "The first day must not be after the last day",
    )


def test_participants_are_paid_on_their_share_and_a_missing_rate_shows_no_amount(
    pay: dict[str, Any],
) -> None:
    body = get(pay["sa"], "participants", date_from=DAY.isoformat(), date_to=DAY.isoformat())
    body = body.json()
    assert table(
        body,
        "project_code",
        "participant_code",
        "name",
        "approved_sessions",
        "payable_minutes",
        "rate",
        "amount",
    ) == [
        ("PAYONE", "P900001", "Asha", 2, "7.00", "1.00", "7.00"),
        ("PAYONE", "P900002", "Bina", 1, "5.00", "1.00", "5.00"),
        ("PAYONE", "P900003", "Chitra", 1, "2.00", "1.00", "2.00"),
        # PAYTWO has no participant rate yet: the minutes, no amount.
        ("PAYTWO", "P900002", "Bina", 1, "1.67", None, None),
        ("PAYTWO", "P900003", "Chitra", 1, "1.67", None, None),
    ]
    assert body["totals"] == {
        "count": 6,
        "minutes": "17.34",
        "amount": "14.00",
        "minutes_without_rate": "3.34",
    }
    by_code = get(pay["sa"], "participants", search="p900003").json()
    assert table(by_code, "project_code") == [("PAYONE",), ("PAYTWO",)]


def test_the_spreadsheets_add_up_and_are_safe_to_open(pay: dict[str, Any]) -> None:
    answer = pay["sa"].get(
        "/api/v1/payments/moderators/export",
        params={"date_from": DAY.isoformat(), "date_to": DAY.isoformat()},
    )
    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/csv")
    assert 'filename="payments_moderators_all_' in answer.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(answer.content.decode("utf-8-sig"))))
    assert rows == [
        [
            "project",
            "moderator",
            "approved_tasks",
            "approved_minutes",
            "rate_inr_per_minute",
            "amount_inr",
        ],
        ["PAYONE", "'=Mona", "1", "4.00", "2.00", "8.00"],
        ["PAYONE", "mo", "1", "10.00", "2.00", "20.00"],
        ["PAYTWO", "mo", "1", "3.33", "3.35", "11.16"],
        ["Total", "", "3", "17.33", "", "39.16"],
    ]
    people = pay["sa"].get(
        "/api/v1/payments/participants/export", params={"project_id": str(pay["p2"].id)}
    )
    rows = list(csv.reader(io.StringIO(people.content.decode("utf-8-sig"))))
    assert rows[1:] == [
        ["PAYTWO", "P900002", "Bina", "2", "4.67", "", "No rate set"],
        ["PAYTWO", "P900003", "Chitra", "2", "4.67", "", "No rate set"],
        ["Total", "", "", "4", "9.34", "", "0.00"],
    ]
    assert 'filename="payments_participants_PAYTWO_' in people.headers["content-disposition"]
    downloads = pay["db"].scalars(
        select(AuditLog.after_summary).where(AuditLog.action == "payments.exported")
    )
    assert len(list(downloads)) == 2


def test_rates_are_kept_per_project_checked_and_audited(pay: dict[str, Any]) -> None:
    sa, p1 = pay["sa"], pay["p1"]
    rates = {r["project_code"]: r for r in sa.get("/api/v1/payments/rates").json()}
    assert (rates["PAYONE"]["moderator_rate"], rates["PAYONE"]["participant_rate"]) == (
        "2.00",
        "1.00",
    )
    assert (rates["PAYTWO"]["participant_rate"], rates["PAYTWO"]["updated_by"]) == (None, "sa")
    for bad in ("-1", "1.005", "100001"):
        refused = sa.put(f"/api/v1/payments/rates/{p1.id}", json={"moderator_rate": bad})
        assert refused.status_code == 422, bad
    changed = sa.put(
        f"/api/v1/payments/rates/{p1.id}",
        json={"moderator_rate": "2.5", "participant_rate": "1.00"},
    )
    assert changed.json()["moderator_rate"] == "2.50"
    entries = (
        pay["db"]
        .execute(
            select(AuditLog.before_summary, AuditLog.after_summary)
            .where(AuditLog.action == "payments.rates_changed", AuditLog.project_id == p1.id)
            .order_by(AuditLog.created_at)
        )
        .all()
    )
    assert len(entries) == 2  # set, then changed
    assert "2.00" in str(entries[1][0])
    assert "2.50" in str(entries[1][1])
    # The new rate applies to the project's approved minutes: 10 min x 2.50.
    body = get(sa, "moderators", project_id=str(p1.id), search="mo").json()
    assert ("mo", "25.00") in table(body, "name", "amount")


def test_only_the_people_who_run_a_project_see_its_payments(pay: dict[str, Any]) -> None:
    p1, p2 = pay["p1"], pay["p2"]
    # Moderators, QC Executives and Client Viewers see no payments at all.
    for who in ("mo", "qc", "cv"):
        api = pay[who]
        for path in (
            "/api/v1/payments/rates",
            "/api/v1/payments/moderators",
            "/api/v1/payments/participants",
            "/api/v1/payments/moderators/export",
            "/api/v1/payments/participants/export",
        ):
            assert api.get(path).status_code == 403, (who, path)
        assert (
            api.put(f"/api/v1/payments/rates/{p1.id}", json={"moderator_rate": "9"}).status_code
            == 403
        )
    # A Project Admin sees their own project only; another project is like a missing one.
    pa = pay["pa"]
    assert [r["project_code"] for r in pa.get("/api/v1/payments/rates").json()] == ["PAYONE"]
    assert {r["project_code"] for r in get(pa, "moderators").json()["rows"]} == {"PAYONE"}
    assert {r["project_code"] for r in get(pa, "participants").json()["rows"]} == {"PAYONE"}
    assert get(pa, "moderators", project_id=str(p2.id)).status_code == 404
    assert pa.put(f"/api/v1/payments/rates/{p2.id}", json={}).status_code == 404
    assert pa.put(f"/api/v1/payments/rates/{p1.id}", json={}).status_code == 200
