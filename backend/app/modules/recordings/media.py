"""Audio files: browser original, 16 kHz derived file, inspection, measurements.

AUDIO-019..022: a deterministic pipeline. The original (32-bit float, native rate, mono) is never
changed. The derived file is a resample with libsoxr "VHQ" (the resampler FFmpeg uses for
`aresample=resampler=soxr`), then float -> signed 16-bit by rounding to nearest and clipping, with
no dither, no gain, no filtering. Every step is recorded by the caller.
"""

from __future__ import annotations

import hashlib
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soxr

TARGET_RATE = 16_000
BLOCK = 1 << 20
SILENCE_DBFS = -50.0
FRAME_SECONDS = 0.02
CONVERSION_PARAMETERS = (
    f"libsoxr quality=VHQ, {TARGET_RATE} Hz, mono, "
    "float32 -> int16 round-half-even, clip, no dither"
)
SOXR_VERSION = getattr(soxr, "__version__", "unknown")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(BLOCK), b""):
            digest.update(part)
    return digest.hexdigest()


def _float_wav_header(sample_count: int, rate: int) -> bytes:
    data_bytes = sample_count * 4
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)  # WAVE_FORMAT_IEEE_FLOAT, mono
    fact = struct.pack("<I", sample_count)
    return (
        b"RIFF"
        + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(fact) + 8 + data_bytes)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"fact"
        + struct.pack("<I", len(fact))
        + fact
        + b"data"
        + struct.pack("<I", data_bytes)
    )


def write_float_wav(raw: Path, out: Path, rate: int) -> None:
    """Wrap raw little-endian float32 mono samples in a WAV container without changing them."""
    size = raw.stat().st_size
    if size % 4:
        raise ValueError("raw float32 data is not a whole number of samples")
    with out.open("wb") as dst, raw.open("rb") as src:
        dst.write(_float_wav_header(size // 4, rate))
        for part in iter(lambda: src.read(BLOCK), b""):
            dst.write(part)


def resample_to_pcm16(raw: Path, rate: int, out: Path) -> None:
    stream = soxr.ResampleStream(rate, TARGET_RATE, 1, dtype="float32", quality="VHQ")
    with raw.open("rb") as src, wave.open(str(out), "wb") as dst:
        dst.setnchannels(1)
        dst.setsampwidth(2)
        dst.setframerate(TARGET_RATE)
        while True:
            part = src.read(BLOCK * 4)
            last = len(part) < BLOCK * 4
            samples = np.frombuffer(part, dtype="<f4")
            resampled = stream.resample_chunk(samples, last=last)
            pcm = np.clip(np.round(resampled.astype(np.float64) * 32768.0), -32768, 32767).astype(
                "<i2"
            )
            dst.writeframes(pcm.tobytes())
            if last:
                break


@dataclass(frozen=True)
class WavInfo:
    container: str
    codec: str
    sample_format: str
    sample_rate: int
    bit_depth: int
    channels: int
    duration_ms: int
    size_bytes: int
    data_offset: int
    data_bytes: int


def inspect_wav(path: Path) -> WavInfo:
    """Read the RIFF/WAVE structure directly (no decoding library involved)."""
    with path.open("rb") as handle:
        head = handle.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ValueError("not a RIFF/WAVE file")
        fmt: tuple[int, ...] | None = None
        while True:
            chunk = handle.read(8)
            if len(chunk) < 8:
                raise ValueError("WAV file has no data chunk")
            cid, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if cid == b"fmt ":
                fmt = struct.unpack("<HHIIHH", handle.read(16))
                handle.seek(size - 16 + (size % 2), 1)
            elif cid == b"data":
                if fmt is None:
                    raise ValueError("WAV data chunk before fmt chunk")
                tag, channels, rate, _byte_rate, block_align, bits = fmt
                codec = {1: f"pcm_s{bits}le", 3: f"pcm_f{bits}le"}.get(tag, f"wav_format_{tag}")
                frames = size // block_align if block_align else 0
                return WavInfo(
                    container="wav",
                    codec=codec,
                    sample_format="int" if tag == 1 else "float",
                    sample_rate=rate,
                    bit_depth=bits,
                    channels=channels,
                    duration_ms=round(frames * 1000 / rate) if rate else 0,
                    size_bytes=path.stat().st_size,
                    data_offset=handle.tell(),
                    data_bytes=size,
                )
            else:
                handle.seek(size + (size % 2), 1)


@dataclass(frozen=True)
class Levels:
    peak_dbfs: float | None
    rms_dbfs: float | None
    clip_count: int
    clip_pct: float
    silence_pct: float


def _db(value: float) -> float | None:
    return round(20 * np.log10(value), 2) if value > 0 else None


def measure(path: Path) -> Levels:
    """Peak, RMS, clipping and silence over the whole file; read-only (AUDIO-018)."""
    info = inspect_wav(path)
    dtype, scale, clip_at = (
        ("<i2", 32768.0, 32767) if info.codec == "pcm_s16le" else ("<f4", 1.0, 1.0)
    )
    data = np.memmap(
        path,
        dtype=dtype,
        mode="r",
        offset=info.data_offset,
        shape=(info.data_bytes // np.dtype(dtype).itemsize,),
    )
    frame = max(1, int(info.sample_rate * FRAME_SECONDS))
    peak = 0.0
    sum_sq = 0.0
    clips = 0
    silent = frames = 0
    for start in range(0, len(data), BLOCK):
        block = np.asarray(data[start : start + BLOCK], dtype=np.float64) / scale
        if not len(block):
            continue
        peak = max(peak, float(np.max(np.abs(block))))
        sum_sq += float(np.sum(block * block))
        clips += int(
            np.count_nonzero(
                np.abs(np.asarray(data[start : start + BLOCK], dtype=np.float64)) >= clip_at
            )
        )
        usable = len(block) - len(block) % frame
        if usable:
            rms = np.sqrt(np.mean(block[:usable].reshape(-1, frame) ** 2, axis=1))
            silent += int(np.count_nonzero(rms < 10 ** (SILENCE_DBFS / 20)))
            frames += len(rms)
    total = len(data)
    del data
    return Levels(
        peak_dbfs=_db(peak),
        rms_dbfs=_db(float(np.sqrt(sum_sq / total))) if total else None,
        clip_count=clips,
        clip_pct=round(100 * clips / total, 4) if total else 0.0,
        silence_pct=round(100 * silent / frames, 2) if frames else 100.0,
    )
