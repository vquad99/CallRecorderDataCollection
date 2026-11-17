"""/api/v1/tasks (TASK-*), consent capture."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.permissions import Perm, Role
from app.db.paging import Page, PageNumber, PageSize
from app.modules.audio_qc import service as audio_qc
from app.modules.auth.deps import CurrentPrincipal, DbSession, Principal, client_ip, require
from app.modules.auth.models import User
from app.modules.participants import consent as consents
from app.modules.participants.models import ConsentMethod, ConsentStatus, Participant
from app.modules.projects.service import get_manageable
from app.modules.tasks import bulk, service, workflow
from app.modules.tasks.models import TASK_STATUSES, Task

router = APIRouter(
    prefix="/tasks", tags=["tasks"], dependencies=[Depends(require(Perm.TASKS_VIEW))]
)

Status = Literal[
    "DRAFT",
    "ASSIGNED",
    "IN_PROGRESS",
    "RECORDED",
    "AUDIO_QC",
    "ADMIN_REVIEW",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
    "ON_HOLD",
]
Mode = Literal["TELEPHONY", "FACE_TO_FACE"]
Priority = Literal["LOW", "NORMAL", "HIGH", "URGENT"]


class TaskSummary(BaseModel):
    id: uuid.UUID
    task_code: str
    project_id: uuid.UUID
    recording_mode: Mode
    status: Status
    priority: Priority
    due_at: datetime | None
    created_at: datetime


class PartyOut(BaseModel):
    id: uuid.UUID
    participant_code: str
    consent_status: str | None
    consent_at: datetime | None


class TaskDetail(TaskSummary):
    held_from: str | None
    reason_code: str | None
    participant_a: PartyOut
    participant_b: PartyOut
    moderator_id: uuid.UUID | None
    moderator_name: str | None
    allowed_transitions: list[str]
    reasons: dict[str, list[str]]
    can_assign: bool
    # The caller may change the moderator now (assigns tasks, and the status still allows it).
    can_reassign: bool
    is_moderator: bool
    # D-119: participants (A, B) without consent to record; recording is refused until empty.
    consent_missing: list[str]


def summary(t: Task) -> TaskSummary:
    return TaskSummary.model_validate(t, from_attributes=True)


def detail(db: DbSession, principal: Principal, t: Task) -> TaskDetail:
    sides = consents.for_task(db, t)
    moderator = service.active_assignee(db, t.id, Role.MODERATOR.value)
    actor = service.actor_from(principal, t, moderator)

    def party(side: consents.SideConsent) -> PartyOut:
        p = db.get_one(Participant, side.participant_id)
        noted = side.latest_noted
        return PartyOut(
            id=p.id,
            participant_code=p.participant_code,
            consent_status=noted.status if noted else None,
            consent_at=noted.created_at if noted else None,
        )

    mod_name = (
        db.scalar(select(User.display_name).where(User.id == moderator.user_id))
        if moderator
        else None
    )
    return TaskDetail(
        **summary(t).model_dump(),
        held_from=t.held_from,
        reason_code=t.reason_code,
        participant_a=party(sides[0]),
        participant_b=party(sides[1]),
        moderator_id=moderator.user_id if moderator else None,
        moderator_name=mod_name,
        allowed_transitions=workflow.user_options(t.status, t.held_from, actor),
        reasons={k: sorted(v) for k, v in workflow.REASONS.items()},
        can_assign=actor.can_assign,
        can_reassign=service.can_reassign(actor, t),
        is_moderator=actor.is_moderator,
        consent_missing=consents.missing(sides),
    )


class TaskPage(Page[TaskSummary]):
    pass


@router.get("", response_model=TaskPage)
def list_tasks(
    principal: CurrentPrincipal,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    status: Status | None = None,
    mode: Mode | None = None,
    mine: bool = False,
    search: Annotated[str | None, Query(max_length=40)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> TaskPage:
    f = service.TaskFilter(
        project_id=project_id, status=status, mode=mode, mine=mine, search=search
    )
    items, total = service.list_tasks(db, principal, f, page, page_size)
    return TaskPage(items=[summary(t) for t in items], total=total, page=page, page_size=page_size)


class CreateTaskBody(BaseModel):
    project_id: uuid.UUID
    recording_mode: Mode
    participant_a_id: uuid.UUID
    participant_b_id: uuid.UUID
    priority: Priority = "NORMAL"
    due_at: datetime | None = None
    # Optional: assign the moderator at once, so the task starts as Assigned (D-085).
    moderator_id: uuid.UUID | None = None


@router.post("", response_model=TaskDetail, status_code=201)
def create_task(
    body: CreateTaskBody, request: Request, principal: CurrentPrincipal, db: DbSession
) -> TaskDetail:
    data = service.TaskInput(
        recording_mode=body.recording_mode,
        participant_a_id=body.participant_a_id,
        participant_b_id=body.participant_b_id,
        priority=body.priority,
        due_at=body.due_at,
    )
    ip = client_ip(request)
    if body.moderator_id is not None:
        # Checked before the task exists, so a wrong choice never leaves a half-made task;
        # only someone who may add tasks here learns who is a moderator of the project.
        project = get_manageable(db, principal, body.project_id, Perm.TASKS_ASSIGN)
        service.require_member_with_role(db, project.id, body.moderator_id, Role.MODERATOR)
    task = service.create_task(db, principal, body.project_id, data, ip)
    if body.moderator_id is not None:
        task = service.assign_moderator(db, principal, task.id, body.moderator_id, None, ip)
    return detail(db, principal, task)


class ImportTasksBody(BaseModel):
    project_id: uuid.UUID
    csv: str = Field(min_length=1, max_length=500_000)
    confirm: bool = False


class ImportTaskRow(BaseModel):
    line: int
    pair: str
    ok: bool
    message: str
    task_code: str | None


class ImportTasksOut(BaseModel):
    rows: list[ImportTaskRow]
    ready: int
    created: int


@router.post("/import", response_model=ImportTasksOut)
def import_tasks(
    body: ImportTasksBody, request: Request, principal: CurrentPrincipal, db: DbSession
) -> ImportTasksOut:
    """Add many tasks from a CSV file; check first, then add (D-083)."""
    rows = bulk.import_csv(
        db, principal, body.project_id, body.csv, body.confirm, client_ip(request)
    )
    return ImportTasksOut(
        rows=[ImportTaskRow.model_validate(r, from_attributes=True) for r in rows],
        ready=sum(1 for r in rows if r.ok),
        created=sum(1 for r in rows if r.task_code),
    )


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> TaskDetail:
    return detail(db, principal, service.get_task(db, principal, task_id))


class AssignBody(BaseModel):
    user_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)


@router.post("/{task_id}/assign", response_model=TaskDetail)
def assign(
    task_id: uuid.UUID,
    body: AssignBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TaskDetail:
    return detail(
        db,
        principal,
        service.assign_moderator(
            db, principal, task_id, body.user_id, body.reason, client_ip(request)
        ),
    )


class DeleteBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.post("/{task_id}/delete", status_code=204)
def delete_task(
    task_id: uuid.UUID,
    body: DeleteBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> None:
    """Delete a task made by mistake, while nothing has happened on it (D-115)."""
    service.delete_task(db, principal, task_id, body.reason, client_ip(request))


class TransitionBody(BaseModel):
    to: Status
    reason_code: str | None = Field(default=None, max_length=50)
    comment: str = Field(default="", max_length=2000)


@router.post("/{task_id}/transition", response_model=TaskDetail)
def transition(
    task_id: uuid.UUID,
    body: TransitionBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TaskDetail:
    task = service.get_task(db, principal, task_id)
    actor = service.actor_for(db, principal, task)
    if task.status == "RECORDED" and body.to == "AUDIO_QC":
        # Who may do it first, then whether the recording's automatic check is there: the
        # moderator sends it on only once QC has something to read (D-092).
        workflow.check(
            task.status,
            body.to,
            actor,
            held_from=task.held_from,
            reason_code=body.reason_code,
            comment=body.comment,
        )
        audio_qc.ensure_checked(db, task)
    service.transition(
        db,
        task,
        body.to,
        actor,
        actor_id=principal.user_id,
        reason_code=body.reason_code,
        comment=body.comment,
        ip=client_ip(request),
    )
    return detail(db, principal, task)


class ConsentBody(BaseModel):
    participant_id: uuid.UUID
    status: ConsentStatus
    method: ConsentMethod
    note: str = Field(default="", max_length=2000)


@router.post("/{task_id}/consent", response_model=TaskDetail, status_code=201)
def consent(
    task_id: uuid.UUID,
    body: ConsentBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TaskDetail:
    service.capture_consent(
        db,
        principal,
        task_id,
        body.participant_id,
        body.status,
        body.method,
        body.note,
        client_ip(request),
    )
    return detail(db, principal, service.get_task(db, principal, task_id))


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class TimelineOut(BaseModel):
    at: datetime
    kind: str
    actor: str | None
    text: str
    # Set for status changes only (kind "status"); null for assignments and comments.
    from_status: str | None = None
    to_status: str | None = None
    reason_code: str | None = None
    comment: str | None = None


@router.post("/{task_id}/comments", status_code=201, response_model=TimelineOut)
def add_comment(
    task_id: uuid.UUID,
    body: CommentBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TimelineOut:
    c = service.add_comment(db, principal, task_id, body.body, client_ip(request))
    return TimelineOut(at=c.created_at, kind="comment", actor=principal.display_name, text=c.body)


@router.get("/{task_id}/timeline", response_model=list[TimelineOut])
def timeline(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[TimelineOut]:
    return [
        TimelineOut.model_validate(e, from_attributes=True)
        for e in service.timeline(db, principal, task_id)
    ]


assert set(Status.__args__) == set(TASK_STATUSES)  # type: ignore[attr-defined]  # noqa: S101
