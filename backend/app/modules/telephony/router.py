"""Phone-call routes (TEL-002, TEL-018, TEL-036, TEL-037, D-101, D-102, D-103).

Every action goes to the server and the answer shows what the provider actually said; the page
never shows a call as connected on its own (TEL-037).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from app.adapters.telephony import ProviderError
from app.api.deps import AppSettings, Cipher, Provider
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.telephony import analytics, service
from app.modules.telephony.models import Call, CallEvent
from app.modules.users.service import display_names

router = APIRouter(tags=["telephony"], dependencies=[Depends(require(Perm.TASKS_VIEW))])
users_router = APIRouter(tags=["telephony"], dependencies=[Depends(require(Perm.USERS_MANAGE))])
# The signed-in user's own phone seat (D-130): any account, for itself only.
account_router = APIRouter(prefix="/auth", tags=["telephony"])

CancelReason = Literal[
    "NO_ANSWER", "WRONG_NUMBER", "CALL_DROPPED", "POOR_QUALITY", "CONSENT_REFUSED", "OTHER"
]
ChecklistItem = Literal["A_JOINED", "B_JOINED", "MODERATOR_MUTED", "QUALITY_OK"]


class SeatLogin(BaseModel):
    """How the caller's page signs their phone seat in to TxContact's agent manager (D-133)."""

    url: str
    tenant_id: str
    # The caller's own seat and the extension it signs in on; null without a seat.
    agent_id: str | None
    extension: str | None
    # Whether the seat's password is saved: without it the seat cannot be signed in.
    has_password: bool


class TelephonyStatus(BaseModel):
    configured: bool
    provider: str
    # Null: the seat is made Ready elsewhere (TxContact's Chirp app), as before D-133.
    seat_login: SeatLogin | None = None


@router.get("/telephony/status", response_model=TelephonyStatus)
def status(
    provider: Provider, settings: AppSettings, principal: CurrentPrincipal
) -> TelephonyStatus:
    seat = principal.telephony_agent_id
    return TelephonyStatus(
        configured=provider is not None,
        provider=provider.name if provider else "TXCONTACT",
        seat_login=SeatLogin(
            url=settings.txcontact_agent_endpoint,
            tenant_id=settings.txcontact_tenant_id,
            agent_id=seat,
            extension=service.seat_extension(settings, seat) if seat else None,
            has_password=principal.telephony_has_password,
        )
        if provider is not None and settings.txcontact_seat_login
        else None,
    )


class CandidateOut(BaseModel):
    # `key` chooses this candidate; `session_id` and `file` are the provider's names, masked.
    key: str
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
    # Checklist items the moderator ticked, each with the time (D-103).
    checklist: dict[str, str]
    # Participant B rung into the call by the platform (D-111).
    b_dial_attempts: int
    b_dialled_at: datetime | None
    b_dial_status: str | None
    b_phone_hint: str | None
    # The conversation as the moderator marked it (D-113).
    record_started_at: datetime | None
    record_stopped_at: datetime | None
    candidates: list[CandidateOut]
    events: list[EventOut]


def _out(db: DbSession, calls: list[Call]) -> list[CallOut]:
    events = service.events_of(db, [c.id for c in calls])
    people = {c.moderator_id for c in calls} | {
        e.actor_id for es in events.values() for e in es if e.actor_id
    }
    names = display_names(db, people)

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
            # Shown masked: a provider's call id or file name may carry the caller's number.
            provider_session_id=service.mask(c.provider_session_id)
            if c.provider_session_id
            else None,
            recording_id=c.recording_id,
            fetch_attempts=c.fetch_attempts,
            next_fetch_at=c.next_fetch_at,
            failure_code=c.failure_code,
            failure_detail=c.failure_detail,
            checklist=service.checklist_of(c),
            b_dial_attempts=c.b_dial_attempts,
            b_dialled_at=c.b_dialled_at,
            b_dial_status=c.b_dial_status,
            b_phone_hint=c.b_phone_hint,
            record_started_at=c.record_started_at,
            record_stopped_at=c.record_stopped_at,
            candidates=[
                CandidateOut(
                    **{
                        **vars(x),
                        "key": service.candidate_key(x.session_id),
                        "session_id": service.mask(x.session_id),
                        "file": service.mask(x.file),
                    }
                )
                for x in service.candidates_of(c)
            ],
            events=[event(e) for e in events[c.id]],
        )
        for c in calls
    ]


@router.get("/tasks/{task_id}/calls", response_model=list[CallOut])
def task_calls(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[CallOut]:
    return _out(db, service.list_calls(db, principal, task_id))


@router.post("/tasks/{task_id}/calls", response_model=CallOut, status_code=201)
def start_call(
    task_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
    provider: Provider,
) -> CallOut:
    call = service.start_call(
        db, settings, provider, cipher, principal, task_id, client_ip(request)
    )
    return _out(db, [call])[0]


class TickBody(BaseModel):
    item: ChecklistItem
    done: bool = True


@router.post(
    "/calls/{call_id}/checklist",
    response_model=CallOut,
    dependencies=[Depends(require(Perm.CALLS_END))],
)
def tick(
    call_id: uuid.UUID, body: TickBody, request: Request, principal: CurrentPrincipal, db: DbSession
) -> CallOut:
    call = service.tick(db, principal, call_id, body.item, body.done, client_ip(request))
    return _out(db, [call])[0]


@router.post("/calls/{call_id}/call-b", response_model=CallOut)
def call_b(
    call_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
    provider: Provider,
) -> CallOut:
    """Ring participant B into the call on the moderator's seat (D-111)."""
    call = service.call_b(db, provider, cipher, principal, call_id, client_ip(request))
    return _out(db, [call])[0]


@router.post("/calls/{call_id}/recording/start", response_model=CallOut)
def start_recording(
    call_id: uuid.UUID, request: Request, principal: CurrentPrincipal, db: DbSession
) -> CallOut:
    """Mark where the conversation starts, once A and B are on the line (D-113)."""
    call = service.mark_recording(db, principal, call_id, True, client_ip(request))
    return _out(db, [call])[0]


@router.post("/calls/{call_id}/recording/stop", response_model=CallOut)
def stop_recording(
    call_id: uuid.UUID, request: Request, principal: CurrentPrincipal, db: DbSession
) -> CallOut:
    """Mark where the conversation ends (D-113)."""
    call = service.mark_recording(db, principal, call_id, False, client_ip(request))
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
    settings: AppSettings,
) -> CallOut:
    call = service.close_call(db, settings, principal, call_id, body.note, client_ip(request))
    return _out(db, [call])[0]


class CancelBody(BaseModel):
    reason: CancelReason
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
    key: str = Field(min_length=1, max_length=64)


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
    call = service.choose_match(db, principal, call_id, body.key, client_ip(request))
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
    # The seat's password (D-130): left out keeps the saved one, "" removes it.
    password: str | None = Field(default=None, max_length=200)


class AgentSeatOut(BaseModel):
    user_id: uuid.UUID
    telephony_agent_id: str | None
    # Whether a password is saved for the seat; the password itself is only in the reveal.
    has_password: bool


class SeatPasswordOut(BaseModel):
    password: str


@users_router.put("/users/{user_id}/telephony-agent", response_model=AgentSeatOut)
def set_agent_seat(
    user_id: uuid.UUID,
    body: AgentSeatBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> AgentSeatOut:
    user = service.set_agent_seat(
        db, cipher, principal, user_id, body.agent_id, body.password, client_ip(request)
    )
    return AgentSeatOut(
        user_id=user.id,
        telephony_agent_id=user.telephony_agent_id,
        has_password=user.telephony_password_enc is not None,
    )


@users_router.get("/users/{user_id}/telephony-agent/password", response_model=SeatPasswordOut)
def user_seat_password(
    user_id: uuid.UUID, request: Request, principal: CurrentPrincipal, db: DbSession, cipher: Cipher
) -> SeatPasswordOut:
    """A Super Admin shows the saved seat password of a user (D-130). Audited."""
    return SeatPasswordOut(
        password=service.seat_password(db, cipher, principal, user_id, client_ip(request))
    )


@account_router.get("/phone-seat/password", response_model=SeatPasswordOut)
def own_seat_password(
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
    purpose: Literal["show", "line"] = "show",
) -> SeatPasswordOut:
    """The signed-in moderator's own seat password (D-130): shown on their account page, or
    (`purpose=line`) taken by their page to sign the seat in to TxContact (D-133). Audited."""
    return SeatPasswordOut(
        password=service.seat_password(
            db, cipher, principal, principal.user_id, client_ip(request), purpose == "line"
        )
    )


# ------------------------------------------------------------------- analytics (D-102, D-103)


class DayOut(BaseModel):
    day: str
    calls: int
    recorded: int
    failed: int
    open: int
    recorded_minutes: float


class ModeratorOut(BaseModel):
    moderator_id: uuid.UUID
    name: str
    calls: int
    recorded: int
    failed: int
    recorded_minutes: float
    avg_call_minutes: float | None


class ProjectCallsOut(BaseModel):
    project_id: uuid.UUID
    code: str
    name: str
    calls: int
    recorded: int
    failed: int
    recorded_minutes: float


class AnalyticsOut(BaseModel):
    days: int
    truncated: bool
    calls: int
    in_call: int
    stale_calls: int
    recorded: int
    dial_failed: int
    cancelled: int
    waiting_for_recording: int
    needs_person: int
    success_pct: float | None
    avg_call_minutes: float | None
    avg_fetch_minutes: float | None
    recorded_minutes: float
    today_recorded_minutes: float
    target_minutes_per_day: float | None
    funnel: dict[str, int]
    tasks_called: int
    tasks_called_again: int
    calls_per_task: float | None
    tasks_by_status: dict[str, int]
    tasks_not_called: int
    automatic_checks: dict[str, int]
    qc_decisions: dict[str, int]
    checklist: dict[str, int]
    by_day: list[DayOut]
    by_hour: list[int]
    by_moderator: list[ModeratorOut]
    by_project: list[ProjectCallsOut]
    cancel_reasons: dict[str, int]
    problems: dict[str, int]


Days = Annotated[int, Query(ge=1, le=analytics.MAX_DAYS)]


@router.get(
    "/telephony/analytics",
    response_model=AnalyticsOut,
    dependencies=[Depends(require(Perm.TASKS_ASSIGN))],
)
def call_analytics(
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    project_id: uuid.UUID | None = None,
    days: Days = 30,
) -> AnalyticsOut:
    result = analytics.analytics(db, principal, settings, project_id=project_id, days=days)
    return AnalyticsOut.model_validate({**vars(result), "by_day": [vars(d) for d in result.by_day]})


class CallListItem(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    task_code: str
    project_code: str
    state: str
    # Still "on the call" long after any call can last: left open, needs a person.
    stale: bool
    agent_id: str
    phone_hint: str
    moderator_name: str
    dialled_at: datetime
    closed_at: datetime | None
    cancel_reason: str | None
    failure_code: str | None
    recording_id: uuid.UUID | None
    recording_seconds: float | None


class CallPage(BaseModel):
    items: list[CallListItem]
    total: int
    page: int
    page_size: int


@router.get("/calls", response_model=CallPage)
def all_calls(
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
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
        db, principal, settings, project_id=project_id, state=state, page=page, page_size=page_size
    )
    return CallPage(
        items=[
            CallListItem(
                id=r.call.id,
                task_id=r.call.task_id,
                task_code=r.task_code,
                project_code=r.project_code,
                state=r.call.state,
                stale=r.stale,
                agent_id=r.call.agent_id,
                phone_hint=r.call.phone_hint,
                moderator_name=r.moderator_name,
                dialled_at=r.call.dialled_at,
                closed_at=r.call.closed_at,
                cancel_reason=r.call.cancel_reason,
                failure_code=r.call.failure_code,
                recording_id=r.call.recording_id,
                recording_seconds=r.recording_seconds,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/calls/export", dependencies=[Depends(require(Perm.TASKS_ASSIGN))])
def export_calls(
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    project_id: uuid.UUID | None = None,
    days: Days = 30,
) -> Response:
    """Every call of the period as a CSV file: the tracker people keep in a spreadsheet."""
    body, count = analytics.calls_csv(db, principal, settings, project_id=project_id, days=days)
    audit.record(
        db,
        action="calls.exported",
        entity_type="project" if project_id else "calls",
        entity_id=project_id,
        project_id=project_id,
        actor_id=principal.user_id,
        ip=client_ip(request),
        after={"days": days, "rows": count},
    )
    db.commit()
    name = f"phone_calls_{datetime.now(UTC):%Y%m%d}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
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
def provider_traffic(settings: AppSettings, provider: Provider, days: Days = 30) -> TrafficOut:
    """The provider's own count of calls per hour of the day (the address is the adapter's
    business). Account-wide: the provider does not split it by project, so only people who
    assign tasks see it."""
    first, last = analytics.day_range(days, settings.txcontact_timezone)
    if provider is None:
        return TrafficOut(
            available=False,
            message="Phone calls are not configured on this server",
            first_day=first.isoformat(),
            last_day=last.isoformat(),
        )
    try:
        data = provider.traffic(first, last)
    except ProviderError as exc:
        return TrafficOut(
            available=False,
            message=str(exc),
            first_day=first.isoformat(),
            last_day=last.isoformat(),
        )
    return TrafficOut(
        available=True,
        message="",
        data=data,
        first_day=first.isoformat(),
        last_day=last.isoformat(),
    )
