"""Recording tasks (TASK-*).

Visibility: Super Admin sees every task; a holder of tasks.assign sees tasks in their projects;
everyone else sees only tasks they are actively assigned to (TASK-005). A task is made, and given
to a moderator, only for two people who agreed to the project's consent form (D-129).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm, Role
from app.db.paging import paginate
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, in_projects
from app.modules.auth.models import RoleRecord, User, UserRole
from app.modules.participants import consent
from app.modules.participants.models import ConsentRecord, Participant, ParticipantProjectLink
from app.modules.projects.models import ProjectMembership
from app.modules.projects.service import ensure_accepts_new_work, get_manageable
from app.modules.tasks import workflow
from app.modules.tasks.models import Task, TaskAssignment, TaskComment, TaskStatusHistory

# Statuses in which the moderator may still be changed.
REASSIGNABLE = frozenset({"DRAFT", "ASSIGNED", "ON_HOLD"})


class _RoleWords(NamedTuple):
    noun: str  # in messages
    wrong_role: str  # error code for someone without the role
    audit_prefix: str  # audit actions <prefix>assigned / <prefix>reassigned
    audit_key: str


# The roles a person is assigned to a task in.
_ROLE_WORDS = {
    Role.MODERATOR: _RoleWords("moderator", "NOT_A_MODERATOR", "task.", "moderator"),
    Role.QC_EXECUTIVE: _RoleWords("QC Executive", "NOT_A_QC_EXECUTIVE", "task.qc_", "qc"),
}


def _role_noun(role_code: str) -> str:
    """How a task role reads at the start of a history line ("Moderator", "QC Executive")."""
    noun = next((w.noun for r, w in _ROLE_WORDS.items() if r.value == role_code), role_code)
    return noun[:1].upper() + noun[1:]


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


def is_moderator(db: Session, principal: Principal, task: Task) -> bool:
    """The caller is the task's assigned moderator."""
    moderator = active_assignee(db, task.id, Role.MODERATOR.value)
    return moderator is not None and moderator.user_id == principal.user_id


def require_moderator(db: Session, principal: Principal, task: Task, message: str) -> None:
    """Only the task's assigned moderator may do this; anyone else gets 403 with `message`."""
    if not is_moderator(db, principal, task):
        raise forbidden(message)


def actor_from(
    principal: Principal, task: Task, moderator: TaskAssignment | None
) -> workflow.Actor:
    """The caller as the workflow sees them, given the task's moderator assignment."""
    return workflow.Actor(
        can_assign=principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id),
        is_moderator=moderator is not None and moderator.user_id == principal.user_id,
    )


def actor_for(db: Session, principal: Principal, task: Task) -> workflow.Actor:
    return actor_from(principal, task, active_assignee(db, task.id, Role.MODERATOR.value))


def get_task(db: Session, principal: Principal, task_id: uuid.UUID) -> Task:
    if not principal.can(Perm.TASKS_VIEW):
        raise forbidden()
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task")
    if principal.is_super_admin:
        return task
    if task.project_id not in principal.project_ids:
        raise not_found("Task")
    if principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id) or _is_assigned(
        db, task.id, principal.user_id
    ):
        return task
    raise not_found("Task")


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
        query = query.where(in_projects(principal, Task.project_id))
        if not principal.can(Perm.TASKS_ASSIGN):
            query = query.where(mine)
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
        term = f.search.strip().upper()
        people = select(Participant.id).where(
            Participant.participant_code.contains(term, autoescape=True)
        )
        query = query.where(
            or_(
                Task.task_code.contains(term, autoescape=True),
                Task.participant_a_id.in_(people),
                Task.participant_b_id.in_(people),
            )
        )
    return paginate(db, query.order_by(Task.created_at.desc()), page, page_size)


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
        if target == "AUDIO_QC":
            auto_assign_qc(db, task)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return task


def recording_people(db: Session, task: Task) -> set[uuid.UUID]:
    """The task's moderator and everyone who made one of its recordings: none of them may check
    the task in QC (D-088)."""
    from app.modules.recordings.models import Recording

    people = set(db.scalars(select(Recording.created_by).where(Recording.task_id == task.id)))
    moderator = active_assignee(db, task.id, Role.MODERATOR.value)
    if moderator is not None:
        people.add(moderator.user_id)
    return people


def auto_assign_qc(db: Session, task: Task) -> uuid.UUID | None:
    """Gives a task reaching QC to a QC Executive of its project (D-116), when it has none: the
    active QC Executive with the fewest tasks waiting in QC; on a tie, the one given a task
    longest ago (round robin). Never the task's moderator or someone who recorded it. Nobody
    fits: the task waits, and a project admin assigns it by hand. Returns the person chosen."""
    if active_assignee(db, task.id, Role.QC_EXECUTIVE.value) is not None:
        return None
    # One choice at a time per project, so two tasks sent together are spread, not doubled.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"qc-assign:{task.project_id}"}
    )
    excluded = recording_people(db, task)
    qc_role = select(RoleRecord.id).where(RoleRecord.code == Role.QC_EXECUTIVE.value)
    candidates = [
        u
        for u in db.scalars(
            select(User)
            .join(ProjectMembership, ProjectMembership.user_id == User.id)
            .where(
                ProjectMembership.project_id == task.project_id,
                User.status == "ACTIVE",
                exists().where(
                    UserRole.user_id == User.id, UserRole.role_id.in_(qc_role.scalar_subquery())
                ),
            )
        )
        if u.id not in excluded
    ]
    if not candidates:
        return None
    ids = [u.id for u in candidates]
    waiting = dict(
        db.execute(
            select(TaskAssignment.user_id, func.count())
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.role_code == Role.QC_EXECUTIVE.value,
                TaskAssignment.active.is_(True),
                Task.status == "AUDIO_QC",
                TaskAssignment.user_id.in_(ids),
            )
            .group_by(TaskAssignment.user_id)
        ).all()
    )
    last_given = dict(
        db.execute(
            select(TaskAssignment.user_id, func.max(TaskAssignment.created_at))
            .where(
                TaskAssignment.role_code == Role.QC_EXECUTIVE.value,
                TaskAssignment.user_id.in_(ids),
            )
            .group_by(TaskAssignment.user_id)
        ).all()
    )
    never = datetime.min.replace(tzinfo=UTC)
    chosen = min(
        candidates,
        key=lambda u: (waiting.get(u.id, 0), last_given.get(u.id) or never, u.display_name),
    )
    db.add(
        TaskAssignment(
            task_id=task.id,
            user_id=chosen.id,
            role_code=Role.QC_EXECUTIVE.value,
            assigned_by=None,
            reason="Assigned by the platform: fewest tasks waiting in QC",
        )
    )
    audit.record(
        db,
        action="task.qc_auto_assigned",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        actor_id=None,
        after={"qc": str(chosen.id), "waiting_before": waiting.get(chosen.id, 0)},
    )
    return chosen.id


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


def require_agreed(
    db: Session, project_id: uuid.UUID, people: list[Participant], *, status_code: int
) -> None:
    """A task is made or given to a moderator only for people who agreed to the project's
    consent form (D-129): CONSENT_REQUIRED naming the others."""
    answers = consent.latest_own_answers(db, project_id, [p.id for p in people])
    waiting = [p.participant_code for p in people if not consent.agreed(answers.get(p.id))]
    if waiting:
        raise AppError(
            f"{' and '.join(waiting)} {'has' if len(waiting) == 1 else 'have'} not agreed to "
            "this project's consent form yet.",
            code="CONSENT_REQUIRED",
            status_code=status_code,
            details=[{"participants": waiting}],
        )


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
    project = get_manageable(db, principal, project_id, Perm.TASKS_ASSIGN)
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
    require_agreed(db, project.id, [a, b], status_code=422)
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


def require_member_with_role(
    db: Session, project_id: uuid.UUID, user_id: uuid.UUID, role: Role
) -> User:
    """The user may take this role on the project's tasks: an active member holding the role.
    422 NOT_PROJECT_MEMBER, or NOT_A_MODERATOR / NOT_A_QC_EXECUTIVE."""
    words = _ROLE_WORDS[role]
    user = db.get(User, user_id)
    is_member = user is not None and db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.project_id == project_id, ProjectMembership.user_id == user.id
        )
    )
    if user is None or not is_member:
        raise AppError(
            f"The {words.noun} must be a member of the project",
            code="NOT_PROJECT_MEMBER",
            status_code=422,
        )
    if user.status != "ACTIVE" or role.value not in {r.code for r in user.roles}:
        title = words.noun[0].upper() + words.noun[1:]
        raise AppError(
            f"Choose an active user with the {title} role", code=words.wrong_role, status_code=422
        )
    return user


def replace_assignee(
    db: Session,
    principal: Principal,
    task: Task,
    user: User,
    role: Role,
    reason: str | None,
    ip: str | None,
) -> TaskAssignment | None:
    """Gives the task's `role` to `user`, ending the assignment of whoever held it; replacing
    someone needs a reason. Audited, not committed. Returns the assignment that was ended."""
    words = _ROLE_WORDS[role]
    current = active_assignee(db, task.id, role.value)
    if current is not None and current.user_id == user.id:
        raise AppError(
            f"Already assigned to this {words.noun}", code="ALREADY_ASSIGNED", status_code=409
        )
    reason = (reason or "").strip()
    if current is not None and not reason:
        raise AppError("Give a reason for reassigning", code="REASON_REQUIRED", status_code=422)
    if current is not None:
        current.active = False
        current.ended_at = datetime.now(UTC)
        db.flush()  # the one-active-assignment index must see the old one ended first
    db.add(
        TaskAssignment(
            task_id=task.id,
            user_id=user.id,
            role_code=role.value,
            assigned_by=principal.user_id,
            reason=reason or None,
        )
    )
    audit.record(
        db,
        action=f"{words.audit_prefix}{'reassigned' if current else 'assigned'}",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        before={words.audit_key: str(current.user_id)} if current else None,
        after={words.audit_key: str(user.id), "reason": reason},
    )
    return current


def can_reassign(actor: workflow.Actor, task: Task) -> bool:
    return actor.can_assign and task.status in REASSIGNABLE


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
    people = [
        db.get_one(Participant, pid) for pid in (task.participant_a_id, task.participant_b_id)
    ]
    require_agreed(db, task.project_id, people, status_code=409)
    user = require_member_with_role(db, task.project_id, user_id, Role.MODERATOR)
    qc = active_assignee(db, task.id, Role.QC_EXECUTIVE.value)
    if qc is not None and qc.user_id == user.id:
        # The QC Executive of a task cannot also record it, whichever was assigned first (D-088).
        raise AppError(
            "The person who checks a session cannot record it", code="SAME_PERSON", status_code=422
        )
    try:
        replace_assignee(db, principal, task, user, Role.MODERATOR, reason, ip)
        if task.status == "DRAFT":
            workflow.check(
                task.status,
                "ASSIGNED",
                workflow.SYSTEM,
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


def consent_missing_error(missing: list[str]) -> AppError:
    return AppError(
        f"Participant {' and '.join(missing)} has not agreed on the consent form yet. Calling "
        "and recording wait until both have agreed.",
        code="CONSENT_MISSING",
        status_code=409,
        details=[{"missing": missing}],
    )


def require_consent(db: Session, task: Task) -> None:
    """Recording needs consent from both participants first (D-119)."""
    missing = consent.missing(consent.for_task(db, task))
    if missing:
        raise consent_missing_error(missing)


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


def delete_task(
    db: Session, principal: Principal, task_id: uuid.UUID, reason: str, ip: str | None
) -> str:
    """Removes a task made by mistake (D-115): only by people who assign tasks, and only while
    nothing has happened on it: no recording, no phone call, no consent noted, no QC result. A
    task with work on it is cancelled instead, so its history stays. Returns the task code."""
    from app.modules.audio_qc.models import AudioQcResult
    from app.modules.recordings.models import Recording
    from app.modules.telephony.models import Call

    task = get_task(db, principal, task_id)
    if not principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id):
        raise forbidden()
    if not reason.strip():
        raise AppError("Say why the task is deleted", code="REASON_REQUIRED", status_code=422)
    work = [
        ("a recording", exists().where(Recording.task_id == task.id)),
        ("a phone call", exists().where(Call.task_id == task.id)),
        ("consent noted", exists().where(ConsentRecord.task_id == task.id)),
        ("an audio check", exists().where(AudioQcResult.task_id == task.id)),
    ]
    found = [what for what, there in work if db.scalar(select(there))]
    if found:
        raise AppError(
            f"This task already has {' and '.join(found)}, so it is kept for the record. "
            "Cancel it instead.",
            code="TASK_HAS_WORK",
            status_code=409,
        )
    code = task.task_code
    for model in (TaskComment, TaskStatusHistory, TaskAssignment):
        db.query(model).filter(model.task_id == task.id).delete(synchronize_session=False)
    db.delete(task)
    audit.record(
        db,
        action="task.deleted",
        entity_type="task",
        entity_id=task_id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        before={"task_code": code, "status": task.status, "mode": task.recording_mode},
        after={"reason": reason.strip()},
    )
    db.commit()
    return code


@dataclass(frozen=True)
class TimelineEntry:
    at: datetime
    kind: str
    actor: str | None
    text: str
    # Status changes only: the change itself, so a page need not read it back out of `text`.
    from_status: str | None = None
    to_status: str | None = None
    reason_code: str | None = None
    comment: str | None = None


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
                from_status=h.from_status,
                to_status=h.to_status,
                reason_code=h.reason_code,
                comment=h.comment,
            )
        )
    for a in assignments:
        reason = f" ({a.reason})" if a.reason else ""
        entries.append(
            TimelineEntry(
                a.created_at,
                "assignment",
                names.get(a.assigned_by) if a.assigned_by else None,
                f"{_role_noun(a.role_code)} assigned: {names.get(a.user_id, a.user_id)}{reason}",
            )
        )
    for c in comments:
        entries.append(TimelineEntry(c.created_at, "comment", names.get(c.author_id), c.body))
    return sorted(entries, key=lambda e: e.at)
