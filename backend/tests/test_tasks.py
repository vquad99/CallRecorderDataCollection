"""Task lifecycle: creation rules, moderator assignment, the state machine, history, rollback,
visibility, consent capture, comments, timeline.

Requirements: TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-012, PROJ-010, PART-004
"""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from app.modules.audit import service as audit_service
from app.modules.tasks import service, workflow
from app.modules.tasks.models import TASK_STATUSES, Task, TaskStatusHistory
from tests.conftest import make_participant, make_project, make_user, set_status

pytestmark = pytest.mark.db


@pytest.fixture
def world(db: Any, new_api: Any) -> dict[str, Any]:
    project = make_project(db, "VOICE")
    mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    mod2 = make_user(db, "mod2@example.org", ["MODERATOR"], projects=[project])
    outsider = make_user(db, "out@example.org", ["MODERATOR"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    apis = {n: new_api() for n in ("pa", "mod", "mod2")}
    for n, a in apis.items():
        assert a.login(f"{n}@example.org").status_code == 200
    a = make_participant(apis["pa"], project.id, "Asha", "+919876543210")
    b = make_participant(apis["pa"], project.id, "Bina", "+919876543211")
    c = make_participant(apis["pa"], project.id, "Chitra")
    return {
        "project": project,
        "mod_user": mod,
        "mod2_user": mod2,
        "outsider": outsider,
        "a": a,
        "b": b,
        "c": c,
        **apis,
    }


def _create(w: dict[str, Any], mode: str = "TELEPHONY", b: str = "b") -> Any:
    return w["pa"].post(
        "/api/v1/tasks",
        json={
            "project_id": str(w["project"].id),
            "recording_mode": mode,
            "participant_a_id": w["a"]["id"],
            "participant_b_id": w[b]["id"],
            "priority": "HIGH",
        },
    )


def test_create_rules(world: dict[str, Any], db: Any) -> None:
    created = _create(world)
    assert created.status_code == 201
    task = created.json()
    assert task["task_code"].startswith("T")
    assert task["status"] == "DRAFT"
    assert _create(world, b="c").json()["error"]["code"] == "PHONE_REQUIRED"
    assert _create(world, mode="FACE_TO_FACE", b="c").status_code == 201
    same = world["pa"].post(
        "/api/v1/tasks",
        json={
            "project_id": str(world["project"].id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": world["a"]["id"],
            "participant_b_id": world["a"]["id"],
        },
    )
    assert same.json()["error"]["code"] == "SAME_PARTICIPANT"
    world["project"].status = "ARCHIVED"
    db.commit()
    assert _create(world).json()["error"]["code"] == "PROJECT_NOT_ACCEPTING_WORK"


def test_assignment_rules_and_visibility(world: dict[str, Any]) -> None:
    task = _create(world).json()
    tid = task["id"]
    outsider = world["pa"].post(
        f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["outsider"].id)}
    )
    assert outsider.json()["error"]["code"] == "NOT_PROJECT_MEMBER"
    assigned = (
        world["pa"]
        .post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
        .json()
    )
    assert assigned["status"] == "ASSIGNED"
    assert assigned["moderator_name"] == "mod"
    assert world["mod"].get(f"/api/v1/tasks/{tid}").status_code == 200
    assert world["mod2"].get(f"/api/v1/tasks/{tid}").status_code == 404
    assert world["mod2"].get("/api/v1/tasks").json()["total"] == 0
    assert world["mod"].get("/api/v1/tasks").json()["total"] == 1

    no_reason = world["pa"].post(
        f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod2_user"].id)}
    )
    assert no_reason.json()["error"]["code"] == "REASON_REQUIRED"
    moved = world["pa"].post(
        f"/api/v1/tasks/{tid}/assign",
        json={"user_id": str(world["mod2_user"].id), "reason": "mod is on leave"},
    )
    assert moved.json()["moderator_name"] == "mod2"
    assert world["mod"].get(f"/api/v1/tasks/{tid}").status_code == 404
    timeline = world["pa"].get(f"/api/v1/tasks/{tid}/timeline").json()
    assert any("mod is on leave" in e["text"] for e in timeline)


def test_only_the_assigned_moderator_starts_the_task(world: dict[str, Any]) -> None:
    tid = _create(world).json()["id"]
    world["pa"].post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    assert (
        world["pa"]
        .post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
        .json()["error"]["code"]
        == "FORBIDDEN"
    )
    started = world["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    assert started.json()["status"] == "IN_PROGRESS"


def test_full_lifecycle_to_approved_with_history(world: dict[str, Any], db: Any) -> None:
    tid = _create(world).json()["id"]
    world["pa"].post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    world["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    db.expire_all()
    task = db.get(Task, tid)
    for target in workflow.FORWARD_PATH[3:]:
        service.system_transition(db, task, target)
    assert task.status == "APPROVED"
    history = db.scalars(
        select(TaskStatusHistory.to_status)
        .where(TaskStatusHistory.task_id == task.id)
        .order_by(TaskStatusHistory.created_at)
    ).all()
    assert list(history) == list(workflow.FORWARD_PATH)


def test_platform_only_steps_cannot_be_set_through_the_api(world: dict[str, Any], db: Any) -> None:
    tid = _create(world).json()["id"]
    for status, target in [
        ("DRAFT", "ASSIGNED"),
        ("IN_PROGRESS", "RECORDED"),
        ("RECORDED", "AUDIO_QC"),
        ("AUDIO_QC", "APPROVED"),
        ("AUDIO_QC", "RETURNED"),
    ]:
        set_status(db, tid, status)
        response = world["pa"].post(f"/api/v1/tasks/{tid}/transition", json={"to": target})
        assert response.json()["error"]["code"] == "INVALID_TRANSITION", (status, target)


def test_every_invalid_transition_fails_through_the_api(world: dict[str, Any], db: Any) -> None:
    tid = _create(world).json()["id"]
    world["pa"].post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    accepted = []
    for status in TASK_STATUSES:
        for target in TASK_STATUSES:
            set_status(db, tid, status, held_from="ASSIGNED" if status == "ON_HOLD" else None)
            kind = workflow.required_kind(
                status, target, "ASSIGNED" if status == "ON_HOLD" else None
            )
            api = world["mod"] if kind == "moderator" else world["pa"]
            response = api.post(
                f"/api/v1/tasks/{tid}/transition",
                json={"to": target, "reason_code": "OTHER", "comment": "test"},
            )
            if response.status_code == 200:
                accepted.append((status, target))
            else:
                assert response.status_code in (403, 409, 422), (
                    status,
                    target,
                    response.status_code,
                )
    allowed = {
        (s, t)
        for s in TASK_STATUSES
        for t in TASK_STATUSES
        if workflow.required_kind(s, t, "ASSIGNED" if s == "ON_HOLD" else None)
        in ("assign", "moderator")
    }
    assert set(accepted) == allowed


def test_exception_states_need_reason_codes_and_hold_resumes(world: dict[str, Any]) -> None:
    tid = _create(world).json()["id"]
    world["pa"].post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})

    def t(body: dict[str, Any]) -> Any:
        return world["pa"].post(f"/api/v1/tasks/{tid}/transition", json=body)

    assert t({"to": "ON_HOLD"}).json()["error"]["code"] == "REASON_REQUIRED"
    assert (
        t({"to": "ON_HOLD", "reason_code": "OTHER"}).json()["error"]["code"] == "COMMENT_REQUIRED"
    )
    held = t({"to": "ON_HOLD", "reason_code": "WAITING_FOR_PARTICIPANT"}).json()
    assert (held["status"], held["held_from"]) == ("ON_HOLD", "ASSIGNED")
    assert held["allowed_transitions"] == ["ASSIGNED", "CANCELLED"]
    assert t({"to": "IN_PROGRESS"}).json()["error"]["code"] == "INVALID_TRANSITION"
    assert t({"to": "ASSIGNED"}).json()["status"] == "ASSIGNED"


def test_failed_history_write_rolls_back_the_status(
    world: dict[str, Any], db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = _create(world).json()["id"]
    db.expire_all()
    task = db.get(Task, tid)

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("audit store down")

    monkeypatch.setattr(audit_service, "record", boom)
    with pytest.raises(RuntimeError):
        service.transition(
            db,
            task,
            "CANCELLED",
            workflow.Actor(can_assign=True),
            actor_id=None,
            reason_code="CLIENT_REQUEST",
        )
    db.expire_all()
    assert db.get(Task, tid).status == "DRAFT"
    assert (
        db.scalars(
            select(TaskStatusHistory).where(TaskStatusHistory.to_status == "CANCELLED")
        ).all()
        == []
    )


def test_task_status_only_changes_inside_the_task_service() -> None:
    import re

    pattern = re.compile(r"\btask\.status\s*=(?!=)")
    app_dir = Path(__file__).resolve().parent.parent / "app"
    hits = {
        str(p.relative_to(app_dir)): len(pattern.findall(p.read_text()))
        for p in app_dir.rglob("*.py")
    }
    assert {k: v for k, v in hits.items() if v} == {"modules/tasks/service.py": 1}


def test_consent_capture_rules(world: dict[str, Any]) -> None:
    tid = _create(world).json()["id"]
    body = {"participant_id": world["a"]["id"], "status": "GIVEN", "method": "VERBAL_RECORDED"}
    assert world["mod"].post(f"/api/v1/tasks/{tid}/consent", json=body).status_code == 404
    world["pa"].post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    assert world["pa"].post(f"/api/v1/tasks/{tid}/consent", json=body).status_code == 403
    not_on_task = world["mod"].post(
        f"/api/v1/tasks/{tid}/consent", json={**body, "participant_id": world["c"]["id"]}
    )
    assert not_on_task.json()["error"]["code"] == "PARTICIPANT_NOT_ON_TASK"
    detail = world["mod"].post(f"/api/v1/tasks/{tid}/consent", json=body).json()
    assert detail["participant_a"]["consent_status"] == "GIVEN"
    assert detail["participant_b"]["consent_status"] is None


def test_filters_comments_and_timeline(world: dict[str, Any]) -> None:
    tid = _create(world).json()["id"]
    _create(world, mode="FACE_TO_FACE", b="c")
    assert world["pa"].get("/api/v1/tasks", params={"mode": "FACE_TO_FACE"}).json()["total"] == 1
    assert world["pa"].get("/api/v1/tasks", params={"status": "DRAFT"}).json()["total"] == 2
    assert (
        world["pa"]
        .post(f"/api/v1/tasks/{tid}/comments", json={"body": "Call after 5 pm"})
        .status_code
        == 201
    )
    kinds = [e["kind"] for e in world["pa"].get(f"/api/v1/tasks/{tid}/timeline").json()]
    assert kinds == ["status", "comment"]


def test_bulk_task_upload_checks_then_adds_and_assigns(world: dict[str, Any], db: Any) -> None:
    """D-083: many tasks from a CSV of participant codes; check first, then add."""
    a, b, c = (world[k]["participant_code"] for k in ("a", "b", "c"))
    csv = (
        "participant_a,participant_b,mode,priority,due_date,moderator\n"
        f"{a},{b},face_to_face,high,2026-12-01,mod@example.org\n"
        f"{a},{c},,,,\n"
        f"{a},{a},,,,\n"
        f"{a},P999999,,,,\n"
        f"{a},{c},telephony,,,\n"
        f"{a},{b},,someday,,\n"
        f"{a},{b},,,01/12/2026,\n"
        f"{a},{b},,,,out@example.org\n"
    )
    body = {"project_id": str(world["project"].id), "csv": csv}
    check = world["pa"].post("/api/v1/tasks/import", json=body).json()
    assert [r["ok"] for r in check["rows"]] == [True, True] + [False] * 6
    assert check["created"] == 0
    assert db.scalar(select(func.count()).select_from(Task)) == 0
    messages = [r["message"] for r in check["rows"]]
    assert messages[2] == "Participant A and B must be different people"
    assert "not in this project" in messages[3]
    assert "phone number" in messages[4]
    assert "Priority" in messages[5]
    assert "YYYY-MM-DD" in messages[6]
    assert "not a member" in messages[7]

    added = world["pa"].post("/api/v1/tasks/import", json={**body, "confirm": True}).json()
    assert added["created"] == 2
    first, second = added["rows"][0], added["rows"][1]
    assert first["message"] == "Added and assigned to mod@example.org"
    assert second["message"] == "Added"
    assert second["task_code"].startswith("T")
    tasks = {t.task_code: t for t in db.scalars(select(Task))}
    assert tasks[first["task_code"]].status == "ASSIGNED"
    assert tasks[first["task_code"]].priority == "HIGH"
    assert tasks[second["task_code"]].status == "DRAFT"
    assert tasks[second["task_code"]].recording_mode == "FACE_TO_FACE"


def test_bulk_task_upload_needs_the_assign_permission(world: dict[str, Any]) -> None:
    body = {"project_id": str(world["project"].id), "csv": "participant_a,participant_b\n"}
    assert world["mod"].post("/api/v1/tasks/import", json=body).status_code == 403
    bad = (
        world["pa"]
        .post("/api/v1/tasks/import", json={**body, "csv": "a,b\nP000001,P000002\n"})
        .json()
    )
    assert bad["error"]["code"] == "INVALID_CSV"
