"""API fields the task, participant and account pages read (2026-11-17), and emails to many people
sent after the answer instead of inside it.

Requirements: TASK-001, TASK-006, PART-002, AUTH-005, USER-005
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.modules.portal import service as portal
from app.modules.projects.models import Project
from app.modules.users import service as users
from tests.conftest import Api, drop_email, make_participant, make_project, make_user

pytestmark = pytest.mark.db


class FakeCelery:
    """Stands in for the broker: keeps what was sent, or fails like an unreachable Redis."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, list[Any]]] = []

    def send_task(self, name: str, args: list[Any]) -> None:
        if self.fail:
            raise ConnectionError("broker down")
        self.sent.append((name, args))


@pytest.fixture
def world(db: Any, db_app: Any, new_api: Any) -> dict[str, Any]:
    project = make_project(db, "ADD")
    mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    pa: Api = new_api()
    assert pa.login("pa@example.org").status_code == 200
    moderator: Api = new_api()
    assert moderator.login("mod@example.org").status_code == 200
    a = make_participant(pa, project.id, "Asha", phone="+919876543210")
    b = make_participant(pa, project.id, "Bina")
    task = pa.post(
        "/api/v1/tasks",
        json={
            "project_id": str(project.id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": a["id"],
            "participant_b_id": b["id"],
        },
    ).json()
    return {
        "db": db,
        "app": db_app,
        "project": project,
        "pa": pa,
        "mod": moderator,
        "mod_id": str(mod.id),
        "a": a,
        "b": b,
        "task": task,
        "new_api": new_api,
    }


def test_task_detail_says_whether_the_moderator_can_be_changed(world: dict[str, Any]) -> None:
    pa, mod, tid = world["pa"], world["mod"], world["task"]["id"]
    assert world["task"]["can_reassign"] is True, "a draft task"
    assigned = pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": world["mod_id"]}).json()
    assert (assigned["status"], assigned["can_reassign"]) == ("ASSIGNED", True)
    assert mod.get(f"/api/v1/tasks/{tid}").json()["can_reassign"] is False, "not an assigner"
    mod.post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    assert pa.get(f"/api/v1/tasks/{tid}").json()["can_reassign"] is False, "work has started"


def test_a_masked_phone_number_says_so(world: dict[str, Any]) -> None:
    pa, mod = world["pa"], world["mod"]
    base = f"/api/v1/projects/{world['project'].id}/participants"
    a, b = world["a"], world["b"]
    full = pa.get(f"{base}/{a['id']}").json()
    assert (full["phone"], full["phone_masked"]) == ("+919876543210", False)
    pa.post(f"/api/v1/tasks/{world['task']['id']}/assign", json={"user_id": world["mod_id"]})
    masked = mod.get(f"{base}/{a['id']}").json()  # the project shows numbers to admins only
    assert (masked["phone"], masked["phone_masked"], masked["has_phone"]) == (
        "••••••10",
        True,
        True,
    )
    none = mod.get(f"{base}/{b['id']}").json()
    assert (none["phone"], none["phone_masked"], none["has_phone"]) == (None, False, False)


def test_timeline_entries_carry_the_status_change_itself(world: dict[str, Any]) -> None:
    pa, tid = world["pa"], world["task"]["id"]
    pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": world["mod_id"]})
    pa.post(f"/api/v1/tasks/{tid}/comments", json={"body": "Call after 5 pm"})
    pa.post(
        f"/api/v1/tasks/{tid}/transition",
        json={"to": "ON_HOLD", "reason_code": "CLIENT_REQUEST", "comment": "Wait for the client"},
    )
    entries = pa.get(f"/api/v1/tasks/{tid}/timeline").json()
    status = [e for e in entries if e["kind"] == "status"]
    assert [(e["from_status"], e["to_status"]) for e in status] == [
        (None, "DRAFT"),
        ("DRAFT", "ASSIGNED"),
        ("ASSIGNED", "ON_HOLD"),
    ]
    assert (status[-1]["reason_code"], status[-1]["comment"]) == (
        "CLIENT_REQUEST",
        "Wait for the client",
    )
    assert status[-1]["text"] == "ASSIGNED -> ON_HOLD CLIENT_REQUEST Wait for the client"
    for other in (e for e in entries if e["kind"] != "status"):
        assert (other["from_status"], other["to_status"], other["reason_code"]) == (None,) * 3
        assert other["comment"] is None


def test_me_tells_the_page_when_an_idle_session_ends(world: dict[str, Any]) -> None:
    me = world["pa"].get("/api/v1/auth/me").json()
    assert me["session_idle_minutes"] == world["app"].state.settings.session_idle_minutes == 10


def _with_email(world: dict[str, Any]) -> str:
    base = f"/api/v1/projects/{world['project'].id}/participants"
    db = world["db"]
    db.get(Project, world["project"].id).consent_text = "I agree to be recorded."
    db.commit()
    drop_email(db, world["a"]["id"])  # A was saved before emails were required
    world["pa"].patch(
        f"{base}/{world['b']['id']}",
        json={"display_label": "Bina", "language_code": "hi", "email": "bina@example.org"},
    )
    return base


def test_bulk_consent_forms_are_emailed_after_the_answer(
    world: dict[str, Any], outbox: Path
) -> None:
    base = _with_email(world)
    celery = FakeCelery()
    world["app"].state.celery = celery
    ids = [world["a"]["id"], world["b"]["id"]]
    answer = (
        world["pa"]
        .post(f"{base}/bulk", json={"action": "send_consent", "participant_ids": ids})
        .json()
    )
    assert (answer["done"], answer["failed"]) == (1, 1), "checked now: A has no email"
    assert answer["results"][1]["message"] == "Consent form will be emailed"
    assert not list(outbox.glob("*.eml")), "nothing is sent inside the request"
    [(name, args)] = celery.sent
    assert (name, args[1]) == (portal.SEND_LINKS_TASK, [world["b"]["id"]])

    portal.send_links_job(world["app"].state, *args)  # what the worker does
    assert len(list(outbox.glob("*.eml"))) == 1
    listed = {p["id"]: p for p in world["pa"].get(base).json()["items"]}
    assert listed[world["b"]["id"]]["link_active"] is True


def test_bulk_consent_reports_a_broker_that_cannot_be_reached(world: dict[str, Any]) -> None:
    base = _with_email(world)
    world["app"].state.celery = FakeCelery(fail=True)
    answer = (
        world["pa"]
        .post(
            f"{base}/bulk", json={"action": "send_consent", "participant_ids": [world["b"]["id"]]}
        )
        .json()
    )
    assert (answer["done"], answer["failed"]) == (0, 1)
    assert "could not be queued" in answer["results"][0]["message"]


def test_import_invitations_are_emailed_after_the_answer(
    world: dict[str, Any], outbox: Path
) -> None:
    root: Api = world["new_api"]()
    assert root.login("root@example.org").status_code == 200
    csv = "email,display_name,roles\nnew1@example.org,New One,MODERATOR\nnew2@example.org,New Two,QC_EXECUTIVE\n"
    celery = FakeCelery()
    world["app"].state.celery = celery
    result = root.post("/api/v1/users/import/confirm", json={"csv": csv}).json()
    assert (result["created"], result["invites_failed"]) == (2, 0)
    assert not list(outbox.glob("*.eml"))
    [(name, args)] = celery.sent
    assert name == users.SEND_INVITATIONS_TASK
    users.send_invitations_job(world["app"].state, *args)
    assert len(list(outbox.glob("*.eml"))) == 2

    world["app"].state.celery = FakeCelery(fail=True)
    csv = "email,display_name,roles\nnew3@example.org,New Three,MODERATOR\n"
    result = root.post("/api/v1/users/import/confirm", json={"csv": csv}).json()
    assert (result["created"], result["invites_failed"]) == (1, 1)
