"""Recording tasks (TASK-*), consent capture (PART-006, TEL-015 groundwork).

Visibility: Super Admin sees every task; a holder of tasks.assign sees tasks in their projects;
everyone else sees only tasks they are actively assigned to (TASK-005).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm, Role
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.participants.models import ConsentRecord, Participant, ParticipantProjectLink
from app.modules.projects.models import Project, ProjectMembership
from app.modules.projects.service import ensure_accepts_new_work
from app.modules.projects.service import get_visible as get_visible_project
from app.modules.tasks import workflow
from app.modules.tasks.models import Task, TaskAssignment, TaskComment, TaskStatusHistory

REASSIGNABLE = frozenset({"DRAFT", "ASSIGNED", "ON_HOLD", "RETURNED"})
CONSENT_OPEN = frozenset({"ASSIGNED", "IN_PROGRESS"})


def not_found() -> AppError:
    return AppError("Task not found", code="NOT_FOUND", status_code=404)


def active_assignee(db: Session, task_id: uuid.UUID, role_code: str) -> TaskAssignment | None:
    return db.scalar(
        select(TaskAssignment).where(
            TaskAssignment.task_id == task_id,
            TaskAssignment.role_code == role_code,
            TaskAssignment.active.is_(True),
        )
    )


def _is_assigned(db: Session, task_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.active.is_(True),
                )
            )
        )
    )


def actor_for(db: Session, principal: Principal, task: Task) -> workflow.Actor:
    moderator = active_assignee(db, task.id, "MODERATOR")
    return workflow.Actor(
        can_assign=principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id),
        is_moderator=moderator is not None and moderator.user_id == principal.user_id,
    )


def get_task(db: Session, principal: Principal, task_id: uuid.UUID) -> Task:
    if not principal.can(Perm.TASKS_VIEW):
        raise forbidden()
    task = db.get(Task, task_id)
    if task is None:
        raise not_found()
    if principal.is_super_admin:
        return task
    if task.project_id not in principal.project_ids:
        raise not_found()
    if principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id) or _is_assigned(
        db, task.id, principal.user_id
    ):
        return task
    raise not_found()


@dataclass(frozen=True)
class TaskFilter:
    project_id: uuid.UUID | None = None
    status: str | None = None
    mode: str | None = None
    mine: bool = False
    search: str | None = None  # a task code or a participant code, or part of one (O7)


def list_tasks(
    db: Session, principal: Principal, f: TaskFilter, page: int, page_size: int
) -> tuple[list[Task], int]:
    if not principal.can(Perm.TASKS_VIEW):
        raise forbidden()
    query = select(Task)
    mine = exists().where(
        TaskAssignment.task_id == Task.id,
        TaskAssignment.user_id == principal.user_id,
        TaskAssignment.active.is_(True),
    )
    if not principal.is_super_admin:
        projects = list(principal.project_ids) or [uuid.UUID(int=0)]
        if principal.can(Perm.TASKS_ASSIGN):
            query = query.where(Task.project_id.in_(projects))
        else:
            query = query.where(Task.project_id.in_(projects), mine)
    if f.mine:
        query = query.where(mine)
    if f.project_id:
        query = query.where(Task.project_id == f.project_id)
    if f.status:
        query = query.where(Task.status == f.status)
    if f.mode:
        query = query.where(Task.recording_mode == f.mode)
    if f.search and f.search.strip():
        # Codes only (T000123, P000045): never names or phone numbers, so no personal data is
        # searchable here. LIKE wildcards in the input are matched literally.
        term = (
            f.search.strip().upper().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        like = f"%{term}%"
        people = select(Participant.id).where(Participant.participant_code.like(like, escape="\\"))
        query = query.where(
            or_(
                Task.task_code.like(like, escape="\\"),
                Task.participant_a_id.in_(people),
                Task.participant_b_id.in_(people),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), int(total)


def _record_transition(
    db: Session,
    task: Task,
    target: str,
    actor_id: uuid.UUID | None,
    reason_code: str | None,
    comment: str,
    ip: str | None,
) -> None:
    previous = task.status
    if target == "ON_HOLD":
        task.held_from = previous
    elif previous == "ON_HOLD":
        task.held_from = None
    task.status = target
    task.reason_code = reason_code
    db.add(
        TaskStatusHistory(
            task_id=task.id,
            from_status=previous,
            to_status=target,
            actor_id=actor_id,
            reason_code=reason_code,
            comment=comment,
        )
    )
    audit.record(
        db,
        action="task.status_changed",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        actor_id=actor_id,
        ip=ip,
        before={"status": previous},
        after={"status": target, "reason_code": reason_code, "comment": comment},
    )


def transition(
    db: Session,
    task: Task,
    target: str,
    actor: workflow.Actor,
    *,
    actor_id: uuid.UUID | None,
    reason_code: str | None = None,
    comment: str = "",
    ip: str | None = None,
) -> Task:
    """The only way a task's status changes; status, history and audit commit together."""
    workflow.check(
        task.status,
        target,
        actor,
        held_from=task.held_from,
        reason_code=reason_code,
        comment=comment,
    )
    try:
        _record_transition(db, task, target, actor_id, reason_code, comment, ip)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return task


def system_transition(
    db: Session, task: Task, target: str, *, comment: str = "", reason_code: str | None = None
) -> Task:
    """For the platform's own modules (recording, audio QC)."""
    return transition(
        db, task, target, workflow.SYSTEM, actor_id=None, reason_code=reason_code, comment=comment
    )


def _project_participant(
    db: Session, project_id: uuid.UUID, participant_id: uuid.UUID
) -> Participant:
    participant = db.get(Participant, participant_id)
    linked = participant is not None and db.scalar(
        select(ParticipantProjectLink.id).where(
            ParticipantProjectLink.project_id == project_id,
            ParticipantProjectLink.participant_id == participant_id,
        )
    )
    if participant is None or not linked or participant.deleted_at is not None:
        raise AppError(
            "Participant is not in this project", code="PARTICIPANT_NOT_IN_PROJECT", status_code=422
        )
    return participant


@dataclass(frozen=True)
class TaskInput:
    recording_mode: str
    participant_a_id: uuid.UUID
    participant_b_id: uuid.UUID
    priority: str
    due_at: datetime | None


def create_task(
    db: Session, principal: Principal, project_id: uuid.UUID, data: TaskInput, ip: str | None
) -> Task:
    project = get_visible_project(db, principal, project_id)
    if not principal.can_in_project(Perm.TASKS_ASSIGN, project.id):
        raise forbidden()
    ensure_accepts_new_work(project)
    allowed = (data.recording_mode == "TELEPHONY" and project.allows_telephony) or (
        data.recording_mode == "FACE_TO_FACE" and project.allows_face_to_face
    )
    if not allowed:
        raise AppError(
            "This project does not allow that recording mode",
            code="MODE_NOT_ALLOWED",
            status_code=422,
        )
    if data.participant_a_id == data.participant_b_id:
        raise AppError(
            "Participant A and B must be different people", code="SAME_PARTICIPANT", status_code=422
        )
    a = _project_participant(db, project.id, data.participant_a_id)
    b = _project_participant(db, project.id, data.participant_b_id)
    if data.recording_mode == "TELEPHONY" and not (a.phone_e164_enc and b.phone_e164_enc):
        raise AppError(
            "Telephony tasks need a phone number for both participants",
            code="PHONE_REQUIRED",
            status_code=422,
        )
    code = f"T{db.scalar(text("SELECT nextval('task_code_seq')")):06d}"
    task = Task(
        id=uuid.uuid4(),
        task_code=code,
        project_id=project.id,
        recording_mode=data.recording_mode,
        status="DRAFT",
        priority=data.priority,
        due_at=data.due_at,
        participant_a_id=a.id,
        participant_b_id=b.id,
        created_by=principal.user_id,
    )
    db.add(task)
    db.add(
        TaskStatusHistory(
            task_id=task.id, from_status=None, to_status="DRAFT", actor_id=principal.user_id
        )
    )
    audit.record(
        db,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={
            "task_code": code,
            "mode": data.recording_mode,
            "participants": [a.participant_code, b.participant_code],
        },
    )
    db.commit()
    return task


def check_moderator(db: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> User:
    """The user may moderate this project's tasks: an active member with the Moderator role."""
    user = db.get(User, user_id)
    is_member = user is not None and db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.project_id == project_id, ProjectMembership.user_id == user.id
        )
    )
    if user is None or not is_member:
        raise AppError(
            "The moderator must be a member of the project",
            code="NOT_PROJECT_MEMBER",
            status_code=422,
        )
    if user.status != "ACTIVE" or Role.MODERATOR.value not in {r.code for r in user.roles}:
        raise AppError(
            "Choose an active user with the Moderator role", code="NOT_A_MODERATOR", status_code=422
        )
    return user


def assign_moderator(
    db: Session,
    principal: Principal,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str | None,
    ip: str | None,
) -> Task:
    task = get_task(db, principal, task_id)
    if not principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id):
        raise forbidden()
    if task.status not in REASSIGNABLE:
        raise AppError(
            f"A {task.status} task cannot be reassigned", code="TASK_LOCKED", status_code=409
        )
    user = check_moderator(db, task.project_id, user_id)
    current = active_assignee(db, task.id, "MODERATOR")
    if current is not None and current.user_id == user.id:
        raise AppError(
            "Already assigned to this moderator", code="ALREADY_ASSIGNED", status_code=409
        )
    if current is not None and not (reason and reason.strip()):
        raise AppError("Give a reason for reassigning", code="REASON_REQUIRED", status_code=422)
    try:
        if current is not None:
            current.active = False
            current.ended_at = datetime.now(UTC)
            db.flush()
        db.add(
            TaskAssignment(
                task_id=task.id,
                user_id=user.id,
                role_code="MODERATOR",
                assigned_by=principal.user_id,
                reason=(reason or "").strip() or None,
            )
        )
        audit.record(
            db,
            action="task.reassigned" if current else "task.assigned",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            actor_id=principal.user_id,
            ip=ip,
            before={"moderator": str(current.user_id)} if current else None,
            after={"moderator": str(user.id), "reason": (reason or "").strip()},
        )
        if task.status in ("DRAFT", "RETURNED"):
            workflow.check(
                task.status,
                "ASSIGNED",
                workflow.SYSTEM if task.status == "DRAFT" else workflow.Actor(can_assign=True),
                held_from=None,
                reason_code=None,
                comment="",
            )
            _record_transition(
                db, task, "ASSIGNED", principal.user_id, None, "Moderator assigned", ip
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return task


def capture_consent(
    db: Session,
    principal: Principal,
    task_id: uuid.UUID,
    participant_id: uuid.UUID,
    status: str,
    method: str,
    note: str,
    ip: str | None,
) -> ConsentRecord:
    task = get_task(db, principal, task_id)
    if not principal.can_in_project(Perm.CONSENT_CAPTURE, task.project_id):
        raise forbidden()
    moderator = active_assignee(db, task.id, "MODERATOR")
    if moderator is None or moderator.user_id != principal.user_id:
        raise AppError(
            "Only the assigned moderator records consent", code="FORBIDDEN", status_code=403
        )
    if task.status not in CONSENT_OPEN:
        raise AppError(
            "Consent is recorded while the task is assigned or in progress",
            code="TASK_LOCKED",
            status_code=409,
        )
    if participant_id not in (task.participant_a_id, task.participant_b_id):
        raise AppError(
            "Participant is not on this task", code="PARTICIPANT_NOT_ON_TASK", status_code=422
        )
    project = db.get(Project, task.project_id)
    assert project is not None  # noqa: S101  (foreign key guarantees it)
    record = ConsentRecord(
        participant_id=participant_id,
        project_id=task.project_id,
        task_id=task.id,
        status=status,
        method=method,
        policy_version=project.consent_policy_version,
        captured_by=principal.user_id,
        note=note,
    )
    db.add(record)
    audit.record(
        db,
        action="consent.recorded",
        entity_type="participant",
        entity_id=participant_id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={
            "task": task.task_code,
            "status": status,
            "method": method,
            "policy_version": record.policy_version,
        },
    )
    db.commit()
    return record


def latest_consent(db: Session, task: Task) -> dict[uuid.UUID, ConsentRecord]:
    rows = db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.task_id == task.id)
        .order_by(ConsentRecord.created_at)
    ).all()
    return {r.participant_id: r for r in rows}


def add_comment(
    db: Session, principal: Principal, task_id: uuid.UUID, body: str, ip: str | None
) -> TaskComment:
    task = get_task(db, principal, task_id)
    comment = TaskComment(task_id=task.id, author_id=principal.user_id, body=body.strip())
    db.add(comment)
    audit.record(
        db,
        action="task.commented",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return comment


@dataclass(frozen=True)
class TimelineEntry:
    at: datetime
    kind: str
    actor: str | None
    text: str


def timeline(db: Session, principal: Principal, task_id: uuid.UUID) -> list[TimelineEntry]:
    task = get_task(db, principal, task_id)
    history = db.scalars(
        select(TaskStatusHistory).where(TaskStatusHistory.task_id == task.id)
    ).all()
    assignments = db.scalars(select(TaskAssignment).where(TaskAssignment.task_id == task.id)).all()
    comments = db.scalars(select(TaskComment).where(TaskComment.task_id == task.id)).all()
    # Names of the people this task's history mentions, not of every account (O5).
    people = {h.actor_id for h in history} | {c.author_id for c in comments}
    people |= {a.user_id for a in assignments} | {a.assigned_by for a in assignments}
    people.discard(None)
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(people))).all()
    names = {user_id: name for user_id, name in rows}
    entries: list[TimelineEntry] = []
    for h in history:
        label = f"{h.from_status or 'created'} -> {h.to_status}"
        extra = " ".join(x for x in (h.reason_code or "", h.comment) if x)
        entries.append(
            TimelineEntry(
                h.created_at,
                "status",
                names.get(h.actor_id) if h.actor_id else "Platform",
                f"{label} {extra}".strip(),
            )
        )
    for a in assignments:
        reason = f" ({a.reason})" if a.reason else ""
        entries.append(
            TimelineEntry(
                a.created_at,
                "assignment",
                names.get(a.assigned_by) if a.assigned_by else None,
                f"{a.role_code.title()} assigned: {names.get(a.user_id, a.user_id)}{reason}",
            )
        )
    for c in comments:
        entries.append(TimelineEntry(c.created_at, "comment", names.get(c.author_id), c.body))
    return sorted(entries, key=lambda e: e.at)
