"""Audio pipeline units: original WAV wrapper, 16 kHz conversion, inspection, measurements.

Requirements: AUDIO-014, AUDIO-019, AUDIO-020, AUDIO-021, AUDIO-022, AUDIO-017
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile

from app.modules.recordings import media


def _raw(
    path: Path, seconds: float, rate: int = 48000, amplitude: float = 0.5, silence: float = 0.0
) -> Path:
    t = np.arange(int(seconds * rate)) / rate
    tone = (amplitude * np.sin(2 * np.pi * 440 * t)).astype("<f4")
    path.write_bytes(np.concatenate([tone, np.zeros(int(silence * rate), dtype="<f4")]).tobytes())
    return path


def test_original_is_the_same_samples_in_a_wav_container(tmp_path: Path) -> None:
    raw = _raw(tmp_path / "a.f32", 1.0)
    media.write_float_wav(raw, tmp_path / "a.wav", 48000)
    info = media.inspect_wav(tmp_path / "a.wav")
    assert (info.codec, info.sample_rate, info.bit_depth, info.channels, info.duration_ms) == (
        "pcm_f32le",
        48000,
        32,
        1,
        1000,
    )
    data, rate = soundfile.read(tmp_path / "a.wav", dtype="float32")
    assert rate == 48000
    assert np.array_equal(data, np.frombuffer(raw.read_bytes(), dtype="<f4"))


def test_derived_file_meets_the_target_and_is_deterministic(tmp_path: Path) -> None:
    raw = _raw(tmp_path / "a.f32", 2.0)
    media.resample_to_pcm16(raw, 48000, tmp_path / "one.wav")
    media.resample_to_pcm16(raw, 48000, tmp_path / "two.wav")
    assert media.sha256_file(tmp_path / "one.wav") == media.sha256_file(tmp_path / "two.wav")
    info = soundfile.info(str(tmp_path / "one.wav"))
    assert (info.samplerate, info.channels, info.subtype, info.format) == (
        16000,
        1,
        "PCM_16",
        "WAV",
    )
    assert abs(info.duration - 2.0) < 0.01
    ours = media.inspect_wav(tmp_path / "one.wav")
    assert (ours.codec, ours.sample_rate, ours.channels, ours.bit_depth) == (
        "pcm_s16le",
        16000,
        1,
        16,
    )


def test_measurements(tmp_path: Path) -> None:
    raw = _raw(tmp_path / "a.f32", 3.0, silence=1.0)
    media.resample_to_pcm16(raw, 48000, tmp_path / "d.wav")
    levels = media.measure(tmp_path / "d.wav")
    assert levels.peak_dbfs == pytest.approx(-6.02, abs=0.2)
    assert levels.silence_pct == pytest.approx(25.0, abs=1.0)
    assert levels.clip_count == 0
    loud = _raw(tmp_path / "l.f32", 1.0, amplitude=1.5)
    media.resample_to_pcm16(loud, 48000, tmp_path / "l.wav")
    assert media.measure(tmp_path / "l.wav").clip_count > 0


def test_inspect_rejects_non_wav(tmp_path: Path) -> None:
    (tmp_path / "x.wav").write_bytes(b"ID3 not a wav file")
    with pytest.raises(ValueError, match="not a RIFF/WAVE"):
        media.inspect_wav(tmp_path / "x.wav")


def test_ffprobe_agrees_with_our_inspection(tmp_path: Path) -> None:
    """Independent inspection (runbook G3.7). CI installs FFmpeg and sets REQUIRE_FFPROBE=1."""
    import json
    import os
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        if os.environ.get("REQUIRE_FFPROBE") == "1":
            pytest.fail("REQUIRE_FFPROBE=1 but ffprobe is not installed")
        pytest.skip("ffprobe not installed here (independent check NOT RUN locally; runs in CI)")
    raw = _raw(tmp_path / "a.f32", 1.0)
    media.resample_to_pcm16(raw, 48000, tmp_path / "d.wav")
    out = subprocess.run(  # noqa: S603
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(tmp_path / "d.wav"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(out.stdout)["streams"][0]
    assert (
        stream["codec_name"],
        stream["sample_rate"],
        stream["channels"],
        stream["bits_per_sample"],
    ) == ("pcm_s16le", "16000", 1, 16)
