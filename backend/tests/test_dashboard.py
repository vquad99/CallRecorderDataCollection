"""Dashboard: progress for clients, own work for staff, operations for managers (owner 2026-11-10).

Requirements: DASH-001, DASH-002, DASH-004, DASH-005, ROLE-007
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from app.modules.auth.models import User
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task
from tests import test_recordings
from tests.conftest import make_project, make_user
from tests.test_recordings import _record, chunks

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world

MANAGER_ONLY = ("queues", "team", "storage_bytes")
STAFF_ONLY = ("tasks_by_status", "qc")


def _users(world: dict[str, Any]) -> dict[str, Any]:
    db, project = world["db"], world["project"]
    other = make_project(db, "ELSEWHERE")
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[project])
    make_user(db, "cv.other@example.org", ["CLIENT_VIEWER"], projects=[other])
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    return {"other": other}


def test_hours_are_counted_once_per_recording_against_the_daily_target(
    world: dict[str, Any],
) -> None:
    _users(world)
    db, project = world["db"], world["project"]
    project.target_face_to_face_hours_per_day = 2.5
    project.target_telephony_hours_per_day = 1.5
    db.commit()
    _record(world, chunks(3, 1))  # 4 s
    body = world["pa"].get("/api/v1/dashboard", params={"project_id": str(project.id)}).json()
    assert body["view"] == "manager"
    assert body["recordings"] == 1
    ftf = next(m for m in body["by_mode"] if m["mode"] == "FACE_TO_FACE")
    assert ftf["recordings"] == 1
    assert ftf["recorded_hours"] == round(4 / 3600, 2)
    assert body["target_hours_per_day"] == 4.0
    assert len(body["daily"]) == 30
    assert body["approved_hours"] == 0
    assert body["tasks_total"] == 1
    assert body["tasks_by_status"] == {"RECORDED": 1}, "waits for the moderator (D-092)"
    assert body["queues"]["failed_processing"] == 0
    assert body["team"][0]["recordings"] == 1
    assert body["storage_bytes"] > 0


def test_approved_hours_follow_the_task_reaching_approved(world: dict[str, Any]) -> None:
    rid = _record(world, chunks(60, 0))
    assert rid
    db = world["db"]
    db.execute(update(Task).where(Task.id == world["task"]["id"]).values(status="APPROVED"))
    db.commit()
    body = world["pa"].get("/api/v1/dashboard").json()
    assert body["approved_hours"] == body["recorded_hours"] == round(60 / 3600, 2)
    assert body["tasks_approved"] == 1
    assert body["qc"]["passed"] == 1


def test_a_client_sees_progress_only_and_only_for_its_projects(world: dict[str, Any]) -> None:
    extra = _users(world)
    _record(world, chunks(2, 0))
    client = world["api"]("cv@example.org")
    body = client.get("/api/v1/dashboard").json()
    assert body["view"] == "client"
    assert body["recordings"] == 1
    for key in MANAGER_ONLY + STAFF_ONLY:
        assert body[key] is None, key
    assert [p["code"] for p in body["projects"]] == ["VOICE"]
    # Another project's client sees none of it, and naming the project answers like a missing one.
    outsider = world["api"]("cv.other@example.org")
    assert outsider.get("/api/v1/dashboard").json()["recordings"] == 0
    missing = outsider.get(
        "/api/v1/dashboard", params={"project_id": "00000000-0000-0000-0000-000000000001"}
    )
    foreign = outsider.get("/api/v1/dashboard", params={"project_id": str(world["project"].id)})
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == missing.json()["error"]["code"]
    assert (
        outsider.get("/api/v1/dashboard", params={"project_id": str(extra["other"].id)}).status_code
        == 200
    )


def test_staff_see_their_own_work_without_the_operations_view(world: dict[str, Any]) -> None:
    _record(world, chunks(2, 0))
    db, project = world["db"], world["project"]
    project.target_face_to_face_hours_per_day = 2.5
    db.commit()
    mine = world["mod"].get("/api/v1/dashboard").json()
    assert mine["view"] == "worker"
    assert mine["target_hours_per_day"] == 0, "no project targets in someone's own work"
    assert all(m["target_hours_per_day"] == 0 for m in mine["by_mode"])
    assert mine["recordings"] == 1
    assert mine["tasks_by_status"] == {"RECORDED": 1}
    for key in MANAGER_ONLY:
        assert mine[key] is None, key
    # A moderator in the same project with no tasks sees zero, not the project's totals.
    other = world["api"]("mod2@example.org").get("/api/v1/dashboard").json()
    assert (other["recordings"], other["tasks_total"]) == (0, 0)
    qc = world["api"]("qc@example.org").get("/api/v1/dashboard").json()
    assert (qc["view"], qc["recordings"]) == ("worker", 0)


def test_a_super_admin_sees_every_project(world: dict[str, Any]) -> None:
    _users(world)
    _record(world, chunks(2, 0))
    body = world["api"]("root@example.org").get("/api/v1/dashboard").json()
    assert body["view"] == "manager"
    assert {p["code"] for p in body["projects"]} == {"VOICE", "ELSEWHERE"}
    assert body["recordings"] == 1


def test_the_window_is_bounded(world: dict[str, Any]) -> None:
    pa = world["pa"]
    assert len(pa.get("/api/v1/dashboard", params={"days": 7}).json()["daily"]) == 7
    assert pa.get("/api/v1/dashboard", params={"days": 365}).status_code == 422


def test_a_client_sees_only_projects_it_belongs_to_everywhere(world: dict[str, Any]) -> None:
    extra = _users(world)
    client = world["api"]("cv@example.org")
    listed = [p["code"] for p in client.get("/api/v1/projects").json()["items"]]
    assert listed == ["VOICE"]
    assert client.get(f"/api/v1/projects/{extra['other'].id}").status_code == 404
    assert [p["code"] for p in client.get("/api/v1/dashboard").json()["projects"]] == ["VOICE"]


HOUR = 3_600_000


def _take(db: Any, project: Any, task_id: uuid.UUID, by: uuid.UUID, ms: int, at: datetime) -> None:
    """A finished recording of the task, its delivery file `ms` long."""
    rec = Recording(
        task_id=task_id,
        mode="FACE_TO_FACE",
        state="READY",
        created_by=by,
        native_sample_rate=16000,
        channel_count=1,
        channel_handling="mono",
        started_at=at,
    )
    db.add(rec)
    db.flush()
    db.add(
        AudioAsset(
            recording_id=rec.id,
            project_id=project.id,
            kind="FTF_DERIVED_PCM",
            version=1,
            storage_key=f"{project.code}/{rec.id}.wav",
            file_extension="wav",
            container="wav",
            codec="pcm_s16le",
            sample_format="int",
            sample_rate=16000,
            bit_depth=16,
            channels=1,
            duration_ms=ms,
            size_bytes=ms * 32,
            sha256=rec.id.hex * 2,
            clip_count=0,
            clip_pct=0.0,
            silence_pct=0.0,
            effective_ms=ms // 2,
            longest_pause_ms=0,
            pauses_ms=[],
        )
    )
    db.commit()


def test_a_replaced_recording_is_not_counted_again(world: dict[str, Any]) -> None:
    """D-135: the moderator chose Record again, so the task has two finished takes, 1 h then
    2 h. Every figure counts the current take only, as the Progress tab, the export and the
    minutes do; the moderators' output still shows both takes they made."""
    _users(world)
    db, project = world["db"], world["project"]
    tid = uuid.UUID(world["task"]["id"])
    mod = db.scalar(select(User.id).where(User.email == "mod@example.org"))
    now = datetime.now(UTC)
    _take(db, project, tid, mod, 1 * HOUR, now - timedelta(minutes=90))
    _take(db, project, tid, mod, 2 * HOUR, now - timedelta(minutes=20))
    db.execute(update(Task).where(Task.id == tid).values(status="APPROVED"))
    db.execute(update(Project).where(Project.id == project.id).values(progress_counts="FULL"))
    db.commit()

    progress = world["pa"].get(f"/api/v1/projects/{project.id}/progress")
    assert progress.status_code == 200, progress.text
    approved_ms = progress.json()["completed"]["approved_ms"]
    assert approved_ms == 2 * HOUR
    for who in (world["pa"], world["api"]("cv@example.org")):
        body = who.get("/api/v1/dashboard", params={"project_id": str(project.id)}).json()
        assert body["recordings"] == 1
        assert body["recorded_hours"] == body["approved_hours"] == approved_ms / HOUR
        assert body["completed_hours"] == 2.0, "FULL: the current take's full length"
        assert body["effective_hours"] == 1.0
        assert round(sum(d["approved_hours"] for d in body["daily"]), 2) == 2.0
        face = next(m for m in body["by_mode"] if m["mode"] == "FACE_TO_FACE")
        assert (face["recordings"], face["approved_hours"]) == (1, 2.0)
    team = world["pa"].get("/api/v1/dashboard").json()["team"]
    assert [(t["recordings"], t["recorded_hours"]) for t in team] == [(2, 3.0)]


def test_the_daily_target_is_the_live_projects_unless_one_is_chosen(
    world: dict[str, Any],
) -> None:
    """A completed, paused or archived project's target is not today's work: over several
    projects only the active ones add theirs; a project chosen shows its own."""
    db, voice = world["db"], world["project"]
    voice.target_face_to_face_hours_per_day = 2
    voice.target_telephony_hours_per_day = 1
    others = {}
    for code, status, hours in (
        ("DONE", "COMPLETED", 5),
        ("HELD", "PAUSED", 3),
        ("OLD", "ARCHIVED", 7),
    ):
        others[code] = make_project(db, code, status=status)
        others[code].target_face_to_face_hours_per_day = hours
        others[code].target_telephony_hours_per_day = 0
    db.commit()
    make_user(db, "pa.all@example.org", ["PROJECT_ADMIN"], projects=[voice, *others.values()])
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    for email in ("pa.all@example.org", "root@example.org"):
        who = world["api"](email)
        everything = who.get("/api/v1/dashboard").json()
        assert everything["target_hours_per_day"] == 3.0, email
        by_mode = {m["mode"]: m["target_hours_per_day"] for m in everything["by_mode"]}
        assert by_mode == {"FACE_TO_FACE": 2.0, "TELEPHONY": 1.0}
        done = who.get("/api/v1/dashboard", params={"project_id": str(others["DONE"].id)}).json()
        assert done["target_hours_per_day"] == 5.0, email
