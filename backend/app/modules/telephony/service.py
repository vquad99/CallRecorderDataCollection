"""Phone calls through the telephony provider (TEL-002, TEL-010, TEL-011, TEL-018, TEL-027, D-101).

The flow (owner, 2026-11-13):
1. The moderator starts the call: the provider rings participant A and connects them to the
   moderator's agent seat.
2. The moderator adds participant B from the provider's agent screen, ticks the call checklist
   (A joined, B joined, muted and listening, voices clear), and records both consents.
3. The moderator closes the call here: both people joined and both consents recorded. A call that
   did not work is cancelled with a reason instead.
4. The platform finds the call among the provider's calls (agent seat, time, A's number), downloads
   the recording, keeps the provider's file unchanged, builds the 16 kHz delivery file, and moves
   the task to Recorded; the automatic audio check runs as for face-to-face recordings. That
   part is the platform's own work: fetch.py.

Every step is written to call_events (the call's history) and every person's action to the audit
log. If the platform cannot tell which provider call is this one, a person picks it; nothing is
guessed. A call can always be cancelled.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.telephony import ProviderError, ProviderSession, TelephonyProvider
from app.adapters.txcontact import UnsupportedNumber, digits
from app.core.config import Settings
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm, Role
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.auth.security import FieldCipher
from app.modules.participants import consent
from app.modules.participants.models import Participant
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task
from app.modules.telephony.models import (
    CANCEL_REASONS,
    CHECKLIST_ITEMS,
    CHECKLIST_REQUIRED,
    Call,
    CallEvent,
)

logger = logging.getLogger("app.telephony")

MAX_CALLS_LISTED = 20
MAX_EVENTS_LISTED = 200
CHECKLIST_LABELS = {
    "A_JOINED": "participant A joined the call",
    "B_JOINED": "participant B joined the call",
    "MODERATOR_MUTED": "the moderator is muted and listening",
    "QUALITY_OK": "both voices are clear",
}


def not_configured() -> AppError:
    return AppError(
        "Phone calls are not configured on this server", code="NOT_CONFIGURED", status_code=503
    )


def mask(text: str) -> str:
    """A provider's file name or call id may carry the caller's number: any run of nine or more
    digits is shown by its last two only. Used for everything people see or export; the real
    name is kept only where the download needs it."""
    return re.sub(r"\d{9,}", lambda m: "…" + m.group()[-2:], text or "")


@dataclass(frozen=True)
class Candidate:
    """A provider call a person may choose. Stored with the real file name (the download needs
    it); shown through `mask`, with only the last two digits of each number."""

    session_id: str
    start: str | None
    duration: str
    from_hint: str
    to_hint: str
    file: str


def candidate_from(s: ProviderSession) -> Candidate:
    return Candidate(
        session_id=s.session_id,
        start=s.start.isoformat() if s.start else None,
        duration=s.duration,
        from_hint=digits(s.from_number)[-2:],
        to_hint=digits(s.to_number)[-2:],
        file=s.rec_filename,
    )


def candidate_key(session_id: str) -> str:
    """What the page sends back to choose a candidate: not the provider's own id, which is only
    ever shown masked."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:24]


def candidates_of(call: Call) -> list[Candidate]:
    try:
        rows = json.loads(call.candidates or "[]")
    except json.JSONDecodeError:
        return []
    return [Candidate(**row) for row in rows if isinstance(row, dict)]


def checklist_of(call: Call) -> dict[str, str]:
    """Checklist items the moderator ticked, each with the time it was ticked."""
    try:
        ticked = json.loads(call.checklist or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(ticked, dict):
        return {}
    return {k: str(v) for k, v in ticked.items() if k in CHECKLIST_ITEMS}


def record_event(
    db: Session, call: Call, kind: str, detail: str = "", actor_id: uuid.UUID | None = None
) -> None:
    db.add(CallEvent(call_id=call.id, kind=kind, actor_id=actor_id, detail=detail[:2000]))


def _audit(
    db: Session,
    call: Call,
    action: str,
    principal: Principal,
    ip: str | None,
    after: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action=action,
        entity_type="call",
        entity_id=call.id,
        project_id=call.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={"state": call.state, **(after or {})},
    )


def _phone(cipher: FieldCipher, participant: Participant, side: str) -> str:
    if not participant.phone_e164_enc:
        raise AppError(
            f"Participant {side} has no phone number", code="PHONE_MISSING", status_code=409
        )
    return cipher.decrypt(participant.phone_e164_enc)


# ---------------------------------------------------------------------------- people's actions


def list_calls(db: Session, principal: Principal, task_id: uuid.UUID) -> list[Call]:
    """The task's newest calls (a task is called a handful of times at most)."""
    task = tasks.get_task(db, principal, task_id)
    return list(
        db.scalars(
            select(Call)
            .where(Call.task_id == task.id)
            .order_by(Call.created_at.desc())
            .limit(MAX_CALLS_LISTED)
        ).all()
    )


def events_of(db: Session, call_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[CallEvent]]:
    """Each call's history, oldest first; the newest MAX_EVENTS_LISTED of a call that has more."""
    out: dict[uuid.UUID, list[CallEvent]] = {cid: [] for cid in call_ids}
    if not call_ids:
        return out
    for e in db.scalars(
        select(CallEvent).where(CallEvent.call_id.in_(call_ids)).order_by(CallEvent.created_at)
    ).all():
        out[e.call_id].append(e)
    return {cid: events[-MAX_EVENTS_LISTED:] for cid, events in out.items()}


def start_call(
    db: Session,
    settings: Settings,
    provider: TelephonyProvider | None,
    cipher: FieldCipher,
    principal: Principal,
    task_id: uuid.UUID,
    ip: str | None,
) -> Call:
    if provider is None:
        raise not_configured()
    task = tasks.get_task(db, principal, task_id)
    if not principal.can_in_project(Perm.CALLS_START, task.project_id):
        raise forbidden()
    tasks.require_moderator(db, principal, task, "Only the assigned moderator calls for this task")
    if task.recording_mode != "TELEPHONY":
        raise AppError("This is not a telephony task", code="MODE_NOT_ALLOWED", status_code=422)
    if task.status != "IN_PROGRESS":
        raise AppError(
            "Start the task before calling", code="TASK_NOT_IN_PROGRESS", status_code=409
        )
    user = db.get(User, principal.user_id)
    agent_id = (user.telephony_agent_id or "").strip() if user else ""
    if not agent_id:
        raise AppError(
            "You have no TxContact agent seat yet; ask a Super Admin to add it to your account",
            code="NO_AGENT_SEAT",
            status_code=409,
        )
    # Nobody is rung before both have agreed (D-127): the call is only for recording them. An
    # "I agree" cannot be withdrawn (D-129), so B, agreed here, is still agreed when rung.
    missing = consent.missing(consent.for_task(db, task))
    if missing:
        raise tasks.consent_missing_error(missing)
    a = db.get_one(Participant, task.participant_a_id)
    phone = _phone(cipher, a, "A")
    # A participant's phone is not rung over and over (refused and cancelled calls count too).
    recent = (
        db.scalar(
            select(func.count())
            .select_from(Call)
            .where(
                Call.task_id == task.id, Call.dialled_at >= datetime.now(UTC) - timedelta(hours=1)
            )
        )
        or 0
    )
    if recent >= settings.telephony_max_calls_per_task_per_hour:
        raise AppError(
            f"This task has been called {recent} times in the last hour; wait before calling again",
            code="TOO_MANY_CALLS",
            status_code=429,
            headers={"Retry-After": "600"},
        )
    call = Call(
        id=uuid.uuid4(),
        task_id=task.id,
        project_id=task.project_id,
        provider=provider.name,
        moderator_id=principal.user_id,
        agent_id=agent_id,
        phone_hint=digits(phone)[-2:],
        state="DIALLING",
        dialled_at=datetime.now(UTC),
    )
    db.add(call)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(
            "This task already has a call in progress; close or cancel it first",
            code="CALL_OPEN",
            status_code=409,
        ) from None
    record_event(
        db,
        call,
        "DIAL_REQUESTED",
        f"Asked {provider.name} to ring participant A (number ending {call.phone_hint}) and "
        f"connect them to agent seat {agent_id}",
        principal.user_id,
    )
    _audit(db, call, "call.started", principal, ip, {"agent_id": agent_id})
    # Saved before the provider is asked: if anything stops between here and its answer, the
    # request is still on record and the call can be cancelled. It also frees the database
    # connection while the provider is thinking.
    db.commit()
    try:
        result = provider.dial(phone, agent_id)
    except UnsupportedNumber as exc:
        _dial_failed(db, call, "PHONE_NOT_SUPPORTED", str(exc))
    except ProviderError as exc:
        # No answer is not a refusal: the provider may still be ringing the phone.
        _dial_failed(
            db,
            call,
            "PROVIDER_UNREACHABLE",
            f"{exc}. The phone may still ring: look at your TxContact screen before calling again",
        )
    else:
        answer = f"HTTP {result.http_status}: {result.response_excerpt or '(empty answer)'}"
        if result.accepted:
            call.provider_reference = result.reference
            record_event(db, call, "DIAL_ACCEPTED", f"{provider.name} answered {answer}")
        else:
            _dial_failed(db, call, "PROVIDER_REFUSED", f"{provider.name} answered {answer}")
    db.commit()
    return call


def _dial_failed(db: Session, call: Call, code: str, detail: str) -> None:
    call.state = "DIAL_FAILED"
    call.failure_code = code
    call.failure_detail = detail
    call.closed_at = datetime.now(UTC)
    record_event(db, call, "DIAL_FAILED", detail)


def _call_for_change(db: Session, principal: Principal, call_id: uuid.UUID) -> tuple[Call, Task]:
    call = db.get(Call, call_id)
    if call is None:
        raise not_found("Call")
    try:
        task = tasks.get_task(db, principal, call.task_id)
    except AppError:
        raise not_found("Call") from None
    if not principal.can_in_project(Perm.CALLS_END, task.project_id):
        raise forbidden()
    # The moderator who made the call, the moderator the task is with now (after a reassignment
    # the new one takes the call over), or someone who assigns tasks in the project.
    assigned = tasks.active_assignee(db, task.id, Role.MODERATOR.value)
    own = call.moderator_id == principal.user_id or (
        assigned is not None and assigned.user_id == principal.user_id
    )
    manager = principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id)
    if not (own or manager):
        raise forbidden("Only the task's moderator, or a project admin, can change this call")
    return call, task


def _require_calling_moderator(db: Session, principal: Principal, task: Task, message: str) -> None:
    """Only the task's assigned moderator, who may place calls, does this on the call."""
    if not principal.can_in_project(Perm.CALLS_START, task.project_id):
        raise forbidden(message)
    tasks.require_moderator(db, principal, task, message)


def _require_state(call: Call, *states: str) -> None:
    if call.state not in states:
        raise AppError(
            f"The call is {call.state.lower().replace('_', ' ')}",
            code="CALL_STATE",
            status_code=409,
        )


def tick(
    db: Session,
    principal: Principal,
    call_id: uuid.UUID,
    item: str,
    done: bool,
    ip: str | None,
) -> Call:
    """The moderator confirms (or takes back) one checklist item while on the call."""
    call, _ = _call_for_change(db, principal, call_id)
    if item not in CHECKLIST_ITEMS:
        raise AppError("Unknown checklist item", code="VALIDATION_ERROR", status_code=422)
    # Boxes ticked one after the other arrive almost together: the row is locked and read again,
    # so each tick is added to the ones before it and none is lost.
    db.refresh(call, with_for_update=True)
    _require_state(call, "DIALLING")
    ticked = checklist_of(call)
    if done == (item in ticked):
        db.rollback()  # already so: a second click changes nothing (and the lock is let go)
        return call
    if done:
        ticked[item] = datetime.now(UTC).isoformat(timespec="seconds")
        record_event(
            db, call, "CHECKLIST", f"Confirmed: {CHECKLIST_LABELS[item]}", principal.user_id
        )
    else:
        del ticked[item]
        record_event(
            db, call, "CHECKLIST", f"Taken back: {CHECKLIST_LABELS[item]}", principal.user_id
        )
    call.checklist = json.dumps(ticked)
    _audit(db, call, "call.checklist", principal, ip, {"item": item, "done": done})
    db.commit()
    return call


MAX_B_DIALS = 3  # rings of participant B within one call


def call_b(
    db: Session,
    provider: TelephonyProvider | None,
    cipher: FieldCipher,
    principal: Principal,
    call_id: uuid.UUID,
    ip: str | None,
) -> Call:
    """Rings participant B into the call that is on the moderator's seat (D-111). Only the task's
    moderator, only while the call is on, only after A is confirmed on the line."""
    if provider is None:
        raise not_configured()
    call, task = _call_for_change(db, principal, call_id)
    _require_calling_moderator(db, principal, task, "Only the task's moderator rings participant B")
    # Two clicks arrive together: the row is locked, so B is rung once.
    db.refresh(call, with_for_update=True)
    _require_state(call, "DIALLING")
    if "A_JOINED" not in checklist_of(call):
        db.rollback()
        raise AppError(
            "Confirm that participant A is on the call before ringing participant B",
            code="A_NOT_JOINED",
            status_code=409,
        )
    if call.b_dial_attempts >= MAX_B_DIALS:
        db.rollback()
        raise AppError(
            f"Participant B has been rung {MAX_B_DIALS} times in this call; close or cancel it "
            "and start again",
            code="TOO_MANY_CALLS",
            status_code=429,
        )
    b = db.get_one(Participant, task.participant_b_id)
    phone = _phone(cipher, b, "B")
    call.b_dial_attempts += 1
    call.b_dialled_at = datetime.now(UTC)
    call.b_dial_status = None
    call.b_reference = None
    call.b_phone_hint = digits(phone)[-2:]
    record_event(
        db,
        call,
        "B_DIAL_REQUESTED",
        f"Asked {provider.name} to ring participant B (number ending {call.b_phone_hint}) into "
        f"the call on agent seat {call.agent_id}",
        principal.user_id,
    )
    _audit(db, call, "call.b_dialled", principal, ip, {"attempt": call.b_dial_attempts})
    db.commit()  # on record before the provider is asked, as for A
    try:
        result = provider.attach(phone, call.agent_id)
    except UnsupportedNumber as exc:
        call.b_dial_status = "REFUSED"
        record_event(db, call, "B_DIAL_FAILED", str(exc))
    except ProviderError as exc:
        call.b_dial_status = "UNREACHABLE"
        record_event(
            db,
            call,
            "B_DIAL_FAILED",
            f"{exc}. B's phone may still ring: look at your TxContact screen before ringing again",
        )
    else:
        answer = f"HTTP {result.http_status}: {result.response_excerpt or '(empty answer)'}"
        if result.accepted:
            call.b_dial_status = "ACCEPTED"
            call.b_reference = result.reference
            record_event(db, call, "B_DIAL_ACCEPTED", f"{provider.name} answered {answer}")
        else:
            call.b_dial_status = "REFUSED"
            record_event(db, call, "B_DIAL_FAILED", f"{provider.name} answered {answer}")
    db.commit()
    return call


def mark_recording(
    db: Session, principal: Principal, call_id: uuid.UUID, start: bool, ip: str | None
) -> Call:
    """The moderator marks where the conversation starts (both people on the line) or stops
    (D-113). Starting again moves the start and clears the stop."""
    call, task = _call_for_change(db, principal, call_id)
    _require_calling_moderator(db, principal, task, "Only the task's moderator marks the recording")
    db.refresh(call, with_for_update=True)
    _require_state(call, "DIALLING")
    now = datetime.now(UTC)
    if start:
        ticked = checklist_of(call)
        if any(item not in ticked for item in CHECKLIST_REQUIRED):
            db.rollback()
            raise AppError(
                "Tick that participant A and participant B are on the call before starting the "
                "recording",
                code="CHECKLIST_INCOMPLETE",
                status_code=409,
            )
        missing = consent.missing(consent.for_task(db, task))
        if missing:
            db.rollback()
            raise tasks.consent_missing_error(missing)
        again = call.record_started_at is not None
        call.record_started_at = now
        call.record_stopped_at = None
        record_event(
            db,
            call,
            "RECORDING_STARTED",
            "Recording started again: the earlier start is replaced"
            if again
            else "Recording started: the conversation is kept from here",
            principal.user_id,
        )
    else:
        if call.record_started_at is None:
            db.rollback()
            raise AppError(
                "Start the recording first", code="RECORDING_NOT_STARTED", status_code=409
            )
        if call.record_stopped_at is not None:
            db.rollback()
            return call
        call.record_stopped_at = now
        seconds = int((now - call.record_started_at).total_seconds())
        record_event(
            db,
            call,
            "RECORDING_STOPPED",
            f"Recording stopped after {seconds // 60} min {seconds % 60} s",
            principal.user_id,
        )
    _audit(db, call, "call.recording_marked", principal, ip, {"start": start})
    db.commit()
    return call


def close_call(
    db: Session,
    settings: Settings,
    principal: Principal,
    call_id: uuid.UUID,
    note: str,
    ip: str | None,
) -> Call:
    call, task = _call_for_change(db, principal, call_id)
    _require_state(call, "DIALLING")
    ticked = checklist_of(call)
    if any(item not in ticked for item in CHECKLIST_REQUIRED):
        raise AppError(
            "Confirm that participant A and participant B joined before closing the call. "
            "If the conversation did not happen, cancel the call instead.",
            code="CHECKLIST_INCOMPLETE",
            status_code=409,
        )
    missing = consent.missing(consent.for_task(db, task))
    if missing:
        raise AppError(
            f"Record consent for participant {' and '.join(missing)} before closing the call. "
            "If consent was refused, cancel the call instead.",
            code="CONSENT_MISSING",
            status_code=409,
        )
    if call.record_started_at is None:
        raise AppError(
            "Click Start recording when both people are on the line, and Stop recording when "
            "they have finished, before closing the call.",
            code="RECORDING_NOT_STARTED",
            status_code=409,
        )
    now = datetime.now(UTC)
    if call.record_stopped_at is None:
        call.record_stopped_at = now  # not stopped by hand: the conversation ends with the call
    call.state = "WAITING_FOR_RECORDING"
    call.closed_at = now
    call.note = note.strip()
    call.next_fetch_at = now + timedelta(seconds=settings.telephony_first_look_seconds)
    call.fetch_attempts = 0
    record_event(
        db,
        call,
        "CALL_CLOSED",
        "Call closed; looking for its recording" + (f". Note: {call.note}" if call.note else ""),
        principal.user_id,
    )
    _audit(db, call, "call.closed", principal, ip)
    db.commit()
    return call


def cancel_call(
    db: Session,
    principal: Principal,
    call_id: uuid.UUID,
    reason: str,
    note: str,
    ip: str | None,
) -> Call:
    """End a call without a recording. Allowed at every stage before the recording is stored, also
    while it is being fetched: a call must never be something nobody can stop."""
    call, _ = _call_for_change(db, principal, call_id)
    # The fetch makes a call RECORDED with the row locked: locked and read again here, a cancel
    # that arrives at that moment waits and then finds the call recorded, instead of writing
    # over it.
    db.refresh(call, with_for_update=True)
    _require_state(call, "DIALLING", "WAITING_FOR_RECORDING", "NEEDS_MATCH", "FETCH_FAILED")
    if reason not in CANCEL_REASONS:
        raise AppError(
            f"Choose a reason: {', '.join(CANCEL_REASONS)}", code="REASON_REQUIRED", status_code=422
        )
    if reason == "OTHER" and not note.strip():
        raise AppError("Explain the reason in the note", code="COMMENT_REQUIRED", status_code=422)
    mark_cancelled(db, call, reason, note.strip(), principal.user_id)
    _audit(db, call, "call.cancelled", principal, ip, {"reason": reason})
    db.commit()
    return call


def mark_cancelled(
    db: Session, call: Call, reason: str, note: str, actor_id: uuid.UUID | None
) -> None:
    call.state = "CANCELLED"
    call.cancel_reason = reason
    call.note = note
    call.closed_at = call.closed_at or datetime.now(UTC)
    call.next_fetch_at = None
    if call.recording_id is None:
        # A provider recording found or chosen for this call is let go, so the call it really
        # belongs to can take it; the call's history still names it (masked).
        call.provider_session_id = None
        call.provider_file = None
    record_event(
        db,
        call,
        "CALL_CANCELLED",
        f"Cancelled: {reason.lower().replace('_', ' ')}" + (f". {note}" if note else ""),
        actor_id,
    )


def choose_match(
    db: Session, principal: Principal, call_id: uuid.UUID, key: str, ip: str | None
) -> Call:
    call, _ = _call_for_change(db, principal, call_id)
    _require_state(call, "NEEDS_MATCH")
    chosen = next((c for c in candidates_of(call) if candidate_key(c.session_id) == key), None)
    if chosen is None:
        raise AppError(
            "Choose one of the calls listed for this call", code="NOT_A_CANDIDATE", status_code=422
        )
    session_id = chosen.session_id
    taken = db.scalar(
        select(Call.id).where(
            Call.provider == call.provider,
            Call.provider_session_id == session_id,
            Call.id != call.id,
        )
    )
    if taken is not None:
        raise AppError(
            "That recording already belongs to another call", code="SESSION_TAKEN", status_code=409
        )
    call.provider_session_id = session_id
    call.provider_file = chosen.file
    call.state = "WAITING_FOR_RECORDING"
    call.fetch_attempts = 0
    call.next_fetch_at = datetime.now(UTC)
    call.failure_code = call.failure_detail = None
    started = chosen.start or "at an unknown time"
    record_event(
        db,
        call,
        "MATCH_CHOSEN",
        f"Chosen by hand: provider call {mask(session_id)}, started {started}",
        principal.user_id,
    )
    _audit(db, call, "call.match_chosen", principal, ip, {"session_id": mask(session_id)})
    db.commit()
    return call


def retry(db: Session, principal: Principal, call_id: uuid.UUID, ip: str | None) -> Call:
    call, _ = _call_for_change(db, principal, call_id)
    _require_state(call, "NEEDS_MATCH", "FETCH_FAILED")
    call.state = "WAITING_FOR_RECORDING"
    call.fetch_attempts = 0
    call.next_fetch_at = datetime.now(UTC)
    call.failure_code = call.failure_detail = None
    record_event(
        db, call, "RETRY_REQUESTED", "Asked to look for the recording again", principal.user_id
    )
    _audit(db, call, "call.retry", principal, ip)
    db.commit()
    return call


def set_agent_seat(
    db: Session,
    cipher: FieldCipher,
    principal: Principal,
    user_id: uuid.UUID,
    agent_id: str | None,
    password: str | None,
    ip: str | None,
) -> User:
    """A moderator's phone seat and its password (D-101, D-130). The password: None keeps the
    saved one, "" removes it, anything else replaces it (stored encrypted). A seat removed takes
    its password with it. The audit says whether a password is saved, never the password."""
    if not principal.can(Perm.USERS_MANAGE):
        raise forbidden()
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    value = (agent_id or "").strip() or None
    if value is None and password:
        raise AppError(
            "Enter the seat number for this password", code="VALIDATION_ERROR", status_code=422
        )
    if value is not None:
        taken = db.scalar(
            select(User.id).where(User.telephony_agent_id == value, User.id != user.id)
        )
        if taken is not None:
            raise AppError(
                "Another user already has this agent seat", code="AGENT_SEAT_TAKEN", status_code=409
            )
    before = {
        "telephony_agent_id": user.telephony_agent_id,
        "has_password": user.telephony_password_enc is not None,
    }
    user.telephony_agent_id = value
    if value is None or password == "":
        user.telephony_password_enc = None
    elif password is not None:
        user.telephony_password_enc = cipher.encrypt(password)
    after: dict[str, Any] = {
        "telephony_agent_id": value,
        "has_password": user.telephony_password_enc is not None,
    }
    if password:
        after["password_changed"] = True
    if before != after:
        audit.record(
            db,
            action="user.agent_seat",
            entity_type="user",
            entity_id=user.id,
            actor_id=principal.user_id,
            ip=ip,
            before=before,
            after=after,
        )
    db.commit()
    return user


def seat_extension(settings: Settings, agent_id: str) -> str:
    """The EXTENSION a seat signs in on at TxContact's agent manager (D-133): TXCONTACT_EXTENSION
    with "{seat}" standing for the seat number; empty means the seat number itself."""
    return (settings.txcontact_extension or "{seat}").replace("{seat}", agent_id)


def seat_password(
    db: Session,
    cipher: FieldCipher,
    principal: Principal,
    user_id: uuid.UUID,
    ip: str | None,
    for_line: bool = False,
) -> str:
    """The saved password of a user's phone seat (D-130), for a Super Admin or for the user
    themselves; anyone else is refused. Every reveal is audited, without the password: as shown,
    or (`for_line`) as sent to the user's own page to sign the seat in (D-133)."""
    if not (principal.is_super_admin or principal.user_id == user_id):
        raise forbidden()
    user = db.get(User, user_id)
    if user is None or not user.telephony_password_enc:
        raise not_found("Seat password")
    password = cipher.decrypt(user.telephony_password_enc)
    audit.record(
        db,
        action="user.phone_line_signed_in" if for_line else "user.seat_password_shown",
        entity_type="user",
        entity_id=user.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"telephony_agent_id": user.telephony_agent_id},
    )
    db.commit()
    return password
