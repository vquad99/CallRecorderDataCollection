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
   the task to Recorded; the automatic audio check runs as for face-to-face recordings.

Every step is written to call_events (the call's history) and every person's action to the audit
log. If the platform cannot tell which provider call is this one, a person picks it; nothing is
guessed. Whatever goes wrong while fetching, the call ends up either waiting for its next try or
shown to a person with the reason (D-103); it can always be cancelled.

Storage keys (STOR-002):
  <project>/telephony/YYYY/MM/DD/<task>/provider-original/<recording>.<ext>
  <project>/telephony/YYYY/MM/DD/<task>/final/<recording>_v<n>.wav
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.telephony import ProviderError, ProviderSession, TelephonyProvider
from app.adapters.txcontact import UnsupportedNumber, digits, file_name
from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm
from app.core.storage import ObjectStorage
from app.modules.audio_qc import service as audio_qc
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.auth.security import FieldCipher
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from app.modules.recordings import media
from app.modules.recordings import service as recordings
from app.modules.recordings.models import AssetProcessingStep, AudioAsset, Recording
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

DELIVERY_KIND = "TELEPHONY_DERIVED_PCM"
ORIGINAL_KIND = "PROVIDER_ORIGINAL_MIXED"
# A provider call counts as this one when it started between dialling and closing, with this much
# slack on either side for clocks that differ.
TIME_SLACK = timedelta(minutes=2)
# After a redial on the same seat the earlier attempt is that close in time: the window then opens
# only this long before dialling, so a dropped first attempt is not taken for this call.
REDIAL_SLACK = timedelta(seconds=10)
# Held while one process works on a call, so a second process leaves it alone. Long enough for a
# slow download; the last step checks again that nobody else finished or cancelled the call.
LEASE = timedelta(minutes=30)
# A task put on hold keeps its closed call waiting; the call is looked at again this often.
HOLD_RECHECK = timedelta(minutes=5)
MAX_DOWNLOAD_ATTEMPTS = 5
MIN_SEARCHES = 3
MAX_CALLS_LISTED = 20
MAX_EVENTS_LISTED = 200
_CONTENT_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg"}
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


def not_found() -> AppError:
    return AppError("Call not found", code="NOT_FOUND", status_code=404)


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


def _candidate(s: ProviderSession) -> Candidate:
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


def _event(
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


def _phone(cipher: FieldCipher, participant: Participant) -> str:
    if not participant.phone_e164_enc:
        raise AppError("Participant A has no phone number", code="PHONE_MISSING", status_code=409)
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


def _consent_sides(db: Session, task: Task, status: str) -> list[str]:
    """Which of A and B have this as their latest consent answer for the session."""
    consent = tasks.latest_consent(db, task)
    return [
        side
        for side, pid in (("A", task.participant_a_id), ("B", task.participant_b_id))
        if consent.get(pid) is not None and consent[pid].status == status
    ]


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
    moderator = tasks.active_assignee(db, task.id, "MODERATOR")
    if moderator is None or moderator.user_id != principal.user_id:
        raise AppError(
            "Only the assigned moderator calls for this task", code="FORBIDDEN", status_code=403
        )
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
    refused = _consent_sides(db, task, "REFUSED")
    if refused:
        # Someone who said no to this session is not rung again. A wrong tick is put right in
        # the consent box first.
        raise AppError(
            f"Participant {' and '.join(refused)} refused consent for this session and is not "
            "called again",
            code="CONSENT_REFUSED",
            status_code=409,
        )
    a = db.get(Participant, task.participant_a_id)
    assert a is not None  # noqa: S101  (foreign key)
    phone = _phone(cipher, a)
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
    _event(
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
            _event(db, call, "DIAL_ACCEPTED", f"{provider.name} answered {answer}")
        else:
            _dial_failed(db, call, "PROVIDER_REFUSED", f"{provider.name} answered {answer}")
    db.commit()
    return call


def _dial_failed(db: Session, call: Call, code: str, detail: str) -> None:
    call.state = "DIAL_FAILED"
    call.failure_code = code
    call.failure_detail = detail
    call.closed_at = datetime.now(UTC)
    _event(db, call, "DIAL_FAILED", detail)


def _call_for_change(db: Session, principal: Principal, call_id: uuid.UUID) -> tuple[Call, Task]:
    call = db.get(Call, call_id)
    if call is None:
        raise not_found()
    try:
        task = tasks.get_task(db, principal, call.task_id)
    except AppError:
        raise not_found() from None
    if not principal.can_in_project(Perm.CALLS_END, task.project_id):
        raise forbidden()
    # The moderator who made the call, the moderator the task is with now (after a reassignment
    # the new one takes the call over), or someone who assigns tasks in the project.
    assigned = tasks.active_assignee(db, task.id, "MODERATOR")
    own = call.moderator_id == principal.user_id or (
        assigned is not None and assigned.user_id == principal.user_id
    )
    manager = principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id)
    if not (own or manager):
        raise AppError(
            "Only the task's moderator, or a project admin, can change this call",
            code="FORBIDDEN",
            status_code=403,
        )
    return call, task


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
        _event(db, call, "CHECKLIST", f"Confirmed: {CHECKLIST_LABELS[item]}", principal.user_id)
    else:
        del ticked[item]
        _event(db, call, "CHECKLIST", f"Taken back: {CHECKLIST_LABELS[item]}", principal.user_id)
    call.checklist = json.dumps(ticked)
    _audit(db, call, "call.checklist", principal, ip, {"item": item, "done": done})
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
    given = _consent_sides(db, task, "GIVEN")
    missing = [side for side in ("A", "B") if side not in given]
    if missing:
        raise AppError(
            f"Record consent for participant {' and '.join(missing)} before closing the call. "
            "If consent was refused, cancel the call instead.",
            code="CONSENT_MISSING",
            status_code=409,
        )
    now = datetime.now(UTC)
    call.state = "WAITING_FOR_RECORDING"
    call.closed_at = now
    call.note = note.strip()
    call.next_fetch_at = now + timedelta(seconds=settings.telephony_first_look_seconds)
    call.fetch_attempts = 0
    _event(
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
    _require_state(call, "DIALLING", "WAITING_FOR_RECORDING", "NEEDS_MATCH", "FETCH_FAILED")
    if reason not in CANCEL_REASONS:
        raise AppError(
            f"Choose a reason: {', '.join(CANCEL_REASONS)}", code="REASON_REQUIRED", status_code=422
        )
    if reason == "OTHER" and not note.strip():
        raise AppError("Explain the reason in the note", code="COMMENT_REQUIRED", status_code=422)
    _cancel(db, call, reason, note.strip(), principal.user_id)
    _audit(db, call, "call.cancelled", principal, ip, {"reason": reason})
    db.commit()
    return call


def _cancel(db: Session, call: Call, reason: str, note: str, actor_id: uuid.UUID | None) -> None:
    call.state = "CANCELLED"
    call.cancel_reason = reason
    call.note = note
    call.closed_at = call.closed_at or datetime.now(UTC)
    call.next_fetch_at = None
    _event(
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
    _event(
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
    _event(db, call, "RETRY_REQUESTED", "Asked to look for the recording again", principal.user_id)
    _audit(db, call, "call.retry", principal, ip)
    db.commit()
    return call


def set_agent_seat(
    db: Session, principal: Principal, user_id: uuid.UUID, agent_id: str | None, ip: str | None
) -> User:
    if not principal.can(Perm.USERS_MANAGE):
        raise forbidden()
    user = db.get(User, user_id)
    if user is None:
        raise AppError("User not found", code="NOT_FOUND", status_code=404)
    value = (agent_id or "").strip() or None
    if value is not None:
        taken = db.scalar(
            select(User.id).where(User.telephony_agent_id == value, User.id != user.id)
        )
        if taken is not None:
            raise AppError(
                "Another user already has this agent seat", code="AGENT_SEAT_TAKEN", status_code=409
            )
    before = user.telephony_agent_id
    user.telephony_agent_id = value
    if before != value:
        audit.record(
            db,
            action="user.agent_seat",
            entity_type="user",
            entity_id=user.id,
            actor_id=principal.user_id,
            ip=ip,
            before={"telephony_agent_id": before},
            after={"telephony_agent_id": value},
        )
    db.commit()
    return user


# ---------------------------------------------------------------------------- the platform's work


class _Superseded(Exception):
    """While a recording was being stored, the call was finished or cancelled by someone else."""


def due_calls(db: Session, now: datetime | None = None, limit: int = 50) -> list[uuid.UUID]:
    now = now or datetime.now(UTC)
    return list(
        db.scalars(
            select(Call.id)
            .where(Call.state == "WAITING_FOR_RECORDING", Call.next_fetch_at <= now)
            .order_by(Call.next_fetch_at)
            .limit(limit)
        ).all()
    )


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(300, 30 * 2 ** max(0, attempts - 1)))


@dataclass(frozen=True)
class MatchResult:
    confirmed: list[ProviderSession]  # right time, right agent, A's number on it
    loose: list[ProviderSession]  # right time and agent, number not confirmed


def match(
    sessions: list[ProviderSession],
    call: Call,
    phone_e164: str,
    taken: set[str],
    *,
    redial: bool = False,
) -> MatchResult:
    """Pure: which of the provider's calls can be this one. `redial`: another call went out on
    the same seat just before this one, so the window opens only REDIAL_SLACK before dialling."""
    national = digits(phone_e164)[-10:]
    start_from = call.dialled_at - (REDIAL_SLACK if redial else TIME_SLACK)
    start_to = (call.closed_at or call.dialled_at) + TIME_SLACK
    seen: set[str] = set()
    confirmed: list[ProviderSession] = []
    loose: list[ProviderSession] = []
    for s in sessions:
        if not s.session_id or s.session_id in seen or s.session_id in taken:
            continue
        seen.add(s.session_id)
        if not s.rec_filename or s.start is None or not start_from <= s.start <= start_to:
            continue
        if s.agent_id and s.agent_id != call.agent_id:
            continue
        ends = (digits(s.from_number), digits(s.to_number))
        if national and any(e.endswith(national) for e in ends if e):
            confirmed.append(s)
        else:
            loose.append(s)
    return MatchResult(confirmed, loose)


def _claim(db: Session, call_id: uuid.UUID) -> Call | None:
    now = datetime.now(UTC)
    claimed = db.execute(
        update(Call)
        .where(
            Call.id == call_id,
            Call.state == "WAITING_FOR_RECORDING",
            and_(Call.next_fetch_at.is_not(None), Call.next_fetch_at <= now),
        )
        .values(next_fetch_at=now + LEASE, fetch_attempts=Call.fetch_attempts + 1)
        .returning(Call.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()
    if claimed is None:
        return None
    call = db.get(Call, call_id)
    if call is not None:
        db.refresh(call)
    return call


def fetch(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    provider: TelephonyProvider,
    cipher: FieldCipher,
    call_id: uuid.UUID,
) -> Call | None:
    """One step for a call waiting for its recording: search, then download and store.

    Whatever goes wrong, the call ends the step either waiting for its next try or shown to a
    person with the reason; it is never left claimed and silent.
    """
    claimed = _claim(db, call_id)
    if claimed is None:
        return None
    try:
        return _fetch_claimed(db, settings, storage, provider, cipher, claimed)
    except Exception as exc:
        db.rollback()
        logger.exception("telephony_fetch_crashed", extra={"call_id": str(call_id)})
        call = db.get(Call, call_id)
        if call is not None:
            db.refresh(call)
        if call is not None and call.state == "WAITING_FOR_RECORDING":
            detail = f"Unexpected problem ({type(exc).__name__})"
            _event(db, call, "FETCH_ERROR", detail)
            _fail_or_retry(db, call, datetime.now(UTC), "UNEXPECTED_ERROR", detail)
        return call


def _fetch_claimed(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    provider: TelephonyProvider,
    cipher: FieldCipher,
    call: Call,
) -> Call:
    call_id = call.id
    task = db.get(Task, call.task_id)
    a = db.get(Participant, task.participant_a_id) if task else None
    assert task is not None  # noqa: S101  (foreign key)
    assert a is not None  # noqa: S101  (foreign key)
    db.refresh(task)  # the status as it is now, not as this session last saw it
    now = datetime.now(UTC)
    if task.status == "ON_HOLD":
        # The task is paused, not over: the call waits with it and this look does not count.
        call.next_fetch_at = now + HOLD_RECHECK
        call.fetch_attempts = max(0, call.fetch_attempts - 1)
        db.commit()
        return call
    if task.status != "IN_PROGRESS":
        # The task moved on without this call (cancelled, re-assigned, or recorded by a later
        # call): its recording is not fetched into a session that is over.
        _cancel(
            db,
            call,
            "OTHER",
            f"The task had moved to {task.status.lower().replace('_', ' ')} before this "
            "call's recording arrived",
            None,
        )
        db.commit()
        return call
    session: ProviderSession | None = None
    if call.provider_session_id is None:
        if call.fetch_attempts == 1:
            _event(db, call, "SEARCHING", "Looking for the call's recording at the provider")
        try:
            session = _search(db, settings, provider, cipher, call, a, now)
        except ProviderError as exc:
            _event(db, call, "SEARCH_ERROR", str(exc))
            if _search_window_over(settings, call, now):
                # The provider could not be searched for the whole window (for example a wrong
                # recording login): a person is told, instead of trying for ever.
                _needs_match(
                    db,
                    call,
                    [],
                    "SEARCH_FAILED",
                    f"The provider's recordings could not be searched: {exc}. Look again once "
                    "this is fixed, or cancel the call",
                )
            else:
                call.next_fetch_at = now + _backoff(call.fetch_attempts)
            db.commit()
            return call
        db.commit()  # the match (or the next look) is kept even if the download fails
        if session is None:
            return call
    else:
        try:
            session = _known_session(settings, provider, call)
        except ProviderError as exc:
            _event(db, call, "FETCH_ERROR", str(exc))
            _fail_or_retry(db, call, now, "PROVIDER_UNREACHABLE", str(exc))
            return call
        if session is None:
            _event(db, call, "FETCH_ERROR", "The chosen call is no longer listed by the provider")
            _fail_or_retry(db, call, now, "SESSION_GONE", "The chosen call was not found")
            return call
    try:
        _store_recording(db, settings, storage, provider, call, task, session)
    except _Superseded:
        db.rollback()
        logger.info("telephony_fetch_superseded", extra={"call_id": str(call_id)})
        current = db.get(Call, call_id)
        assert current is not None  # noqa: S101
        db.refresh(current)
        return current
    except Exception as exc:
        db.rollback()
        logger.exception("telephony_fetch_failed", extra={"call_id": str(call_id)})
        again = db.get(Call, call_id)
        assert again is not None  # noqa: S101
        db.refresh(again)
        if again.state != "WAITING_FOR_RECORDING":
            return again  # cancelled meanwhile: nothing more to say
        if isinstance(exc, ValueError):
            # The file arrived but is not audio this platform can read: trying again will not
            # change that, so a person is told at once.
            detail = str(exc)[:500]
            _event(db, again, "FETCH_ERROR", detail)
            _fail(db, again, "UNREADABLE_AUDIO", detail)
            return again
        # The provider's messages are written for people; anything else (storage, database) is
        # named by its kind only.
        detail = (
            str(exc)[:500]
            if isinstance(exc, ProviderError)
            else f"The recording could not be stored ({type(exc).__name__})"
        )
        _event(db, again, "FETCH_ERROR", detail)
        _fail_or_retry(db, again, datetime.now(UTC), "DOWNLOAD_FAILED", detail)
        return again
    db.refresh(task)
    if task.status == "IN_PROGRESS":
        tasks.system_transition(db, task, "RECORDED", comment="Phone call recording ready")
    if task.status == "RECORDED" and call.recording_id is not None:
        try:
            audio_qc.run_automatic(db, call.recording_id)
        except Exception:
            # The recording itself is safe; the recovery sweep runs the check again (D-079).
            db.rollback()
            logger.exception("automatic_audio_qc_failed", extra={"call_id": str(call_id)})
    return call


def _search_window_over(settings: Settings, call: Call, now: datetime) -> bool:
    closed = call.closed_at or call.dialled_at
    return (
        now >= closed + timedelta(minutes=settings.telephony_fetch_minutes)
        and call.fetch_attempts >= MIN_SEARCHES
    )


def _fail(db: Session, call: Call, code: str, detail: str) -> None:
    call.state = "FETCH_FAILED"
    call.failure_code = code
    call.failure_detail = detail
    call.next_fetch_at = None
    _event(db, call, "FETCH_FAILED", f"Gave up after {call.fetch_attempts} tries: {detail}")
    db.commit()


def _fail_or_retry(db: Session, call: Call, now: datetime, code: str, detail: str) -> None:
    if call.fetch_attempts >= MAX_DOWNLOAD_ATTEMPTS:
        _fail(db, call, code, detail)
    else:
        call.next_fetch_at = now + _backoff(call.fetch_attempts)
        db.commit()


def _days(provider_tz: str, *moments: datetime) -> list[date]:
    """The provider's calendar days the moments fall on (its search takes one day at a time)."""
    tz = ZoneInfo(provider_tz)
    days: list[date] = []
    for moment in moments:
        day = moment.astimezone(tz).date()
        if day not in days:
            days.append(day)
    return days


def _search(
    db: Session,
    settings: Settings,
    provider: TelephonyProvider,
    cipher: FieldCipher,
    call: Call,
    a: Participant,
    now: datetime,
) -> ProviderSession | None:
    closed = call.closed_at or call.dialled_at
    sessions: list[ProviderSession] = []
    # The slack on both sides counts for the day too: a call just after midnight is looked for
    # under the day before as well.
    for day in _days(
        settings.txcontact_timezone, call.dialled_at - TIME_SLACK, closed + TIME_SLACK
    ):
        sessions += provider.sessions(call.agent_id, day)
    ids = sorted({s.session_id for s in sessions if s.session_id})
    taken = (
        set(
            db.scalars(
                select(Call.provider_session_id).where(
                    Call.provider == call.provider,
                    Call.provider_session_id.in_(ids),
                    Call.id != call.id,
                )
            ).all()
        )
        if ids
        else set()
    )
    redial = (
        db.scalar(
            select(Call.id)
            .where(
                Call.provider == call.provider,
                Call.agent_id == call.agent_id,
                Call.id != call.id,
                Call.dialled_at < call.dialled_at,
                Call.dialled_at >= call.dialled_at - TIME_SLACK,
            )
            .limit(1)
        )
        is not None
    )
    # Without a number for participant A (removed since the call) nothing can be confirmed: the
    # calls at the right time are shown to a person once the window is over.
    phone = cipher.decrypt(a.phone_e164_enc) if a.phone_e164_enc else ""
    result = match(sessions, call, phone, {t for t in taken if t}, redial=redial)
    if len(result.confirmed) == 1:
        s = result.confirmed[0]
        call.provider_session_id = s.session_id
        call.provider_file = s.rec_filename
        call.fetch_attempts = 1
        _event(
            db,
            call,
            "MATCHED",
            f"Found provider call {mask(s.session_id)}, started "
            f"{s.start.isoformat() if s.start else '?'}, file {mask(s.rec_filename)}",
        )
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ProviderError("That recording was just taken by another call") from None
        return s
    if len(result.confirmed) > 1:
        _needs_match(
            db,
            call,
            result.confirmed,
            "SEVERAL_CALLS",
            f"{len(result.confirmed)} provider calls fit this call; choose the right one",
        )
        return None
    if _search_window_over(settings, call, now):
        if result.loose:
            _needs_match(
                db,
                call,
                result.loose,
                "NUMBER_NOT_CONFIRMED",
                "Provider calls at the right time were found, but none shows participant A's "
                "number; choose the right one",
            )
        else:
            _needs_match(
                db,
                call,
                [],
                "RECORDING_NOT_FOUND",
                f"No recording was found within {settings.telephony_fetch_minutes} minutes of "
                "closing the call; look again later or cancel the call",
            )
        return None
    call.next_fetch_at = now + _backoff(call.fetch_attempts)
    return None


def _needs_match(
    db: Session, call: Call, found: list[ProviderSession], code: str, detail: str
) -> None:
    call.state = "NEEDS_MATCH"
    call.candidates = json.dumps([asdict(_candidate(s)) for s in found[:20]])
    call.failure_code = code
    call.failure_detail = detail
    call.next_fetch_at = None
    _event(db, call, "NEEDS_MATCH", detail)


def _known_session(
    settings: Settings, provider: TelephonyProvider, call: Call
) -> ProviderSession | None:
    """The provider call chosen earlier, looked up again for its current file name."""
    closed = call.closed_at or call.dialled_at
    for day in _days(
        settings.txcontact_timezone, call.dialled_at - TIME_SLACK, closed + TIME_SLACK
    ):
        for s in provider.sessions(call.agent_id, day):
            if s.session_id == call.provider_session_id:
                return s
    if call.provider_file:
        # Listed under a day the search did not cover: the file name chosen earlier still works.
        return ProviderSession(
            session_id=call.provider_session_id or "",
            trans_id="",
            from_number="",
            to_number="",
            agent_id=call.agent_id,
            start=None,
            end=None,
            duration="",
            rec_filename=call.provider_file,
            rec_ext="",
            rec_status="",
        )
    return None


def _prefix(project: Project, task: Task, when: datetime) -> str:
    return f"{project.code}/telephony/{when:%Y/%m/%d}/{task.id}"


def _store_recording(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    provider: TelephonyProvider,
    call: Call,
    task: Task,
    session: ProviderSession,
) -> None:
    project = db.get(Project, task.project_id)
    assert project is not None  # noqa: S101
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    name = file_name(session)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "bin"
    ext = ext if ext.isalnum() and len(ext) <= 5 else "bin"
    rec = Recording(
        id=uuid.uuid4(),
        task_id=task.id,
        mode="TELEPHONY",
        state="READY",
        created_by=call.moderator_id,
        native_sample_rate=8000,
        channel_count=1,
        device_channel_count=None,
        channel_handling="",
        device_label=f"{provider.name} call {mask(session.session_id)}"[:300],
        user_agent="",
        started_at=session.start or call.dialled_at,
        ended_at=session.end or call.closed_at,
    )
    base = _prefix(project, task, rec.started_at)
    stored: list[str] = []  # objects put in storage by this attempt, removed if it does not finish
    try:
        with tempfile.TemporaryDirectory(dir=work) as tmp:
            raw = Path(tmp) / f"provider.{ext}"
            decoded = Path(tmp) / "decoded.wav"
            derived = Path(tmp) / "derived.wav"
            size = provider.download(session, raw, settings.telephony_max_download_bytes)
            _event(db, call, "DOWNLOADED", f"Downloaded {mask(name)} ({size} bytes)")
            heard = media.decode_to_float_wav(raw, decoded)
            info = media.inspect_wav(decoded)
            if info.data_bytes == 0:
                raise ValueError("the provider's recording holds no audio")
            rec.native_sample_rate = heard.sample_rate
            rec.channel_count = heard.channels
            rec.channel_handling = (
                "mono" if heard.channels == 1 else f"all {heard.channels} channels kept, not mixed"
            )
            rec.frames_received = info.data_bytes // (4 * heard.channels)
            db.add(rec)
            db.flush()
            levels = media.measure(decoded)
            original = AudioAsset(
                id=uuid.uuid4(),
                recording_id=rec.id,
                project_id=project.id,
                kind=ORIGINAL_KIND,
                version=1,
                parent_asset_id=None,
                storage_key=f"{base}/provider-original/{rec.id}.{ext}",
                file_extension=ext,
                container=heard.container[:20],
                codec=heard.codec[:30],
                sample_format="float" if heard.codec in ("float", "double") else "int",
                sample_rate=heard.sample_rate,
                bit_depth=heard.bit_depth,
                channels=heard.channels,
                duration_ms=info.duration_ms,
                size_bytes=size,
                sha256=media.sha256_file(raw),
                peak_dbfs=levels.peak_dbfs,
                rms_dbfs=levels.rms_dbfs,
                clip_count=levels.clip_count,
                clip_pct=levels.clip_pct,
                silence_pct=levels.silence_pct,
                dynamic_range_db=levels.dynamic_range_db,
                content_fingerprint=levels.content_fingerprint,
            )
            stored.append(original.storage_key)
            storage.put_file(
                original.storage_key,
                raw,
                content_type=_CONTENT_TYPES.get(ext, "application/octet-stream"),
                sha256=original.sha256,
            )
            recordings._check_stored(storage, original, "provider original")
            db.add(original)
            db.flush()
            db.add(
                AssetProcessingStep(
                    asset_id=original.id,
                    seq=1,
                    tool=f"{provider.name} recording download",
                    tool_version="1",
                    parameters=(
                        f"provider call {mask(session.session_id)}, file {mask(name)}; "
                        "bytes kept unchanged"
                    ),
                    input_sha256=None,
                    output_sha256=original.sha256,
                )
            )
            media.resample_keep_channels_to_pcm16(
                decoded,
                heard.sample_rate,
                derived,
                heard.channels,
                offset=info.data_offset,
                length=info.data_bytes,
            )
            final = recordings._asset(
                db, rec, project, DELIVERY_KIND, f"{base}/final/{rec.id}_v1.wav", derived, original
            )
            if (final.codec, final.sample_rate, final.channels) != (
                "pcm_s16le",
                media.TARGET_RATE,
                heard.channels,
            ):
                raise RuntimeError("delivery file does not match the 16 kHz 16-bit target")
            stored.append(final.storage_key)
            storage.put_file(
                final.storage_key, derived, content_type="audio/wav", sha256=final.sha256
            )
            recordings._check_stored(storage, final, "delivery")
            db.add(final)
            db.flush()
            db.add(
                AssetProcessingStep(
                    asset_id=final.id,
                    seq=1,
                    tool="libsndfile decode + python-soxr",
                    tool_version=media.SOXR_VERSION,
                    parameters=(
                        f"{heard.container}/{heard.codec} decoded to float32 at "
                        f"{heard.sample_rate} Hz; {rec.channel_handling}; libsoxr quality=VHQ, "
                        f"{media.TARGET_RATE} Hz, float32 -> int16 round-half-even, clip, no dither"
                    ),
                    input_sha256=original.sha256,
                    output_sha256=final.sha256,
                )
            )
        # Someone may have cancelled the call, or another process finished it, while the file was
        # coming down: the row is locked and looked at once more before anything is made final.
        state_now = db.execute(
            select(Call.state).where(Call.id == call.id).with_for_update()
        ).scalar_one()
        if state_now != "WAITING_FOR_RECORDING":
            raise _Superseded
        call.state = "RECORDED"
        call.recording_id = rec.id
        call.provider_session_id = session.session_id
        call.provider_file = session.rec_filename or call.provider_file
        call.next_fetch_at = None
        call.failure_code = call.failure_detail = None
        _event(
            db,
            call,
            "RECORDED",
            f"Recording stored: {heard.sample_rate} Hz, {heard.channels} channel(s), "
            f"{round(info.duration_ms / 1000)} s; delivery file made at {media.TARGET_RATE} Hz",
        )
        db.commit()
    except Exception:
        # Nothing of an attempt that did not finish stays in storage.
        for key in stored:
            try:
                storage.delete(key)
            except Exception:
                logger.exception("telephony_cleanup_failed", extra={"key": key})
        raise
