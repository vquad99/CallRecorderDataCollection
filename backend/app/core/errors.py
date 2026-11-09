"""One error format for every failure (FND-006).

Body: {"error": {"code", "message", "request_id", "details"?}}. No stack traces or input values
are ever returned to the client; full details go to the server log.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "RATE_LIMITED",
}


class AppError(Exception):
    """An expected failure with a stable machine-readable code."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "BAD_REQUEST",
        status_code: int = 400,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.headers = headers
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


def error_body(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id_var.get()}
    if details:
        error["details"] = details
    return {"error": error}


async def _app_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return JSONResponse(
        error_body(exc.code, exc.message, exc.details),
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code = _HTTP_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ").lower()
    return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    details = [
        {
            "loc": [str(p) for p in err.get("loc", ())],
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        error_body("VALIDATION_ERROR", "Request validation failed", details), status_code=422
    )


async def _database_unavailable(_: Request, exc: Exception) -> JSONResponse:
    """The database cannot be reached (or asked to retry): a temporary state, not a crash (H)."""
    logging.getLogger("app.errors").warning(
        "database_unavailable", extra={"error_type": type(exc).__name__}
    )
    return JSONResponse(
        error_body(
            "DATABASE_UNAVAILABLE", "The database is not reachable right now; try again shortly"
        ),
        status_code=503,
        headers={"Retry-After": "5"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(OperationalError, _database_unavailable)
