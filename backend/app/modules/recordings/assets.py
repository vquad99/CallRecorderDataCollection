"""Audio files kept in storage (STOR-002, AUDIO-017, O4): where they go, the record of each file,
and how a file is stored. Used by face-to-face processing and by phone recordings alike.

Storage keys: <project>/<face-to-face|telephony>/YYYY/MM/DD/<task>/...
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.storage import ObjectStorage
from app.modules.projects.models import Project
from app.modules.recordings import media
from app.modules.recordings.models import AssetProcessingStep, AudioAsset, Recording
from app.modules.tasks.models import Task

_FOLDERS = {"FACE_TO_FACE": "face-to-face", "TELEPHONY": "telephony"}


def storage_prefix(project: Project, task: Task, when: datetime) -> str:
    """Where a task's files go: by project, recording mode, day and task."""
    return f"{project.code}/{_FOLDERS[task.recording_mode]}/{when:%Y/%m/%d}/{task.id}"


def next_version(db: Session, recording_id: uuid.UUID, kind: str) -> int:
    current = db.scalar(
        select(func.max(AudioAsset.version)).where(
            AudioAsset.recording_id == recording_id, AudioAsset.kind == kind
        )
    )
    return (current or 0) + 1


def wav_asset(
    rec: Recording,
    project: Project,
    kind: str,
    version: int,
    key: str,
    path: Path,
    parent: AudioAsset | None,
) -> AudioAsset:
    """The record of a WAV file, with what was measured from the file itself."""
    info = media.inspect_wav(path)
    levels = media.measure(path)
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
        dynamic_range_db=levels.dynamic_range_db,
        content_fingerprint=levels.content_fingerprint,
    )


@dataclass(frozen=True)
class Step:
    """How a file was made, kept with it (AUDIO-017)."""

    tool: str
    tool_version: str
    parameters: str
    input_sha256: str | None = None


def store_asset(
    db: Session,
    storage: ObjectStorage,
    asset: AudioAsset,
    path: Path,
    step: Step,
    *,
    label: str,
    content_type: str = "audio/wav",
) -> None:
    """Puts the file into storage, checks that it arrived intact, and adds its record and the
    step that made it to the session (flushed, not committed)."""
    storage.put_file(asset.storage_key, path, content_type=content_type, sha256=asset.sha256)
    stored = storage.head(asset.storage_key)
    if stored is None or (stored.size, stored.sha256) != (asset.size_bytes, asset.sha256):
        raise RuntimeError(f"{label} file did not arrive intact in storage")
    db.add(asset)
    db.flush()
    db.add(
        AssetProcessingStep(
            asset_id=asset.id,
            seq=1,
            tool=step.tool,
            tool_version=step.tool_version,
            parameters=step.parameters,
            input_sha256=step.input_sha256,
            output_sha256=asset.sha256,
        )
    )
