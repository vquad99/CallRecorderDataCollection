"""Phone-call routes (TEL-002, TEL-018, TEL-036, TEL-037, D-101).

Every action goes to the server and the answer shows what the provider actually said; the page
never shows a call as connected on its own (TEL-037).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.auth.models import User
from app.modules.auth.router import Cipher
from app.modules.telephony import service
from app.modules.telephony.models import Call, CallEvent

router = APIRouter(tags=["telephony"], dependencies=[Depends(require(Perm.TASKS_VIEW))])
users_router = APIRouter(tags=["telephony"], dependencies=[Depends(require(Perm.USERS_MANAGE))])


class TelephonyStatus(BaseModel):
    configured: bool
    provider: str


@router.get("/telephony/status", response_model=TelephonyStatus)
def status(request: Request) -> TelephonyStatus:
    provider = request.app.state.telephony
    return TelephonyStatus(
        configured=provider is not None, provider=provider.name if provider else "TXCONTACT"
    )


class CandidateOut(BaseModel):
    session_id: str
    start: str | None
    duration: str
    from_hint: str
    to_hint: str
    file: str


class EventOut(BaseModel):
    at: datetime
    kind: str
    actor: str | None
    text: str


class CallOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    provider: str
    state: str
    agent_id: str
    phone_hint: str
    moderator_id: uuid.UUID
    moderator_name: str | None
    dialled_at: datetime
    closed_at: datetime | None
    cancel_reason: str | None
    note: str
    provider_reference: str | None
    provider_session_id: str | None
    recording_id: uuid.UUID | None
    fetch_attempts: int
    next_fetch_at: datetime | None
    failure_code: str | None
    failure_detail: str | None
    candidates: list[CandidateOut]
    events: list[EventOut]


def _out(db: DbSession, calls: list[Call]) -> list[CallOut]:
    events = service.events_of(db, [c.id for c in calls])
    people = {c.moderator_id for c in calls} | {
        e.actor_id for es in events.values() for e in es if e.actor_id
    }
    names = (
        dict(db.execute(select(User.id, User.display_name).where(User.id.in_(people))).all())
        if people
        else {}
    )

    def event(e: CallEvent) -> EventOut:
        actor = names.get(e.actor_id) if e.actor_id else None
        return EventOut(at=e.created_at, kind=e.kind, actor=actor, text=e.detail)

    return [
        CallOut(
            id=c.id,
            task_id=c.task_id,
            provider=c.provider,
            state=c.state,
            agent_id=c.agent_id,
            phone_hint=c.phone_hint,
            moderator_id=c.moderator_id,
            moderator_name=names.get(c.moderator_id),
            dialled_at=c.dialled_at,
            closed_at=c.closed_at,
            cancel_reason=c.cancel_reason,
            note=c.note,
            provider_reference=c.provider_reference,
            provider_session_id=c.provider_session_id,
            recording_id=c.recording_id,
            fetch_attempts=c.fetch_attempts,
            next_fetch_at=c.next_fetch_at,
            failure_code=c.failure_code,
            failure_detail=c.failure_detail,
            candidates=[CandidateOut(**vars(x)) for x in service.candidates_of(c)],
            events=[event(e) for e in events[c.id]],
        )
        for c in calls
    ]


@router.get("/tasks/{task_id}/calls", response_model=list[CallOut])
def task_calls(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[CallOut]:
    return _out(db, service.list_calls(db, principal, task_id))


@router.post(
    "/tasks/{task_id}/calls",
    response_model=CallOut,
    status_code=201,
)
def start_call(
    task_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> CallOut:
    call = service.start_call(
        db, request.app.state.telephony, cipher, principal, task_id, client_ip(request)
    )
    return _out(db, [call])[0]


class CloseBody(BaseModel):
    note: str = Field(default="", max_length=1000)


@router.post(
    "/calls/{call_id}/close",
    response_model=CallOut,
    dependencies=[Depends(require(Perm.CALLS_END))],
)
def close_call(
    call_id: uuid.UUID,
    body: CloseBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> CallOut:
    call = service.close_call(db, principal, call_id, body.note, client_ip(request))
    return _out(db, [call])[0]


class CancelBody(BaseModel):
    reason: Literal["NO_ANSWER", "WRONG_NUMBER", "CALL_DROPPED", "CONSENT_REFUSED", "OTHER"]
    note: str = Field(default="", max_length=1000)


@router.post(
    "/calls/{call_id}/cancel",
    response_model=CallOut,
    dependencies=[Depends(require(Perm.CALLS_END))],
)
def cancel_call(
    call_id: uuid.UUID,
    body: CancelBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> CallOut:
    call = service.cancel_call(db, principal, call_id, body.reason, body.note, client_ip(request))
    return _out(db, [call])[0]


class MatchBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)


@router.post(
    "/calls/{call_id}/match",
    response_model=CallOut,
    dependencies=[Depends(require(Perm.CALLS_END))],
)
def choose_match(
    call_id: uuid.UUID,
    body: MatchBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> CallOut:
    call = service.choose_match(db, principal, call_id, body.session_id, client_ip(request))
    return _out(db, [call])[0]


@router.post(
    "/calls/{call_id}/retry",
    response_model=CallOut,
    dependencies=[Depends(require(Perm.CALLS_END))],
)
def retry(
    call_id: uuid.UUID, request: Request, principal: CurrentPrincipal, db: DbSession
) -> CallOut:
    call = service.retry(db, principal, call_id, client_ip(request))
    return _out(db, [call])[0]


class AgentSeatBody(BaseModel):
    agent_id: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_-]*$")


class AgentSeatOut(BaseModel):
    user_id: uuid.UUID
    telephony_agent_id: str | None


@users_router.put("/users/{user_id}/telephony-agent", response_model=AgentSeatOut)
def set_agent_seat(
    user_id: uuid.UUID,
    body: AgentSeatBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> AgentSeatOut:
    user = service.set_agent_seat(db, principal, user_id, body.agent_id, client_ip(request))
    return AgentSeatOut(user_id=user.id, telephony_agent_id=user.telephony_agent_id)
