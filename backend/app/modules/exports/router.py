"""/api/v1/projects/{project_id}/export (reports, D-094) and /exports (bundles, D-105)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.permissions import Perm
from app.core.storage import require_storage
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.exports import bundle, jobs, service
from app.modules.exports.models import ExportJob
from app.modules.projects.service import get_visible as get_visible_project
from app.modules.recordings.worker_dispatch import dispatch_export

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["exports"],
    dependencies=[Depends(require(Perm.EXPORTS_CREATE))],
)

Report = Literal["progress", "participants"]
Content = Literal["audio", "metadata", "both"]
Scope = Literal["approved", "finished"]
TableFormat = Literal["csv", "tsv"]
Mode = Literal["FACE_TO_FACE", "TELEPHONY"]
LANGUAGE = r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$"


class ExportSummary(BaseModel):
    recordings: int
    face_to_face: int
    telephony: int
    audio_bytes: int
    file_name: str


class ExportRequest(BaseModel):
    content: Content = "both"
    scope: Scope = "approved"
    table_format: TableFormat = "csv"
    mode: Mode | None = None
    language: str | None = Field(default=None, max_length=35, pattern=LANGUAGE)
    recorded_from: date | None = None
    recorded_to: date | None = None
    originals: bool = False
    contact: bool = False

    def selection(self) -> bundle.Selection:
        return bundle.Selection(**self.model_dump())


class ExportJobOut(BaseModel):
    id: uuid.UUID
    state: str
    content: str
    scope: str
    table_format: str
    filters: dict[str, Any]
    file_name: str
    recordings: int
    files: int
    size_bytes: int
    sha256: str | None
    error: str | None
    requested_by: str | None
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    downloads: int
    last_downloaded_at: datetime | None


class ExportJobPage(BaseModel):
    items: list[ExportJobOut]
    total: int
    page: int
    page_size: int


class ExportLink(BaseModel):
    url: str
    valid_seconds: int
    file_name: str
    sha256: str | None


def _out(job: ExportJob, requested_by: str | None) -> ExportJobOut:
    return ExportJobOut(
        id=job.id,
        state=job.state,
        content=job.content,
        scope=job.scope,
        table_format=job.table_format,
        filters=job.filters,
        file_name=job.file_name,
        recordings=job.recordings,
        files=job.files,
        size_bytes=job.size_bytes,
        sha256=job.sha256,
        error=job.error,
        requested_by=requested_by,
        created_at=job.created_at,
        finished_at=job.finished_at,
        expires_at=job.expires_at,
        downloads=job.downloads,
        last_downloaded_at=job.last_downloaded_at,
    )


@router.get("/export/summary", response_model=ExportSummary)
def summary(
    project_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    content: Content = "both",
    scope: Scope = "approved",
    mode: Mode | None = None,
    language: str | None = Query(default=None, max_length=35, pattern=LANGUAGE),
    recorded_from: date | None = None,
    recorded_to: date | None = None,
    originals: bool = False,
) -> ExportSummary:
    """What a bundle would hold, before asking for it."""
    project = get_visible_project(db, principal, project_id)
    sel = bundle.Selection(
        content=content,
        scope=scope,
        mode=mode,
        language=language,
        recorded_from=recorded_from,
        recorded_to=recorded_to,
        originals=originals,
    )
    bundle.check(db, principal, project, sel)
    entries = bundle.select_entries(db, project, sel, request.app.state.settings.report_timezone)
    return ExportSummary(
        recordings=len(entries),
        face_to_face=sum(1 for e in entries if e.mode == "FACE_TO_FACE"),
        telephony=sum(1 for e in entries if e.mode == "TELEPHONY"),
        audio_bytes=bundle.audio_bytes(sel, entries),
        file_name=bundle.file_name(project, sel),
    )


@router.get("/export")
def report(
    project_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    content: Report = "progress",
    table_format: Annotated[TableFormat, Query(alias="format")] = "csv",
) -> Response:
    """A report as one table: CSV, or TSV with `format=tsv`."""
    project = service.report_project(db, principal, project_id, content, table_format)
    body = service.report(db, project, content, table_format)
    service.record(db, principal, project, content, table_format, client_ip(request))
    name = service.file_name(project, content, table_format)
    media = "text/tab-separated-values" if table_format == "tsv" else "text/csv"
    return Response(
        content=body,
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/exports", response_model=ExportJobOut, status_code=202)
def request_export(
    project_id: uuid.UUID,
    body: ExportRequest,
    request: Request,
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ExportJobOut:
    """Ask for a bundle of recordings. It is made in the background: the answer is the job, to
    be looked at again until it is READY."""
    require_storage(request)
    job = jobs.create(
        db,
        request.app.state.settings,
        principal,
        project_id,
        body.selection(),
        client_ip(request),
    )
    dispatch_export(request.app, job.id, background)
    return _out(job, principal.display_name)


@router.get("/exports", response_model=ExportJobPage)
def list_exports(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=20, ge=1, le=50),
) -> ExportJobPage:
    listed, total = jobs.list_jobs(db, principal, project_id, page, page_size)
    return ExportJobPage(
        items=[_out(x.job, x.requested_by) for x in listed],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/exports/{job_id}", response_model=ExportJobOut)
def get_export(
    project_id: uuid.UUID, job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> ExportJobOut:
    found = jobs.get(db, principal, project_id, job_id)
    return _out(found.job, found.requested_by)


@router.post("/exports/{job_id}/download-link", response_model=ExportLink)
def export_download_link(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ExportLink:
    """A link to the bundle that works for a few minutes; every link is audited."""
    url, seconds, job = jobs.download_link(
        db,
        request.app.state.settings,
        require_storage(request),
        principal,
        project_id,
        job_id,
        client_ip(request),
    )
    return ExportLink(url=url, valid_seconds=seconds, file_name=job.file_name, sha256=job.sha256)


@router.delete("/exports/{job_id}", response_model=ExportJobOut)
def remove_export(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ExportJobOut:
    """Remove a bundle from storage now, or withdraw an export that has not started."""
    job = jobs.remove(
        db, request.app.state.storage, principal, project_id, job_id, client_ip(request)
    )
    return _out(job, None)
