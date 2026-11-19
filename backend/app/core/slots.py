"""Heavy work a process does only a few at a time (password hashes, one task's bundle): the rest
wait their turn, then give up with 503 BUSY."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.errors import AppError


@contextmanager
def turn(slots: threading.BoundedSemaphore, wait_seconds: float, busy: str) -> Iterator[None]:
    """Holds one of `slots` while the block runs; 503 BUSY (message `busy`) when none comes free
    within `wait_seconds`."""
    if not slots.acquire(timeout=wait_seconds):
        raise AppError(busy, code="BUSY", status_code=503)
    try:
        yield
    finally:
        slots.release()
