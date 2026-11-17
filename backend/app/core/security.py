"""Baseline HTTP security headers on every API response (SEC-013, first part), and the names of
the cookies and header the session and CSRF checks use (shared by the middleware, the rate limiter
and the auth dependencies).

The frontend's own Content-Security-Policy is set by the web server that serves it (Phase 10).
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SESSION_COOKIE = "ccp_session"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}
_HSTS = "max-age=31536000; includeSubDomains"
# API answers hold personal data (participants, consent, audit): never stored by a browser or a
# shared cache, and never rendered as a page (SEC-013).
_API_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _BASE_HEADERS.items():
                    headers.setdefault(name, value)
                if scope["path"].startswith("/api/"):
                    for name, value in _API_HEADERS.items():
                        headers.setdefault(name, value)
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", _HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
