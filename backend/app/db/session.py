"""Database engine with a configured connection pool; request session dependency (FND-008)."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

logger = logging.getLogger("app.db")

# Per-request database use, filled by the engine hooks and read by the request log (O8).
db_stats_var: ContextVar[dict[str, float] | None] = ContextVar("db_stats", default=None)


def _watch(engine: Engine, slow_query_ms: int) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _start(conn: Any, *_: Any) -> None:
        conn.info.setdefault("query_started", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _end(conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        elapsed = 1000 * (time.perf_counter() - conn.info["query_started"].pop())
        stats = db_stats_var.get()
        if stats is not None:
            stats["queries"] += 1
            stats["ms"] += elapsed
        if slow_query_ms and elapsed > slow_query_ms:
            # The statement shape only: parameter values (personal data) are never logged.
            logger.warning(
                "slow_query",
                extra={
                    "duration_ms": round(elapsed, 1),
                    "statement": " ".join(statement.split())[:300],
                },
            )


def create_db_engine(settings: Settings) -> Engine:
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )
    _watch(engine, settings.slow_query_ms)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session
