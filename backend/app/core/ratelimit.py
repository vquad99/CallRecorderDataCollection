"""Request rate limits per signed-in session (or per IP when signed out) (SEC-005).

Fixed one-minute windows. Redis is used when REDIS_URL is set (required in production) so every
backend process shares the counts; without it, counts live in this process (development, tests).
"""

from __future__ import annotations

import hashlib
import ipaddress
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


# A per-address ceiling on top of the per-session limit: a made-up session cookie on every request
# would otherwise get a fresh allowance each time (security review 2026-11-10). Generous, because
# an office of staff can share one address.
ADDRESS_MULTIPLIER = 10


def address_key(address: str | None) -> str | None:
    """The address a limit counts. One IPv6 customer usually holds a whole /64, so an IPv6
    address counts as its /64; otherwise a new address per request would dodge every per-address
    limit (D-088). IPv4 and anything unparseable are used as given."""
    if not address:
        return address
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(parsed, ipaddress.IPv6Address):
        if parsed.ipv4_mapped is not None:
            return str(parsed.ipv4_mapped)
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False))
    return str(parsed)


def rate_limit(request: Request) -> None:
    settings: Settings = request.app.state.settings
    limiter: Limiter = request.app.state.rate_limiter
    write = request.method in _UNSAFE
    limit = settings.rate_limit_writes_per_minute if write else settings.rate_limit_reads_per_minute
    kind = "w" if write else "r"
    address = address_key(request.client.host if request.client else None) or "-"
    session = request.cookies.get("ccp_session")
    if session:
        keys = [
            (f"rl:{kind}:{hashlib.sha256(session.encode()).hexdigest()[:24]}", limit),
            (f"rl:{kind}:ip:{address}", limit * ADDRESS_MULTIPLIER),
        ]
    else:
        keys = [(f"rl:{kind}:{address}", limit)]
    for key, allowed in keys:
        retry = limiter.hit(key, allowed)
        if retry is not None:
            raise AppError(
                "Too many requests. Try again shortly.",
                code="RATE_LIMITED",
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
