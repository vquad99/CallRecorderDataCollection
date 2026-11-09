"""Celery worker: `celery -A app.worker worker` (needs REDIS_URL and storage settings)."""

from __future__ import annotations

import uuid

from celery import Celery

from app.core.config import load_settings
from app.core.logging import configure_logging
from app.core.storage import build_storage
from app.db.session import create_db_engine, make_session_factory
from app.modules.recordings import service

settings = load_settings()
configure_logging(settings.log_level, settings.secret_values())
if settings.redis_url is None:
    raise SystemExit("The worker needs REDIS_URL")
celery_app = Celery("ccp", broker=settings.redis_url.get_secret_value())
celery_app.conf.update(
    task_acks_late=True, worker_prefetch_multiplier=1, task_reject_on_worker_lost=True
)
_sessions = make_session_factory(create_db_engine(settings))
_storage = build_storage(settings)


@celery_app.task(
    name="recordings.process", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)  # type: ignore[untyped-decorator]
def process_recording(recording_id: str) -> None:
    if _storage is None:
        raise RuntimeError("storage is not configured for the worker")
    with _sessions() as db:
        service.process(db, settings, _storage, uuid.UUID(recording_id))
