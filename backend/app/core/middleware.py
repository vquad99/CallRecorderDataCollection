"""Request context middleware (FND-005): request ID, access log, last-resort error handler.

Runs as the outermost application middleware so the request ID is set for every log line and
every response, including unexpected 500s, which it answers itself in the standard error format.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.core.logging import request_id_var
from app.db.session import db_stats_var

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


_CHUNK_PATH = re.compile(r"^/api/v1/recordings/[^/]+/chunks/[^/]+$")
# A JSON \u0000 escape: preceded by an even number of backslashes (an odd number means the text
# itself contains a backslash followed by "u0000", which is allowed).
_JSON_NUL = re.compile(rb"(?<!\\)(?:\\\\)*\\u0000")


class RequestLimitsMiddleware:
    """Input limits applied before the application reads a request (SEC-006).

    Size: audio chunk uploads may be up to MAX_CHUNK_BYTES, everything else up to MAX_REQUEST_BYTES;
    larger bodies get 413. The declared Content-Length is checked first; a body sent without one
    (chunked transfer) is read up to the limit and refused as soon as it passes it, so memory use
    stays bounded either way.

    NUL characters: PostgreSQL text cannot hold them, so a NUL in the path, the query string or a
    JSON body is refused with 422 here instead of failing as a server error deeper down (any caller,
    signed in or not, could otherwise trigger 500s at will). Binary audio chunks are not inspected.
    """

    def __init__(self, app: ASGIApp, *, default_limit: int, chunk_limit: int) -> None:
        self.app = app
        self.default_limit = default_limit
        self.chunk_limit = chunk_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if "\x00" in scope["path"] or b"%00" in scope.get("query_string", b""):
            await self._refuse_nul(send)
            return
        if scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        is_chunk = bool(_CHUNK_PATH.match(scope["path"]))
        limit = self.chunk_limit if is_chunk else self.default_limit
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await self._refuse(send, limit)
            return
        parts: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # client went away before sending the whole body
            part = message.get("body", b"")
            size += len(part)
            if size > limit:
                await self._refuse(send, limit)
                return
            parts.append(part)
            if not message.get("more_body", False):
                break
        body = b"".join(parts)
        if not is_chunk and _JSON_NUL.search(body):
            await self._refuse_nul(send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, send)

    @staticmethod
    async def _refuse(send: Send, limit: int) -> None:
        await _send_error(
            send, 413, "PAYLOAD_TOO_LARGE", f"Request body is larger than {limit} bytes"
        )

    @staticmethod
    async def _refuse_nul(send: Send) -> None:
        await _send_error(send, 422, "VALIDATION_ERROR", "Text must not contain NUL characters")


async def _send_error(send: Send, status: int, code: str, message: str) -> None:
    payload = json.dumps(error_body(code, message)).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, slow_request_ms: int = 0) -> None:
        self.app = app
        self.slow_request_ms = slow_request_ms

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        stats = {"queries": 0, "ms": 0.0}
        stats_token = db_stats_var.set(stats)
        started = perf_counter()
        state = {"status": 500, "started": False}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                state["started"] = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.exception("unhandled_error", extra={"path": scope.get("path")})
            if state["started"]:
                raise
            body = json.dumps(error_body("INTERNAL_ERROR", "Internal server error")).encode()
            await send_with_id(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
        finally:
            duration = round((perf_counter() - started) * 1000, 2)
            fields = {
                "method": scope.get("method"),
                "path": scope.get("path"),
                "status": state["status"],
                "duration_ms": duration,
                "db_queries": int(stats["queries"]),
                "db_ms": round(stats["ms"], 2),
            }
            logger.info("request", extra=fields)
            if self.slow_request_ms and duration > self.slow_request_ms:
                logger.warning("slow_request", extra=fields)
            db_stats_var.reset(stats_token)
            request_id_var.reset(token)
