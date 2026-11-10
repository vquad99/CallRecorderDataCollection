"""/api/v1/tasks (TASK-*), consent capture."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, Principal, client_ip, require
from app.modules.auth.models import User
from app.modules.participants.models import Participant
from app.modules.tasks import service, workflow
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
    "TRANSCRIPTION_PENDING",
    "TRANSCRIPTION_IN_PROGRESS",
    "TRANSCRIPT_QC",
    "APPROVED",
    "REJECTED",
    "RETURNED",
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
    is_moderator: bool


def summary(t: Task) -> TaskSummary:
    return TaskSummary.model_validate(t, from_attributes=True)


def detail(db: DbSession, principal: Principal, t: Task) -> TaskDetail:
    consent = service.latest_consent(db, t)
    moderator = service.active_assignee(db, t.id, "MODERATOR")
    actor = service.actor_for(db, principal, t)

    def party(pid: uuid.UUID) -> PartyOut:
        p = db.get(Participant, pid)
        assert p is not None  # noqa: S101
        c = consent.get(pid)
        return PartyOut(
            id=p.id,
            participant_code=p.participant_code,
            consent_status=c.status if c else None,
            consent_at=c.created_at if c else None,
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
        participant_a=party(t.participant_a_id),
        participant_b=party(t.participant_b_id),
        moderator_id=moderator.user_id if moderator else None,
        moderator_name=mod_name,
        allowed_transitions=workflow.user_options(t.status, t.held_from, actor),
        reasons={k: sorted(v) for k, v in workflow.REASONS.items()},
        can_assign=actor.can_assign,
        is_moderator=actor.is_moderator,
    )


class TaskPage(BaseModel):
    items: list[TaskSummary]
    total: int
    page: int
    page_size: int


@router.get("", response_model=TaskPage)
def list_tasks(
    principal: CurrentPrincipal,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    status: Status | None = None,
    mode: Mode | None = None,
    mine: bool = False,
    search: Annotated[str | None, Query(max_length=40)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
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
    return detail(
        db, principal, service.create_task(db, principal, body.project_id, data, client_ip(request))
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
    status: Literal["GIVEN", "REFUSED", "WITHDRAWN"]
    method: Literal["VERBAL_RECORDED", "VERBAL_NOTED", "WRITTEN", "DIGITAL"]
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
        TimelineOut(at=e.at, kind=e.kind, actor=e.actor, text=e.text)
        for e in service.timeline(db, principal, task_id)
    ]


assert set(Status.__args__) == set(TASK_STATUSES)  # type: ignore[attr-defined]  # noqa: S101
