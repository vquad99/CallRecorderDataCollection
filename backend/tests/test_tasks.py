"""Task lifecycle: creation rules, consent before a task (D-129), moderator assignment, the
state machine, history, rollback, visibility, comments, timeline.

Requirements: TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-012, PROJ-010, PART-004
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.modules.audit import service as audit_service
from app.modules.participants.models import ConsentRecord
from app.modules.tasks import service, workflow
from app.modules.tasks.models import TASK_STATUSES, Task, TaskStatusHistory
from tests.conftest import agree, make_participant, make_project, make_user, set_status

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
        ("AUDIO_QC", "ADMIN_REVIEW"),
        ("AUDIO_QC", "APPROVED"),
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
    # Sending to QC also needs a checked recording (D-092), which this test has none of.
    allowed.discard(("RECORDED", "AUDIO_QC"))
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


def test_tasks_are_only_for_people_who_agreed_to_the_consent_form(
    world: dict[str, Any], db: Any
) -> None:
    """D-129: a task is made, or given to a moderator, only when both participants agreed to the
    project's consent form; the file upload says so on the row at the check."""
    pa, pid = world["pa"], world["project"].id
    world["d"] = d = make_participant(pa, pid, "Devi", agreed=False)
    world["e"] = e = make_participant(pa, pid, "Esha", agreed=False)
    a_code, c_code = world["a"]["participant_code"], world["c"]["participant_code"]
    d_code, e_code = d["participant_code"], e["participant_code"]

    def new(a: str, b: str, **extra: Any) -> Any:
        body = {"project_id": str(pid), "recording_mode": "FACE_TO_FACE"}
        return pa.post(
            "/api/v1/tasks",
            json={**body, "participant_a_id": world[a]["id"], "participant_b_id": world[b]["id"]}
            | extra,
        )

    one = new("a", "d")
    assert (one.status_code, one.json()["error"]["code"]) == (422, "CONSENT_REQUIRED")
    assert one.json()["error"]["message"] == (
        f"{d_code} has not agreed to this project's consent form yet."
    )
    both = new("d", "e", moderator_id=str(world["mod_user"].id))
    assert both.json()["error"]["message"] == (
        f"{d_code} and {e_code} have not agreed to this project's consent form yet."
    )
    assert db.scalar(select(func.count()).select_from(Task)) == 0, "no half-made task"
    csv = (
        f"participant_a,participant_b,mode\n{a_code},{d_code},face_to_face\n"
        f"{a_code},{c_code},face_to_face\n"
    )
    rows = pa.post("/api/v1/tasks/import", json={"project_id": str(pid), "csv": csv}).json()
    assert [(r["ok"], r["message"]) for r in rows["rows"]] == [
        (False, f"{d_code} has not agreed to this project's consent form yet."),
        (True, "Ready to add"),
    ]
    # Agreed later on their page: now the task can be made.
    agree(pa, pid, d["id"])
    assert new("a", "d").status_code == 201
    # Consent that no longer counts (withdrawn before D-129): the task gets no moderator.
    tid = new("a", "c").json()["id"]
    db.add(
        ConsentRecord(
            participant_id=uuid.UUID(world["c"]["id"]),
            project_id=pid,
            task_id=None,
            status="WITHDRAWN",
            method="DIGITAL",
            policy_version="1",
            captured_by=None,
        )
    )
    db.commit()
    no = pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    assert (no.status_code, no.json()["error"]["code"]) == (409, "CONSENT_REQUIRED")
    assert no.json()["error"]["message"].startswith(c_code)
    assert pa.get(f"/api/v1/tasks/{tid}").json()["status"] == "DRAFT"


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


def test_new_task_can_assign_the_moderator_at_once(world: dict[str, Any], db: Any) -> None:
    """D-085: New task takes an optional moderator; the task then starts as Assigned."""
    body = {
        "project_id": str(world["project"].id),
        "recording_mode": "FACE_TO_FACE",
        "participant_a_id": world["a"]["id"],
        "participant_b_id": world["c"]["id"],
    }
    before = db.scalar(select(func.count()).select_from(Task))
    wrong = world["pa"].post(
        "/api/v1/tasks", json={**body, "moderator_id": str(world["outsider"].id)}
    )
    assert wrong.json()["error"]["code"] == "NOT_PROJECT_MEMBER"
    assert db.scalar(select(func.count()).select_from(Task)) == before  # nothing half-made
    made = world["pa"].post(
        "/api/v1/tasks", json={**body, "moderator_id": str(world["mod_user"].id)}
    )
    assert made.status_code == 201
    assert made.json()["status"] == "ASSIGNED"
    assert made.json()["moderator_id"] == str(world["mod_user"].id)


def test_bulk_task_upload_reports_a_line_with_extra_values(world: dict[str, Any]) -> None:
    """D-088: a line with more values than the header was a server error for the whole file."""
    a, b = world["a"]["participant_code"], world["b"]["participant_code"]
    body = {
        "project_id": str(world["project"].id),
        "csv": f"participant_a,participant_b\n{a},{b},surplus\n{a},{b}\n",
    }
    check = world["pa"].post("/api/v1/tasks/import", json=body)
    assert check.status_code == 200
    rows = check.json()["rows"]
    assert [r["ok"] for r in rows] == [False, True]
    assert "more values" in rows[0]["message"]


def test_the_moderator_listens_first_then_qc_then_the_admin(world: dict[str, Any], db: Any) -> None:
    """D-092: RECORDED waits for the moderator (send to QC or record again); a QC pass goes to
    ADMIN_REVIEW, where only someone who assigns tasks approves, rejects or returns."""
    tid = _create(world).json()["id"]
    world["pa"].post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    set_status(db, tid, "RECORDED")
    again = world["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    assert again.json()["status"] == "IN_PROGRESS", "record again"
    set_status(db, tid, "RECORDED")
    assert (
        world["pa"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "AUDIO_QC"}).status_code
        == 403
    ), "only the task's moderator sends it to QC"
    no_check = world["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "AUDIO_QC"})
    assert no_check.json()["error"]["code"] == "CHECK_PENDING"
    set_status(db, tid, "ADMIN_REVIEW")
    mod_try = world["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "APPROVED"})
    assert mod_try.status_code == 403
    back = world["pa"].post(
        f"/api/v1/tasks/{tid}/transition",
        json={"to": "RETURNED", "reason_code": "RE_RECORD", "comment": ""},
    )
    assert back.json()["error"]["code"] == "VALIDATION_ERROR", "no such status any more (D-118)"
    done = world["pa"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "APPROVED"})
    assert done.json()["status"] == "APPROVED"


def test_a_task_made_by_mistake_is_deleted_but_one_with_work_is_kept(
    world: dict[str, Any], db: Any
) -> None:
    """D-115: people who assign tasks delete a task on which nothing has happened, with a
    reason, on record; a task with consent (or a recording, a call, a check) is cancelled."""
    from app.modules.audit.models import AuditLog
    from app.modules.tasks.models import Task

    pa, mod = world["pa"], world["mod"]
    tid = _create(world).json()["id"]
    code = pa.get(f"/api/v1/tasks/{tid}").json()["task_code"]
    pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    pa.post(f"/api/v1/tasks/{tid}/comments", json={"body": "made twice by mistake"})
    # Not by its moderator; not without a reason.
    assert mod.post(f"/api/v1/tasks/{tid}/delete", json={"reason": "x"}).status_code == 403
    assert pa.post(f"/api/v1/tasks/{tid}/delete", json={"reason": " "}).status_code == 422
    gone = pa.post(f"/api/v1/tasks/{tid}/delete", json={"reason": "Made twice by mistake"})
    assert gone.status_code == 204, gone.text
    assert pa.get(f"/api/v1/tasks/{tid}").status_code == 404
    db.expire_all()
    assert db.get(Task, tid) is None
    entry = db.query(AuditLog).filter(AuditLog.action == "task.deleted").one()
    assert code in (entry.before_summary or "")
    assert "Made twice by mistake" in (entry.after_summary or "")

    # Consent noted on it (by a moderator, before D-129): kept, and the answer says to cancel it.
    kept = _create(world).json()["id"]
    pa.post(f"/api/v1/tasks/{kept}/assign", json={"user_id": str(world["mod_user"].id)})
    db.add(
        ConsentRecord(
            participant_id=uuid.UUID(world["a"]["id"]),
            project_id=world["project"].id,
            task_id=uuid.UUID(kept),
            status="GIVEN",
            method="VERBAL_NOTED",
            policy_version="1",
            captured_by=world["mod_user"].id,
        )
    )
    db.commit()
    refused = pa.post(f"/api/v1/tasks/{kept}/delete", json={"reason": "test"})
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "TASK_HAS_WORK")
    assert "consent noted" in refused.json()["error"]["message"]
    assert pa.get(f"/api/v1/tasks/{kept}").status_code == 200


def _history(db: Any, tid: str) -> list[str]:
    db.expire_all()
    return list(
        db.scalars(
            select(TaskStatusHistory.to_status)
            .where(TaskStatusHistory.task_id == uuid.UUID(tid))
            .order_by(TaskStatusHistory.created_at)
        )
    )


def test_a_status_change_is_checked_against_the_status_as_it_is_now(
    world: dict[str, Any], db: Any
) -> None:
    """Audit TASK-05: the task's row is locked and read again before its status changes, so a
    Start worked out from a task read before an admin's Cancel is refused (409) and the task
    stays cancelled, with nothing written for the refused change."""
    tid = _create(world).json()["id"]
    world["pa"].post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    db.expire_all()
    stale = db.get(Task, tid)
    assert stale.status == "ASSIGNED"
    cancel = {"to": "CANCELLED", "reason_code": "CLIENT_REQUEST"}
    assert world["pa"].post(f"/api/v1/tasks/{tid}/transition", json=cancel).status_code == 200
    assert stale.status == "ASSIGNED", "the copy read before the cancel"
    with pytest.raises(AppError) as refused:
        service.transition(
            db,
            stale,
            "IN_PROGRESS",
            workflow.Actor(is_moderator=True),
            actor_id=world["mod_user"].id,
        )
    assert (refused.value.code, refused.value.status_code) == ("INVALID_TRANSITION", 409)
    assert _history(db, tid) == ["DRAFT", "ASSIGNED", "CANCELLED"]
    assert db.get(Task, tid).status == "CANCELLED"
    # Nothing is left locked: the task page still answers, and the moderator's Start is refused.
    start = world["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    assert start.status_code in (403, 404, 409)
    assert world["pa"].get(f"/api/v1/tasks/{tid}").json()["status"] == "CANCELLED"
    # A task deleted meanwhile (made by mistake, D-115): not found, not a server error.
    gone = _create(world).json()["id"]
    db.expire_all()
    stale = db.get(Task, gone)
    assert stale.status == "DRAFT"
    deleted = world["pa"].post(f"/api/v1/tasks/{gone}/delete", json={"reason": "Made twice"})
    assert deleted.status_code == 204
    with pytest.raises(AppError) as missing:
        service.transition(
            db,
            stale,
            "CANCELLED",
            workflow.Actor(can_assign=True),
            actor_id=None,
            reason_code="OTHER",
        )
    assert (missing.value.code, missing.value.status_code) == ("NOT_FOUND", 404)


def test_a_draft_put_on_hold_and_then_assigned_resumes_as_assigned(
    world: dict[str, Any],
) -> None:
    """Audit TASK-07: a Draft put on hold gets a moderator while on hold; resuming brings it back
    as Assigned, where its moderator can start it (it used to come back as a Draft nobody could
    start)."""
    pa, tid = world["pa"], _create(world).json()["id"]

    def move(api: Any, body: dict[str, Any]) -> Any:
        return api.post(f"/api/v1/tasks/{tid}/transition", json=body)

    held = move(pa, {"to": "ON_HOLD", "reason_code": "WAITING_FOR_PARTICIPANT"}).json()
    assert (held["status"], held["held_from"]) == ("ON_HOLD", "DRAFT")
    assert held["can_reassign"] is True
    assigned = pa.post(
        f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)}
    ).json()
    assert (assigned["status"], assigned["held_from"]) == ("ON_HOLD", "ASSIGNED")
    assert assigned["moderator_name"] == "mod"
    assert assigned["allowed_transitions"] == ["ASSIGNED", "CANCELLED"]
    resumed = move(pa, {"to": "ASSIGNED"}).json()
    assert (resumed["status"], resumed["held_from"]) == ("ASSIGNED", None)
    mine = world["mod"].get(f"/api/v1/tasks/{tid}").json()
    assert mine["allowed_transitions"] == ["IN_PROGRESS"]
    assert move(world["mod"], {"to": "IN_PROGRESS"}).json()["status"] == "IN_PROGRESS"


def test_approval_needs_both_people_s_consent_as_it_counts_now(
    world: dict[str, Any], db: Any
) -> None:
    """Audit SECB-03: at admin review, approval is refused (409 CONSENT_MISSING) while a person
    has no consent that counts in the project now (here withdrawn, as a project switched from
    signed forms to online consent can leave them); who may approve is checked first."""
    pa, mod = world["pa"], world["mod"]
    tid = _create(world, mode="FACE_TO_FACE", b="c").json()["id"]
    pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    set_status(db, tid, "ADMIN_REVIEW")
    db.add(
        ConsentRecord(
            participant_id=uuid.UUID(world["c"]["id"]),
            project_id=world["project"].id,
            task_id=None,
            status="WITHDRAWN",
            method="DIGITAL",
            policy_version="1",
            captured_by=None,
        )
    )
    db.commit()
    assert pa.get(f"/api/v1/tasks/{tid}").json()["consent_missing"] == ["B"]

    def approve(api: Any) -> Any:
        return api.post(f"/api/v1/tasks/{tid}/transition", json={"to": "APPROVED"})

    assert approve(mod).status_code == 403, "who may approve comes first"
    refused = approve(pa)
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "CONSENT_MISSING")
    assert refused.json()["error"]["message"].startswith(
        "Participant B has no consent that counts in this project now."
    )
    assert pa.get(f"/api/v1/tasks/{tid}").json()["status"] == "ADMIN_REVIEW"
    assert "APPROVED" not in _history(db, tid)
    agree(pa, world["project"].id, world["c"]["id"])
    assert approve(pa).json()["status"] == "APPROVED"


def test_the_task_page_knows_its_project_and_whether_it_can_be_deleted(
    world: dict[str, Any], db: Any
) -> None:
    """Audit UXW-04 and FEW-12: GET /tasks/{id} names the project, and says whether Delete can
    work: for people who assign tasks, on a Draft, Assigned or Cancelled task with nothing on it;
    not on a cancelled task with a recording, nor for its moderator."""
    from app.modules.recordings.models import Recording

    pa, mod = world["pa"], world["mod"]
    tid = _create(world).json()["id"]
    draft = pa.get(f"/api/v1/tasks/{tid}").json()
    assert (draft["project_code"], draft["project_name"]) == ("VOICE", "Project VOICE")
    assert draft["can_delete"] is True
    pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    assert pa.get(f"/api/v1/tasks/{tid}").json()["can_delete"] is True
    assert mod.get(f"/api/v1/tasks/{tid}").json()["can_delete"] is False
    assert mod.post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"}).is_success
    assert pa.get(f"/api/v1/tasks/{tid}").json()["can_delete"] is False, "not In progress"
    db.add(
        Recording(
            task_id=uuid.UUID(tid),
            mode="TELEPHONY",
            state="READY",
            created_by=world["mod_user"].id,
            native_sample_rate=16000,
            channel_count=1,
            channel_handling="mono as recorded",
            started_at=datetime(2026, 11, 1, tzinfo=UTC),
        )
    )
    db.commit()
    cancel = {"to": "CANCELLED", "reason_code": "CLIENT_REQUEST"}
    cancelled = pa.post(f"/api/v1/tasks/{tid}/transition", json=cancel).json()
    assert (cancelled["status"], cancelled["can_delete"]) == ("CANCELLED", False)
    refused = pa.post(f"/api/v1/tasks/{tid}/delete", json={"reason": "test"}).json()["error"]
    assert refused["code"] == "TASK_HAS_WORK"
    assert refused["message"] == (
        "This task already has a recording, so it is kept for the record."
    ), "no 'Cancel it instead' on a task already cancelled"
    # A task cancelled before anything happened on it can still be deleted (D-115).
    empty = _create(world).json()["id"]
    gone = pa.post(f"/api/v1/tasks/{empty}/transition", json=cancel).json()
    assert (gone["status"], gone["can_delete"]) == ("CANCELLED", True)


def test_an_ended_task_says_where_it_stopped(world: dict[str, Any], db: Any) -> None:
    """Audit FEW-11: a rejected or cancelled task reports the status it stopped at, for the page's
    progress line: rejected at QC, cancelled from hold (the status it was held from), cancelled
    from a consent form to fix. A task still going reports none."""
    pa, mod_id = world["pa"], str(world["mod_user"].id)

    def task_at(path: list[str]) -> str:
        tid: str = _create(world).json()["id"]
        pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": mod_id})
        world["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
        db.expire_all()
        task = db.get(Task, tid)
        for target in path:
            reason = "AUDIO_QUALITY" if target == "REJECTED" else None
            service.system_transition(db, task, target, reason_code=reason)
        return tid

    def ended(tid: str) -> Any:
        return pa.get(f"/api/v1/tasks/{tid}").json()["ended_from"]

    rejected = task_at(["RECORDED", "AUDIO_QC", "REJECTED"])
    assert ended(rejected) == "AUDIO_QC"
    going = task_at(["RECORDED"])
    assert ended(going) is None

    held = _create(world).json()["id"]
    pa.post(f"/api/v1/tasks/{held}/assign", json={"user_id": mod_id})
    for body in (
        {"to": "ON_HOLD", "reason_code": "WAITING_FOR_PARTICIPANT"},
        {"to": "CANCELLED", "reason_code": "CLIENT_REQUEST"},
    ):
        assert pa.post(f"/api/v1/tasks/{held}/transition", json=body).status_code == 200
    assert ended(held) == "ASSIGNED"

    fixing = task_at(["RECORDED", "AUDIO_QC", "CONSENT_FIX"])
    cancel = {"to": "CANCELLED", "reason_code": "CLIENT_REQUEST"}
    assert pa.post(f"/api/v1/tasks/{fixing}/transition", json=cancel).status_code == 200
    assert ended(fixing) == "CONSENT_FIX"


def test_the_task_list_names_the_moderator_and_both_people(world: dict[str, Any]) -> None:
    """Audit UXW-05: each row of GET /tasks says who holds the task (none before a moderator is
    assigned) and the codes of its two people."""
    pa = world["pa"]
    tid = _create(world).json()["id"]

    def row() -> Any:
        return next(t for t in pa.get("/api/v1/tasks").json()["items"] if t["id"] == tid)

    first = row()
    assert first["moderator_name"] is None
    assert (first["participant_a_code"], first["participant_b_code"]) == (
        world["a"]["participant_code"],
        world["b"]["participant_code"],
    )
    pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(world["mod_user"].id)})
    assert row()["moderator_name"] == "mod"
    moved = pa.post(
        f"/api/v1/tasks/{tid}/assign",
        json={"user_id": str(world["mod2_user"].id), "reason": "mod is on leave"},
    )
    assert moved.status_code == 200
    assert row()["moderator_name"] == "mod2", "only the active moderator"
    mine = world["mod2"].get("/api/v1/tasks").json()["items"]
    assert [(t["task_code"], t["moderator_name"]) for t in mine] == [(first["task_code"], "mod2")]
