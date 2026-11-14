"""Celery worker: `celery -A app.worker worker` (needs REDIS_URL and storage settings)."""

from __future__ import annotations

import uuid

from celery import Celery

from app.adapters.txcontact import TxContact
from app.core.config import load_settings
from app.core.logging import configure_logging
from app.core.storage import build_storage
from app.db.session import create_db_engine, make_session_factory
from app.modules.auth.security import FieldCipher
from app.modules.exports import jobs as export_jobs
from app.modules.recordings import service
from app.modules.telephony import service as telephony

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
_telephony = TxContact(settings) if settings.telephony_configured else None
_cipher = FieldCipher(settings.data_encryption_key.get_secret_value())


@celery_app.task(
    name="recordings.process", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)  # type: ignore[untyped-decorator]
def process_recording(recording_id: str) -> None:
    if _storage is None:
        raise RuntimeError("storage is not configured for the worker")
    with _sessions() as db:
        service.process(db, settings, _storage, uuid.UUID(recording_id))


@celery_app.task(name="telephony.fetch")  # type: ignore[untyped-decorator]
def fetch_call_recording(call_id: str) -> None:
    """Look for a closed call's recording, and store it when found (D-101). Retries are planned
    by the call itself (next_fetch_at), so Celery does not retry here."""
    if _storage is None or _telephony is None:
        raise RuntimeError("storage or telephony is not configured for the worker")
    with _sessions() as db:
        telephony.fetch(db, settings, _storage, _telephony, _cipher, uuid.UUID(call_id))


@celery_app.task(name="exports.build")  # type: ignore[untyped-decorator]
def build_export(job_id: str) -> None:
    """Make one export bundle and put it into storage (D-105). A job is claimed inside `run`,
    so one sent twice is made once; the sweep sends a job again when a worker stopped half-way."""
    with _sessions() as db:
        export_jobs.run(db, settings, _storage, _cipher, uuid.UUID(job_id))
