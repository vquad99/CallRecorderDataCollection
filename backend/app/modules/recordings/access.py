"""Which recordings of a task a person may see (D-135).

A task can have several finished recordings: when the moderator listens and chooses Record again
or Call again, the newer recording replaces the older one (rejected by the moderator). The people
who run the project and the task's moderator see every recording; everyone else (QC Executives,
Client Viewers) sees only the current one, and a replaced recording's files, details and consent
record answer them like a missing one (404).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.core.permissions import Perm
from app.modules.auth.deps import Principal
from app.modules.recordings.models import Recording, current_recording_of
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task


def sees_replaced(db: Session, principal: Principal, task: Task) -> bool:
    """The caller runs the task's project or is its moderator, so sees replaced recordings too."""
    return principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id) or tasks.is_moderator(
        db, principal, task
    )


def current_id(db: Session, task_id: uuid.UUID) -> uuid.UUID | None:
    """The task's current recording, if it has a finished one."""
    return db.scalar(current_recording_of(task_id).with_only_columns(Recording.id))


def get_recording(
    db: Session, principal: Principal, recording_id: uuid.UUID
) -> tuple[Recording, Task]:
    """A recording of a task the caller sees; 404 otherwise (no existence leak)."""
    rec = db.get(Recording, recording_id)
    if rec is None:
        raise not_found("Recording")
    try:
        task = tasks.get_task(db, principal, rec.task_id)
    except AppError:
        raise not_found("Recording") from None
    return rec, task


def readable(
    db: Session, principal: Principal, recording_id: uuid.UUID, what: str = "Recording"
) -> tuple[Recording, Task]:
    """get_recording(), and a replaced recording only for people who see those: anyone else
    gets 404 "<what> not found", the answer for one that does not exist."""
    rec, task = get_recording(db, principal, recording_id)
    if not sees_replaced(db, principal, task) and current_id(db, task.id) != rec.id:
        raise not_found(what)
    return rec, task


def listed(
    db: Session, principal: Principal, task: Task
) -> tuple[list[Recording], uuid.UUID | None]:
    """The task's recordings this caller sees, newest first, and the current one's id."""
    current = current_id(db, task.id)
    query = select(Recording).where(Recording.task_id == task.id)
    if not sees_replaced(db, principal, task):
        query = query.where(Recording.id == current)
    return list(db.scalars(query.order_by(Recording.started_at.desc()))), current
