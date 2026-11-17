"""The platform's own work on a closed phone call (D-101, D-103, D-113): find the call's recording
among the provider's calls, download it, keep the provider's file unchanged, build the 16 kHz
delivery file (cut to the moderator's recording marks), and move the task to Recorded.

Whatever goes wrong, the call ends each step either waiting for its next try or shown to a person
with the reason; it can always be cancelled. People's actions on calls are in service.py.

Storage keys (STOR-002):
  <project>/telephony/YYYY/MM/DD/<task>/provider-original/<recording>.<ext>
  <project>/telephony/YYYY/MM/DD/<task>/final/<recording>_v<n>.wav
"""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.telephony import ProviderError, ProviderSession, TelephonyProvider
from app.adapters.txcontact import digits, file_name
from app.core.config import Settings
from app.core.storage import ObjectStorage
from app.modules.audio_qc import service as audio_qc
from app.modules.auth.security import FieldCipher
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from app.modules.recordings import assets, media
from app.modules.recordings.models import TELEPHONY_DELIVERY_KIND, AudioAsset, Recording
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task
from app.modules.telephony.models import Call
from app.modules.telephony.service import candidate_from, mark_cancelled, mask, record_event

logger = logging.getLogger("app.telephony")

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
_CONTENT_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg"}


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
            record_event(db, call, "FETCH_ERROR", detail)
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
    task = db.get_one(Task, call.task_id)
    a = db.get_one(Participant, task.participant_a_id)
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
        mark_cancelled(
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
            record_event(db, call, "SEARCHING", "Looking for the call's recording at the provider")
        try:
            session = _search(db, settings, provider, cipher, call, a, now)
        except ProviderError as exc:
            record_event(db, call, "SEARCH_ERROR", str(exc))
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
            record_event(db, call, "FETCH_ERROR", str(exc))
            _fail_or_retry(db, call, now, "PROVIDER_UNREACHABLE", str(exc))
            return call
        if session is None:
            record_event(
                db, call, "FETCH_ERROR", "The chosen call is no longer listed by the provider"
            )
            _fail_or_retry(db, call, now, "SESSION_GONE", "The chosen call was not found")
            return call
    try:
        _store_recording(db, settings, storage, provider, call, task, session)
    except _Superseded:
        db.rollback()
        logger.info("telephony_fetch_superseded", extra={"call_id": str(call_id)})
        current = db.get_one(Call, call_id)
        db.refresh(current)
        return current
    except Exception as exc:
        db.rollback()
        logger.exception("telephony_fetch_failed", extra={"call_id": str(call_id)})
        again = db.get_one(Call, call_id)
        db.refresh(again)
        if again.state != "WAITING_FOR_RECORDING":
            return again  # cancelled meanwhile: nothing more to say
        if isinstance(exc, ValueError):
            # The file arrived but is not audio this platform can read: trying again will not
            # change that, so a person is told at once.
            detail = str(exc)[:500]
            record_event(db, again, "FETCH_ERROR", detail)
            _fail(db, again, "UNREADABLE_AUDIO", detail)
            return again
        # The provider's messages are written for people; anything else (storage, database) is
        # named by its kind only.
        detail = (
            str(exc)[:500]
            if isinstance(exc, ProviderError)
            else f"The recording could not be stored ({type(exc).__name__})"
        )
        record_event(db, again, "FETCH_ERROR", detail)
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
    record_event(db, call, "FETCH_FAILED", f"Gave up after {call.fetch_attempts} tries: {detail}")
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
        record_event(
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
    call.candidates = json.dumps([asdict(candidate_from(s)) for s in found[:20]])
    call.failure_code = code
    call.failure_detail = detail
    call.next_fetch_at = None
    record_event(db, call, "NEEDS_MATCH", detail)


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


@dataclass(frozen=True)
class Window:
    first_frame: int
    last_frame: int
    cut: bool
    description: str


def recording_window(
    call: Call, session: ProviderSession, frames: int, rate: int, margin: float
) -> Window:
    """Pure (D-113): the frames of the provider's file between the moderator's Start and Stop
    recording, with `margin` seconds kept on each side. The provider's file starts at
    `session.start`. When that time is unknown or the marks fall outside the file, the whole
    file is kept and the reason is said."""
    whole = Window(0, frames, False, "whole call kept")
    started, stopped = call.record_started_at, call.record_stopped_at
    if started is None or stopped is None:
        return Window(0, frames, False, "whole call kept (no recording marks)")
    if session.start is None:
        return Window(0, frames, False, "whole call kept: the provider gave no start time")
    first = round(((started - session.start).total_seconds() - margin) * rate)
    last = round(((stopped - session.start).total_seconds() + margin) * rate)
    first, last = max(0, first), min(frames, last)
    if last - first < rate:  # less than a second left: the marks do not fit this file
        return Window(
            0,
            frames,
            False,
            "whole call kept: the recording marks fall outside the provider's file",
        )
    if (first, last) == (0, frames):
        return whole
    return Window(
        first,
        last,
        True,
        f"cut to the moderator's recording marks: {first / rate:.1f} s to {last / rate:.1f} s "
        f"of the provider's {frames / rate:.1f} s (margin {margin:g} s)",
    )


def _store_recording(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    provider: TelephonyProvider,
    call: Call,
    task: Task,
    session: ProviderSession,
) -> None:
    project = db.get_one(Project, task.project_id)
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
    base = assets.storage_prefix(project, task, rec.started_at)
    stored: list[str] = []  # objects put in storage by this attempt, removed if it does not finish
    try:
        with tempfile.TemporaryDirectory(dir=work) as tmp:
            raw = Path(tmp) / f"provider.{ext}"
            decoded = Path(tmp) / "decoded.wav"
            derived = Path(tmp) / "derived.wav"
            size = provider.download(session, raw, settings.telephony_max_download_bytes)
            record_event(db, call, "DOWNLOADED", f"Downloaded {mask(name)} ({size} bytes)")
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
            assets.store_asset(
                db,
                storage,
                original,
                raw,
                assets.Step(
                    f"{provider.name} recording download",
                    "1",
                    f"provider call {mask(session.session_id)}, file {mask(name)}; "
                    "bytes kept unchanged",
                ),
                label="provider original",
                content_type=_CONTENT_TYPES.get(ext, "application/octet-stream"),
            )
            cut = recording_window(
                call,
                session,
                info.data_bytes // (4 * heard.channels),
                heard.sample_rate,
                settings.telephony_mark_margin_seconds,
            )
            frame_bytes = 4 * heard.channels
            media.resample_keep_channels_to_pcm16(
                decoded,
                heard.sample_rate,
                derived,
                heard.channels,
                offset=info.data_offset + cut.first_frame * frame_bytes,
                length=(cut.last_frame - cut.first_frame) * frame_bytes,
            )
            if cut.cut:
                record_event(db, call, "DOWNLOADED", f"Delivery file {cut.description}")
                if session.start:
                    rec.started_at = session.start + timedelta(
                        seconds=cut.first_frame / heard.sample_rate
                    )
            final = assets.wav_asset(
                rec,
                project,
                TELEPHONY_DELIVERY_KIND,
                1,
                f"{base}/final/{rec.id}_v1.wav",
                derived,
                original,
            )
            if (final.codec, final.sample_rate, final.channels) != (
                "pcm_s16le",
                media.TARGET_RATE,
                heard.channels,
            ):
                raise RuntimeError("delivery file does not match the 16 kHz 16-bit target")
            stored.append(final.storage_key)
            assets.store_asset(
                db,
                storage,
                final,
                derived,
                assets.Step(
                    "libsndfile decode + python-soxr",
                    media.SOXR_VERSION,
                    f"{heard.container}/{heard.codec} decoded to float32 at "
                    f"{heard.sample_rate} Hz; {cut.description}; "
                    f"{rec.channel_handling}; libsoxr quality=VHQ, "
                    f"{media.TARGET_RATE} Hz, float32 -> int16 round-half-even, clip, no dither",
                    original.sha256,
                ),
                label="delivery",
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
        record_event(
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
