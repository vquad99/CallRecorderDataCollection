"""/api/v1/audit-logs: read-only view of the append-only audit log (SEC-001)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.core.permissions import Perm
from app.modules.audit.models import AuditLog
from app.modules.auth.deps import DbSession, Principal, require
from app.modules.auth.models import User

router = APIRouter(prefix="/audit-logs", tags=["audit"])
Auditor = Annotated[Principal, Depends(require(Perm.AUDIT_VIEW))]


class AuditOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor_email: str | None
    action: str
    entity_type: str
    entity_id: str | None
    project_id: uuid.UUID | None
    before: Any
    after: Any
    ip: str | None
    request_id: str | None


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    page: int
    page_size: int


def _load(value: str | None) -> Any:
    return json.loads(value) if value else None


@router.get("", response_model=AuditPage)
def list_audit(
    principal: Auditor,
    db: DbSession,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=100)] = None,
    project_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    query = select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_id)
    if not principal.is_super_admin:
        # Project Admins see entries about their own projects only.
        query = query.where(
            AuditLog.project_id.in_(list(principal.project_ids) or [uuid.UUID(int=0)])
        )
    if action:
        query = query.where(or_(AuditLog.action == action, AuditLog.action.like(f"{action}.%")))
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if project_id:
        query = query.where(AuditLog.project_id == project_id)
    if since:
        query = query.where(AuditLog.created_at >= since)
    if until:
        query = query.where(AuditLog.created_at < until)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        AuditOut(
            id=log.id,
            created_at=log.created_at,
            actor_email=email,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            project_id=log.project_id,
            before=_load(log.before_summary),
            after=_load(log.after_summary),
            ip=log.ip,
            request_id=log.request_id,
        )
        for log, email in rows
    ]
    return AuditPage(items=items, total=int(total), page=page, page_size=page_size)
