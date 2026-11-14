"""Versioned API root (FND-012). Every module router is mounted here under /api/v1."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app import __version__
from app.api.health import readiness
from app.core.permissions import Perm
from app.core.ratelimit import rate_limit
from app.modules.audio_qc.router import metadata_router as recording_metadata_router
from app.modules.audio_qc.router import router as audio_qc_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.deps import csrf_protect, require
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.exports.router import router as exports_router
from app.modules.operations import service as operations
from app.modules.participants.router import router as participants_router
from app.modules.portal.router import admin_view_router as portal_admin_view_router
from app.modules.portal.router import public_router as portal_public_router
from app.modules.portal.router import staff_router as portal_staff_router
from app.modules.projects.router import router as projects_router
from app.modules.recordings.router import router as recordings_router
from app.modules.recordings.router import usage_router as storage_usage_router
from app.modules.settings.router import router as settings_router
from app.modules.tasks.router import router as tasks_router
from app.modules.telephony.router import router as telephony_router
from app.modules.telephony.router import users_router as telephony_users_router
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


class AlertOut(BaseModel):
    code: str
    summary: str
    count: int
    since: datetime


class AlertsOut(BaseModel):
    # Whether anyone is told by email (ALERT_EMAIL), and to how many addresses.
    email_configured: bool
    recipients: int
    active: list[AlertOut]


class SystemStatus(BaseModel):
    status: str
    checks: dict[str, str]
    version: VersionInfo
    # What the platform found wrong with itself at its last look (D-109).
    alerts: AlertsOut


@api_router.get(
    "/system/status",
    response_model=SystemStatus,
    tags=["meta"],
    dependencies=[Depends(require(Perm.SETTINGS_MANAGE))],
)
def system_status(request: Request) -> SystemStatus:
    """Component health for the Super Admin's System status page (owner 2026-11-11: only the
    Super Admin sees it). /health/ready stays for the load balancer, private networks only."""
    body, _ = readiness(request.app)
    to = operations.recipients(request.app.state.settings)
    with request.app.state.session_factory() as db:
        found = [
            AlertOut(code=a.code, summary=a.summary, count=a.count, since=a.first_seen_at)
            for a in operations.active(db)
        ]
    return SystemStatus(
        status=body["status"],
        checks=body["checks"],
        version=version(request),
        alerts=AlertsOut(email_configured=bool(to), recipients=len(to), active=found),
    )


api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(projects_router)
api_router.include_router(settings_router)
api_router.include_router(participants_router)
api_router.include_router(tasks_router)
api_router.include_router(telephony_router)
api_router.include_router(telephony_users_router)
api_router.include_router(audit_router)
api_router.include_router(recordings_router)
api_router.include_router(audio_qc_router)
api_router.include_router(recording_metadata_router)
api_router.include_router(storage_usage_router)
api_router.include_router(dashboard_router)
api_router.include_router(exports_router)
api_router.include_router(portal_public_router)
api_router.include_router(portal_admin_view_router)
api_router.include_router(portal_staff_router)
