"""Liveness and readiness checks (FND-007). Not under /api/v1: load balancers call them."""

from __future__ import annotations

import logging
from typing import Any

import redis
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings

logger = logging.getLogger("app.health")

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


def _check_database(engine: Engine) -> str:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("readiness_database_failed", extra={"error_type": type(exc).__name__})
        return "error"
    return "ok"


def _check_redis(settings: Settings) -> str:
    if settings.redis_url is None:
        return "not_configured"
    client = redis.Redis.from_url(
        settings.redis_url.get_secret_value(), socket_connect_timeout=2, socket_timeout=2
    )
    try:
        client.ping()
    except redis.RedisError as exc:
        logger.warning("readiness_redis_failed", extra={"error_type": type(exc).__name__})
        return "error"
    finally:
        client.close()
    return "ok"


def _check_storage(storage: Any) -> str:
    if storage is None:
        return "not_configured"
    try:
        storage.ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        logger.warning("readiness_storage_failed", extra={"error_type": type(exc).__name__})
        return "error"
    return "ok"


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    checks: dict[str, Any] = {
        "database": _check_database(request.app.state.engine),
        "redis": _check_redis(settings),
        "storage": _check_storage(request.app.state.storage),
    }
    is_ready = all(value in ("ok", "not_configured") for value in checks.values())
    body = {"status": "ready" if is_ready else "not_ready", "checks": checks}
    return JSONResponse(body, status_code=200 if is_ready else 503)
