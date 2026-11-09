"""Request rate limits per signed-in session (or per IP when signed out) (SEC-005).

Fixed one-minute windows. Redis is used when REDIS_URL is set (required in production) so every
backend process shares the counts; without it, counts live in this process (development, tests).
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Protocol

import redis
from fastapi import Request

from app.core.config import Settings
from app.core.errors import AppError

WINDOW_SECONDS = 60
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class Limiter(Protocol):
    def hit(self, key: str, limit: int) -> int | None:
        """Count one request; return seconds to wait if the limit is exceeded, else None."""


class MemoryLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int) -> int | None:
        now = int(time.time())
        window = now // WINDOW_SECONDS
        with self._lock:
            start, count = self._counts.get(key, (window, 0))
            count = count + 1 if start == window else 1
            self._counts[key] = (window, count)
        return (window + 1) * WINDOW_SECONDS - now if count > limit else None


class RedisLimiter:
    def __init__(self, url: str) -> None:
        self._client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)

    def hit(self, key: str, limit: int) -> int | None:
        now = int(time.time())
        window = now // WINDOW_SECONDS
        name = f"{key}:{window}"
        pipe = self._client.pipeline()
        pipe.incr(name)
        pipe.expire(name, WINDOW_SECONDS * 2)
        count = int(pipe.execute()[0])
        return (window + 1) * WINDOW_SECONDS - now if count > limit else None


def build_limiter(settings: Settings) -> Limiter:
    return (
        RedisLimiter(settings.redis_url.get_secret_value())
        if settings.redis_url
        else MemoryLimiter()
    )


def rate_limit(request: Request) -> None:
    settings: Settings = request.app.state.settings
    limiter: Limiter = request.app.state.rate_limiter
    write = request.method in _UNSAFE
    limit = settings.rate_limit_writes_per_minute if write else settings.rate_limit_reads_per_minute
    session = request.cookies.get("ccp_session")
    who = (
        hashlib.sha256(session.encode()).hexdigest()[:24]
        if session
        else (request.client.host if request.client else "-")
    )
    retry = limiter.hit(f"rl:{'w' if write else 'r'}:{who}", limit)
    if retry is not None:
        raise AppError(
            "Too many requests. Try again shortly.",
            code="RATE_LIMITED",
            status_code=429,
            headers={"Retry-After": str(retry)},
        )
