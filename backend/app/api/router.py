"""Versioned API root (FND-012). Every module router is mounted here under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app import __version__
from app.core.ratelimit import rate_limit
from app.modules.audit.router import router as audit_router
from app.modules.auth.deps import csrf_protect
from app.modules.auth.router import router as auth_router
from app.modules.participants.router import router as participants_router
from app.modules.projects.router import router as projects_router
from app.modules.recordings.router import router as recordings_router
from app.modules.recordings.router import usage_router as storage_usage_router
from app.modules.settings.router import router as settings_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router

# Every state-changing request under /api/v1 must carry the CSRF token (SEC-007).
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(rate_limit), Depends(csrf_protect)])


class VersionInfo(BaseModel):
    name: str
    version: str
    environment: str


@api_router.get("/version", response_model=VersionInfo, tags=["meta"])
def version(request: Request) -> VersionInfo:
    return VersionInfo(
        name="conversation-collection-platform",
        version=__version__,
        environment=request.app.state.settings.app_env,
    )


api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(projects_router)
api_router.include_router(settings_router)
api_router.include_router(participants_router)
api_router.include_router(tasks_router)
api_router.include_router(audit_router)
api_router.include_router(recordings_router)
api_router.include_router(storage_usage_router)
