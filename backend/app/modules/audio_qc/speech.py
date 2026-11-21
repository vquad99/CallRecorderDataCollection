"""Effective speech for files made before it was measured (D-148): the backfill.

A file made since D-148 is measured when it is made (recordings/assets.wav_asset). Final files
made before have no effective speech; the recovery sweep (recordings/worker_dispatch.recover)
measures a few of them each time it runs, and `python -m app.cli backfill-effective-speech`
measures them all at once. Each file is claimed with a row lock that other processes skip, read
from storage, checked against its SHA-256 and measured by the same code as a new file
(media.measure). A file that cannot be measured (gone from storage, changed, unreadable) gets the
reason in `speech_error` and is not tried again; a storage that cannot be reached stops the run,
and the next sweep tries again.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.storage import ObjectStorage
from app.modules.recordings import media
from app.modules.recordings.assets import speech_columns
from app.modules.recordings.models import FINAL_KINDS, AudioAsset

logger = logging.getLogger("app.audio_qc")

# Files measured per recovery sweep (each web process sweeps every RECOVERY_INTERVAL_SECONDS).
SWEEP_BATCH = 3


@dataclass
class Backfill:
    measured: int = 0
    failed: int = 0

    @property
    def done(self) -> int:
        return self.measured + self.failed


def _still_missing() -> tuple[ColumnElement[bool], ...]:
    return (
        AudioAsset.kind.in_(FINAL_KINDS),
        AudioAsset.effective_ms.is_(None),
        AudioAsset.speech_error.is_(None),
        AudioAsset.deleted_at.is_(None),
    )


def missing_count(db: Session) -> int:
    """Final files still without effective speech (and not known to be unmeasurable)."""
    return int(db.scalar(select(func.count()).where(*_still_missing())) or 0)


def _measure(storage: ObjectStorage, asset: AudioAsset, work: Path) -> media.Speech | str:
    """The file's effective speech, or why it cannot be measured. Storage errors are raised."""
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        copy = Path(tmp) / "final.wav"
        if storage.head(asset.storage_key) is None:
            return "The file is not in storage"
        storage.get_to_file(asset.storage_key, copy)
        if media.sha256_file(copy) != asset.sha256:
            return "The stored file does not match its SHA-256"
        try:
            levels = media.measure(copy)
        except (ValueError, OSError) as exc:
            return (f"The file could not be read: {exc}" if str(exc) else "Unreadable")[:200]
    if levels.speech is None:
        return "Levels are not measured for this file"
    return levels.speech


def measure_next(db: Session, storage: ObjectStorage, settings: Settings) -> bool | None:
    """Measures the oldest final file still without effective speech. True: measured; False:
    could not be (the reason is kept); None: nothing left. Raises when storage is unreachable."""
    asset = db.scalar(
        select(AudioAsset)
        .where(*_still_missing())
        .order_by(AudioAsset.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if asset is None:
        db.rollback()
        return None
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    try:
        found = _measure(storage, asset, work)
    except Exception:
        db.rollback()
        raise
    if isinstance(found, str):
        asset.speech_error = found
        logger.warning(
            "effective_speech_not_measured", extra={"asset_id": str(asset.id), "reason": found}
        )
    else:
        for name, value in speech_columns(found).items():
            setattr(asset, name, value)
    db.commit()
    return not isinstance(found, str)


def backfill(
    db: Session, storage: ObjectStorage, settings: Settings, limit: int | None
) -> Backfill:
    """Measures up to `limit` files (all of them when None), oldest first."""
    result = Backfill()
    while limit is None or result.done < limit:
        try:
            outcome = measure_next(db, storage, settings)
        except (BotoCoreError, ClientError):
            logger.exception("effective_speech_storage_unavailable")
            break
        if outcome is None:
            break
        if outcome:
            result.measured += 1
        else:
            result.failed += 1
    return result
