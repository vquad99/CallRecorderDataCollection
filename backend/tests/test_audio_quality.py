"""Audio quality and robustness (owner's test list, Option E).

What the platform measures must be exactly right, for every common capture format, and damaged or
impossible audio must be refused clearly instead of producing a plausible-looking file.

Requirements: AUDIO-014, AUDIO-017, AUDIO-019, AUDIO-020, AUDIO-021, AUDIO-022, FTF-011, FTF-013, AQC-002, AQC-003, AQC-010
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile

from app.modules.recordings import media
from tests import audio_fixtures as fx
from tests import test_recordings
from tests.conftest import Api
from tests.test_recordings import BUCKET, START, put

# Fixtures shared with the recording tests (a real app on a fake S3 and a moderator's task).
app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world


def _db(x: float) -> float:
    return float(20 * np.log10(x))


# ------------------------------------------------------------------------------------ measurement


@pytest.mark.parametrize(
    "signal",
    [
        fx.tone(2.0, dbfs=-6.0),
        fx.tone(2.0, dbfs=-30.0, freq=1000.0),
        fx.noise(2.0, dbfs=-20.0),
        fx.noise(2.0, dbfs=-45.0, seed=3),
    ],
    ids=["tone -6", "tone -30", "noise -20", "noise -45"],
)
def test_peak_and_rms_match_an_independent_calculation(tmp_path: Path, signal: np.ndarray) -> None:
    raw = fx.write_raw(tmp_path / "s.f32", signal)
    media.write_float_wav(raw, tmp_path / "o.wav", fx.RATE)
    levels = media.measure(tmp_path / "o.wav")
    x = signal.astype(np.float64)
    assert levels.peak_dbfs == pytest.approx(_db(np.max(np.abs(x))), abs=0.01)
    assert levels.rms_dbfs == pytest.approx(_db(np.sqrt(np.mean(x * x))), abs=0.01)


def test_digital_silence_is_reported_as_silence_with_no_level(tmp_path: Path) -> None:
    raw = fx.write_raw(tmp_path / "s.f32", fx.silence(3.0))
    media.resample_to_pcm16(raw, fx.RATE, tmp_path / "d.wav")
    levels = media.measure(tmp_path / "d.wav")
    assert (levels.peak_dbfs, levels.rms_dbfs, levels.silence_pct, levels.clip_count) == (
        None,
        None,
        100.0,
        0,
    )


@pytest.mark.parametrize(("quiet_dbfs", "counts_as_silence"), [(-60.0, True), (-40.0, False)])
def test_silence_share_and_threshold(
    tmp_path: Path, quiet_dbfs: float, counts_as_silence: bool
) -> None:
    # 7 s of speech-level tone, then 3 s at a level either side of the -50 dBFS silence threshold.
    signal = np.concatenate([fx.tone(7.0, dbfs=-12.0), fx.tone(3.0, dbfs=quiet_dbfs)])
    raw = fx.write_raw(tmp_path / "s.f32", signal)
    media.resample_to_pcm16(raw, fx.RATE, tmp_path / "d.wav")
    expected = 30.0 if counts_as_silence else 0.0
    assert media.measure(tmp_path / "d.wav").silence_pct == pytest.approx(expected, abs=0.5)


def test_low_volume_is_measured_not_hidden(tmp_path: Path) -> None:
    raw = fx.write_raw(tmp_path / "s.f32", fx.tone(2.0, dbfs=-42.0))
    media.resample_to_pcm16(raw, fx.RATE, tmp_path / "d.wav")
    levels = media.measure(tmp_path / "d.wav")
    assert levels.peak_dbfs == pytest.approx(-42.0, abs=0.2)
    assert levels.rms_dbfs == pytest.approx(-45.01, abs=0.2)  # a sine's RMS is 3.01 dB below peak
    assert levels.silence_pct == 0.0


def test_clipping_is_counted_exactly(tmp_path: Path) -> None:
    samples = np.zeros(16_000, dtype=np.int16)
    samples[100:150] = 32767
    samples[5000:5025] = -32768
    samples[9000] = 32766  # one below full scale: not clipping
    levels = media.measure(fx.pcm16_wav(tmp_path / "c.wav", samples))
    assert levels.clip_count == 75
    assert levels.clip_pct == pytest.approx(100 * 75 / 16_000, abs=1e-4)  # stored to 4 places


def test_over_range_capture_is_kept_in_the_original_and_clipped_in_the_delivery(
    tmp_path: Path,
) -> None:
    hot = (1.6 * np.sin(2 * np.pi * 440 * np.arange(fx.RATE) / fx.RATE)).astype("<f4")
    raw = fx.write_raw(tmp_path / "s.f32", hot)
    media.write_float_wav(raw, tmp_path / "o.wav", fx.RATE)
    original, _ = soundfile.read(tmp_path / "o.wav", dtype="float32")
    assert float(np.max(original)) == pytest.approx(1.6, abs=1e-6), "original never altered"
    media.resample_to_pcm16(raw, fx.RATE, tmp_path / "d.wav")
    derived = media.measure(tmp_path / "d.wav")
    assert derived.clip_count > 0
    assert derived.peak_dbfs == pytest.approx(0.0, abs=0.01)


# -------------------------------------------------------------------- formats the browser can send

RATES = [8_000, 11_025, 16_000, 22_050, 32_000, 44_100, 48_000, 88_200, 96_000, 192_000]


@pytest.mark.parametrize("rate", RATES)
def test_every_capture_rate_converts_to_16k_with_the_same_length(tmp_path: Path, rate: int) -> None:
    signal = fx.tone(3.0, rate=rate, freq=300.0)
    raw = fx.write_raw(tmp_path / "s.f32", signal)
    media.write_float_wav(raw, tmp_path / "o.wav", rate)
    media.resample_to_pcm16(raw, rate, tmp_path / "a.wav")
    media.resample_to_pcm16(raw, rate, tmp_path / "b.wav")
    assert media.sha256_file(tmp_path / "a.wav") == media.sha256_file(tmp_path / "b.wav")
    original, derived = media.inspect_wav(tmp_path / "o.wav"), media.inspect_wav(tmp_path / "a.wav")
    assert (derived.sample_rate, derived.channels, derived.codec) == (16_000, 1, "pcm_s16le")
    frames = derived.data_bytes // 2
    assert abs(frames - round(len(signal) * 16_000 / rate)) <= 1
    assert abs(derived.duration_ms - original.duration_ms) <= 1
    level = media.measure(tmp_path / "a.wav")
    assert level.peak_dbfs == pytest.approx(-6.0, abs=0.3), "no gain added or lost"


@pytest.mark.parametrize("channels", [1, 2, 3, 4, 6, 8])
def test_any_channel_count_keeps_all_channels_and_delivers_channel_one(
    tmp_path: Path, channels: int
) -> None:
    parts = [fx.tone(1.0, freq=200.0 + 150 * c, dbfs=-6.0 - c) for c in range(channels)]
    raw = fx.write_raw(tmp_path / "s.f32", fx.interleave(*parts))
    media.write_float_wav(raw, tmp_path / "o.wav", fx.RATE, channels)
    data, _ = soundfile.read(tmp_path / "o.wav", dtype="float32", always_2d=True)
    assert data.shape == (fx.RATE, channels)
    assert all(np.array_equal(data[:, c], parts[c]) for c in range(channels))
    media.resample_to_pcm16(raw, fx.RATE, tmp_path / "d.wav", channels)
    first = fx.write_raw(tmp_path / "first.f32", parts[0])
    media.resample_to_pcm16(first, fx.RATE, tmp_path / "ref.wav")
    assert media.sha256_file(tmp_path / "d.wav") == media.sha256_file(tmp_path / "ref.wav")


def test_a_very_short_recording_still_converts(tmp_path: Path) -> None:
    raw = fx.write_raw(tmp_path / "s.f32", fx.tone(0.01))  # 10 ms
    media.resample_to_pcm16(raw, fx.RATE, tmp_path / "d.wav")
    assert media.inspect_wav(tmp_path / "d.wav").duration_ms == 10


# ------------------------------------------------------------------------------- damaged files


def _wav(tmp_path: Path) -> bytes:
    raw = fx.write_raw(tmp_path / "s.f32", fx.tone(1.0))
    media.write_float_wav(raw, tmp_path / "ok.wav", fx.RATE)
    return (tmp_path / "ok.wav").read_bytes()


@pytest.mark.parametrize(
    "damage",
    [
        "cut in the middle of the samples",
        "header only",
        "cut inside the header",
        "no data chunk",
        "not a WAV file",
        "data size not whole frames",
        "zero channels",
    ],
)
def test_damaged_files_are_refused_with_a_clear_reason(tmp_path: Path, damage: str) -> None:
    good = _wav(tmp_path)
    data_at = good.index(b"data")
    bad = {
        "cut in the middle of the samples": good[: len(good) // 2],
        "header only": good[: data_at + 8],
        "cut inside the header": good[:20],
        "no data chunk": good[:data_at],
        "not a WAV file": b"ID3\x04" + good[4:],
        "data size not whole frames": good[: data_at + 4]
        + (len(good) - data_at - 8 + 2).to_bytes(4, "little")
        + good[data_at + 8 :]
        + b"\0\0",
        "zero channels": good[:22] + (0).to_bytes(2, "little") + good[24:],
    }[damage]
    path = tmp_path / "bad.wav"
    path.write_bytes(bad)
    with pytest.raises(ValueError, match=r"WAV|RIFF"):
        media.inspect_wav(path)  # the inspection itself must notice, before anything reads samples


# ------------------------------------------------------------------ uploads with impossible audio


def _chunk(values: list[float]) -> bytes:
    return np.asarray(values * 1000, dtype="<f4").tobytes()


@pytest.mark.parametrize(
    "values",
    [[0.1, float("nan")], [0.1, float("inf")], [float("-inf"), 0.2]],
    ids=["not a number", "infinite", "minus infinite"],
)
def test_upload_with_impossible_sample_values_is_refused(
    world: dict[str, Any], values: list[float]
) -> None:
    mod: Api = world["mod"]
    rid = mod.post(f"/api/v1/tasks/{world['task']['id']}/recordings", json=START).json()["id"]
    response = put(mod, rid, 0, _chunk(values))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_AUDIO"
    assert mod.get(f"/api/v1/recordings/{rid}").json()["chunks_received"] == 0


def test_a_part_damaged_in_storage_fails_processing_truthfully(
    world: dict[str, Any], s3: Any
) -> None:
    mod: Api = world["mod"]
    rid = mod.post(f"/api/v1/tasks/{world['task']['id']}/recordings", json=START).json()["id"]
    data = fx.tone(1.0).tobytes()
    assert put(mod, rid, 0, data).status_code == 200
    key = next(
        o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"] if o["Key"].endswith(".f32")
    )
    s3.put_object(Bucket=BUCKET, Key=key, Body=data[:-400])  # shortened behind our back
    mod.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 1})
    detail = mod.get(f"/api/v1/recordings/{rid}").json()
    assert detail["state"] == "FAILED"
    assert detail["assets"] == []
    assert mod.get(f"/api/v1/tasks/{world['task']['id']}").json()["status"] == "IN_PROGRESS"


# ----------------------------------------------------------------- independent inspection (CI)


@pytest.mark.parametrize(("rate", "channels"), [(8_000, 1), (44_100, 2), (96_000, 4)])
def test_ffprobe_agrees_on_unusual_formats(tmp_path: Path, rate: int, channels: int) -> None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        if os.environ.get("REQUIRE_FFPROBE") == "1":
            pytest.fail("REQUIRE_FFPROBE=1 but ffprobe is not installed")
        pytest.skip("ffprobe not installed here (independent check NOT RUN locally; runs in CI)")
    parts = [fx.tone(1.0, rate=rate, freq=200.0 * (c + 1)) for c in range(channels)]
    raw = fx.write_raw(tmp_path / "s.f32", fx.interleave(*parts))
    media.write_float_wav(raw, tmp_path / "o.wav", rate, channels)
    media.resample_to_pcm16(raw, rate, tmp_path / "d.wav", channels)
    for path, expected in (
        (tmp_path / "o.wav", ("pcm_f32le", str(rate), channels)),
        (tmp_path / "d.wav", ("pcm_s16le", "16000", 1)),
    ):
        out = subprocess.run(  # noqa: S603
            [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        s = json.loads(out.stdout)["streams"][0]
        assert (s["codec_name"], s["sample_rate"], s["channels"]) == expected
        assert abs(float(s["duration"]) - 1.0) < 0.002
