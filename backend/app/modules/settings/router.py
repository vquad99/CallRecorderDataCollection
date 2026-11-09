"""/api/v1/settings: capacity targets editable without a deployment (CAP-001, CAP-002)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import DbSession, Principal, client_ip, require
from app.modules.settings.models import SystemSetting

router = APIRouter(prefix="/settings", tags=["settings"])
Admin = Annotated[Principal, Depends(require(Perm.SETTINGS_MANAGE))]

# Editable keys and their bounds. Values live only in system_settings.
EDITABLE: dict[str, tuple[int, int]] = {
    "capacity.staff_accounts": (1, 100_000),
    "capacity.concurrent_conferences": (1, 10_000),
    "capacity.participants_per_conversation": (2, 2),
    "capacity.total_hours_per_day": (1, 1_000_000),
    "capacity.face_to_face_hours_per_day": (0, 1_000_000),
    "capacity.telephony_hours_per_day": (0, 1_000_000),
}


class SettingOut(BaseModel):
    key: str
    value: int | None
    min_value: int
    max_value: int
    updated_at: datetime


def _rows(db: DbSession) -> list[SystemSetting]:
    return list(
        db.scalars(
            select(SystemSetting).where(SystemSetting.key.in_(EDITABLE)).order_by(SystemSetting.key)
        ).all()
    )


def _out(row: SystemSetting) -> SettingOut:
    low, high = EDITABLE[row.key]
    return SettingOut(
        key=row.key, value=row.value_int, min_value=low, max_value=high, updated_at=row.updated_at
    )


@router.get("", response_model=list[SettingOut])
def list_settings(_: Admin, db: DbSession) -> list[SettingOut]:
    return [_out(r) for r in _rows(db)]


class UpdateSettings(BaseModel):
    values: dict[str, int] = Field(min_length=1, max_length=len(EDITABLE))


@router.patch("", response_model=list[SettingOut])
def update_settings(
    body: UpdateSettings, request: Request, admin: Admin, db: DbSession
) -> list[SettingOut]:
    unknown = sorted(set(body.values) - set(EDITABLE))
    if unknown:
        raise AppError(
            f"Unknown setting: {', '.join(unknown)}", code="UNKNOWN_SETTING", status_code=422
        )
    for key, value in body.values.items():
        low, high = EDITABLE[key]
        if not low <= value <= high:
            raise AppError(
                f"{key} must be between {low} and {high}", code="OUT_OF_RANGE", status_code=422
            )
    rows = {r.key: r for r in _rows(db)}
    before = {k: rows[k].value_int for k in body.values if k in rows}
    for key, value in body.values.items():
        row = rows.get(key)
        if row is None:
            row = SystemSetting(key=key, value_type="int")
            db.add(row)
        row.value_int = value
        row.updated_by = admin.user_id
    audit.record(
        db,
        action="settings.changed",
        entity_type="system_settings",
        entity_id=None,
        actor_id=admin.user_id,
        ip=client_ip(request),
        before=before,
        after=dict(body.values),
    )
    db.commit()
    return [_out(r) for r in _rows(db)]
