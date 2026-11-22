"""Face-to-face recordings: start, chunked upload, interruption, completion, processing, links,
retention and usage (FTF-*, STOR-*, AUDIO-014..024).

Storage keys (STOR-002):
  <project>/face-to-face/YYYY/MM/DD/<task>/original/chunks/<recording>/<seq>.f32
  <project>/face-to-face/YYYY/MM/DD/<task>/original/<recording>.wav
  <project>/face-to-face/YYYY/MM/DD/<task>/derived/<recording>_v<n>.wav
"""

from __future__ import annotations

import hashlib
import logging
import random
import shutil
import tempfile
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm
from app.core.storage import ListedObject, ObjectStorage
from app.modules.audio_qc import service as audio_qc
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, in_projects
from app.modules.exports.models import ExportJob
from app.modules.participants.models import ParticipantDocument
from app.modules.projects.models import Project, ProjectAudioRule, ProjectRetentionRule
from app.modules.recordings import assets, media
from app.modules.recordings.access import get_recording, readable
from app.modules.recordings.models import (
    FTF_DELIVERY_KIND,
    AudioAsset,
    Recording,
    RecordingChunk,
)
from app.modules.tasks import service as tasks
from app.modules.tasks import workflow
from app.modules.tasks.models import Task, TaskStatusHistory

logger = logging.getLogger("app.recordings")


def storage_unavailable() -> AppError:
    """Storage is unreachable or failing: the client keeps the data and tries again (H)."""
    return AppError(
        "File storage is not reachable right now; the upload will be retried",
        code="STORAGE_UNAVAILABLE",
        status_code=503,
        headers={"Retry-After": "5"},
    )


@dataclass(frozen=True)
class StartInput:
    native_sample_rate: int
    channel_count: int  # channels the capture actually delivers; the original keeps all of them
    device_channel_count: int | None  # what the browser reports for the microphone track
    echo_cancellation: bool | None
    noise_suppression: bool | None
    auto_gain_control: bool | None
    device_label: str
    user_agent: str


def start(
    db: Session, principal: Principal, task_id: uuid.UUID, data: StartInput, ip: str | None
) -> Recording:
    task = tasks.get_task(db, principal, task_id)
    if not principal.can_in_project(Perm.RECORDINGS_CREATE, task.project_id):
        raise forbidden()
    tasks.require_moderator(db, principal, task, "Only the assigned moderator records this task")
    if task.recording_mode != "FACE_TO_FACE":
        raise AppError("This is not a face-to-face task", code="MODE_NOT_ALLOWED", status_code=422)
    if task.status != "IN_PROGRESS":
        raise AppError(
            "Start the task before recording", code="TASK_NOT_IN_PROGRESS", status_code=409
        )
    rate = required_rate(db, task.project_id)
    if data.native_sample_rate != rate:
        # The delivery file is the recording itself, never converted (D-123).
        raise AppError(
            f"Record at {rate} Hz: use the latest Chrome or Edge.",
            code="SAMPLE_RATE_NOT_ALLOWED",
            status_code=422,
        )
    tasks.require_consent(db, task)
    open_one = open_recording(db, task.id)
    if open_one is not None:
        raise _recording_open(open_one.id)
    rec = Recording(
        id=uuid.uuid4(),
        task_id=task.id,
        mode="FACE_TO_FACE",
        state="RECORDING",
        created_by=principal.user_id,
        started_at=datetime.now(UTC),
        channel_handling=media.channel_handling(data.channel_count),
        **data.__dict__,
    )
    db.add(rec)
    try:
        db.flush()
    except IntegrityError:
        # Two starts at the same moment (a double click): both passed the check above, and the
        # database lets only one in (uq_recordings_one_open_per_task). The other is told, not 500.
        db.rollback()
        winner = open_recording(db, task_id)
        raise _recording_open(winner.id if winner is not None else None) from None
    audit.record(
        db,
        action="recording.started",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={
            "task": task.task_code,
            "rate": data.native_sample_rate,
            "channels": data.channel_count,
            "device_channels": data.device_channel_count,
            "echo_cancellation": data.echo_cancellation,
            "noise_suppression": data.noise_suppression,
            "auto_gain_control": data.auto_gain_control,
        },
    )
    db.commit()
    return rec


OPEN_STATES = ("RECORDING", "INTERRUPTED")


def open_recording(db: Session, task_id: uuid.UUID) -> Recording | None:
    """The task's unfinished recording (at most one, uq_recordings_one_open_per_task)."""
    return db.scalar(
        select(Recording).where(Recording.task_id == task_id, Recording.state.in_(OPEN_STATES))
    )


def _recording_open(recording_id: uuid.UUID | None) -> AppError:
    return AppError(
        "This task already has an unfinished recording; finish or discard it first",
        code="RECORDING_OPEN",
        status_code=409,
        details=[{"recording_id": str(recording_id)}] if recording_id is not None else None,
    )


def required_rate(db: Session, project_id: uuid.UUID) -> int:
    """The sample rate a face-to-face recording of this project is made at: the project's audio
    rule for face-to-face (16 kHz unless the project says otherwise)."""
    rate = db.scalar(
        select(ProjectAudioRule.sample_rate).where(
            ProjectAudioRule.project_id == project_id, ProjectAudioRule.mode == "FACE_TO_FACE"
        )
    )
    return rate or media.TARGET_RATE


def _owned_open(
    db: Session,
    principal: Principal,
    recording_id: uuid.UUID,
    states: tuple[str, ...],
    *,
    or_task_moderator: bool = False,
) -> tuple[Recording, Task]:
    """The recording, for the moderator who started it. With `or_task_moderator`, also for the
    task's moderator now: after a reassignment (On hold, then another moderator) the new one
    stops, keeps or discards the recording left open, or the task stays stuck (TASK-03). Parts are
    uploaded only by the browser that started it."""
    rec, task = get_recording(db, principal, recording_id)
    if rec.created_by != principal.user_id and not (
        or_task_moderator and tasks.is_moderator(db, principal, task)
    ):
        if or_task_moderator:
            raise forbidden("Only the task's moderator can change this recording")
        raise forbidden("Only the moderator who started this recording can change it")
    _require_state(rec, states)
    return rec, task


def _require_state(rec: Recording, states: tuple[str, ...]) -> None:
    if rec.state not in states:
        raise AppError(
            f"The recording is {rec.state.lower()}", code="RECORDING_CLOSED", status_code=409
        )


def put_chunk(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    principal: Principal,
    recording_id: uuid.UUID,
    seq: int,
    data: bytes,
    claimed_sha256: str,
) -> RecordingChunk:
    rec, task = _owned_open(db, principal, recording_id, ("RECORDING",))
    frame_bytes = 4 * rec.channel_count  # one float32 sample per channel
    if not data or len(data) > settings.max_chunk_bytes or len(data) % frame_bytes:
        raise AppError(
            f"Chunk must be whole frames ({rec.channel_count} float32 samples each) within the "
            "size limit",
            code="INVALID_CHUNK",
            status_code=422,
        )
    actual = hashlib.sha256(data).hexdigest()
    if actual != claimed_sha256.lower():
        raise AppError(
            "Chunk checksum does not match; send it again",
            code="CHECKSUM_MISMATCH",
            status_code=422,
        )
    if not media.all_finite(data):
        # A browser never sends these; they would turn into noise or silence in the delivery file.
        raise AppError(
            "Chunk contains invalid sample values (not a number or infinite)",
            code="INVALID_AUDIO",
            status_code=422,
        )
    # Parts sent at the same moment are taken one after the other: the row is locked and read
    # again, so the length and size checks below see every part stored before this one, and two
    # parts with one number cannot both be written to storage. Held until the commit.
    db.refresh(rec, with_for_update=True)
    _require_state(rec, ("RECORDING",))
    existing = db.scalar(
        select(RecordingChunk).where(
            RecordingChunk.recording_id == rec.id, RecordingChunk.seq == seq
        )
    )
    if existing is not None:
        if existing.sha256 == actual:
            return existing  # a retried upload of the same chunk is harmless (STOR-004)
        raise AppError(
            "A different chunk with this number was already stored",
            code="CHUNK_CONFLICT",
            status_code=409,
        )
    frames = rec.frames_received + len(data) // frame_bytes
    if frames / rec.native_sample_rate > settings.max_recording_seconds:
        raise AppError(
            "Recording is longer than the allowed maximum", code="TOO_LONG", status_code=422
        )
    if frames * frame_bytes > settings.max_recording_bytes:
        raise AppError(
            "Recording is larger than the allowed maximum", code="TOO_LARGE", status_code=422
        )
    project = db.get_one(Project, task.project_id)
    key = f"{assets.storage_prefix(project, task, rec.started_at)}/original/chunks/{rec.id}/"
    key += f"{seq:06d}.f32"
    try:
        storage.put_bytes(key, data, content_type="application/octet-stream", sha256=actual)
    except (BotoCoreError, ClientError):
        db.rollback()
        logger.warning("chunk_storage_failed", extra={"recording_id": str(rec.id), "seq": seq})
        raise storage_unavailable() from None
    chunk = RecordingChunk(
        recording_id=rec.id, seq=seq, size_bytes=len(data), sha256=actual, storage_key=key
    )
    db.add(chunk)
    rec.chunks_received += 1
    rec.frames_received += len(data) // frame_bytes
    db.commit()
    return chunk


def mark_interrupted(
    db: Session, principal: Principal, recording_id: uuid.UUID, reason: str, ip: str | None
) -> Recording:
    rec, task = _owned_open(db, principal, recording_id, ("RECORDING",), or_task_moderator=True)
    rec.state = "INTERRUPTED"
    rec.interrupted = True
    rec.interruption_reason = reason
    audit.record(
        db,
        action="recording.interrupted",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={"reason": reason, "chunks_saved": rec.chunks_received},
    )
    db.commit()
    return rec


def complete(
    db: Session, principal: Principal, recording_id: uuid.UUID, chunk_count: int, ip: str | None
) -> Recording:
    rec, task = _owned_open(db, principal, recording_id, OPEN_STATES, or_task_moderator=True)
    stored = set(
        db.scalars(select(RecordingChunk.seq).where(RecordingChunk.recording_id == rec.id)).all()
    )
    expected = chunk_count if rec.state == "RECORDING" else len(stored)
    missing = sorted(set(range(expected)) - stored)
    if expected == 0 or missing:
        raise AppError(
            "Some parts of the recording have not arrived yet",
            code="MISSING_CHUNKS",
            status_code=409,
            details=[{"missing": missing[:100]}],
        )
    if rec.state == "INTERRUPTED" and stored != set(range(expected)):
        raise AppError("Saved parts are not continuous", code="MISSING_CHUNKS", status_code=409)
    rec.state = "UPLOADED"
    rec.ended_at = datetime.now(UTC)
    audit.record(
        db,
        action="recording.completed",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={"chunks": expected, "interrupted": rec.interrupted},
    )
    db.commit()
    return rec


def discard(
    db: Session,
    storage: ObjectStorage,
    principal: Principal,
    recording_id: uuid.UUID,
    reason: str,
    ip: str | None,
) -> Recording:
    rec, task = _owned_open(db, principal, recording_id, OPEN_STATES, or_task_moderator=True)
    for chunk in db.scalars(
        select(RecordingChunk).where(RecordingChunk.recording_id == rec.id)
    ).all():
        try:
            storage.delete(chunk.storage_key)
        except (BotoCoreError, ClientError):
            db.rollback()
            raise storage_unavailable() from None
        chunk.object_deleted = True
    rec.state = "DISCARDED"
    rec.ended_at = datetime.now(UTC)
    audit.record(
        db,
        action="recording.discarded",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={"reason": reason},
    )
    db.commit()
    return rec


def _store_original(
    db: Session,
    storage: ObjectStorage,
    rec: Recording,
    project: Project,
    base: str,
    chunks: Sequence[RecordingChunk],
    path: Path,
) -> AudioAsset:
    """The browser original: the WAV header, then the stored parts in order. One copy on disk,
    never the whole file in memory (O3)."""
    total = sum(chunk.size_bytes for chunk in chunks)
    frame_bytes = 4 * rec.channel_count
    if total % frame_bytes:
        raise RuntimeError("stored parts are not whole frames")
    with path.open("wb") as handle:
        handle.write(
            media.float_wav_header(total // frame_bytes, rec.native_sample_rate, rec.channel_count)
        )
        for chunk in chunks:
            if storage.append_to(chunk.storage_key, handle) != chunk.size_bytes:
                raise RuntimeError(f"chunk {chunk.seq} size changed in storage")
    original = assets.wav_asset(
        rec, project, "BROWSER_ORIGINAL", 1, f"{base}/original/{rec.id}.wav", path, None
    )
    expected = ("pcm_f32le", rec.native_sample_rate, rec.channel_count)
    actual = (original.codec, original.sample_rate, original.channels)
    if actual != expected:
        raise RuntimeError(f"original file is {actual}, expected {expected}")
    if original.duration_ms != round(rec.frames_received * 1000 / rec.native_sample_rate):
        raise RuntimeError("original file length does not match the frames received")
    assets.store_asset(
        db,
        storage,
        original,
        path,
        assets.Step(
            "ccp chunk assembly",
            "1",
            f"{len(chunks)} float32 chunks joined in order, WAV header; "
            f"{rec.channel_count} channel(s) interleaved as captured",
        ),
        label="original",
    )
    db.flush()
    return original


def process(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    recording_id: uuid.UUID,
    *,
    again: bool = False,
) -> Recording:
    """Build the original and the derived 16 kHz file, validate both, mark the task recorded.

    The recording is claimed with one conditional UPDATE, so two processes (a re-delivered job, the
    recovery sweep, a second web worker) never work on it at once; a PROCESSING recording older than
    PROCESSING_STALE_MINUTES was abandoned by a stopped process and may be claimed again (H). A
    READY recording is processed again only when asked (`again`): a job sent twice, or sent again
    by the sweep while it waited in the queue, finds it done and changes nothing (TASK-02).

    Both files are on record (committed) before any uploaded part is removed, and the parts go
    last, best effort: a storage or database failure can never lose a finished recording
    (TASK-01). Parts left behind are removed by `storage-orphans` once the recording is READY.
    """
    if db.get(Recording, recording_id) is None:
        raise not_found("Recording")
    stale = datetime.now(UTC) - timedelta(minutes=settings.processing_stale_minutes)
    claimable = ("UPLOADED", "FAILED", "READY") if again else ("UPLOADED", "FAILED")
    claimed = (
        db.execute(
            update(Recording)
            .where(
                Recording.id == recording_id,
                or_(
                    Recording.state.in_(claimable),
                    and_(Recording.state == "PROCESSING", Recording.updated_at < stale),
                ),
            )
            .values(state="PROCESSING", updated_at=func.now())
            .returning(Recording.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        is not None
    )
    db.commit()
    rec = db.get_one(Recording, recording_id)
    db.refresh(rec)
    if not claimed:
        logger.info("processing_already_claimed", extra={"recording_id": str(recording_id)})
        if not again and rec.state == "READY" and _task_left_behind(db, rec):
            # The process that saved it stopped before the task moved (a worker stopped by a
            # deploy, whose job is then delivered again): only that step is done now.
            task_recorded(db, db.get_one(Task, rec.task_id), "Face-to-face recording ready")
        return rec
    task = db.get_one(Task, rec.task_id)
    project = db.get_one(Project, task.project_id)
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    base = assets.storage_prefix(project, task, rec.started_at)
    try:
        with tempfile.TemporaryDirectory(dir=work) as tmp:
            original, derived = Path(tmp) / "original.wav", Path(tmp) / "derived.wav"
            chunks = db.scalars(
                select(RecordingChunk)
                .where(RecordingChunk.recording_id == rec.id)
                .order_by(RecordingChunk.seq)
            ).all()
            original_asset = db.scalar(
                select(AudioAsset).where(
                    AudioAsset.recording_id == rec.id, AudioAsset.kind == "BROWSER_ORIGINAL"
                )
            )
            if original_asset is None:
                original_asset = _store_original(db, storage, rec, project, base, chunks, original)
            else:
                storage.get_to_file(original_asset.storage_key, original)
                if media.sha256_file(original) != original_asset.sha256:
                    raise RuntimeError("stored original no longer matches its checksum")
            info = media.inspect_wav(original)
            media.pcm16_delivery(
                original,
                rec.native_sample_rate,
                derived,
                info.channels,
                offset=info.data_offset,
                length=info.data_bytes,
            )
            version = assets.next_version(db, rec.id, FTF_DELIVERY_KIND)
            derived_asset = assets.wav_asset(
                rec,
                project,
                FTF_DELIVERY_KIND,
                version,
                f"{base}/derived/{rec.id}_v{version}.wav",
                derived,
                original_asset,
            )
            if (derived_asset.codec, derived_asset.sample_rate, derived_asset.channels) != (
                "pcm_s16le",
                rec.native_sample_rate,
                1,
            ):
                raise RuntimeError("delivery file is not the recording as 16-bit mono")
            assets.store_asset(
                db,
                storage,
                derived_asset,
                derived,
                assets.Step(
                    *media.DELIVERY_TOOL,
                    media.delivery_parameters(info.channels, rec.native_sample_rate),
                    original_asset.sha256,
                ),
                label="derived",
            )
        # Saved first: both files are on record before anything uploaded is removed (TASK-01).
        rec.state = "READY"
        rec.failure_reason = None
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("recording_processing_failed", extra={"recording_id": str(recording_id)})
        rec = db.get_one(Recording, recording_id)
        rec.state = "FAILED"
        rec.failure_reason = type(exc).__name__
        db.commit()
        raise
    if not again:
        task_recorded(db, task, "Face-to-face recording ready")
    db.refresh(task)  # the status as it is now
    if task.status == "RECORDED":
        try:
            audio_qc.run_automatic(db, rec.id)
        except Exception:
            # The recording itself is safe; the recovery sweep runs the check again (D-079).
            db.rollback()
            logger.exception("automatic_audio_qc_failed", extra={"recording_id": str(rec.id)})
    _remove_parts(db, storage, rec)
    return rec


def task_recorded(db: Session, task: Task, comment: str) -> None:
    """A new recording of the task is ready (face to face, or a phone call's). A task in progress
    moves to Recorded. A task put on hold while the recording was being made resumes at Recorded,
    not In progress, so the finished conversation is not recorded again (TASK-04). Any other
    status is left as it is; the recording is kept either way.

    The task's row is locked while it is looked at (FOR NO KEY UPDATE, as tasks.transition does),
    so a hold or a cancel at the same moment is seen; a move the workflow refuses meanwhile
    changes nothing (TASK-05), instead of failing the job and having it run again."""
    tasks.lock_task(db, task)
    if task.status == "IN_PROGRESS":
        try:
            tasks.system_transition(db, task, "RECORDED", comment=comment)
        except AppError:
            db.rollback()
            db.refresh(task)
        return
    if task.status == "ON_HOLD" and task.held_from == "IN_PROGRESS":
        task.held_from = "RECORDED"
        audit.record(
            db,
            action="task.held_from_changed",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            actor_id=None,
            before={"held_from": "IN_PROGRESS"},
            after={
                "held_from": "RECORDED",
                "comment": f"{comment} while the task was on hold: it resumes at Recorded",
            },
        )
    db.commit()


def _task_left_behind(db: Session, rec: Recording) -> bool:
    """The task's status has not changed since this READY recording was being made: the move it
    calls for did not happen. Both times are the database's: the recording's last change (made
    READY) and the task's status history. A Record again, a hold or the move itself came later
    and says no."""
    moved = db.scalar(
        select(
            exists().where(
                TaskStatusHistory.task_id == rec.task_id,
                TaskStatusHistory.created_at > rec.updated_at,
            )
        )
    )
    return not moved


def _remove_parts(db: Session, storage: ObjectStorage, rec: Recording) -> None:
    """Removes the uploaded parts of a recording whose files are saved: best effort, last. When
    storage fails, the rest stay (harmless) for `storage-orphans`, which removes the parts of a
    READY recording; the recording is never touched here."""
    parts = db.scalars(
        select(RecordingChunk)
        .where(RecordingChunk.recording_id == rec.id, RecordingChunk.object_deleted.is_(False))
        .order_by(RecordingChunk.seq)
    ).all()
    removed = 0
    try:
        for part in parts:
            storage.delete(part.storage_key)
            part.object_deleted = True
            removed += 1
    except (BotoCoreError, ClientError):
        logger.warning(
            "chunk_cleanup_failed",
            extra={"recording_id": str(rec.id), "removed": removed, "left": len(parts) - removed},
        )
    db.commit()


@dataclass(frozen=True)
class AssetProblem:
    asset_id: uuid.UUID
    storage_key: str
    problem: str


def verify_assets(
    db: Session, storage: ObjectStorage, *, deep: int = 0, work_dir: Path | None = None
) -> tuple[int, list[AssetProblem]]:
    """Every live file is in storage with its size and SHA-256 label; `deep` of them, chosen at
    random, are downloaded and hashed again (O4). Returns (files checked, problems found)."""
    assets = db.scalars(select(AudioAsset).where(AudioAsset.deleted_at.is_(None))).all()
    problems: list[AssetProblem] = []
    intact: list[AudioAsset] = []
    for a in assets:
        info = storage.head(a.storage_key)
        if info is None:
            problems.append(AssetProblem(a.id, a.storage_key, "missing from storage"))
        elif info.size != a.size_bytes:
            problems.append(
                AssetProblem(a.id, a.storage_key, f"size {info.size}, expected {a.size_bytes}")
            )
        elif info.sha256 != a.sha256:
            problems.append(
                AssetProblem(a.id, a.storage_key, "checksum label differs from the record")
            )
        else:
            intact.append(a)
    for a in random.sample(intact, min(deep, len(intact))):
        with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
            path = Path(tmp) / "check.bin"
            storage.get_to_file(a.storage_key, path)
            if media.sha256_file(path) != a.sha256:
                problems.append(
                    AssetProblem(a.id, a.storage_key, "content does not match its checksum")
                )
    return len(assets), problems


def storage_orphans(
    db: Session, storage: ObjectStorage, older_than: timedelta, now: datetime | None = None
) -> list[ListedObject]:
    """Objects no record points to (left by a process that stopped between upload and save),
    older than `older_than` so nothing still being written is touched (O12). Backups are kept,
    and so are participants' documents, replaced ones too, until the participant is removed
    (D-144), and export bundles while they can be downloaded (READY jobs keep their key; an
    expired or failed one has none). An uploaded part counts only until its recording is READY:
    then its files are saved and a part left behind by processing is no longer needed (TASK-01)."""
    now = now or datetime.now(UTC)
    known = set(db.scalars(select(AudioAsset.storage_key).where(AudioAsset.deleted_at.is_(None))))
    known |= set(
        db.scalars(
            select(RecordingChunk.storage_key)
            .join(Recording, Recording.id == RecordingChunk.recording_id)
            .where(RecordingChunk.object_deleted.is_(False), Recording.state != "READY")
        )
    )
    known |= set(
        db.scalars(
            select(ParticipantDocument.storage_key).where(ParticipantDocument.removed_at.is_(None))
        )
    )
    known |= {
        key
        for key in db.scalars(
            select(ExportJob.storage_key).where(ExportJob.storage_key.is_not(None))
        )
        if key
    }
    cutoff = now - older_than
    return [
        o
        for o in storage.list_objects()
        if o.key not in known and o.modified < cutoff and not o.key.startswith("backups/")
    ]


def clean_work_dir(settings: Settings, now: float | None = None) -> int:
    """Remove scratch folders a stopped process left in MEDIA_WORK_DIR (O12). Anything younger
    than twice PROCESSING_STALE_MINUTES may still be in use and is left alone."""
    work = Path(settings.media_work_dir)
    if not work.is_dir():
        return 0
    cutoff = (now or time.time()) - 2 * 60 * settings.processing_stale_minutes
    removed = 0
    for entry in work.iterdir():
        if entry.stat().st_mtime < cutoff:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
    return removed


def stalled_recordings(
    db: Session, settings: Settings, now: datetime | None = None
) -> list[uuid.UUID]:
    """Recordings whose processing never started or was abandoned by a stopped process (H)."""
    now = now or datetime.now(UTC)
    pickup = now - timedelta(seconds=settings.processing_pickup_seconds)
    stale = now - timedelta(minutes=settings.processing_stale_minutes)
    return list(
        db.scalars(
            select(Recording.id)
            .where(
                or_(
                    and_(Recording.state == "UPLOADED", Recording.updated_at < pickup),
                    and_(Recording.state == "PROCESSING", Recording.updated_at < stale),
                )
            )
            .order_by(Recording.updated_at)
        ).all()
    )


def assets_for(
    db: Session, principal: Principal, recording_id: uuid.UUID
) -> tuple[Recording, list[AudioAsset]]:
    rec, task = readable(db, principal, recording_id)
    items = db.scalars(
        select(AudioAsset)
        .where(AudioAsset.recording_id == rec.id, AudioAsset.deleted_at.is_(None))
        .order_by(AudioAsset.kind, AudioAsset.version)
    ).all()
    if not principal.can_in_project(Perm.RECORDINGS_VIEW, task.project_id):
        raise forbidden()
    return rec, list(items)


def asset_url(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    principal: Principal,
    asset_id: uuid.UUID,
    purpose: str,
    ip: str | None,
) -> tuple[str, int]:
    asset = db.get(AudioAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise not_found("File")
    # Task visibility first: assigned people and project managers only. Client Viewers receive final
    # files through exports (Phase 9), not through recording links. A replaced recording's files
    # only for those who see replaced recordings (D-135).
    readable(db, principal, asset.recording_id, "File")
    needed = Perm.RECORDINGS_DOWNLOAD if purpose == "download" else Perm.RECORDINGS_VIEW
    if not principal.can_in_project(needed, asset.project_id):
        raise forbidden()
    seconds = settings.signed_url_seconds
    # The file's own extension: a provider original may be an MP3, not a WAV.
    extension = asset.file_extension or "wav"
    name = f"{asset.kind.lower()}_{asset.id}.{extension}" if purpose == "download" else None
    url = storage.signed_get_url(asset.storage_key, seconds=seconds, download_name=name)
    audit.record(
        db,
        action=f"asset.{purpose}_link",
        entity_type="audio_asset",
        entity_id=asset.id,
        project_id=asset.project_id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return url, seconds


def apply_retention(
    db: Session, storage: ObjectStorage, now: datetime | None = None, *, limit: int | None = None
) -> int:
    """Delete stored files older than their project's retention rule (STOR-009), and only files
    of closed tasks (approved, rejected or cancelled): a file that QC, an approval or a delivery
    may still need is kept, whatever the rule says (PROJ-01). Each file on its own: the object,
    `deleted_at`, the audit entry, one commit; so a stop half-way leaves at most the file being
    deleted still on record, and the next run finishes it. Two runs at once never take the same
    file. At most `limit` files (every one when None), oldest first. Returns how many."""
    now = now or datetime.now(UTC)
    deleted = 0
    rules = db.execute(
        select(
            ProjectRetentionRule.project_id,
            ProjectRetentionRule.asset_kind,
            ProjectRetentionRule.retain_days,
        ).order_by(ProjectRetentionRule.project_id, ProjectRetentionRule.asset_kind)
    ).all()
    for project_id, kind, retain_days in rules:
        if limit is not None and deleted >= limit:
            break
        cutoff = now - timedelta(days=retain_days)
        expired = select(AudioAsset.id).where(
            AudioAsset.project_id == project_id,
            AudioAsset.kind == kind,
            AudioAsset.deleted_at.is_(None),
            AudioAsset.created_at < cutoff,
            AudioAsset.recording_id.in_(
                select(Recording.id)
                .join(Task, Task.id == Recording.task_id)
                .where(Task.status.in_(workflow.TERMINAL))
            ),
        )
        expired = expired.order_by(AudioAsset.created_at)
        if limit is not None:
            expired = expired.limit(limit - deleted)
        for asset_id in db.scalars(expired).all():
            asset = db.scalar(
                select(AudioAsset)
                .where(AudioAsset.id == asset_id, AudioAsset.deleted_at.is_(None))
                .with_for_update(skip_locked=True, key_share=True)
            )
            if asset is None:  # deleted meanwhile by another run
                db.rollback()
                continue
            try:
                storage.delete(asset.storage_key)
            except (BotoCoreError, ClientError):
                db.rollback()
                raise
            asset.deleted_at = now
            audit.record(
                db,
                action="asset.deleted_by_retention",
                entity_type="audio_asset",
                entity_id=asset.id,
                project_id=asset.project_id,
                actor_id=None,
                after={"kind": asset.kind, "retain_days": retain_days},
            )
            db.commit()
            deleted += 1
    db.commit()
    return deleted


def usage(db: Session, principal: Principal) -> list[tuple[str, str, int, int]]:
    """(project code, asset kind, files, bytes) for the projects the caller manages (STOR-010).

    Project-wide storage figures are administration data: Super Admin sees every project, a Project
    Admin their own; other roles' dashboards cover their own work only (matrix, D-049)."""
    if not (principal.can(Perm.DASHBOARD_VIEW) and principal.can(Perm.PROJECTS_MANAGE)):
        raise forbidden()
    query = (
        select(
            Project.code,
            AudioAsset.kind,
            func.count(),
            func.coalesce(func.sum(AudioAsset.size_bytes), 0),
        )
        .join(Project, Project.id == AudioAsset.project_id)
        .where(AudioAsset.deleted_at.is_(None))
        .group_by(Project.code, AudioAsset.kind)
        .order_by(Project.code, AudioAsset.kind)
    )
    query = query.where(in_projects(principal, AudioAsset.project_id))
    return [(code, kind, int(n), int(size)) for code, kind, n, size in db.execute(query).all()]
