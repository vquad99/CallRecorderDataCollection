"""GET /api/v1/dashboard - progress for clients, own work for staff, operations for managers."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, require
from app.modules.dashboard import service

router = APIRouter(tags=["dashboard"], dependencies=[Depends(require(Perm.DASHBOARD_VIEW))])


class ProjectRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class ModeOut(BaseModel):
    mode: str
    recorded_hours: float
    approved_hours: float
    recordings: int
    target_hours_per_day: float


class DayOut(BaseModel):
    day: date
    recorded_hours: float
    approved_hours: float


class TeamRow(BaseModel):
    name: str
    recordings: int
    recorded_hours: float


class DashboardOut(BaseModel):
    view: str
    timezone: str
    project_id: uuid.UUID | None
    projects: list[ProjectRef]
    recorded_hours: float
    approved_hours: float
    recordings: int
    target_hours_per_day: float
    today_hours: float
    by_mode: list[ModeOut]
    daily: list[DayOut]
    tasks_total: int
    tasks_approved: int
    tasks_by_status: dict[str, int] | None
    qc: dict[str, int] | None
    queues: dict[str, int] | None
    team: list[TeamRow] | None
    storage_bytes: int | None


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=7, le=90),
) -> DashboardOut:
    s = service.summary(
        db,
        principal,
        project_id=project_id,
        days=days,
        timezone=request.app.state.settings.report_timezone,
    )
    return DashboardOut.model_validate(s, from_attributes=True)
