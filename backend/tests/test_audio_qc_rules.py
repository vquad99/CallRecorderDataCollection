"""The automatic audio check on generated files with known content (TA-AQC-01..07, 09..12, 15).

Every fixture is generated, so every expected value is known. No database: the rules are pure.

Requirements: AQC-001, AQC-002, AQC-003, AQC-004, AQC-005, AQC-006, AQC-007, AQC-008, AQC-009, AQC-010, AUDIO-018
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import numpy as np
import pytest
import soundfile

from app.modules.audio_qc import service as qc
from tests.audio_fixtures import pcm16_wav

RATE = 16_000
RULE = qc.Limits(
    sample_rate=16_000,
    bit_depth=16,
    channels=1,
    max_silence_pct=25.0,
    max_clipping_pct=None,
    min_duration_seconds=0,
    max_duration_seconds=None,
)


def _tone(seconds: float, rate: int = RATE, freq: float = 440.0, amp: float = 0.5) -> np.ndarray:
    t = np.arange(round(seconds * rate)) / rate
    return amp * np.sin(2 * np.pi * freq * t)


def _wav(tmp: Path, name: str, data: np.ndarray, rate: int = RATE, subtype: str = "PCM_16") -> Path:
    path = tmp / name
    soundfile.write(path, data, rate, subtype=subtype, format="WAV")
    return path


def _run(
    path: Path,
    limits: qc.Limits | None = RULE,
    *,
    duplicate: qc.Duplicate | None = None,
    expected_sha256: str | None = None,
) -> tuple[str, str | None, dict[str, qc.Check]]:
    measured, error = qc.analyze_file(path)
    checks = qc.evaluate(
        measured, limits, decode_error=error, duplicate=duplicate, expected_sha256=expected_sha256
    )
    outcome, reason = qc.outcome_of(checks)
    return outcome, reason, {c.code: c for c in checks}


def test_a_clean_mono_file_passes_and_shows_every_measurement(tmp_path: Path) -> None:
    outcome, reason, checks = _run(_wav(tmp_path, "ok.wav", _tone(6)))
    assert (outcome, reason) == ("PASS", None)
    for code in (
        "DECODES",
        "CHECKSUM",
        "FORMAT",
        "FILE_SIZE",
        "SAMPLE_RATE",
        "BIT_DEPTH",
        "CHANNELS",
        "SILENCE",
        "DUPLICATE",
    ):
        assert checks[code].state == "PASS", code
    assert checks["DURATION"].state == "INFO", "no length limit set: shown, not judged"
    assert checks["CLIPPING"].state == "INFO", "no clipping limit set: shown, not judged"
    assert "peak -6.0 dBFS" in checks["LEVELS"].measured
    assert checks["DYNAMIC_RANGE"].measured.endswith(" dB")
    assert checks["CHANNEL_LEAKAGE"].state == "NOT_APPLICABLE"


def test_signal_to_noise_is_left_empty_with_a_reason(tmp_path: Path) -> None:
    _, _, checks = _run(_wav(tmp_path, "ok.wav", _tone(3)))
    assert checks["SNR"].state == "NOT_APPLICABLE"
    assert "validated" in checks["SNR"].message


def test_a_clean_stereo_file_passes_and_measures_channel_separation(tmp_path: Path) -> None:
    two = np.stack([_tone(6, freq=440), _tone(6, freq=1000, amp=0.25)], axis=1)
    outcome, _, checks = _run(
        _wav(tmp_path, "stereo.wav", two), qc.Limits(**{**RULE.__dict__, "channels": 2})
    )
    assert outcome == "PASS"
    assert checks["CHANNEL_LEAKAGE"].state == "INFO"
    assert "correlation" in checks["CHANNEL_LEAKAGE"].measured


def test_the_same_sound_in_both_channels_is_never_taken_for_two_speakers(tmp_path: Path) -> None:
    mono = _tone(6)
    outcome, reason, checks = _run(
        _wav(tmp_path, "mixed.wav", np.stack([mono, mono], axis=1)),
        qc.Limits(**{**RULE.__dict__, "channels": 2}),
    )
    assert (outcome, reason) == ("NEEDS_REVIEW", "SAME_SOUND_BOTH_CHANNELS")
    assert checks["CHANNEL_LEAKAGE"].state == "REVIEW"


@pytest.mark.parametrize(
    ("rate", "subtype", "channels", "reason"),
    [
        (48_000, "PCM_16", 1, "WRONG_SAMPLE_RATE"),
        (16_000, "PCM_24", 1, "WRONG_BIT_DEPTH"),
        (16_000, "PCM_16", 2, "WRONG_CHANNELS"),
    ],
)
def test_a_file_that_breaks_the_project_rule_fails_with_its_reason(
    tmp_path: Path, rate: int, subtype: str, channels: int, reason: str
) -> None:
    data = _tone(3, rate=rate)
    if channels == 2:
        data = np.stack([data, _tone(3, rate=rate, freq=900)], axis=1)
    outcome, got, checks = _run(_wav(tmp_path, "bad.wav", data, rate=rate, subtype=subtype))
    assert (outcome, got) == ("FAIL", reason)
    if subtype == "PCM_24":
        assert checks["LEVELS"].measured == "Not measured", "never read with the wrong sample size"


def test_a_missing_track_fails(tmp_path: Path) -> None:
    outcome, reason, checks = _run(
        _wav(tmp_path, "one.wav", _tone(3)), qc.Limits(**{**RULE.__dict__, "channels": 2})
    )
    assert (outcome, reason) == ("FAIL", "MISSING_TRACK")
    assert checks["CHANNELS"].message == "A track is missing"


def test_length_limits_come_from_the_project(tmp_path: Path) -> None:
    path = _wav(tmp_path, "short.wav", _tone(3))
    short = qc.Limits(**{**RULE.__dict__, "min_duration_seconds": 10})
    assert _run(path, short)[:2] == ("FAIL", "TOO_SHORT")
    capped = qc.Limits(**{**RULE.__dict__, "max_duration_seconds": 2})
    assert _run(path, capped)[:2] == ("FAIL", "TOO_LONG")
    fits = qc.Limits(**{**RULE.__dict__, "min_duration_seconds": 1, "max_duration_seconds": 5})
    assert _run(path, fits)[2]["DURATION"].state == "PASS"


def test_too_much_silence_is_flagged_for_a_person_to_hear(tmp_path: Path) -> None:
    data = np.concatenate([_tone(3), np.zeros(3 * RATE)])  # half silent; the rule allows 25 %
    outcome, reason, checks = _run(_wav(tmp_path, "quiet.wav", data))
    assert (outcome, reason) == ("NEEDS_REVIEW", "TOO_MUCH_SILENCE")
    assert checks["SILENCE"].measured == "50.0 %"
    relaxed = qc.Limits(**{**RULE.__dict__, "max_silence_pct": 60.0})
    assert _run(_wav(tmp_path, "quiet2.wav", data), relaxed)[0] == "PASS"


def test_a_file_with_no_sound_at_all_fails(tmp_path: Path) -> None:
    outcome, reason, checks = _run(_wav(tmp_path, "zero.wav", np.zeros(3 * RATE)))
    assert (outcome, reason) == ("FAIL", "NO_SIGNAL")
    assert checks["LEVELS"].measured == "silent"


def test_clipping_is_shown_without_a_limit_and_flagged_over_one(tmp_path: Path) -> None:
    samples = np.round(_tone(3, amp=0.5) * 32767).astype(np.int64)
    samples[:4800] = 32767  # 0.3 s pinned at full scale = 10 % of the file
    path = pcm16_wav(tmp_path / "clip.wav", samples)
    _, _, checks = _run(path)
    assert checks["CLIPPING"].state == "INFO"
    limited = qc.Limits(**{**RULE.__dict__, "max_clipping_pct": 1.0})
    outcome, reason, checks = _run(path, limited)
    assert (outcome, reason) == ("NEEDS_REVIEW", "CLIPPING")
    assert checks["CLIPPING"].measured == "10.000 %"


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"not audio at all", "DECODE_ERROR"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", "DECODE_ERROR"),
        (b"", "DECODE_ERROR"),
    ],
)
def test_a_damaged_file_fails_and_says_why(tmp_path: Path, content: bytes, reason: str) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(content)
    outcome, got, checks = _run(path)
    assert (outcome, got) == ("FAIL", reason)
    assert checks["DECODES"].measured, "the decode error is recorded"


def test_a_cut_off_file_fails(tmp_path: Path) -> None:
    whole = _wav(tmp_path, "whole.wav", _tone(3)).read_bytes()
    cut = tmp_path / "cut.wav"
    cut.write_bytes(whole[: len(whole) // 2])
    outcome, reason, checks = _run(cut)
    assert (outcome, reason) == ("FAIL", "DECODE_ERROR")
    assert "truncated" in checks["DECODES"].measured


def test_no_file_fails_as_missing_audio(tmp_path: Path) -> None:
    assert _run(tmp_path / "absent.wav")[:2] == ("FAIL", "MISSING_AUDIO")


def test_checking_never_changes_the_file(tmp_path: Path) -> None:
    path = _wav(tmp_path, "ok.wav", _tone(3))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    _run(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_a_file_that_changed_in_storage_fails(tmp_path: Path) -> None:
    outcome, reason, _ = _run(_wav(tmp_path, "ok.wav", _tone(3)), expected_sha256="0" * 64)
    assert (outcome, reason) == ("FAIL", "CHECKSUM_MISMATCH")


def test_duplicates_fail_when_identical_and_ask_for_a_listen_when_alike(tmp_path: Path) -> None:
    path = _wav(tmp_path, "ok.wav", _tone(6))
    other = uuid.uuid4()
    exact = qc.Duplicate(exact=True, recording_id=other)
    assert _run(path, duplicate=exact)[:2] == ("FAIL", "DUPLICATE")
    alike = qc.Duplicate(exact=False, recording_id=other)
    assert _run(path, duplicate=alike)[:2] == ("NEEDS_REVIEW", "POSSIBLE_DUPLICATE")


def test_the_same_sound_gives_the_same_fingerprint_and_short_files_are_not_compared(
    tmp_path: Path,
) -> None:
    a, _ = qc.analyze_file(_wav(tmp_path, "a.wav", _tone(6)))
    b, _ = qc.analyze_file(_wav(tmp_path, "b.wav", _tone(6), subtype="FLOAT"))
    assert a
    assert b
    assert a.sha256 != b.sha256
    assert a.content_fingerprint == b.content_fingerprint
    assert qc.comparable(a)
    short, _ = qc.analyze_file(_wav(tmp_path, "s.wav", _tone(2)))
    assert short
    assert not qc.comparable(short)


def test_without_a_project_rule_a_person_must_look(tmp_path: Path) -> None:
    assert _run(_wav(tmp_path, "ok.wav", _tone(3)), None)[:2] == ("NEEDS_REVIEW", "NO_RULE")


def test_the_outcome_is_the_worst_check() -> None:
    checks = [
        qc.Check("A", "PASS"),
        qc.Check("B", "REVIEW", reason="TOO_MUCH_SILENCE"),
        qc.Check("C", "FAIL", reason="WRONG_SAMPLE_RATE"),
    ]
    assert qc.outcome_of(checks) == ("FAIL", "WRONG_SAMPLE_RATE")
    assert qc.outcome_of(checks[:2]) == ("NEEDS_REVIEW", "TOO_MUCH_SILENCE")
    assert qc.summary(checks) == "Failed: c"
