"""Run recording processing in the background: Celery with Redis, otherwise in-process.

Recovery (Option H): if a hand-off fails or a process stops mid-way, the recording is left UPLOADED
or PROCESSING. `recover` finds such recordings and processes them again; it runs at start-up and
every RECOVERY_INTERVAL_SECONDS in each web process, and on demand with
`python -m app.cli recover-recordings`. Claiming inside `service.process` keeps two processes from
working on the same recording. The same sweep applies the projects' retention rules, once an hour
(PROJ-01).

Queues (CALL-04): export bundles go to the queue EXPORTS_QUEUE names (settings.exports_queue). On
AWS it is a queue of its own (`exports`) served by a one-slot worker, so a long export never holds
the slots that process recordings and fetch phone calls; by default it is Celery's default queue,
the one every other job uses.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import BackgroundTasks, FastAPI
from sqlalchemy import text

from app.modules.audio_qc import service as audio_qc
from app.modules.recordings import service

logger = logging.getLogger("app.recordings")

# Retention (PROJ-01): one process deletes at a time (pg_try_advisory_xact_lock); each process
# looks once an hour, and again at the next sweep while a full batch was deleted.
RETENTION_LOCK_KEY = 0x0CC9A1E8
RETENTION_EVERY = timedelta(hours=1)
RETENTION_BATCH = 500


def run_inline(app: FastAPI, recording_id: uuid.UUID) -> None:
    try:
        with app.state.session_factory() as db:
            service.process(db, app.state.settings, app.state.storage, recording_id)
    except Exception:
        logger.exception("inline_processing_failed", extra={"recording_id": str(recording_id)})


def _send(celery: Any, recording_id: uuid.UUID) -> bool:
    try:
        celery.send_task("recordings.process", args=[str(recording_id)])
        return True
    except Exception:
        # Redis unreachable: the recording stays UPLOADED and the recovery sweep sends it later.
        logger.exception("processing_dispatch_failed", extra={"recording_id": str(recording_id)})
        return False


def dispatch_processing(app: FastAPI, recording_id: uuid.UUID, background: BackgroundTasks) -> None:
    celery: Any = getattr(app.state, "celery", None)
    if celery is not None:
        _send(celery, recording_id)
    else:
        # Development and tests without Redis: runs after the response, in this process.
        background.add_task(run_inline, app, recording_id)


def recover(app: FastAPI) -> int:
    """Hand every stalled recording to processing again; returns how many were found."""
    if app.state.storage is None:
        return 0
    removed = service.clean_work_dir(app.state.settings)
    if removed:
        logger.info("work_dir_cleaned", extra={"removed": removed})
    with app.state.session_factory() as db:
        stalled = service.stalled_recordings(db, app.state.settings)
    celery: Any = getattr(app.state, "celery", None)
    for recording_id in stalled:
        if celery is not None:
            if not _send(celery, recording_id):
                break
        else:
            run_inline(app, recording_id)
    if stalled:
        logger.info("recovery_dispatched", extra={"count": len(stalled)})
    check_pending_audio(app)
    fetch_call_recordings(app)
    sweep_exports(app)
    apply_retention_when_due(app)
    fill_effective_speech(app)
    check_operations(app)
    return len(stalled)


def apply_retention_when_due(app: FastAPI, now: datetime | None = None) -> int | None:
    """Delete the files of closed tasks that are past their project's retention rule (PROJ-01,
    STOR-009, service.apply_retention): from the sweep, once an hour in each process (at the next
    sweep again while a full batch was deleted), one process at a time. RETENTION_SWEEP_ENABLED
    false turns it off; `python -m app.cli retention` runs it by hand. Returns how many files were
    deleted, or None when it did not run."""
    settings = app.state.settings
    if not settings.retention_sweep_enabled or app.state.storage is None:
        return None
    now = now or datetime.now(UTC)
    due: datetime | None = getattr(app.state, "retention_due_at", None)
    if due is not None and now < due:
        return None
    app.state.retention_due_at = now + RETENTION_EVERY
    try:
        with app.state.session_factory() as lock:
            # Held by this open transaction while the files are deleted, each in its own commit.
            if not lock.execute(
                text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": RETENTION_LOCK_KEY}
            ).scalar():
                return None
            with app.state.session_factory() as db:
                deleted = service.apply_retention(db, app.state.storage, limit=RETENTION_BATCH)
    except Exception:
        logger.exception("retention_sweep_failed")
        return None
    if deleted >= RETENTION_BATCH:
        app.state.retention_due_at = now  # more are waiting: the next sweep goes on
    if deleted:
        logger.info("retention_applied", extra={"deleted": deleted})
    return deleted


def fill_effective_speech(app: FastAPI) -> int:
    """Measure the effective speech of a few files made before D-148 (audio_qc/speech.py)."""
    from app.modules.audio_qc import speech

    try:
        with app.state.session_factory() as db:
            done = speech.backfill(db, app.state.storage, app.state.settings, speech.SWEEP_BATCH)
    except Exception:
        logger.exception("effective_speech_backfill_failed")
        return 0
    if done.done:
        logger.info(
            "effective_speech_backfilled", extra={"measured": done.measured, "failed": done.failed}
        )
    return done.done


def fetch_call_recordings(app: FastAPI) -> int:
    """Hand every closed phone call that is due for a look to the worker (D-101). Each call is
    claimed inside `telephony.fetch`, so a call sent twice is worked on once."""
    provider = getattr(app.state, "telephony", None)
    if provider is None or app.state.storage is None:
        return 0
    from app.modules.telephony import fetch as telephony

    with app.state.session_factory() as db:
        due = telephony.due_calls(db)
    celery: Any = getattr(app.state, "celery", None)
    for call_id in due:
        if celery is not None:
            try:
                celery.send_task("telephony.fetch", args=[str(call_id)])
            except Exception:
                logger.exception("call_fetch_dispatch_failed", extra={"call_id": str(call_id)})
                break
        else:
            try:
                with app.state.session_factory() as db:
                    telephony.fetch(
                        db,
                        app.state.settings,
                        app.state.storage,
                        provider,
                        app.state.cipher,
                        call_id,
                    )
            except Exception:
                logger.exception("call_fetch_failed", extra={"call_id": str(call_id)})
    return len(due)


def run_export_inline(app: FastAPI, job_id: uuid.UUID) -> None:
    from app.modules.exports import jobs

    try:
        with app.state.session_factory() as db:
            jobs.run(db, app.state.settings, app.state.storage, app.state.cipher, job_id)
    except Exception:
        logger.exception("inline_export_failed", extra={"export_id": str(job_id)})


def dispatch_export(app: FastAPI, job_id: uuid.UUID, background: BackgroundTasks | None) -> None:
    """Hand an export to the worker on the exports queue (settings.exports_queue, CALL-04); without
    Celery it is made in this process, after the answer has been sent. A hand-off that fails is
    repeated by the sweep."""
    celery: Any = getattr(app.state, "celery", None)
    if celery is not None:
        try:
            celery.send_task(
                "exports.build", args=[str(job_id)], queue=app.state.settings.exports_queue
            )
        except Exception:
            logger.exception("export_dispatch_failed", extra={"export_id": str(job_id)})
    elif background is not None:
        background.add_task(run_export_inline, app, job_id)
    else:
        run_export_inline(app, job_id)


def sweep_exports(app: FastAPI) -> int:
    """Remove bundles past their time, and send waiting exports to a worker again (D-105)."""
    from app.modules.exports import jobs

    with app.state.session_factory() as db:
        waiting = jobs.sweep(db, app.state.settings, app.state.storage)
    for job_id in waiting:
        dispatch_export(app, job_id, None)
    return len(waiting)


def check_operations(app: FastAPI) -> str | None:
    """Look for things that need a person, keep them for the status page and email the people
    who run the platform when there is something new to say (D-109)."""
    from app.api.health import readiness
    from app.modules.operations import service as operations

    try:
        checks, _ = readiness(app)
        with app.state.session_factory() as db:
            problems = operations.find_problems(db, app.state.settings, checks["checks"])
            return operations.review(db, app.state.settings, app.state.email_sender, problems)
    except Exception:
        logger.exception("operation_check_failed")
        return None


def check_pending_audio(app: FastAPI) -> int:
    """Run the automatic audio check for finished recordings that missed it (D-079)."""
    done = 0
    with app.state.session_factory() as db:
        for recording_id in audio_qc.pending_automatic(db):
            try:
                audio_qc.run_automatic(db, recording_id)
                done += 1
            except Exception:
                db.rollback()
                logger.exception(
                    "audio_qc_recovery_failed", extra={"recording_id": str(recording_id)}
                )
    return done


def start_recovery_loop(app: FastAPI) -> threading.Event:
    """Sweep at start-up, then every RECOVERY_INTERVAL_SECONDS (0: start-up only). Set to stop."""
    stop = threading.Event()
    if app.state.settings.recovery_interval_seconds == 0 and getattr(app.state, "telephony", None):
        # Closed phone calls are looked at by this sweep only: without it no recording arrives.
        logger.warning("call_recordings_need_the_sweep: RECOVERY_INTERVAL_SECONDS is 0")

    def loop() -> None:
        while True:
            try:
                recover(app)
            except Exception:
                logger.exception("recovery_sweep_failed")
            interval = app.state.settings.recovery_interval_seconds
            if interval == 0 or stop.wait(interval):
                return

    threading.Thread(target=loop, name="recording-recovery", daemon=True).start()
    return stop
