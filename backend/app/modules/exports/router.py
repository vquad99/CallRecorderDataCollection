"""/api/v1/projects/{project_id}/export (D-094)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.core.permissions import Perm
from app.core.storage import require_storage
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.exports import service

router = APIRouter(
    prefix="/projects/{project_id}/export",
    tags=["exports"],
    dependencies=[Depends(require(Perm.EXPORTS_CREATE))],
)

Content = Literal["audio", "metadata", "both", "progress", "participants"]
Scope = Literal["approved", "finished"]


class ExportSummary(BaseModel):
    recordings: int
    audio_bytes: int
    file_name: str


@router.get("/summary", response_model=ExportSummary)
def summary(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    content: Content = "both",
    scope: Scope = "approved",
) -> ExportSummary:
    """What an export would hold, before downloading it."""
    p = service.plan(db, principal, project_id, content, scope)
    return ExportSummary(
        recordings=len(p.entries), audio_bytes=p.total_bytes, file_name=service.file_name(p)
    )


@router.get("")
def export(
    project_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    content: Content = "both",
    scope: Scope = "approved",
) -> Response:
    p = service.plan(db, principal, project_id, content, scope)
    name = service.file_name(p)
    disposition = {"Content-Disposition": f'attachment; filename="{name}"'}
    if content in service.REPORTS:
        body = (
            service.progress_csv(db, p.project)
            if content == "progress"
            else service.participants_csv(db, p.project)
        )
        service.record(db, principal, p, client_ip(request))
        return Response(content=body, media_type="text/csv; charset=utf-8", headers=disposition)
    storage = (
        require_storage(request) if content in ("audio", "both") else request.app.state.storage
    )
    service.record(db, principal, p, client_ip(request))
    return StreamingResponse(
        service.stream_zip(p, storage, request.app.state.session_factory),
        media_type="application/zip",
        # Sent as it is made; nginx must not hold it back to buffer it (D-094).
        headers={**disposition, "X-Accel-Buffering": "no"},
    )
