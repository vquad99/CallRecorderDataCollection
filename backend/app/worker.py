"""Celery worker: `celery -A app.worker worker` (needs REDIS_URL and storage settings)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from celery import Celery

from app.adapters.txcontact import TxContact
from app.core.config import load_settings
from app.core.email import build_sender
from app.core.logging import configure_logging
from app.core.storage import build_storage
from app.db.session import create_db_engine, make_session_factory
from app.modules.auth.security import FieldCipher
from app.modules.exports import jobs as export_jobs
from app.modules.portal import service as portal
from app.modules.recordings import service
from app.modules.telephony import fetch as telephony
from app.modules.users import service as users

settings = load_settings()
configure_logging(settings.log_level, settings.secret_values())
if settings.redis_url is None:
    raise SystemExit("The worker needs REDIS_URL")
celery_app = Celery("ccp", broker=settings.redis_url.get_secret_value())
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Export bundles go to EXPORTS_QUEUE (CALL-04): the web app names it when it sends one
    # (worker_dispatch.dispatch_export). By default it is the default queue; on AWS it is
    # `exports`, with one worker on `-Q celery` for recordings, phone calls and emails and one on
    # `-Q exports --concurrency=1`, so a long export never holds the slots the others need.
    task_routes={"exports.build": {"queue": settings.exports_queue}},
)
_sessions = make_session_factory(create_db_engine(settings))
_storage = build_storage(settings)
_telephony = TxContact(settings) if settings.telephony_configured else None
_cipher = FieldCipher(settings.data_encryption_key.get_secret_value())
# What background jobs (app.core.background) read; the web app passes its app.state instead.
_state = SimpleNamespace(
    session_factory=_sessions,
    settings=settings,
    cipher=_cipher,
    email_sender=build_sender(settings),
)


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


@celery_app.task(name=portal.SEND_LINKS_TASK)  # type: ignore[untyped-decorator]
def send_consent_links(
    project_id: str, participant_ids: list[str], actor_id: str, ip: str | None
) -> None:
    """Email a fresh personal link to each participant who just joined a project (D-129)."""
    portal.send_links_job(_state, project_id, participant_ids, actor_id, ip)


@celery_app.task(name=users.SEND_INVITATIONS_TASK)  # type: ignore[untyped-decorator]
def send_invitations(user_ids: list[str]) -> None:
    """Email the invitation of each account a user import created."""
    users.send_invitations_job(_state, user_ids)
