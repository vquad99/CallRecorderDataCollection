"""Audio files: browser original, 16 kHz derived file, inspection, measurements.

AUDIO-019..022: a deterministic pipeline. The original (32-bit float, native rate, every channel
the browser delivered, interleaved) is never changed. The derived file keeps the first channel
(D-041), resamples it with libsoxr "VHQ" (the resampler FFmpeg uses for `aresample=resampler=soxr`),
then converts float -> signed 16-bit by rounding to nearest and clipping, with no dither, no gain,
no filtering, no channel mixing. Every step is recorded by the caller.
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
# The two sample formats this platform writes: browser originals and delivery files.
MEASURABLE_CODECS = ("pcm_s16le", "pcm_f32le")
SOXR_VERSION = getattr(soxr, "__version__", "unknown")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(BLOCK), b""):
            digest.update(part)
    return digest.hexdigest()


def channel_handling(channels: int) -> str:
    """How the derived mono file is made from the original (D-041)."""
    return "mono" if channels == 1 else f"first channel of {channels}"


def conversion_parameters(channels: int) -> str:
    kept = "mono input" if channels == 1 else f"channel 1 of {channels} kept, others not mixed in"
    return (
        f"{kept}; libsoxr quality=VHQ, {TARGET_RATE} Hz, mono, "
        "float32 -> int16 round-half-even, clip, no dither"
    )


def float_wav_header(frames: int, rate: int, channels: int) -> bytes:
    block_align = 4 * channels
    data_bytes = frames * block_align
    # WAVE_FORMAT_IEEE_FLOAT, interleaved channels
    fmt = struct.pack("<HHIIHH", 3, channels, rate, rate * block_align, block_align, 32)
    fact = struct.pack("<I", frames)
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


def write_float_wav(raw: Path, out: Path, rate: int, channels: int = 1) -> None:
    """Wrap raw little-endian float32 samples (interleaved when channels > 1) in a WAV container
    without changing a single byte of them."""
    size = raw.stat().st_size
    if channels < 1 or size % (4 * channels):
        raise ValueError("raw float32 data is not a whole number of frames")
    with out.open("wb") as dst, raw.open("rb") as src:
        dst.write(float_wav_header(size // (4 * channels), rate, channels))
        for part in iter(lambda: src.read(BLOCK), b""):
            dst.write(part)


def resample_to_pcm16(
    raw: Path,
    rate: int,
    out: Path,
    channels: int = 1,
    *,
    offset: int = 0,
    length: int | None = None,
) -> None:
    """Derived file: first channel of the interleaved float32 input, 16 kHz, signed 16-bit.

    Reads `length` bytes from `offset` (a WAV file's data chunk can be read in place, without a
    second copy), one block at a time, so memory use does not grow with the recording's length.
    """
    length = raw.stat().st_size - offset if length is None else length
    if channels < 1 or length % (4 * channels):
        raise ValueError("raw float32 data is not a whole number of frames")
    stream = soxr.ResampleStream(rate, TARGET_RATE, 1, dtype="float32", quality="VHQ")
    block_bytes = BLOCK * 4 * channels  # whole frames per read
    remaining = length
    with raw.open("rb") as src, wave.open(str(out), "wb") as dst:
        src.seek(offset)
        dst.setnchannels(1)
        dst.setsampwidth(2)
        dst.setframerate(TARGET_RATE)
        while True:
            part = src.read(min(block_bytes, remaining))
            remaining -= len(part)
            last = remaining <= 0 or len(part) == 0
            samples = np.ascontiguousarray(np.frombuffer(part, dtype="<f4")[::channels])
            resampled = stream.resample_chunk(samples, last=last)
            pcm = np.clip(np.round(resampled.astype(np.float64) * 32768.0), -32768, 32767).astype(
                "<i2"
            )
            dst.writeframes(pcm.tobytes())
            if last:
                break


def resample_keep_channels_to_pcm16(
    raw: Path, rate: int, out: Path, channels: int, *, offset: int = 0, length: int | None = None
) -> None:
    """Telephony delivery file (D-101): every channel of the interleaved float32 input, 16 kHz,
    signed 16-bit; channels are kept apart, never mixed. Same resampler, rounding and clipping
    as the face-to-face file, one block at a time."""
    length = raw.stat().st_size - offset if length is None else length
    if channels < 1 or length % (4 * channels):
        raise ValueError("raw float32 data is not a whole number of frames")
    stream = soxr.ResampleStream(rate, TARGET_RATE, channels, dtype="float32", quality="VHQ")
    block_bytes = BLOCK * 4 * channels
    remaining = length
    with raw.open("rb") as src, wave.open(str(out), "wb") as dst:
        src.seek(offset)
        dst.setnchannels(channels)
        dst.setsampwidth(2)
        dst.setframerate(TARGET_RATE)
        while True:
            part = src.read(min(block_bytes, remaining))
            remaining -= len(part)
            last = remaining <= 0 or len(part) == 0
            frames = np.frombuffer(part, dtype="<f4").reshape(-1, channels)
            resampled = stream.resample_chunk(frames, last=last)
            pcm = np.clip(np.round(resampled.astype(np.float64) * 32768.0), -32768, 32767).astype(
                "<i2"
            )
            dst.writeframes(np.ascontiguousarray(pcm).tobytes())
            if last:
                break


@dataclass(frozen=True)
class ProviderAudio:
    """What a provider's file turned out to be, as read by libsndfile."""

    container: str
    codec: str
    sample_rate: int
    channels: int
    bit_depth: int


_SUBTYPE_BITS = {
    "PCM_S8": 8,
    "PCM_U8": 8,
    "PCM_16": 16,
    "PCM_24": 24,
    "PCM_32": 32,
    "FLOAT": 32,
    "DOUBLE": 64,
    "ULAW": 8,
    "ALAW": 8,
}


def decode_to_float_wav(src: Path, out: Path) -> ProviderAudio:
    """Decode any file libsndfile reads (WAV incl. mu-law/A-law, MP3, FLAC, Ogg) to a 32-bit float
    WAV at its own rate with all its channels. The samples are decoded, not changed: no
    resampling, gain or mixing. Raises ValueError for a format it cannot read."""
    import soundfile

    try:
        handle = soundfile.SoundFile(str(src))
    except (RuntimeError, soundfile.LibsndfileError):
        # The library's own message names a path on this server; people get the reason only.
        raise ValueError(
            "The provider's file is not audio this platform can read (WAV, MP3, FLAC or Ogg): "
            "the format is not supported or the file is damaged"
        ) from None
    raw = out.with_suffix(".f32")
    with handle, raw.open("wb") as dst:
        rate, channels = int(handle.samplerate), int(handle.channels)
        info = ProviderAudio(
            container=str(handle.format).lower(),
            codec=str(handle.subtype).lower(),
            sample_rate=rate,
            channels=channels,
            bit_depth=_SUBTYPE_BITS.get(str(handle.subtype), 0),
        )
        for block in handle.blocks(blocksize=1 << 16, dtype="float32", always_2d=True):
            dst.write(np.ascontiguousarray(block, dtype="<f4").tobytes())
    try:
        write_float_wav(raw, out, rate, channels)
    finally:
        raw.unlink(missing_ok=True)
    return info


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


def all_finite(data: bytes) -> bool:
    """True when raw float32 samples hold only real numbers (no NaN, no infinity)."""
    return bool(np.isfinite(np.frombuffer(data, dtype="<f4")).all())


def inspect_wav(path: Path) -> WavInfo:
    """Read the RIFF/WAVE structure directly (no decoding library involved).

    Every way a file can be damaged raises ValueError with a plain reason: cut off, inconsistent
    format fields, or a data chunk that is not a whole number of frames.
    """
    file_size = path.stat().st_size
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
                raw = handle.read(16)
                if size < 16 or len(raw) < 16:
                    raise ValueError("WAV file is cut off inside its format header")
                fmt = struct.unpack("<HHIIHH", raw)
                handle.seek(size - 16 + (size % 2), 1)
            elif cid == b"data":
                if fmt is None:
                    raise ValueError("WAV data chunk before fmt chunk")
                tag, channels, rate, _byte_rate, block_align, bits = fmt
                if channels < 1 or rate < 1 or bits < 8 or block_align != channels * (bits // 8):
                    raise ValueError("WAV format fields are inconsistent")
                if size % block_align:
                    raise ValueError("WAV data is not a whole number of frames")
                if handle.tell() + size > file_size:
                    raise ValueError("WAV data is truncated")
                codec = {1: f"pcm_s{bits}le", 3: f"pcm_f{bits}le"}.get(tag, f"wav_format_{tag}")
                frames = size // block_align
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
    # Loud speech minus the noise floor: 95th minus 10th percentile of the 20 ms window levels
    # (AQC-003). None for an empty file.
    dynamic_range_db: float | None = None
    # SHA-256 of the per-second level pattern (whole dB): the same conversation stored twice gives
    # the same value even when the files' bytes differ (AQC-007). None for an empty file.
    content_fingerprint: str | None = None


def _db(value: float) -> float | None:
    return round(20 * np.log10(value), 2) if value > 0 else None


def measure(path: Path) -> Levels:
    """Peak, RMS, clipping and silence over the whole file; read-only (AUDIO-018)."""
    info = inspect_wav(path)
    if info.codec not in MEASURABLE_CODECS:
        raise ValueError(f"levels cannot be measured for {info.codec}")
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
    # A 20 ms window spans every channel's samples for the same 20 ms (interleaved data).
    frame = max(1, int(info.sample_rate * FRAME_SECONDS)) * info.channels
    peak = 0.0
    sum_sq = 0.0
    clips = 0
    silent = frames = 0
    window_levels: list[np.ndarray] = []
    step = BLOCK - BLOCK % frame  # blocks hold whole windows, so no window is split
    for start in range(0, len(data), step):
        block = np.asarray(data[start : start + step], dtype=np.float64) / scale
        if not len(block):
            continue
        peak = max(peak, float(np.max(np.abs(block))))
        sum_sq += float(np.sum(block * block))
        clips += int(
            np.count_nonzero(
                np.abs(np.asarray(data[start : start + step], dtype=np.float64)) >= clip_at
            )
        )
        usable = len(block) - len(block) % frame
        if usable:
            rms = np.sqrt(np.mean(block[:usable].reshape(-1, frame) ** 2, axis=1))
            silent += int(np.count_nonzero(rms < 10 ** (SILENCE_DBFS / 20)))
            frames += len(rms)
            window_levels.append(20 * np.log10(np.maximum(rms, 1e-5)))  # floor -100 dBFS
    total = len(data)
    del data
    dynamic_range = fingerprint = None
    if window_levels:
        levels_db = np.concatenate(window_levels)
        low, high = np.percentile(levels_db, [10, 95])
        dynamic_range = round(float(high - low), 2)
        per_second = round(1 / FRAME_SECONDS)
        whole = len(levels_db) - len(levels_db) % per_second
        seconds = levels_db[:whole].reshape(-1, per_second).mean(axis=1) if whole else levels_db[:1]
        pattern = np.clip(np.round(seconds), -100, 0).astype(np.int8)
        fingerprint = hashlib.sha256(pattern.tobytes()).hexdigest()
    return Levels(
        peak_dbfs=_db(peak),
        rms_dbfs=_db(float(np.sqrt(sum_sq / total))) if total else None,
        clip_count=clips,
        clip_pct=round(100 * clips / total, 4) if total else 0.0,
        silence_pct=round(100 * silent / frames, 2) if frames else 100.0,
        dynamic_range_db=dynamic_range,
        content_fingerprint=fingerprint,
    )
