"""API fields the task, participant and account pages read (2026-11-17), and emails to many people
sent after the answer instead of inside it.

Requirements: TASK-001, TASK-006, PART-002, AUTH-005, USER-005
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from app.modules.portal import service as portal
from app.modules.projects.models import Project
from app.modules.users import service as users
from tests.conftest import (
    Api,
    drop_email,
    make_participant,
    make_project,
    make_user,
    read_outbox,
)

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


def _with_form(world: dict[str, Any], project: Any = None) -> str:
    """The project (the world's unless named) gets a consent form; returns its participants
    path."""
    project = project or world["project"]
    db = world["db"]
    db.get(Project, project.id).consent_text = "I agree to be recorded."
    db.commit()
    return f"/api/v1/projects/{project.id}/participants"


def _consent_mails(outbox: Path) -> list[str]:
    return [m for m in read_outbox(outbox) if "Subject: Consent form for" in m]


def _second_project(world: dict[str, Any], code: str) -> Any:
    """Another project the world's Project Admin manages."""
    from app.modules.projects.models import ProjectMembership

    db = world["db"]
    project = make_project(db, code)
    pa_id = world["pa"].get("/api/v1/auth/me").json()["id"]
    db.add(ProjectMembership(user_id=uuid.UUID(pa_id), project_id=project.id))
    db.commit()
    return project


def test_everyone_who_joins_a_project_is_emailed_its_consent_form(
    world: dict[str, Any], outbox: Path
) -> None:
    """D-129: added on the form, from a file, or as someone who already exists - each gets their
    own consent form link by email after the answer, with nobody sending it by hand."""
    pa, base = world["pa"], _with_form(world)
    side = _second_project(world, "SIDE")  # no consent form there
    existing = make_participant(pa, side.id, "Esha")
    assert not _consent_mails(outbox), "a project without a consent form sends nothing"

    made = pa.post(
        base,
        json={"display_label": "Chitra", "language_code": "hi", "email": "chitra@example.org"},
    )
    assert made.status_code == 201, made.text
    assert made.json()["consent_email"] == "Consent form emailed."
    imported = pa.post(
        f"{base}/import",
        json={"csv": "name,email,language\nDevi,devi@example.org,hi\n", "confirm": True},
    ).json()
    assert imported["rows"][0]["message"] == "Added. Consent form emailed."
    linked = pa.post(f"{base}/link", json={"participant_code": existing["participant_code"]})
    assert linked.status_code == 201, linked.text
    assert linked.json()["consent_email"] == "Consent form emailed."

    mails = _consent_mails(outbox)
    for address in ("chitra@example.org", "devi@example.org", existing["email"]):
        [mail] = [m for m in mails if f"To: {address}" in m]
        assert "Subject: Consent form for Project ADD" in mail
        assert "/portal#" in mail
        assert "withdraw" not in mail
    assert len(mails) == 3
    listed = {p["participant_code"]: p for p in pa.get(base).json()["items"]}
    assert all(listed[p.json()["participant_code"]]["link_active"] for p in (made, linked))


def test_without_a_consent_form_nothing_is_sent_and_staff_are_told(
    world: dict[str, Any], outbox: Path
) -> None:
    pa = world["pa"]
    base = f"/api/v1/projects/{world['project'].id}/participants"
    made = pa.post(
        base,
        json={"display_label": "Chitra", "language_code": "hi", "email": "chitra@example.org"},
    )
    assert made.status_code == 201, made.text
    assert made.json()["consent_email"] == "Write the project's consent form, then send it."
    side = _second_project(world, "SIDE")
    moved = pa.post(
        f"{base}/bulk",
        json={
            "action": "assign",
            "participant_ids": [made.json()["id"]],
            "target_project_id": str(side.id),
        },
    ).json()
    assert moved["results"][0]["message"] == (
        "Assigned. Write the project's consent form, then send it."
    )
    assert not _consent_mails(outbox)


def test_consent_forms_of_an_assignment_are_emailed_after_the_answer(
    world: dict[str, Any], outbox: Path
) -> None:
    """Assigned in bulk to a project with a consent form, they get that project's form; the
    emails go out after the answer (by the worker), never inside the request."""
    db = world["db"]
    other = _second_project(world, "OTHER")
    other_base = _with_form(world, other)
    base = f"/api/v1/projects/{world['project'].id}/participants"
    celery = FakeCelery()
    world["app"].state.celery = celery
    drop_email(db, world["a"]["id"])  # A was saved before emails were required
    ids = [world["a"]["id"], world["b"]["id"]]
    answer = (
        world["pa"]
        .post(
            f"{base}/bulk",
            json={"action": "assign", "participant_ids": ids, "target_project_id": str(other.id)},
        )
        .json()
    )
    assert (answer["done"], answer["failed"]) == (2, 0)
    assert [r["message"] for r in answer["results"]] == [
        "Assigned. No email address: add one with Edit, then email the consent form.",
        "Assigned. Consent form emailed.",
    ]
    assert not _consent_mails(outbox), "nothing is sent inside the request"
    [(name, args)] = celery.sent
    assert (name, args[0], args[1]) == (portal.SEND_LINKS_TASK, str(other.id), [world["b"]["id"]])

    portal.send_links_job(world["app"].state, *args)  # what the worker does
    assert len(_consent_mails(outbox)) == 1
    listed = {p["id"]: p for p in world["pa"].get(other_base).json()["items"]}
    assert listed[world["b"]["id"]]["link_active"] is True


def test_a_broker_that_cannot_be_reached_is_reported_and_the_participant_kept(
    world: dict[str, Any],
) -> None:
    base = _with_form(world)
    world["app"].state.celery = FakeCelery(fail=True)
    made = world["pa"].post(
        base,
        json={"display_label": "Chitra", "language_code": "hi", "email": "chitra@example.org"},
    )
    assert made.status_code == 201, made.text
    assert made.json()["consent_email"] == (
        "The consent form could not be emailed now: use Email consent form again."
    )


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
