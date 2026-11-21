"""Request context middleware (FND-005): request ID, access log, last-resort error handler.

Runs as the outermost application middleware so the request ID is set for every log line and
every response, including unexpected 500s, which it answers itself in the standard error format.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import deque
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.core.logging import request_id_var
from app.core.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, UNSAFE_METHODS
from app.db.session import db_stats_var

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


_CHUNK_PATH = re.compile(r"^/api/v1/recordings/[^/]+/chunks/[^/]+$")
# A participant's document upload (D-144): the scanned file itself is the body.
_DOCUMENT_PATH = re.compile(
    r"^/api/v1/projects/[^/]+/participants/[^/]+/documents/(consent-form|address-proof)$"
)
# A JSON \u0000 escape: preceded by an even number of backslashes (an odd number means the text
# itself contains a backslash followed by "u0000", which is allowed).
_JSON_NUL = re.compile(rb"(?<!\\)(?:\\\\)*\\u0000")
API_PREFIX = "/api/v1/"
# State-changing API calls that work without a session: signing in, the password links (reset and
# invitation), and the participant's own page, whose credential is the X-Portal-Token header. Every
# other one needs the session cookie, and every one needs the CSRF cookie and header.
SESSIONLESS_WRITES = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/password/forgot",
        "/api/v1/auth/password/reset",
        "/api/v1/portal/consent",
    }
)
# Bodies larger than this (or of unknown size) are read only a few at a time per process.
LARGE_BODY_BYTES = 256 * 1024
BODY_READ_SLOTS = 16
BODY_READ_WAIT_SECONDS = 15.0

_NUL = (422, "VALIDATION_ERROR", "Text must not contain NUL characters")
_BUSY = (503, "BUSY", "The service is busy. Try again in a moment.")


class RequestLimitsMiddleware:
    """Input limits applied before the application reads a request (SEC-006).

    Who: a state-changing API call without the CSRF cookie and header, or (outside
    SESSIONLESS_WRITES) without the session cookie, is refused before a byte of its body is read,
    with the answer the auth checks would give later. Only presence is checked here; the values
    are checked by the auth dependencies as before.

    Size: audio chunk uploads may be up to MAX_CHUNK_BYTES, a participant's document upload up to
    the document limit (participants/documents.MAX_DOCUMENT_BYTES, D-144), everything else up to
    MAX_REQUEST_BYTES; larger bodies get 413. The declared Content-Length is checked first; a body
    sent without one (chunked transfer) is read up to the limit and refused as soon as it passes
    it, so memory use stays bounded either way. At most BODY_READ_SLOTS large bodies are read at
    once in a process;
    others wait their turn and get 503 BUSY when no turn comes in BODY_READ_WAIT_SECONDS.

    NUL characters: PostgreSQL text cannot hold them, so a NUL in the path, the query string or a
    JSON body is refused with 422 here instead of failing as a server error deeper down (any caller,
    signed in or not, could otherwise trigger 500s at will). Binary bodies (audio chunks, uploaded
    documents) are not inspected.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: int,
        chunk_limit: int,
        document_limit: int,
        document_too_large: str = "",
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.chunk_limit = chunk_limit
        self.document_limit = document_limit
        self.document_too_large = document_too_large
        self._large_reads = asyncio.Semaphore(BODY_READ_SLOTS)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        if "\x00" in path or b"%00" in scope.get("query_string", b""):
            await _send_error(send, *_NUL)
            return
        if scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        refusal = _missing_credentials(path, headers) if path.startswith(API_PREFIX) else None
        if refusal is not None:
            await _send_error(send, *refusal)
            return
        is_chunk = bool(_CHUNK_PATH.match(path))
        is_document = bool(_DOCUMENT_PATH.match(path))
        limit = (
            self.chunk_limit
            if is_chunk
            else self.document_limit
            if is_document
            else self.default_limit
        )
        too_large = self.document_too_large if is_document else ""
        declared = headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await self._refuse(send, limit, too_large)
            return
        if declared is not None and int(declared) <= LARGE_BODY_BYTES:
            body = await _read(receive, limit)
        else:
            try:
                async with asyncio.timeout(BODY_READ_WAIT_SECONDS):
                    await self._large_reads.acquire()
            except TimeoutError:
                await _send_error(send, *_BUSY)
                return
            try:
                body = await _read(receive, limit)
            finally:
                self._large_reads.release()
        if body is None:
            await self._refuse(send, limit, too_large)
            return
        if not body.complete:
            return  # client went away before sending the whole body
        if not (is_chunk or is_document) and _JSON_NUL.search(body.joined()):
            await _send_error(send, *_NUL)
            return
        await self.app(scope, body.replay(receive), send)

    @staticmethod
    async def _refuse(send: Send, limit: int, message: str = "") -> None:
        await _send_error(
            send, 413, "PAYLOAD_TOO_LARGE", message or f"Request body is larger than {limit} bytes"
        )


class _Body:
    """A request body read ahead of the application, kept in the pieces it arrived in, so an audio
    part is not copied into one more buffer here."""

    def __init__(self) -> None:
        self.parts: deque[bytes] = deque()
        self.size = 0
        self.complete = False

    def joined(self) -> bytes:
        """The body as one piece (for the NUL check of a small JSON body); joined once."""
        if len(self.parts) != 1:
            whole = b"".join(self.parts)
            self.parts.clear()
            self.parts.append(whole)
        return self.parts[0]

    def replay(self, receive: Receive) -> Receive:
        """Hands the body to the application piece by piece, letting go of each piece as it goes;
        after the body, messages (such as a disconnect) come from the client again."""
        parts = self.parts
        sent_last = False

        async def replayed() -> Message:
            nonlocal sent_last
            if not sent_last:
                part = parts.popleft() if parts else b""
                sent_last = not parts
                return {"type": "http.request", "body": part, "more_body": not sent_last}
            return await receive()

        return replayed


async def _read(receive: Receive, limit: int) -> _Body | None:
    """The whole body (incomplete when the client went away), or None once it passes `limit`."""
    body = _Body()
    while True:
        message = await receive()
        if message["type"] != "http.request":
            return body
        part = message.get("body", b"")
        body.size += len(part)
        if body.size > limit:
            return None
        if part:
            body.parts.append(part)
        if not message.get("more_body", False):
            body.complete = True
            return body


def _missing_credentials(path: str, headers: Headers) -> tuple[int, str, str] | None:
    """The answer for a state-changing API call that cannot pass the auth checks, or None."""
    cookies = _cookie_names(headers.get("cookie", ""))
    if CSRF_COOKIE not in cookies or not headers.get(CSRF_HEADER):
        return 403, "CSRF_FAILED", "Missing or invalid CSRF token"
    if SESSION_COOKIE not in cookies and path not in SESSIONLESS_WRITES:
        return 401, "UNAUTHENTICATED", "Sign in required"
    return None


def _cookie_names(header: str) -> set[str]:
    """Names of the cookies that carry a value."""
    names = set()
    for pair in header.split(";"):
        name, sep, value = pair.partition("=")
        if sep and value.strip():
            names.add(name.strip())
    return names


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
