"""Application factory (FND-002).

Run: uvicorn app.main:create_app --factory
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import Settings, load_settings
from app.core.email import build_sender
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    RequestLimitsMiddleware,
)
from app.core.ratelimit import build_limiter
from app.core.security import SecurityHeadersMiddleware
from app.core.storage import build_storage
from app.db.session import create_db_engine, make_session_factory
from app.modules.auth.security import FieldCipher


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level, settings.secret_values())
    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    docs = settings.api_docs_enabled
    app = FastAPI(
        title="Conversation Collection Platform API",
        version=__version__,
        docs_url="/api/v1/docs" if docs else None,
        swagger_ui_oauth2_redirect_url="/api/v1/docs/oauth2-redirect",
        openapi_url="/api/v1/openapi.json" if docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.cipher = FieldCipher(settings.data_encryption_key.get_secret_value())
    app.state.email_sender = build_sender(settings)
    app.state.rate_limiter = build_limiter(settings)
    app.state.storage = build_storage(settings)
    app.state.celery = None
    if settings.redis_url is not None:
        from celery import Celery

        app.state.celery = Celery("ccp", broker=settings.redis_url.get_secret_value())

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)

    # Added last = outermost: request context wraps CORS and security headers, which wrap the body
    # size limit, so a 413 still carries the request ID and the security headers.
    app.add_middleware(
        RequestLimitsMiddleware,
        default_limit=settings.max_request_bytes,
        chunk_limit=settings.max_chunk_bytes,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.app_env == "production")
    app.add_middleware(RequestContextMiddleware)
    return app
