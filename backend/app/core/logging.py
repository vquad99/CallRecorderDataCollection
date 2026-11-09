"""Structured JSON logging with request IDs and secret redaction (FND-004)."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}

REDACTED = "***"


class JsonFormatter(logging.Formatter):
    """One JSON object per line; any known secret value is replaced before output."""

    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self._secrets = sorted(set(secrets or []), key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        text = json.dumps(payload, default=str, ensure_ascii=False)
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text


def configure_logging(level: str, secrets: list[str]) -> None:
    """Route every logger (including uvicorn's) through one JSON handler on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(secrets))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True
    # The request middleware writes one access line per request; uvicorn's own would duplicate it.
    logging.getLogger("uvicorn.access").disabled = True
