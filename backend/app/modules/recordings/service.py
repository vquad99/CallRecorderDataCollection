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
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm
from app.core.storage import ObjectStorage
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.projects.models import Project, ProjectRetentionRule
from app.modules.recordings import media
from app.modules.recordings.models import AssetProcessingStep, AudioAsset, Recording, RecordingChunk
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task

logger = logging.getLogger("app.recordings")


def not_found() -> AppError:
    return AppError("Recording not found", code="NOT_FOUND", status_code=404)


def _prefix(project: Project, task: Task, when: datetime) -> str:
    return f"{project.code}/face-to-face/{when:%Y/%m/%d}/{task.id}"


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
    moderator = tasks.active_assignee(db, task.id, "MODERATOR")
    if moderator is None or moderator.user_id != principal.user_id:
        raise AppError(
            "Only the assigned moderator records this task", code="FORBIDDEN", status_code=403
        )
    if task.recording_mode != "FACE_TO_FACE":
        raise AppError("This is not a face-to-face task", code="MODE_NOT_ALLOWED", status_code=422)
    if task.status != "IN_PROGRESS":
        raise AppError(
            "Start the task before recording", code="TASK_NOT_IN_PROGRESS", status_code=409
        )
    open_one = db.scalar(
        select(Recording).where(
            Recording.task_id == task.id, Recording.state.in_(("RECORDING", "INTERRUPTED"))
        )
    )
    if open_one is not None:
        raise AppError(
            "This task already has an unfinished recording; finish or discard it first",
            code="RECORDING_OPEN",
            status_code=409,
            details=[{"recording_id": str(open_one.id)}],
        )
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


def get_recording(
    db: Session, principal: Principal, recording_id: uuid.UUID
) -> tuple[Recording, Task]:
    rec = db.get(Recording, recording_id)
    if rec is None:
        raise not_found()
    try:
        task = tasks.get_task(db, principal, rec.task_id)
    except AppError:
        raise not_found() from None
    return rec, task


def _owned_open(
    db: Session, principal: Principal, recording_id: uuid.UUID, states: tuple[str, ...]
) -> tuple[Recording, Task]:
    rec, task = get_recording(db, principal, recording_id)
    if rec.created_by != principal.user_id:
        raise AppError(
            "Only the moderator who started this recording can change it",
            code="FORBIDDEN",
            status_code=403,
        )
    if rec.state not in states:
        raise AppError(
            f"The recording is {rec.state.lower()}", code="RECORDING_CLOSED", status_code=409
        )
    return rec, task


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
    seconds = (rec.frames_received + len(data) // frame_bytes) / rec.native_sample_rate
    if seconds > settings.max_recording_seconds:
        raise AppError(
            "Recording is longer than the allowed maximum", code="TOO_LONG", status_code=422
        )
    project = db.get(Project, task.project_id)
    assert project is not None  # noqa: S101
    key = f"{_prefix(project, task, rec.started_at)}/original/chunks/{rec.id}/{seq:06d}.f32"
    storage.put_bytes(key, data, content_type="application/octet-stream", sha256=actual)
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
    rec, task = _owned_open(db, principal, recording_id, ("RECORDING",))
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
    rec, task = _owned_open(db, principal, recording_id, ("RECORDING", "INTERRUPTED"))
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
    rec, task = _owned_open(db, principal, recording_id, ("RECORDING", "INTERRUPTED"))
    for chunk in db.scalars(
        select(RecordingChunk).where(RecordingChunk.recording_id == rec.id)
    ).all():
        storage.delete(chunk.storage_key)
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


def _asset(
    db: Session,
    rec: Recording,
    project: Project,
    kind: str,
    key: str,
    path: Path,
    parent: AudioAsset | None,
) -> AudioAsset:
    info = media.inspect_wav(path)
    levels = media.measure(path)
    version = (
        db.scalar(
            select(func.max(AudioAsset.version)).where(
                AudioAsset.recording_id == rec.id, AudioAsset.kind == kind
            )
        )
        or 0
    ) + 1
    return AudioAsset(
        id=uuid.uuid4(),
        recording_id=rec.id,
        project_id=project.id,
        kind=kind,
        version=version,
        parent_asset_id=parent.id if parent else None,
        storage_key=key,
        file_extension="wav",
        container=info.container,
        codec=info.codec,
        sample_format=info.sample_format,
        sample_rate=info.sample_rate,
        bit_depth=info.bit_depth,
        channels=info.channels,
        duration_ms=info.duration_ms,
        size_bytes=info.size_bytes,
        sha256=media.sha256_file(path),
        peak_dbfs=levels.peak_dbfs,
        rms_dbfs=levels.rms_dbfs,
        clip_count=levels.clip_count,
        clip_pct=levels.clip_pct,
        silence_pct=levels.silence_pct,
    )


def process(
    db: Session, settings: Settings, storage: ObjectStorage, recording_id: uuid.UUID
) -> Recording:
    """Build the original and the derived 16 kHz file, validate both, mark the task recorded."""
    rec = db.get(Recording, recording_id)
    if rec is None or rec.state not in ("UPLOADED", "READY", "FAILED"):
        raise not_found()
    task = db.get(Task, rec.task_id)
    project = db.get(Project, task.project_id) if task else None
    assert task is not None  # noqa: S101
    assert project is not None  # noqa: S101
    rec.state = "PROCESSING"
    db.commit()
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=work) as tmp:
            raw, original, derived = (
                Path(tmp) / "raw.f32",
                Path(tmp) / "original.wav",
                Path(tmp) / "derived.wav",
            )
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
                with raw.open("wb") as handle:
                    for chunk in chunks:
                        if storage.append_to(chunk.storage_key, handle) != chunk.size_bytes:
                            raise RuntimeError(f"chunk {chunk.seq} size changed in storage")
                media.write_float_wav(raw, original, rec.native_sample_rate, rec.channel_count)
                base = _prefix(project, task, rec.started_at)
                original_asset = _asset(
                    db,
                    rec,
                    project,
                    "BROWSER_ORIGINAL",
                    f"{base}/original/{rec.id}.wav",
                    original,
                    None,
                )
                expected = ("pcm_f32le", rec.native_sample_rate, rec.channel_count)
                actual = (
                    original_asset.codec,
                    original_asset.sample_rate,
                    original_asset.channels,
                )
                if actual != expected:
                    raise RuntimeError(f"original file is {actual}, expected {expected}")
                if original_asset.duration_ms != round(
                    rec.frames_received * 1000 / rec.native_sample_rate
                ):
                    raise RuntimeError("original file length does not match the frames received")
                storage.put_file(
                    original_asset.storage_key,
                    original,
                    content_type="audio/wav",
                    sha256=original_asset.sha256,
                )
                stored = storage.head(original_asset.storage_key)
                if stored is None or stored.size != original_asset.size_bytes:
                    raise RuntimeError("original file did not arrive intact in storage")
                db.add(original_asset)
                db.flush()
                db.add(
                    AssetProcessingStep(
                        asset_id=original_asset.id,
                        seq=1,
                        tool="ccp chunk assembly",
                        tool_version="1",
                        parameters=(
                            f"{len(chunks)} float32 chunks joined in order, WAV header; "
                            f"{rec.channel_count} channel(s) interleaved as captured"
                        ),
                        input_sha256=None,
                        output_sha256=original_asset.sha256,
                    )
                )
                db.flush()
            else:
                storage.get_to_file(original_asset.storage_key, original)
                if media.sha256_file(original) != original_asset.sha256:
                    raise RuntimeError("stored original no longer matches its checksum")
                with original.open("rb") as src, raw.open("wb") as dst:
                    info = media.inspect_wav(original)
                    src.seek(info.data_offset)
                    dst.write(src.read(info.data_bytes))
            channels = original_asset.channels
            media.resample_to_pcm16(raw, rec.native_sample_rate, derived, channels)
            base = _prefix(project, task, rec.started_at)
            version = (
                db.scalar(
                    select(func.max(AudioAsset.version)).where(
                        AudioAsset.recording_id == rec.id, AudioAsset.kind == "FTF_DERIVED_PCM"
                    )
                )
                or 0
            ) + 1
            derived_asset = _asset(
                db,
                rec,
                project,
                "FTF_DERIVED_PCM",
                f"{base}/derived/{rec.id}_v{version}.wav",
                derived,
                original_asset,
            )
            if (derived_asset.codec, derived_asset.sample_rate, derived_asset.channels) != (
                "pcm_s16le",
                16000,
                1,
            ):
                raise RuntimeError("derived file does not match the 16 kHz mono 16-bit target")
            storage.put_file(
                derived_asset.storage_key,
                derived,
                content_type="audio/wav",
                sha256=derived_asset.sha256,
            )
            db.add(derived_asset)
            db.flush()
            db.add(
                AssetProcessingStep(
                    asset_id=derived_asset.id,
                    seq=1,
                    tool="python-soxr",
                    tool_version=media.SOXR_VERSION,
                    parameters=media.conversion_parameters(channels),
                    input_sha256=original_asset.sha256,
                    output_sha256=derived_asset.sha256,
                )
            )
        for chunk in chunks:
            if not chunk.object_deleted:
                storage.delete(chunk.storage_key)
                chunk.object_deleted = True
        rec.state = "READY"
        rec.failure_reason = None
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("recording_processing_failed", extra={"recording_id": str(recording_id)})
        rec = db.get(Recording, recording_id)
        assert rec is not None  # noqa: S101
        rec.state = "FAILED"
        rec.failure_reason = type(exc).__name__
        db.commit()
        raise
    task = db.get(Task, rec.task_id)
    if task is not None and task.status == "IN_PROGRESS":
        tasks.system_transition(db, task, "RECORDED", comment="Face-to-face recording ready")
    return rec


def assets_for(
    db: Session, principal: Principal, recording_id: uuid.UUID
) -> tuple[Recording, list[AudioAsset]]:
    rec, task = get_recording(db, principal, recording_id)
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
        raise AppError("File not found", code="NOT_FOUND", status_code=404)
    rec = db.get(Recording, asset.recording_id)
    assert rec is not None  # noqa: S101
    # Task visibility first: assigned people and project managers only. Client Viewers receive final
    # files through exports (Phase 9), not through recording links.
    get_recording(db, principal, rec.id)
    needed = Perm.RECORDINGS_DOWNLOAD if purpose == "download" else Perm.RECORDINGS_VIEW
    if not principal.can_in_project(needed, asset.project_id):
        raise forbidden()
    seconds = settings.signed_url_seconds
    name = f"{asset.kind.lower()}_{asset.id}.wav" if purpose == "download" else None
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


def apply_retention(db: Session, storage: ObjectStorage, now: datetime | None = None) -> int:
    """Delete assets older than their project's retention rule (STOR-009). Returns the count."""
    now = now or datetime.now(UTC)
    deleted = 0
    for rule in db.scalars(select(ProjectRetentionRule)).all():
        cutoff = now - timedelta(days=rule.retain_days)
        expired = db.scalars(
            select(AudioAsset).where(
                AudioAsset.project_id == rule.project_id,
                AudioAsset.kind == rule.asset_kind,
                AudioAsset.deleted_at.is_(None),
                AudioAsset.created_at < cutoff,
            )
        ).all()
        for asset in expired:
            storage.delete(asset.storage_key)
            asset.deleted_at = now
            audit.record(
                db,
                action="asset.deleted_by_retention",
                entity_type="audio_asset",
                entity_id=asset.id,
                project_id=asset.project_id,
                actor_id=None,
                after={"kind": asset.kind, "retain_days": rule.retain_days},
            )
            deleted += 1
    db.commit()
    return deleted


def usage(db: Session, principal: Principal) -> list[tuple[str, str, int, int]]:
    """(project code, asset kind, files, bytes) for live assets the caller may see (STOR-010)."""
    if not principal.can(Perm.DASHBOARD_VIEW):
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
    if not principal.is_super_admin:
        query = query.where(
            AudioAsset.project_id.in_(list(principal.project_ids) or [uuid.UUID(int=0)])
        )
    return [(code, kind, int(n), int(size)) for code, kind, n, size in db.execute(query).all()]
