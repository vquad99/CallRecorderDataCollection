"""Audio quality check (AQC-001..010, D-079).

Read-only (AQC-009): the automatic check reads the measurements taken when the delivery file was
made, and a re-check reads a downloaded copy; neither ever changes the audio.

Limits come from the project's audio rule for the recording mode (AQC-001): sample rate, bit depth,
channels, length, silence and clipping. Where the project sets no limit, the value is shown and
nothing is judged; no universal "good audio" limit is invented. Outcome: FAIL when any check fails,
NEEDS_REVIEW when any check needs a person's ear, otherwise PASS. The automatic result never
approves or rejects anything: the QC Executive assigned to the task decides (PASS, FAIL, RETURN).
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm, Role
from app.core.storage import ObjectStorage
from app.modules.audio_qc.models import AudioQcCheck, AudioQcResult
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.participants.models import ConsentRecord, Participant
from app.modules.projects.models import Project, ProjectAudioRule, ProjectMembership
from app.modules.recordings import media
from app.modules.recordings.models import AssetProcessingStep, AudioAsset, Recording
from app.modules.tasks import service as tasks
from app.modules.tasks import workflow
from app.modules.tasks.models import Task, TaskAssignment

logger = logging.getLogger("app.audio_qc")

DELIVERY_KIND = "FTF_DERIVED_PCM"
# Statuses in which a QC Executive may be (re)assigned: anything still open.
QC_ASSIGNABLE = frozenset(
    {"DRAFT", "ASSIGNED", "IN_PROGRESS", "RECORDED", "AUDIO_QC", "ON_HOLD", "RETURNED"}
)
DECISIONS = {"PASS": "APPROVED", "FAIL": "REJECTED", "RETURN": "RETURNED"}
# Content comparison needs enough sound to be meaningful: a short or mostly silent file has a level
# pattern many unrelated files share.
FINGERPRINT_MIN_MS = 5000
FINGERPRINT_MAX_SILENCE_PCT = 90.0
# Left and right count as the same sound when they correlate this closely (a mono mix copied into
# both channels gives 1.0; two people on separate channels stay far below).
IDENTICAL_CHANNELS = 0.999


@dataclass(frozen=True)
class Measured:
    container: str
    codec: str
    sample_rate: int
    bit_depth: int
    channels: int
    duration_ms: int
    size_bytes: int
    sha256: str
    peak_dbfs: float | None
    rms_dbfs: float | None
    clip_pct: float
    silence_pct: float
    dynamic_range_db: float | None
    content_fingerprint: str | None
    channel_correlation: float | None = None
    levels_measured: bool = True


@dataclass(frozen=True)
class Limits:
    sample_rate: int
    bit_depth: int
    channels: int
    max_silence_pct: float
    max_clipping_pct: float | None
    min_duration_seconds: int
    max_duration_seconds: int | None


@dataclass(frozen=True)
class Duplicate:
    exact: bool
    recording_id: uuid.UUID


@dataclass(frozen=True)
class Check:
    code: str
    state: str  # PASS, FAIL, REVIEW, INFO, NOT_APPLICABLE
    measured: str = ""
    expected: str = ""
    message: str = ""
    reason: str | None = None  # reason code the result carries when this check decides it


def not_found() -> AppError:
    return AppError("Task not found", code="NOT_FOUND", status_code=404)


def limits_of(rule: ProjectAudioRule) -> Limits:
    return Limits(
        sample_rate=rule.sample_rate,
        bit_depth=rule.bit_depth,
        channels=rule.channels,
        max_silence_pct=float(rule.max_silence_pct),
        max_clipping_pct=None if rule.max_clipping_pct is None else float(rule.max_clipping_pct),
        min_duration_seconds=rule.min_duration_seconds,
        max_duration_seconds=rule.max_duration_seconds,
    )


def from_asset(asset: AudioAsset) -> Measured:
    """The measurements taken from these exact bytes when the file was made."""
    return Measured(
        container=asset.container,
        codec=asset.codec,
        sample_rate=asset.sample_rate,
        bit_depth=asset.bit_depth,
        channels=asset.channels,
        duration_ms=asset.duration_ms,
        size_bytes=asset.size_bytes,
        sha256=asset.sha256,
        peak_dbfs=asset.peak_dbfs,
        rms_dbfs=asset.rms_dbfs,
        clip_pct=asset.clip_pct,
        silence_pct=asset.silence_pct,
        dynamic_range_db=asset.dynamic_range_db,
        content_fingerprint=asset.content_fingerprint,
    )


def _channel_correlation(path: Path, info: media.WavInfo) -> float | None:
    """Correlation of the first two channels over the whole file (AQC-005 indicator)."""
    if info.channels < 2 or info.codec not in ("pcm_s16le", "pcm_f32le"):
        return None
    dtype = "<i2" if info.codec == "pcm_s16le" else "<f4"
    count = info.data_bytes // np.dtype(dtype).itemsize
    data = np.memmap(path, dtype=dtype, mode="r", offset=info.data_offset, shape=(count,))
    frames = data[: count - count % info.channels].reshape(-1, info.channels)
    sums = np.zeros(5)  # sum l, sum r, sum ll, sum rr, sum lr
    for start in range(0, len(frames), media.BLOCK):
        block = np.asarray(frames[start : start + media.BLOCK, :2], dtype=np.float64)
        left, right = block[:, 0], block[:, 1]
        sums += (
            left.sum(),
            right.sum(),
            (left * left).sum(),
            (right * right).sum(),
            (left * right).sum(),
        )
    n = len(frames)
    del data, frames
    if n == 0:
        return None
    mean_l, mean_r = sums[0] / n, sums[1] / n
    var_l = sums[2] / n - mean_l * mean_l
    var_r = sums[3] / n - mean_r * mean_r
    if var_l <= 0 or var_r <= 0:
        return None
    return round(float((sums[4] / n - mean_l * mean_r) / np.sqrt(var_l * var_r)), 4)


def analyze_file(path: Path) -> tuple[Measured | None, str | None]:
    """(measurements, None) or (None, decode error). Reads the file only (AQC-006, AQC-009)."""
    if not path.exists():
        return None, None
    if path.stat().st_size == 0:
        return None, "The file is empty"
    try:
        info = media.inspect_wav(path)
        measurable = info.codec in media.MEASURABLE_CODECS
        levels = media.measure(path) if measurable else media.Levels(None, None, 0, 0.0, 0.0)
        correlation = _channel_correlation(path, info)
    except (ValueError, OSError) as exc:
        return None, str(exc) or type(exc).__name__
    return (
        Measured(
            container=info.container,
            codec=info.codec,
            sample_rate=info.sample_rate,
            bit_depth=info.bit_depth,
            channels=info.channels,
            duration_ms=info.duration_ms,
            size_bytes=info.size_bytes,
            sha256=media.sha256_file(path),
            peak_dbfs=levels.peak_dbfs,
            rms_dbfs=levels.rms_dbfs,
            clip_pct=levels.clip_pct,
            silence_pct=levels.silence_pct,
            dynamic_range_db=levels.dynamic_range_db,
            content_fingerprint=levels.content_fingerprint,
            channel_correlation=correlation,
            levels_measured=measurable,
        ),
        None,
    )


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.1f} s"


def evaluate(
    measured: Measured | None,
    limits: Limits | None,
    *,
    decode_error: str | None = None,
    duplicate: Duplicate | None = None,
    expected_sha256: str | None = None,
) -> list[Check]:
    """Every check, in a fixed order. Pure: the same inputs always give the same list."""
    if decode_error is not None:
        return [
            Check(
                "DECODES",
                "FAIL",
                decode_error,
                "A readable WAV file",
                "The file could not be read",
                "DECODE_ERROR",
            )
        ]
    if measured is None:
        return [
            Check(
                "AUDIO_PRESENT",
                "FAIL",
                "No file",
                "The delivery file",
                "There is no audio file for this recording",
                "MISSING_AUDIO",
            )
        ]
    m = measured
    out = [
        Check(
            "DECODES",
            "PASS",
            "Read to the end",
            "A readable WAV file",
            "The whole file was read without errors",
        )
    ]
    if expected_sha256 is not None and m.sha256 != expected_sha256:
        out.append(
            Check(
                "CHECKSUM",
                "FAIL",
                m.sha256[:16],
                expected_sha256[:16],
                "The stored file changed after it was made",
                "CHECKSUM_MISMATCH",
            )
        )
    else:
        out.append(
            Check(
                "CHECKSUM",
                "PASS",
                m.sha256[:16],
                "Recorded SHA-256",
                "Fingerprint of the file recorded; the stored copy matched it",
            )
        )
    uncompressed = m.container == "wav" and m.codec.startswith("pcm_")
    out.append(
        Check(
            "FORMAT",
            "PASS" if uncompressed else "FAIL",
            f"{m.container.upper()} {m.codec}",
            "WAV, uncompressed PCM",
            "" if uncompressed else "Not an uncompressed WAV file",
            None if uncompressed else "WRONG_FORMAT",
        )
    )
    bytes_per_frame = max(1, m.channels * m.bit_depth // 8)
    data_ms = (m.size_bytes - 44) / bytes_per_frame / m.sample_rate * 1000 if m.sample_rate else 0
    if m.duration_ms <= 0:
        out.append(
            Check(
                "FILE_SIZE",
                "FAIL",
                f"{m.size_bytes} bytes",
                "Some audio",
                "The file holds no audio",
                "EMPTY_FILE",
            )
        )
    elif abs(data_ms - m.duration_ms) > 50:
        out.append(
            Check(
                "FILE_SIZE",
                "FAIL",
                f"{m.size_bytes} bytes",
                "Size fits the length",
                "The file size does not match its length",
                "FILE_SIZE_MISMATCH",
            )
        )
    else:
        out.append(Check("FILE_SIZE", "PASS", f"{m.size_bytes:,} bytes", "Size fits the length"))
    if limits is None:
        out.append(
            Check(
                "PROJECT_RULE",
                "REVIEW",
                "None",
                "The project's audio rule",
                "This project has no audio rule for this recording type",
                "NO_RULE",
            )
        )
    else:
        for code, have, want, reason in (
            ("SAMPLE_RATE", m.sample_rate, limits.sample_rate, "WRONG_SAMPLE_RATE"),
            ("BIT_DEPTH", m.bit_depth, limits.bit_depth, "WRONG_BIT_DEPTH"),
        ):
            unit = " Hz" if code == "SAMPLE_RATE" else "-bit"
            out.append(
                Check(
                    code,
                    "PASS" if have == want else "FAIL",
                    f"{have}{unit}",
                    f"{want}{unit}",
                    "" if have == want else "Does not match the project",
                    None if have == want else reason,
                )
            )
        if m.channels == limits.channels:
            out.append(Check("CHANNELS", "PASS", str(m.channels), str(limits.channels)))
        else:
            missing = m.channels < limits.channels
            out.append(
                Check(
                    "CHANNELS",
                    "FAIL",
                    str(m.channels),
                    str(limits.channels),
                    "A track is missing" if missing else "More tracks than the project",
                    "MISSING_TRACK" if missing else "WRONG_CHANNELS",
                )
            )
        low, high = limits.min_duration_seconds, limits.max_duration_seconds
        expected = f"{low} s or more" + (f", at most {high} s" if high is not None else "")
        if not low and high is None:
            out.append(Check("DURATION", "INFO", _seconds(m.duration_ms), "No length limit set"))
        elif m.duration_ms < low * 1000:
            out.append(
                Check(
                    "DURATION",
                    "FAIL",
                    _seconds(m.duration_ms),
                    expected,
                    "Shorter than the project allows",
                    "TOO_SHORT",
                )
            )
        elif high is not None and m.duration_ms > high * 1000:
            out.append(
                Check(
                    "DURATION",
                    "FAIL",
                    _seconds(m.duration_ms),
                    expected,
                    "Longer than the project allows",
                    "TOO_LONG",
                )
            )
        else:
            out.append(Check("DURATION", "PASS", _seconds(m.duration_ms), expected))
    if not m.levels_measured:
        for code in ("SILENCE", "CLIPPING", "LEVELS", "DYNAMIC_RANGE"):
            out.append(
                Check(code, "INFO", "Not measured", "", f"Levels are not measured for {m.codec}")
            )
    else:
        if m.peak_dbfs is None and m.duration_ms > 0:
            out.append(
                Check(
                    "SIGNAL",
                    "FAIL",
                    "No sound at all",
                    "Some sound",
                    "Every sample is zero: nothing was captured",
                    "NO_SIGNAL",
                )
            )
        if limits is not None:
            over = m.silence_pct > limits.max_silence_pct
            out.append(
                Check(
                    "SILENCE",
                    "REVIEW" if over else "PASS",
                    f"{m.silence_pct:.1f} %",
                    f"{limits.max_silence_pct:g} % or less",
                    "More silence than the project allows; listen to it" if over else "",
                    "TOO_MUCH_SILENCE" if over else None,
                )
            )
            if limits.max_clipping_pct is None:
                out.append(
                    Check(
                        "CLIPPING",
                        "INFO",
                        f"{m.clip_pct:.3f} %",
                        "No clipping limit set for this project",
                    )
                )
            else:
                clipped = m.clip_pct > limits.max_clipping_pct
                out.append(
                    Check(
                        "CLIPPING",
                        "REVIEW" if clipped else "PASS",
                        f"{m.clip_pct:.3f} %",
                        f"{limits.max_clipping_pct:g} % or less",
                        "Too loud in places (clipped); listen to it" if clipped else "",
                        "CLIPPING" if clipped else None,
                    )
                )
        levels = (
            f"peak {m.peak_dbfs:.1f} dBFS, average {m.rms_dbfs:.1f} dBFS"
            if m.peak_dbfs is not None and m.rms_dbfs is not None
            else "silent"
        )
        out.append(Check("LEVELS", "INFO", levels, "Shown, not judged"))
        out.append(
            Check(
                "DYNAMIC_RANGE",
                "INFO",
                f"{m.dynamic_range_db:.1f} dB"
                if m.dynamic_range_db is not None
                else "Not measured (file made before this check existed)",
                "Shown, not judged",
            )
        )
    out.append(
        Check(
            "SNR",
            "NOT_APPLICABLE",
            "Not measured",
            "",
            "No validated signal-to-noise method for this recording type, so it is left "
            "empty rather than guessed",
        )
    )
    if m.channels < 2:
        out.append(
            Check(
                "CHANNEL_LEAKAGE",
                "NOT_APPLICABLE",
                "One channel",
                "",
                "Only for recordings with one speaker per channel",
            )
        )
    elif m.channel_correlation is None:
        out.append(
            Check(
                "CHANNEL_LEAKAGE",
                "INFO",
                "Not measured",
                "",
                "Measured on a re-check, from the file itself",
            )
        )
    elif m.channel_correlation >= IDENTICAL_CHANNELS:
        out.append(
            Check(
                "CHANNEL_LEAKAGE",
                "REVIEW",
                f"correlation {m.channel_correlation:.3f}",
                "Separate speakers per channel",
                "Left and right carry the same sound: a mixed recording, not one "
                "speaker per channel",
                "SAME_SOUND_BOTH_CHANNELS",
            )
        )
    else:
        out.append(
            Check(
                "CHANNEL_LEAKAGE",
                "INFO",
                f"correlation {m.channel_correlation:.3f}",
                "Shown, not judged",
            )
        )
    if duplicate is not None and duplicate.exact:
        out.append(
            Check(
                "DUPLICATE",
                "FAIL",
                f"Same file as recording {duplicate.recording_id}",
                "No copy in this project",
                "This exact file is already in the project",
                "DUPLICATE",
            )
        )
    elif duplicate is not None:
        out.append(
            Check(
                "DUPLICATE",
                "REVIEW",
                f"Matches recording {duplicate.recording_id}",
                "No copy in this project",
                "Sounds like another recording in this project; compare them",
                "POSSIBLE_DUPLICATE",
            )
        )
    elif not comparable(m):
        out.append(
            Check(
                "DUPLICATE",
                "INFO",
                "Exact copies only",
                "No copy in this project",
                "Too short or too quiet to compare the sound itself",
            )
        )
    else:
        out.append(Check("DUPLICATE", "PASS", "No match", "No copy in this project"))
    return out


def comparable(m: Measured) -> bool:
    return (
        m.content_fingerprint is not None
        and m.duration_ms >= FINGERPRINT_MIN_MS
        and m.silence_pct < FINGERPRINT_MAX_SILENCE_PCT
    )


def outcome_of(checks: list[Check]) -> tuple[str, str | None]:
    for state, outcome in (("FAIL", "FAIL"), ("REVIEW", "NEEDS_REVIEW")):
        hits = [c for c in checks if c.state == state]
        if hits:
            return outcome, hits[0].reason
    return "PASS", None


def summary(checks: list[Check]) -> str:
    fails = [c.code.replace("_", " ").lower() for c in checks if c.state == "FAIL"]
    reviews = [c.code.replace("_", " ").lower() for c in checks if c.state == "REVIEW"]
    if fails:
        return "Failed: " + ", ".join(fails)
    if reviews:
        return "Listen and decide: " + ", ".join(reviews)
    return "All checks passed"


def find_duplicate(
    db: Session, project_id: uuid.UUID, recording_id: uuid.UUID, m: Measured
) -> Duplicate | None:
    """Another recording in the same project with the same file or the same sound (AQC-007)."""
    base = (
        select(AudioAsset.recording_id)
        .where(
            AudioAsset.project_id == project_id,
            AudioAsset.kind == DELIVERY_KIND,
            AudioAsset.recording_id != recording_id,
            AudioAsset.deleted_at.is_(None),
        )
        .order_by(AudioAsset.created_at)
        .limit(1)
    )
    same_file = db.scalar(base.where(AudioAsset.sha256 == m.sha256))
    if same_file is not None:
        return Duplicate(exact=True, recording_id=same_file)
    if comparable(m):
        same_sound = db.scalar(base.where(AudioAsset.content_fingerprint == m.content_fingerprint))
        if same_sound is not None:
            return Duplicate(exact=False, recording_id=same_sound)
    return None


def delivery_asset(db: Session, recording_id: uuid.UUID) -> AudioAsset | None:
    return db.scalar(
        select(AudioAsset)
        .where(
            AudioAsset.recording_id == recording_id,
            AudioAsset.kind == DELIVERY_KIND,
            AudioAsset.deleted_at.is_(None),
        )
        .order_by(AudioAsset.version.desc())
        .limit(1)
    )


def _limits_for(db: Session, task: Task) -> Limits | None:
    rule = db.scalar(
        select(ProjectAudioRule).where(
            ProjectAudioRule.project_id == task.project_id,
            ProjectAudioRule.mode == task.recording_mode,
        )
    )
    return limits_of(rule) if rule is not None else None


def _store(
    db: Session,
    rec: Recording,
    task: Task,
    asset: AudioAsset | None,
    checks: list[Check],
    measured: Measured | None,
    duplicate: Duplicate | None,
    *,
    requested_by: uuid.UUID | None,
) -> AudioQcResult:
    outcome, reason = outcome_of(checks)
    result = AudioQcResult(
        id=uuid.uuid4(),
        recording_id=rec.id,
        task_id=task.id,
        project_id=task.project_id,
        asset_id=asset.id if asset else None,
        automated=True,
        outcome=outcome,
        reason_code=reason,
        comment=summary(checks),
        reviewer_id=requested_by,
        duration_ms=measured.duration_ms if measured else None,
        silence_pct=measured.silence_pct if measured else None,
        clip_pct=measured.clip_pct if measured else None,
        peak_dbfs=measured.peak_dbfs if measured else None,
        rms_dbfs=measured.rms_dbfs if measured else None,
        dynamic_range_db=measured.dynamic_range_db if measured else None,
        duplicate_of_recording_id=duplicate.recording_id if duplicate else None,
    )
    result.checks = [
        AudioQcCheck(
            position=i,
            code=c.code,
            state=c.state,
            measured=c.measured[:200],
            expected=c.expected[:200],
            message=c.message,
        )
        for i, c in enumerate(checks, start=1)
    ]
    db.add(result)
    audit.record(
        db,
        action="audio_qc.automatic",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=requested_by,
        ip=None,
        after={"outcome": outcome, "reason_code": reason},
    )
    return result


def _finish(db: Session, task: Task, result: AudioQcResult) -> None:
    if task.status == "RECORDED":
        db.flush()
        tasks.system_transition(
            db, task, "AUDIO_QC", comment=f"Automatic audio check: {result.outcome}"
        )
    else:
        db.commit()


def run_automatic(db: Session, recording_id: uuid.UUID) -> AudioQcResult:
    """Check the newest delivery file of a ready recording and hand the task to audio QC."""
    rec = db.get(Recording, recording_id)
    if rec is None:
        raise AppError("Recording not found", code="NOT_FOUND", status_code=404)
    task = db.get(Task, rec.task_id)
    assert task is not None  # noqa: S101  (foreign key guarantees it)
    asset = delivery_asset(db, rec.id)
    measured = from_asset(asset) if asset is not None else None
    duplicate = find_duplicate(db, task.project_id, rec.id, measured) if measured else None
    checks = evaluate(measured, _limits_for(db, task), duplicate=duplicate)
    result = _store(db, rec, task, asset, checks, measured, duplicate, requested_by=None)
    _finish(db, task, result)
    return result


def _latest_ready_recording(db: Session, task: Task) -> Recording | None:
    return db.scalar(
        select(Recording)
        .where(Recording.task_id == task.id, Recording.state == "READY")
        .order_by(Recording.started_at.desc())
        .limit(1)
    )


def _can_manage(principal: Principal, task: Task) -> bool:
    return principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id)


def _is_qc(db: Session, principal: Principal, task: Task) -> bool:
    if not principal.can(Perm.AUDIO_QC_REVIEW):
        return False
    if principal.is_super_admin:
        return True
    current = tasks.active_assignee(db, task.id, Role.QC_EXECUTIVE.value)
    return current is not None and current.user_id == principal.user_id


def recheck(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    principal: Principal,
    task_id: uuid.UUID,
) -> AudioQcResult:
    """Download the delivery file again and check it from its bytes (also recovers a task whose
    automatic check did not run)."""
    task = tasks.get_task(db, principal, task_id)
    if not (_can_manage(principal, task) or _is_qc(db, principal, task)):
        raise forbidden()
    if task.status not in ("RECORDED", "AUDIO_QC"):
        raise AppError(
            "There is no recording waiting for a check", code="TASK_NOT_IN_QC", status_code=409
        )
    rec = _latest_ready_recording(db, task)
    if rec is None:
        raise AppError("There is no finished recording yet", code="NO_RECORDING", status_code=409)
    asset = delivery_asset(db, rec.id)
    measured = decode_error = None
    if asset is not None:
        work = Path(settings.media_work_dir)
        work.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=work) as tmp:
                copy = Path(tmp) / "delivery.wav"
                if storage.head(asset.storage_key) is not None:
                    storage.get_to_file(asset.storage_key, copy)
                measured, decode_error = analyze_file(copy)
        except (BotoCoreError, ClientError):
            logger.exception("audio_qc_storage_unavailable", extra={"task_id": str(task.id)})
            raise AppError(
                "File storage is not reachable right now; try again shortly",
                code="STORAGE_UNAVAILABLE",
                status_code=503,
                headers={"Retry-After": "5"},
            ) from None
    duplicate = find_duplicate(db, task.project_id, rec.id, measured) if measured else None
    checks = evaluate(
        measured,
        _limits_for(db, task),
        decode_error=decode_error,
        duplicate=duplicate,
        expected_sha256=asset.sha256 if asset else None,
    )
    result = _store(
        db, rec, task, asset, checks, measured, duplicate, requested_by=principal.user_id
    )
    _finish(db, task, result)
    return result


def assign_qc(
    db: Session,
    principal: Principal,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str | None,
    ip: str | None,
) -> Task:
    task = tasks.get_task(db, principal, task_id)
    if not _can_manage(principal, task):
        raise forbidden()
    if task.status not in QC_ASSIGNABLE:
        raise AppError(
            f"A {task.status} task cannot get a QC Executive", code="TASK_LOCKED", status_code=409
        )
    user = db.get(User, user_id)
    is_member = user is not None and db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.project_id == task.project_id, ProjectMembership.user_id == user.id
        )
    )
    if user is None or not is_member:
        raise AppError(
            "The QC Executive must be a member of the project",
            code="NOT_PROJECT_MEMBER",
            status_code=422,
        )
    if user.status != "ACTIVE" or Role.QC_EXECUTIVE.value not in {r.code for r in user.roles}:
        raise AppError(
            "Choose an active user with the QC Executive role",
            code="NOT_A_QC_EXECUTIVE",
            status_code=422,
        )
    moderator = tasks.active_assignee(db, task.id, Role.MODERATOR.value)
    recorded = db.scalar(
        select(Recording.id).where(Recording.task_id == task.id, Recording.created_by == user.id)
    )
    if (moderator is not None and moderator.user_id == user.id) or recorded is not None:
        raise AppError(
            "The person who records a session cannot check it", code="SAME_PERSON", status_code=422
        )
    current = tasks.active_assignee(db, task.id, Role.QC_EXECUTIVE.value)
    if current is not None and current.user_id == user.id:
        raise AppError(
            "Already assigned to this QC Executive", code="ALREADY_ASSIGNED", status_code=409
        )
    if current is not None and not (reason and reason.strip()):
        raise AppError("Give a reason for reassigning", code="REASON_REQUIRED", status_code=422)
    try:
        if current is not None:
            current.active = False
            current.ended_at = datetime.now(UTC)
            db.flush()
        db.add(
            TaskAssignment(
                task_id=task.id,
                user_id=user.id,
                role_code=Role.QC_EXECUTIVE.value,
                assigned_by=principal.user_id,
                reason=(reason or "").strip() or None,
            )
        )
        audit.record(
            db,
            action="task.qc_reassigned" if current else "task.qc_assigned",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            actor_id=principal.user_id,
            ip=ip,
            before={"qc": str(current.user_id)} if current else None,
            after={"qc": str(user.id), "reason": (reason or "").strip()},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return task


def _latest(db: Session, task_id: uuid.UUID, *, automated: bool) -> AudioQcResult | None:
    return db.scalar(
        select(AudioQcResult)
        .where(AudioQcResult.task_id == task_id, AudioQcResult.automated.is_(automated))
        .order_by(AudioQcResult.created_at.desc())
        .limit(1)
    )


def decide(
    db: Session,
    principal: Principal,
    task_id: uuid.UUID,
    outcome: str,
    reason_code: str | None,
    comment: str,
    ip: str | None,
) -> AudioQcResult:
    """The QC Executive's decision (AQC-008): PASS approves, FAIL rejects, RETURN asks for a new
    recording. Stored with reason, comment, time and reviewer; the task moves in the same commit."""
    task = tasks.get_task(db, principal, task_id)
    if not _is_qc(db, principal, task):
        raise forbidden()
    if task.status != "AUDIO_QC":
        raise AppError(
            "This task is not waiting for an audio check", code="TASK_NOT_IN_QC", status_code=409
        )
    # Checked at decision time too, for every caller including a Super Admin: assigning the QC
    # first and the moderator second used to let one person record and approve (D-088).
    moderator = tasks.active_assignee(db, task.id, Role.MODERATOR.value)
    recorded = db.scalar(
        select(Recording.id).where(
            Recording.task_id == task.id, Recording.created_by == principal.user_id
        )
    )
    if (moderator is not None and moderator.user_id == principal.user_id) or recorded is not None:
        raise AppError(
            "The person who records a session cannot check it", code="SAME_PERSON", status_code=422
        )
    target = DECISIONS.get(outcome)
    if target is None:
        raise AppError("Choose PASS, FAIL or RETURN", code="VALIDATION_ERROR", status_code=422)
    automatic = _latest(db, task.id, automated=True)
    if automatic is None:
        raise AppError("Run the automatic check first", code="NO_AUTOMATIC_CHECK", status_code=409)
    comment = comment.strip()
    if outcome == "PASS":
        reason_code = None
        if automatic.outcome == "FAIL" and not comment:
            raise AppError(
                "The automatic check failed: say why it passes anyway",
                code="COMMENT_REQUIRED",
                status_code=422,
            )
    workflow.check(
        task.status,
        target,
        workflow.SYSTEM,
        held_from=task.held_from,
        reason_code=reason_code,
        comment=comment,
    )
    rec = db.get(Recording, automatic.recording_id)
    assert rec is not None  # noqa: S101
    result = AudioQcResult(
        id=uuid.uuid4(),
        recording_id=automatic.recording_id,
        task_id=task.id,
        project_id=task.project_id,
        asset_id=automatic.asset_id,
        automated=False,
        outcome=outcome,
        reason_code=reason_code,
        comment=comment,
        reviewer_id=principal.user_id,
        duration_ms=automatic.duration_ms,
        silence_pct=automatic.silence_pct,
        clip_pct=automatic.clip_pct,
        peak_dbfs=automatic.peak_dbfs,
        rms_dbfs=automatic.rms_dbfs,
        dynamic_range_db=automatic.dynamic_range_db,
        duplicate_of_recording_id=automatic.duplicate_of_recording_id,
    )
    db.add(result)
    audit.record(
        db,
        action="audio_qc.decision",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={"outcome": outcome, "reason_code": reason_code},
    )
    db.flush()
    tasks.transition(
        db,
        task,
        target,
        workflow.SYSTEM,
        actor_id=principal.user_id,
        reason_code=reason_code,
        comment=comment or f"Audio QC: {outcome}",
    )
    return result


def results_for(db: Session, task_id: uuid.UUID) -> list[AudioQcResult]:
    return list(
        db.scalars(
            select(AudioQcResult)
            .where(AudioQcResult.task_id == task_id)
            .order_by(AudioQcResult.created_at.desc())
            .limit(50)
        ).all()
    )


def view(db: Session, principal: Principal, task_id: uuid.UUID) -> dict[str, Any]:
    task = tasks.get_task(db, principal, task_id)
    qc = tasks.active_assignee(db, task.id, Role.QC_EXECUTIVE.value)
    qc_user = db.get(User, qc.user_id) if qc else None
    results = results_for(db, task.id)
    reviewers = (
        {
            u.id: u.display_name
            for u in db.scalars(
                select(User).where(User.id.in_({r.reviewer_id for r in results if r.reviewer_id}))
            ).all()
        }
        if results
        else {}
    )
    is_qc = _is_qc(db, principal, task)
    can_manage = _can_manage(principal, task)
    return {
        "task_status": task.status,
        "qc_user_id": qc_user.id if qc_user else None,
        "qc_name": qc_user.display_name if qc_user else None,
        "can_decide": is_qc and task.status == "AUDIO_QC",
        "can_assign": can_manage and task.status in QC_ASSIGNABLE,
        "can_recheck": (is_qc or can_manage) and task.status in ("RECORDED", "AUDIO_QC"),
        "reasons": {
            "FAIL": sorted(workflow.REASONS["REJECTED"]),
            "RETURN": sorted(workflow.REASONS["RETURNED"]),
        },
        "results": [
            {
                "id": r.id,
                "recording_id": r.recording_id,
                "asset_id": r.asset_id,
                "automated": r.automated,
                "outcome": r.outcome,
                "reason_code": r.reason_code,
                "comment": r.comment,
                "reviewer_name": reviewers.get(r.reviewer_id) if r.reviewer_id else None,
                "created_at": r.created_at,
                "duration_ms": r.duration_ms,
                "silence_pct": r.silence_pct,
                "clip_pct": r.clip_pct,
                "peak_dbfs": r.peak_dbfs,
                "rms_dbfs": r.rms_dbfs,
                "dynamic_range_db": r.dynamic_range_db,
                "duplicate_of_recording_id": r.duplicate_of_recording_id,
                "checks": [
                    {
                        "code": c.code,
                        "state": c.state,
                        "measured": c.measured,
                        "expected": c.expected,
                        "message": c.message,
                    }
                    for c in r.checks
                ],
            }
            for r in results
        ],
    }


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def metadata(
    db: Session, principal: Principal, recording_id: uuid.UUID, ip: str | None
) -> tuple[str, dict[str, Any]]:
    """The details file that travels with a recording: session, device, every file with its
    measurements and processing, consent status and audio QC. Participants by code only."""
    rec = db.get(Recording, recording_id)
    if rec is None:
        raise AppError("Recording not found", code="NOT_FOUND", status_code=404)
    try:
        task = tasks.get_task(db, principal, rec.task_id)
    except AppError:
        raise AppError("Recording not found", code="NOT_FOUND", status_code=404) from None
    if not principal.can_in_project(Perm.RECORDINGS_DOWNLOAD, task.project_id):
        raise forbidden()
    project = db.get(Project, task.project_id)
    assert project is not None  # noqa: S101
    assets = db.scalars(
        select(AudioAsset)
        .where(AudioAsset.recording_id == rec.id, AudioAsset.deleted_at.is_(None))
        .order_by(AudioAsset.kind, AudioAsset.version)
    ).all()
    steps = (
        db.scalars(
            select(AssetProcessingStep)
            .where(AssetProcessingStep.asset_id.in_([a.id for a in assets]))
            .order_by(AssetProcessingStep.seq)
        ).all()
        if assets
        else []
    )
    by_asset: dict[uuid.UUID, list[AssetProcessingStep]] = {}
    for step in steps:
        by_asset.setdefault(step.asset_id, []).append(step)
    people = []
    for slot, participant_id in (("A", task.participant_a_id), ("B", task.participant_b_id)):
        participant = db.get(Participant, participant_id)
        assert participant is not None  # noqa: S101
        records = db.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.participant_id == participant_id,
                ConsentRecord.project_id == task.project_id,
            )
            .order_by(ConsentRecord.created_at.desc())
        ).all()
        session = next((r for r in records if r.task_id == task.id), None)
        own = next((r for r in records if r.task_id is None and r.captured_by is None), None)
        people.append(
            {
                "slot": slot,
                "participant_code": participant.participant_code,
                "language": participant.language_code,
                "session_consent": session.status if session else None,
                "session_consent_at": _iso(session.created_at) if session else None,
                "session_consent_method": session.method if session else None,
                "consent_form_answer": own.status if own else None,
                "consent_form_version": own.policy_version if own else None,
                "consent_form_review": own.review_status if own else None,
            }
        )
    results = [r for r in results_for(db, task.id) if r.recording_id == rec.id]
    automatic = next((r for r in results if r.automated), None)
    decision = next((r for r in results if not r.automated), None)
    body: dict[str, Any] = {
        "format": "ccp.recording-metadata/1",
        "generated_at": _iso(datetime.now(UTC)),
        "project": {"code": project.code, "name": project.name},
        "session": {
            "task_code": task.task_code,
            "recording_mode": task.recording_mode,
            "status": task.status,
        },
        "participants": people,
        "recording": {
            "id": str(rec.id),
            "state": rec.state,
            "started_at": _iso(rec.started_at),
            "ended_at": _iso(rec.ended_at),
            "native_sample_rate": rec.native_sample_rate,
            "channel_count": rec.channel_count,
            "device_channel_count": rec.device_channel_count,
            "channel_handling": rec.channel_handling,
            "echo_cancellation": rec.echo_cancellation,
            "noise_suppression": rec.noise_suppression,
            "auto_gain_control": rec.auto_gain_control,
            "device_label": rec.device_label,
            "user_agent": rec.user_agent,
            "parts_received": rec.chunks_received,
            "interrupted": rec.interrupted,
            "interruption_reason": rec.interruption_reason,
        },
        "files": [
            {
                "id": str(a.id),
                "kind": a.kind,
                "version": a.version,
                "derived_from": str(a.parent_asset_id) if a.parent_asset_id else None,
                "container": a.container,
                "codec": a.codec,
                "sample_format": a.sample_format,
                "sample_rate": a.sample_rate,
                "bit_depth": a.bit_depth,
                "channels": a.channels,
                "duration_ms": a.duration_ms,
                "size_bytes": a.size_bytes,
                "sha256": a.sha256,
                "peak_dbfs": a.peak_dbfs,
                "rms_dbfs": a.rms_dbfs,
                "clip_count": a.clip_count,
                "clip_pct": a.clip_pct,
                "silence_pct": a.silence_pct,
                "dynamic_range_db": a.dynamic_range_db,
                "content_fingerprint": a.content_fingerprint,
                "created_at": _iso(a.created_at),
                "processing": [
                    {
                        "tool": s.tool,
                        "tool_version": s.tool_version,
                        "parameters": s.parameters,
                        "input_sha256": s.input_sha256,
                        "output_sha256": s.output_sha256,
                    }
                    for s in by_asset.get(a.id, [])
                ],
            }
            for a in assets
        ],
        "audio_qc": {
            "automatic": None
            if automatic is None
            else {
                "outcome": automatic.outcome,
                "reason_code": automatic.reason_code,
                "summary": automatic.comment,
                "checked_at": _iso(automatic.created_at),
                "checks": [
                    {
                        "code": c.code,
                        "state": c.state,
                        "measured": c.measured,
                        "expected": c.expected,
                        "message": c.message,
                    }
                    for c in automatic.checks
                ],
            },
            "decision": None
            if decision is None
            else {
                "outcome": decision.outcome,
                "reason_code": decision.reason_code,
                "comment": decision.comment,
                "reviewer_id": str(decision.reviewer_id) if decision.reviewer_id else None,
                "decided_at": _iso(decision.created_at),
            },
        },
    }
    audit.record(
        db,
        action="recording.metadata_download",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return f"metadata_{task.task_code}_{rec.id}.json", body


def pending_automatic(db: Session, limit: int = 50) -> list[uuid.UUID]:
    """READY recordings whose task still sits at RECORDED: the automatic check did not run (the
    process stopped in between). The recovery sweep checks them."""
    return list(
        db.scalars(
            select(Recording.id)
            .join(Task, Task.id == Recording.task_id)
            .where(Task.status == "RECORDED", Recording.state == "READY")
            .order_by(Recording.updated_at)
            .limit(limit)
        ).all()
    )
