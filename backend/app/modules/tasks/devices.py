"""The device each speaker used in a conversation (D-147).

The moderator is with the speakers, so they fill it: for each participant of the task, the
details the project asks (`projects.device_fields`, projects/moderation.py): device make and
model (at most 60 characters each) and three Yes/No (Bluetooth earphones used, wired earphones
used, loudspeaker on). The call type is the task's recording mode.

- Who changes them: the task's moderator and people who assign tasks in the project, while the
  task is In progress or Recorded; once it went to QC they are read only, for everyone who may see
  the task (its QC Executive, the project's admins).
- Sending a recording to QC (Recorded -> Audio QC) needs every asked detail of both people:
  422 DEVICE_DETAILS_MISSING naming who and what.
- "Same as last time": the newest details saved for the same person on another task of the
  project are offered to whoever fills them; nothing is filled in by itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, forbidden
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.participants.models import Participant
from app.modules.projects import moderation
from app.modules.projects.models import Project
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task, TaskDeviceDetail
from app.modules.users.service import display_names

# While the moderator records and listens; from Audio QC on the details are read only.
EDITABLE = frozenset({"IN_PROGRESS", "RECORDED"})
Side = Literal["A", "B"]
SIDES: tuple[Side, ...] = ("A", "B")


@dataclass(frozen=True)
class Values:
    """One speaker's device details; None = not answered."""

    device_make: str | None = None
    device_model: str | None = None
    bluetooth_earphones: bool | None = None
    wired_earphones: bool | None = None
    loudspeaker_on: bool | None = None

    @classmethod
    def of(cls, row: TaskDeviceDetail | None) -> Values:
        if row is None:
            return cls()
        return cls(**{f.name: getattr(row, f.name) for f in fields(cls)})

    def as_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def missing(self, asked: Sequence[str]) -> list[str]:
        """The asked details without an answer, in the form's order."""
        return [name for name in asked if getattr(self, name) in (None, "")]


def clean(raw: Mapping[str, Any]) -> Values:
    """Values as sent: text tidied (spaces), empty text is no answer."""

    def text(value: Any) -> str | None:
        # The API holds each to MAX_DEVICE_TEXT characters; tidying only makes it shorter.
        if value is None:
            return None
        return " ".join(str(value).split()) or None

    return Values(
        device_make=text(raw.get("device_make")),
        device_model=text(raw.get("device_model")),
        bluetooth_earphones=raw.get("bluetooth_earphones"),
        wired_earphones=raw.get("wired_earphones"),
        loudspeaker_on=raw.get("loudspeaker_on"),
    )


def _people(task: Task) -> dict[Side, uuid.UUID]:
    return {"A": task.participant_a_id, "B": task.participant_b_id}


def _rows(db: Session, task: Task) -> dict[uuid.UUID, TaskDeviceDetail]:
    return {
        row.participant_id: row
        for row in db.scalars(select(TaskDeviceDetail).where(TaskDeviceDetail.task_id == task.id))
    }


def missing_by_person(
    project: Project, task: Task, rows: Mapping[uuid.UUID, TaskDeviceDetail]
) -> dict[uuid.UUID, list[str]]:
    """Per participant (A first), the asked details not answered; people with none left out."""
    asked = list(project.device_fields)
    out = {}
    for pid in _people(task).values():
        gaps = Values.of(rows.get(pid)).missing(asked)
        if gaps:
            out[pid] = gaps
    return out


def _codes(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    return dict(
        db.execute(
            select(Participant.id, Participant.participant_code).where(Participant.id.in_(ids))
        ).all()
    )


def missing_codes(db: Session, project: Project, task: Task) -> list[str]:
    """For the task page: who still needs device details before the task may go to QC (codes,
    A first); empty when the project asks none or the task is past that point."""
    if not project.device_fields or task.status not in EDITABLE:
        return []
    gaps = missing_by_person(project, task, _rows(db, task))
    if not gaps:
        return []
    codes = _codes(db, list(gaps))
    return [codes[pid] for pid in gaps]


def ensure_complete(db: Session, task: Task) -> None:
    """A recording goes to QC only with every asked device detail of both people: 422
    DEVICE_DETAILS_MISSING naming who and what."""
    project = db.get_one(Project, task.project_id)
    if not project.device_fields:
        return
    gaps = missing_by_person(project, task, _rows(db, task))
    if not gaps:
        return
    codes = _codes(db, list(gaps))
    words = moderation.DEVICE_FIELDS
    named = "; ".join(
        f"{codes[pid]} ({', '.join(words[name] for name in names)})" for pid, names in gaps.items()
    )
    raise AppError(
        f"Fill in the device details before sending the task to QC. Missing: {named}.",
        code="DEVICE_DETAILS_MISSING",
        status_code=422,
        details=[{"participants": {codes[pid]: names for pid, names in gaps.items()}}],
    )


def may_edit(db: Session, principal: Principal, task: Task) -> bool:
    """The task's moderator or someone who assigns tasks in the project, before QC."""
    if task.status not in EDITABLE:
        return False
    return principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id) or tasks.is_moderator(
        db, principal, task
    )


@dataclass(frozen=True)
class LastTime:
    """A person's newest details on another task of the project."""

    task_code: str
    values: Values
    filled_at: datetime


@dataclass(frozen=True)
class Party:
    side: Side
    participant_id: uuid.UUID
    participant_code: str
    values: Values
    filled_by: str | None
    filled_at: datetime | None
    missing: list[str]
    last_time: LastTime | None


@dataclass(frozen=True)
class View:
    fields: list[str]
    call_type: moderation.CallType
    editable: bool
    participants: list[Party]

    @property
    def complete(self) -> bool:
        return not any(p.missing for p in self.participants)


def _last_times(db: Session, task: Task) -> dict[uuid.UUID, LastTime]:
    """Each participant's newest details saved on another task of the same project (a person has
    a few conversations in a project, D-143, so the rows are few)."""
    rows = db.execute(
        select(TaskDeviceDetail, Task.task_code)
        .join(Task, Task.id == TaskDeviceDetail.task_id)
        .where(
            TaskDeviceDetail.participant_id.in_(list(_people(task).values())),
            TaskDeviceDetail.filled_at.is_not(None),
            Task.project_id == task.project_id,
            Task.id != task.id,
        )
        .order_by(TaskDeviceDetail.filled_at.desc())
    ).all()
    newest: dict[uuid.UUID, LastTime] = {}
    for row, code in rows:
        if row.filled_at is not None and row.participant_id not in newest:
            newest[row.participant_id] = LastTime(code, Values.of(row), row.filled_at)
    return newest


def _view(db: Session, principal: Principal, task: Task) -> View:
    project = db.get_one(Project, task.project_id)
    asked = list(project.device_fields)
    rows = _rows(db, task)
    editable = may_edit(db, principal, task)
    last = _last_times(db, task) if editable else {}
    people = _people(task)
    codes = _codes(db, list(people.values()))
    names = display_names(db, [r.filled_by for r in rows.values() if r.filled_by])
    parties = []
    for side, pid in people.items():
        row = rows.get(pid)
        values = Values.of(row)
        parties.append(
            Party(
                side=side,
                participant_id=pid,
                participant_code=codes[pid],
                values=values,
                filled_by=names.get(row.filled_by) if row and row.filled_by else None,
                filled_at=row.filled_at if row else None,
                missing=values.missing(asked),
                last_time=last.get(pid),
            )
        )
    return View(
        fields=asked,
        call_type=moderation.CALL_TYPES[task.recording_mode],
        editable=editable,
        participants=parties,
    )


def view(db: Session, principal: Principal, task_id: uuid.UUID) -> View:
    """Everyone who may see the task reads its device details."""
    return _view(db, principal, tasks.get_task(db, principal, task_id))


def save(
    db: Session,
    principal: Principal,
    task_id: uuid.UUID,
    entries: Mapping[Side, Mapping[str, Any]],
    ip: str | None,
) -> View:
    """Both people's details at once (by side A and B). 403 for someone who may not fill them,
    409 DEVICE_DETAILS_LOCKED once the task went to QC (or before the session started), 422
    INVALID_DEVICE_DETAILS unless both sides are given. Changes are audited with the values; a
    save that changes nothing is not."""
    task = tasks.get_task(db, principal, task_id)
    if not (
        principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id)
        or tasks.is_moderator(db, principal, task)
    ):
        raise forbidden("Only the task's moderator or a project admin fills the device details")
    if task.status not in EDITABLE:
        raise AppError(
            "Device details are filled while the task is in progress or recorded; after it went "
            "to QC they stay as they were sent.",
            code="DEVICE_DETAILS_LOCKED",
            status_code=409,
        )
    if set(entries) != set(SIDES):
        raise AppError(
            "Give the device details of both participants (A and B).",
            code="INVALID_DEVICE_DETAILS",
            status_code=422,
        )
    people = _people(task)
    rows = _rows(db, task)
    codes = _codes(db, list(people.values()))
    now = datetime.now(UTC)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for side in SIDES:
        pid = people[side]
        new = clean(entries[side])
        row = rows.get(pid)
        old = Values.of(row)
        if new == old:
            continue
        if row is None:
            row = TaskDeviceDetail(task_id=task.id, participant_id=pid)
            db.add(row)
        for name, value in new.as_dict().items():
            setattr(row, name, value)
        row.filled_by = principal.user_id
        row.filled_at = now
        before[codes[pid]] = old.as_dict()
        after[codes[pid]] = new.as_dict()
    if after:
        audit.record(
            db,
            action="task.device_details_changed",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            actor_id=principal.user_id,
            ip=ip,
            before=before,
            after=after,
        )
        db.commit()
    return _view(db, principal, task)
