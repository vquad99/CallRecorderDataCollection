"""Participants: IDs, phone handling, duplicates, field visibility per role, correction, deletion,
export, consent history.

Requirements: PART-001, PART-002, PART-003, PART-004, PART-005, PART-006, PART-007, PART-008, PART-009, PART-011, PART-012, ROLE-007, SEC-010
"""

from typing import Any

import pytest
from sqlalchemy import select, update

from app.modules.audit.models import AuditLog
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from tests.conftest import Api, make_participant, make_project, make_user

pytestmark = pytest.mark.db


@pytest.fixture
def world(db: Any, new_api: Any) -> dict[str, Any]:
    project = make_project(db, "VOICE")
    other = make_project(db, "OTHER")
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[project])
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[project])
    apis = {}
    for name in ("root", "pa", "mod", "qc", "cv"):
        apis[name] = new_api()
        assert apis[name].login(f"{name}@example.org").status_code == 200
    return {"project": project, "other": other, "mod_user": mod, **apis}


def test_create_assigns_code_and_normalises_phone(world: dict[str, Any], db: Any) -> None:
    pa: Api = world["pa"]
    p = make_participant(pa, world["project"].id, "Asha", "+91 98765-43210")
    assert p["participant_code"].startswith("P")
    assert p["phone"] == "+919876543210"
    stored = db.get(Participant, p["id"])
    assert "9876543210" not in (stored.phone_e164_enc or "")
    assert stored.phone_hint == "10"
    bad = pa.post(
        f"/api/v1/projects/{world['project'].id}/participants",
        json={"display_label": "X", "language_code": "hi", "phone": "98765"},
    )
    assert bad.json()["error"]["code"] == "INVALID_PHONE"


def test_duplicate_phone_is_detected(world: dict[str, Any]) -> None:
    pa: Api = world["pa"]
    first = make_participant(pa, world["project"].id, "Asha", "+919876543210")
    dup = pa.post(
        f"/api/v1/projects/{world['project'].id}/participants",
        json={"display_label": "Asha again", "language_code": "hi", "phone": "0091 98765 43210"},
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["details"] == [{"participant_code": first["participant_code"]}]


def test_language_must_be_one_of_the_projects(world: dict[str, Any], db: Any) -> None:
    from app.modules.projects.models import ProjectLanguage

    db.add(ProjectLanguage(project_id=world["project"].id, language_code="ta", dialect=""))
    db.commit()
    response = world["pa"].post(
        f"/api/v1/projects/{world['project'].id}/participants",
        json={"display_label": "X", "language_code": "hi"},
    )
    assert response.json()["error"]["code"] == "LANGUAGE_NOT_IN_PROJECT"


def _view(api: Api, project_id: Any, participant_id: str) -> dict[str, Any]:
    response = api.get(f"/api/v1/projects/{project_id}/participants/{participant_id}")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def test_fields_shown_per_role_and_assignment(world: dict[str, Any], db: Any) -> None:
    pid = world["project"].id
    a = make_participant(world["pa"], pid, "Asha", "+919876543210")
    b = make_participant(world["pa"], pid, "Bina", "+919876543211")
    for name in ("qc", "cv"):
        seen = _view(world[name], pid, a["id"])
        assert (seen["display_label"], seen["phone"], seen["notes"]) == (None, None, None), name
        assert seen["participant_code"] == a["participant_code"]
    unassigned = _view(world["mod"], pid, a["id"])
    assert (unassigned["display_label"], unassigned["phone"]) == (None, None)

    task = (
        world["pa"]
        .post(
            "/api/v1/tasks",
            json={
                "project_id": str(pid),
                "recording_mode": "TELEPHONY",
                "participant_a_id": a["id"],
                "participant_b_id": b["id"],
            },
        )
        .json()
    )
    assert (
        world["pa"]
        .post(f"/api/v1/tasks/{task['id']}/assign", json={"user_id": str(world["mod_user"].id)})
        .status_code
        == 200
    )
    assigned = _view(world["mod"], pid, a["id"])
    assert assigned["display_label"] == "Asha"
    assert assigned["phone"] == "••••••10"
    db.execute(
        update(Project)
        .where(Project.id == pid)
        .values(phone_visibility_policy="ASSIGNED_MODERATOR")
    )
    db.commit()
    assert _view(world["mod"], pid, a["id"])["phone"] == "+919876543210"


def test_correction_is_audited_without_the_phone_number(world: dict[str, Any], db: Any) -> None:
    pid = world["project"].id
    p = make_participant(world["pa"], pid, "Asha", "+919876543210")
    body = {"display_label": "Asha K", "language_code": "hi", "phone": "+919876500000"}
    assert (
        world["pa"]
        .patch(f"/api/v1/projects/{pid}/participants/{p['id']}", json=body)
        .json()["display_label"]
        == "Asha K"
    )
    db.expire_all()
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "participant.corrected")).one()
    assert '"Asha"' in (entry.before_summary or "")
    assert '"phone_changed": true' in (entry.after_summary or "")
    assert "9876500000" not in (entry.after_summary or "") + (entry.before_summary or "")


def test_delete_removes_personal_data_and_is_blocked_by_open_tasks(world: dict[str, Any]) -> None:
    pid = world["project"].id
    a = make_participant(world["pa"], pid, "Asha", "+919876543210")
    b = make_participant(world["pa"], pid, "Bina", "+919876543211")
    task = (
        world["pa"]
        .post(
            "/api/v1/tasks",
            json={
                "project_id": str(pid),
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": a["id"],
                "participant_b_id": b["id"],
            },
        )
        .json()
    )
    blocked = world["pa"].post(
        f"/api/v1/projects/{pid}/participants/{a['id']}/delete",
        json={"reason": "Asked to be removed"},
    )
    assert blocked.json()["error"]["code"] == "PARTICIPANT_IN_OPEN_TASK"
    world["pa"].post(
        f"/api/v1/tasks/{task['id']}/transition",
        json={"to": "CANCELLED", "reason_code": "CLIENT_REQUEST"},
    )
    gone = (
        world["pa"]
        .post(
            f"/api/v1/projects/{pid}/participants/{a['id']}/delete",
            json={"reason": "Asked to be removed"},
        )
        .json()
    )
    assert gone["deleted"] is True
    assert gone["phone"] is None
    assert gone["display_label"].startswith("Deleted participant")
    assert world["pa"].get(f"/api/v1/projects/{pid}/participants").json()["total"] == 1


def test_contact_export_needs_its_own_permission(world: dict[str, Any]) -> None:
    pid = world["project"].id
    make_participant(world["pa"], pid, "=cmd()", "+919876543210")
    assert world["pa"].get(f"/api/v1/projects/{pid}/participants/export").status_code == 403
    response = world["root"].get(f"/api/v1/projects/{pid}/participants/export")
    assert response.status_code == 200
    assert "+919876543210" in response.text
    assert "'=cmd()" in response.text


def test_consent_is_separate_history_and_access_controlled(world: dict[str, Any]) -> None:
    pid = world["project"].id
    a = make_participant(world["pa"], pid, "Asha", "+919876543210")
    b = make_participant(world["pa"], pid, "Bina", "+919876543211")
    task = (
        world["pa"]
        .post(
            "/api/v1/tasks",
            json={
                "project_id": str(pid),
                "recording_mode": "TELEPHONY",
                "participant_a_id": a["id"],
                "participant_b_id": b["id"],
            },
        )
        .json()
    )
    world["pa"].post(
        f"/api/v1/tasks/{task['id']}/assign", json={"user_id": str(world["mod_user"].id)}
    )
    for status in ("GIVEN", "WITHDRAWN"):
        r = world["mod"].post(
            f"/api/v1/tasks/{task['id']}/consent",
            json={"participant_id": a["id"], "status": status, "method": "VERBAL_RECORDED"},
        )
        assert r.status_code == 201
    history = world["pa"].get(f"/api/v1/projects/{pid}/participants/{a['id']}/consent").json()
    assert [h["status"] for h in history] == ["WITHDRAWN", "GIVEN"]
    assert history[0]["policy_version"] == "1"
    assert history[0]["captured_by"] == str(world["mod_user"].id)
    assert (
        world["qc"].get(f"/api/v1/projects/{pid}/participants/{a['id']}/consent").status_code == 403
    )
    assert (
        world["cv"].get(f"/api/v1/projects/{pid}/participants/{a['id']}/consent").status_code == 403
    )


def test_link_existing_participant_to_another_project(world: dict[str, Any], db: Any) -> None:
    from app.modules.projects.models import ProjectMembership

    p = make_participant(world["pa"], world["project"].id, "Asha", "+919876543210")
    db.add(ProjectMembership(user_id=world["mod_user"].id, project_id=world["other"].id))
    db.commit()
    root: Api = world["root"]
    linked = root.post(
        f"/api/v1/projects/{world['other'].id}/participants/link",
        json={"participant_code": p["participant_code"]},
    )
    assert linked.status_code == 201
    again = root.post(
        f"/api/v1/projects/{world['other'].id}/participants/link",
        json={"participant_code": p["participant_code"]},
    )
    assert again.json()["error"]["code"] == "ALREADY_LINKED"
    assert (
        world["pa"]
        .post(
            f"/api/v1/projects/{world['other'].id}/participants/link",
            json={"participant_code": p["participant_code"]},
        )
        .status_code
        == 404
    )
