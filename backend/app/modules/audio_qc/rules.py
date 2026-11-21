"""The automatic audio check's rules (AQC-001..007): what is measured, and what each check says
about it. Pure: no database, no storage; the same inputs always give the same answer. The service
(service.py) reads the inputs and stores the results.

Limits come from the project's audio rule for the recording mode (AQC-001): sample rate, bit depth,
channels, length, silence and clipping. Where the project sets no limit, the value is shown and
nothing is judged; no universal "good audio" limit is invented. Outcome: FAIL when any check fails,
NEEDS_REVIEW when any check needs a person's ear, otherwise PASS.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.modules.projects.models import Project, ProjectAudioRule
from app.modules.projects.targets import DEFAULT_PAUSE_LIMIT_SECONDS
from app.modules.recordings import media
from app.modules.recordings.models import AudioAsset

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
    # Effective speech and pauses (D-148); None for a file made before them, not measured yet.
    speech: media.Speech | None = None


@dataclass(frozen=True)
class Pauses:
    """The project's pause rule (D-148, projects/targets.py): a silent stretch inside the speech
    longer than `limit_seconds` is a long pause; with `needs_review` long pauses ask for a listen,
    otherwise they are shown only."""

    limit_seconds: int = DEFAULT_PAUSE_LIMIT_SECONDS
    needs_review: bool = False


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
        speech=speech_of_asset(asset),
    )


def speech_of_asset(asset: AudioAsset) -> media.Speech | None:
    """The effective speech kept with a file's record (D-148); None until it is measured."""
    if asset.effective_ms is None:
        return None
    return media.Speech(
        effective_ms=int(asset.effective_ms),
        longest_pause_ms=int(asset.longest_pause_ms or 0),
        pauses_ms=tuple(asset.pauses_ms or ()),
    )


def pauses_of(project: Project) -> Pauses:
    return Pauses(project.pause_limit_seconds, project.long_pauses_need_review)


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
            speech=levels.speech,
        ),
        None,
    )


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.1f} s"


def spoken(ms: int) -> str:
    """A length as people read it: "6 min 12 s", "45 s"."""
    seconds = round(ms / 1000)
    minutes, rest = divmod(seconds, 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def _pauses(m: Measured, rule: Pauses) -> Check:
    """Long pauses (D-148): how many silent stretches inside the speech are longer than the
    project's limit, and the longest. Shown only, or a listen where the project asks for it."""
    limit = rule.limit_seconds
    if m.speech is None:
        return Check(
            "PAUSES",
            "INFO",
            "Not measured yet",
            f"Pauses over {limit} s",
            "Effective speech and pauses are measured shortly for files made before this check",
        )
    count = m.speech.long_pauses(limit * 1000)
    longest = _seconds(m.speech.longest_pause_ms)
    measured = (
        f"{count} over {limit} s, longest {longest}"
        if count
        else f"None over {limit} s (longest {longest})"
    )
    speech = f"Effective speech {spoken(m.speech.effective_ms)} of {spoken(m.duration_ms)}"
    if not rule.needs_review:
        return Check("PAUSES", "INFO", measured, "Shown, not judged", speech)
    return Check(
        "PAUSES",
        "REVIEW" if count else "PASS",
        measured,
        f"No pause over {limit} s",
        f"{speech}; listen to the long pauses" if count else speech,
        "LONG_PAUSES" if count else None,
    )


def evaluate(
    measured: Measured | None,
    limits: Limits | None,
    *,
    decode_error: str | None = None,
    duplicate: Duplicate | None = None,
    expected_sha256: str | None = None,
    pauses: Pauses | None = None,
) -> list[Check]:
    """Every check, in a fixed order. Pure: the same inputs always give the same list. `pauses`:
    the project's pause rule (D-148); the first client's (3 s, shown only) when not given."""
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
        for code in ("SILENCE", "CLIPPING", "LEVELS", "DYNAMIC_RANGE", "PAUSES"):
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
        out.append(_pauses(m, pauses or Pauses()))
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
