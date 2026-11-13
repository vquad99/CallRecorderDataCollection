"""Write audit entries in the same transaction as the action they record."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.modules.audit.models import AuditLog

# Session.info key holding the Super Admin's id while they view the app as someone else (D-100).
VIEWER_KEY = "view_as_viewer_id"


def _summary(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None,
    actor_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    # A Super Admin viewing the app as someone else (D-100): the entry names the Super Admin, never
    # the person whose view it is.
    viewer = db.info.get(VIEWER_KEY)
    if viewer is not None and actor_id != viewer:
        after = {**(after or {}), "viewed_as": str(actor_id) if actor_id else None}
        actor_id = viewer
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            project_id=project_id,
            before_summary=_summary(before),
            after_summary=_summary(after),
            ip=ip,
            request_id=request_id_var.get(),
        )
    )
