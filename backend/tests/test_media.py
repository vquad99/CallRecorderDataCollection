"""Audio pipeline units: original WAV wrapper, 16 kHz conversion, inspection, measurements.

Requirements: AUDIO-014, AUDIO-019, AUDIO-020, AUDIO-021, AUDIO-022, AUDIO-017
"""

from pathlib import Path
from typing import Any

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


def _stereo_raw(path: Path, seconds: float, rate: int = 48000) -> tuple[Path, np.ndarray]:
    t = np.arange(int(seconds * rate)) / rate
    frames = np.stack(
        [0.5 * np.sin(2 * np.pi * 440 * t), 0.25 * np.sin(2 * np.pi * 1000 * t)], axis=1
    ).astype("<f4")
    path.write_bytes(frames.tobytes())
    return path, frames


def test_two_channel_original_is_kept_whole(tmp_path: Path) -> None:
    raw, frames = _stereo_raw(tmp_path / "s.f32", 1.0)
    media.write_float_wav(raw, tmp_path / "s.wav", 48000, channels=2)
    info = media.inspect_wav(tmp_path / "s.wav")
    assert (info.codec, info.channels, info.duration_ms) == ("pcm_f32le", 2, 1000)
    data, rate = soundfile.read(tmp_path / "s.wav", dtype="float32")
    assert rate == 48000
    assert np.array_equal(data, frames)
    (tmp_path / "odd.f32").write_bytes(b"\0" * 12)
    with pytest.raises(ValueError, match="whole number of frames"):
        media.write_float_wav(tmp_path / "odd.f32", tmp_path / "odd.wav", 48000, channels=2)


def test_derived_from_two_channels_is_exactly_channel_one(tmp_path: Path) -> None:
    raw, frames = _stereo_raw(tmp_path / "s.f32", 2.0)
    first = tmp_path / "first.f32"
    first.write_bytes(np.ascontiguousarray(frames[:, 0]).tobytes())
    media.resample_to_pcm16(raw, 48000, tmp_path / "from_stereo.wav", channels=2)
    media.resample_to_pcm16(first, 48000, tmp_path / "from_first.wav")
    assert media.sha256_file(tmp_path / "from_stereo.wav") == media.sha256_file(
        tmp_path / "from_first.wav"
    ), "same bytes as converting channel 1 alone: nothing from channel 2 leaks in"
    assert media.channel_handling(2) == "first channel of 2"
    assert media.channel_handling(1) == "mono"


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

    def probe(path: Path) -> dict[str, Any]:
        out = subprocess.run(  # noqa: S603
            [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        stream: dict[str, Any] = json.loads(out.stdout)["streams"][0]
        return stream

    raw = _raw(tmp_path / "a.f32", 1.0)
    media.resample_to_pcm16(raw, 48000, tmp_path / "d.wav")
    stream = probe(tmp_path / "d.wav")
    assert (
        stream["codec_name"],
        stream["sample_rate"],
        stream["channels"],
        stream["bits_per_sample"],
    ) == ("pcm_s16le", "16000", 1, 16)

    # Two-channel original and the mono file derived from it.
    stereo, _ = _stereo_raw(tmp_path / "s.f32", 1.0)
    media.write_float_wav(stereo, tmp_path / "s.wav", 48000, channels=2)
    media.resample_to_pcm16(stereo, 48000, tmp_path / "sd.wav", channels=2)
    for path, expected in (
        (tmp_path / "s.wav", ("pcm_f32le", "48000", 2, 32)),
        (tmp_path / "sd.wav", ("pcm_s16le", "16000", 1, 16)),
    ):
        stream = probe(path)
        ours = media.inspect_wav(path)
        assert (
            stream["codec_name"],
            stream["sample_rate"],
            stream["channels"],
            stream["bits_per_sample"],
        ) == expected
        assert (ours.codec, str(ours.sample_rate), ours.channels, ours.bit_depth) == expected
        assert abs(float(stream["duration"]) - 1.0) < 0.01
