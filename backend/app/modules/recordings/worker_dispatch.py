"""Run recording processing in the background: Celery with Redis, otherwise in-process.

Recovery (Option H): if a hand-off fails or a process stops mid-way, the recording is left UPLOADED
or PROCESSING. `recover` finds such recordings and processes them again; it runs at start-up and
every RECOVERY_INTERVAL_SECONDS in each web process, and on demand with
`python -m app.cli recover-recordings`. Claiming inside `service.process` keeps two processes from
working on the same recording.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from fastapi import BackgroundTasks, FastAPI

from app.modules.audio_qc import service as audio_qc
from app.modules.recordings import service

logger = logging.getLogger("app.recordings")


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
    return len(stalled)


def fetch_call_recordings(app: FastAPI) -> int:
    """Hand every closed phone call that is due for a look to the worker (D-101). Each call is
    claimed inside `telephony.fetch`, so a call sent twice is worked on once."""
    provider = getattr(app.state, "telephony", None)
    if provider is None or app.state.storage is None:
        return 0
    from app.modules.telephony import service as telephony

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
