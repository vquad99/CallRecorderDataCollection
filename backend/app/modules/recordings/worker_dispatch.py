"""Run recording processing in the background: Celery with Redis, otherwise in-process."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import BackgroundTasks, FastAPI

from app.modules.recordings import service

logger = logging.getLogger("app.recordings")


def run_inline(app: FastAPI, recording_id: uuid.UUID) -> None:
    try:
        with app.state.session_factory() as db:
            service.process(db, app.state.settings, app.state.storage, recording_id)
    except Exception:
        logger.exception("inline_processing_failed", extra={"recording_id": str(recording_id)})


def dispatch_processing(app: FastAPI, recording_id: uuid.UUID, background: BackgroundTasks) -> None:
    celery: Any = getattr(app.state, "celery", None)
    if celery is not None:
        celery.send_task("recordings.process", args=[str(recording_id)])
    else:
        # Development and tests without Redis: runs after the response, in this process.
        background.add_task(run_inline, app, recording_id)
