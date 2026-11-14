"""GET /api/v1/dashboard - progress for clients, own work for staff, operations for managers."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

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
    calls: dict[str, int] | None
    # What the filters offer: `languages`, `dialects` and, for managers, `staff`.
    options: dict[str, Any]
    # The chosen days, when days were chosen.
    date_from: date | None
    date_to: date | None


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=7, le=90),
    mode: Literal["FACE_TO_FACE", "TELEPHONY"] | None = None,
    language: str | None = Query(
        default=None, max_length=35, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
    ),
    dialect: str | None = Query(default=None, min_length=1, max_length=100),
    status: str | None = Query(default=None, max_length=20),
    staff_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> DashboardOut:
    s = service.summary(
        db,
        principal,
        project_id=project_id,
        days=days,
        timezone=request.app.state.settings.report_timezone,
        filters=service.Filters(
            mode=mode,
            language=language,
            dialect=dialect,
            status=status,
            staff_id=staff_id,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    return DashboardOut.model_validate(s, from_attributes=True)
