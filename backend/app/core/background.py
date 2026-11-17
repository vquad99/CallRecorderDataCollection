"""Work done after the answer is sent, such as emails to many people (they used to hold a request
open for minutes: 200 emails x up to 15 s each).

With Redis configured the Celery worker does it (`app/worker.py` registers the same task name);
otherwise this process does it once the answer has gone out (development and tests). A job is a
function `job(state, *args)`: `state` gives `session_factory`, `settings`, `cipher` and
`email_sender` (the web app's `app.state`, or the worker's own), and the arguments are plain
strings so they travel through the broker as they are.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import BackgroundTasks

logger = logging.getLogger("app.background")

Job = Callable[..., None]


def dispatch(app: Any, name: str, args: list[Any], job: Job, background: BackgroundTasks) -> bool:
    """Hands `job(state, *args)` to the worker as task `name`, or runs it after the answer.
    False when the worker could not be reached (nothing was queued)."""
    celery = getattr(app.state, "celery", None)
    if celery is None:
        background.add_task(job, app.state, *args)
        return True
    try:
        celery.send_task(name, args=args)
    except Exception:
        logger.exception("background_dispatch_failed", extra={"task": name})
        return False
    return True
