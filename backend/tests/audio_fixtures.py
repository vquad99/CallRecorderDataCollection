"""Generated audio fixtures with known content (TEST_PLAN.md section 3; Option E).

Signals are generated, not stored, so every expected value is known exactly. Phase 7 (audio QC)
reuses these for its pass / fail rules.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

RATE = 48_000


def tone(seconds: float, rate: int = RATE, freq: float = 440.0, dbfs: float = -6.0) -> np.ndarray:
    t = np.arange(round(seconds * rate)) / rate
    return (10 ** (dbfs / 20) * np.sin(2 * np.pi * freq * t)).astype("<f4")


def silence(seconds: float, rate: int = RATE) -> np.ndarray:
    return np.zeros(round(seconds * rate), dtype="<f4")


def noise(seconds: float, rate: int = RATE, dbfs: float = -20.0, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (10 ** (dbfs / 20) * rng.standard_normal(round(seconds * rate))).astype("<f4")


def interleave(*channels: np.ndarray) -> np.ndarray:
    """Frames of several channels, interleaved as the browser capture sends them."""
    return np.stack(channels, axis=1).astype("<f4").reshape(-1)


def write_raw(path: Path, samples: np.ndarray) -> Path:
    path.write_bytes(samples.astype("<f4").tobytes())
    return path


def pcm16_wav(path: Path, samples: np.ndarray, rate: int = 16_000) -> Path:
    """A plain 16-bit mono WAV from integer samples (for exact clipping counts)."""
    data = np.asarray(samples, dtype="<i2").tobytes()
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
    )
    path.write_bytes(header + data)
    return path
