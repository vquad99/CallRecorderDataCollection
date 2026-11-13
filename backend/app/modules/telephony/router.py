"""Phone-call routes (TEL-002, TEL-018, TEL-036, TEL-037, D-101).

Every action goes to the server and the answer shows what the provider actually said; the page
never shows a call as connected on its own (TEL-037).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.adapters.telephony import ProviderError
from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.auth.models import User
from app.modules.auth.router import AppSettings, Cipher
from app.modules.telephony import analytics, service
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


# ------------------------------------------------------------------------- analytics (D-102)


class DayOut(BaseModel):
    day: str
    calls: int
    recorded: int
    failed: int
    open: int


class ModeratorOut(BaseModel):
    moderator_id: uuid.UUID
    name: str
    calls: int
    recorded: int
    failed: int
    avg_call_minutes: float | None


class AnalyticsOut(BaseModel):
    days: int
    calls: int
    in_call: int
    recorded: int
    dial_failed: int
    cancelled: int
    waiting_for_recording: int
    needs_person: int
    success_pct: float | None
    avg_call_minutes: float | None
    avg_fetch_minutes: float | None
    recorded_minutes: float
    by_day: list[DayOut]
    by_hour: list[int]
    by_moderator: list[ModeratorOut]
    cancel_reasons: dict[str, int]
    problems: dict[str, int]


@router.get("/telephony/analytics", response_model=AnalyticsOut)
def call_analytics(
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    project_id: uuid.UUID | None = None,
    days: Annotated[int, Query(ge=1, le=analytics.MAX_DAYS)] = 30,
) -> AnalyticsOut:
    result = analytics.analytics(
        db, principal, project_id=project_id, days=days, tz_name=settings.report_timezone
    )
    return AnalyticsOut.model_validate({**vars(result), "by_day": [vars(d) for d in result.by_day]})


class CallListItem(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    task_code: str
    project_code: str
    state: str
    agent_id: str
    phone_hint: str
    moderator_name: str
    dialled_at: datetime
    closed_at: datetime | None
    cancel_reason: str | None
    failure_code: str | None
    recording_id: uuid.UUID | None


class CallPage(BaseModel):
    items: list[CallListItem]
    total: int
    page: int
    page_size: int


@router.get("/calls", response_model=CallPage)
def all_calls(
    principal: CurrentPrincipal,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    state: Literal[
        "DIALLING",
        "DIAL_FAILED",
        "CANCELLED",
        "WAITING_FOR_RECORDING",
        "NEEDS_MATCH",
        "FETCH_FAILED",
        "RECORDED",
        "NEEDS_PERSON",
    ]
    | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CallPage:
    rows, total = analytics.list_calls(
        db, principal, project_id=project_id, state=state, page=page, page_size=page_size
    )
    return CallPage(
        items=[
            CallListItem(
                id=r.call.id,
                task_id=r.call.task_id,
                task_code=r.task_code,
                project_code=r.project_code,
                state=r.call.state,
                agent_id=r.call.agent_id,
                phone_hint=r.call.phone_hint,
                moderator_name=r.moderator_name,
                dialled_at=r.call.dialled_at,
                closed_at=r.call.closed_at,
                cancel_reason=r.call.cancel_reason,
                failure_code=r.call.failure_code,
                recording_id=r.call.recording_id,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


class TrafficOut(BaseModel):
    available: bool
    message: str
    first_day: str
    last_day: str
    # Calls per hour of the day as TxContact reports them; the shape is TxContact's own.
    data: Any = None


@router.get(
    "/telephony/provider-traffic",
    response_model=TrafficOut,
    dependencies=[Depends(require(Perm.TASKS_ASSIGN))],
)
def provider_traffic(
    request: Request,
    settings: AppSettings,
    days: Annotated[int, Query(ge=1, le=analytics.MAX_DAYS)] = 30,
) -> TrafficOut:
    """TxContact's own count of calls per hour of the day (its recording service, documented as
    GET /txrecord/api/v1/record/mostcallshour/). Account-wide: TxContact does not split it by
    project, so only people who assign tasks see it."""
    first, last = analytics.day_range(days, settings.txcontact_timezone)
    provider = request.app.state.telephony
    base = {"first_day": first.isoformat(), "last_day": last.isoformat()}
    if provider is None:
        return TrafficOut(
            available=False, message="Phone calls are not configured on this server", **base
        )
    try:
        data = provider.traffic(first, last)
    except ProviderError as exc:
        return TrafficOut(available=False, message=str(exc), **base)
    return TrafficOut(available=True, message="", data=data, **base)
