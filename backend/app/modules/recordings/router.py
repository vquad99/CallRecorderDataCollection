"""Recording, asset-link and storage-usage routes (FTF-*, STOR-*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Path, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AppSettings, Storage
from app.core.permissions import Perm
from app.core.storage import require_storage
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.projects.models import Project
from app.modules.recordings import access, consent_form, service
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.recordings.worker_dispatch import dispatch_processing
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task

router = APIRouter(tags=["recordings"], dependencies=[Depends(require(Perm.RECORDINGS_VIEW))])
usage_router = APIRouter(tags=["storage"], dependencies=[Depends(require(Perm.DASHBOARD_VIEW))])


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: str
    version: int
    parent_asset_id: uuid.UUID | None
    file_extension: str
    container: str
    codec: str
    sample_format: str
    sample_rate: int
    bit_depth: int
    channels: int
    duration_ms: int
    size_bytes: int
    sha256: str
    peak_dbfs: float | None
    rms_dbfs: float | None
    clip_count: int
    clip_pct: float
    silence_pct: float
    # Effective speech (D-148): the time someone speaks, the longest pause inside the speech, and
    # how many pauses are longer than the project's limit (pause_limit_seconds). Null until the
    # file is measured; the count also where the project is not known to the route.
    effective_ms: int | None = None
    longest_pause_ms: int | None = None
    long_pauses: int | None = None
    pause_limit_seconds: int | None = None
    created_at: datetime


class RecordingOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    state: str
    native_sample_rate: int
    channel_count: int
    device_channel_count: int | None
    channel_handling: str
    echo_cancellation: bool | None
    noise_suppression: bool | None
    auto_gain_control: bool | None
    device_label: str
    chunks_received: int
    saved_seconds: float
    interrupted: bool
    interruption_reason: str | None
    failure_reason: str | None
    started_at: datetime
    ended_at: datetime | None
    # The task's current recording: its newest finished one, the one QC checks and an export
    # delivers. An older finished one was replaced by the moderator's Record again (D-135).
    current: bool = False
    assets: list[AssetOut] = []


def asset_out(asset: AudioAsset, pause_limit_seconds: int | None = None) -> AssetOut:
    """A file's record; with the project's pause limit, how many pauses are over it (D-148)."""
    item = AssetOut.model_validate(asset, from_attributes=True)
    if pause_limit_seconds is not None and asset.effective_ms is not None:
        item.pause_limit_seconds = pause_limit_seconds
        item.long_pauses = sum(1 for p in asset.pauses_ms or () if p > pause_limit_seconds * 1000)
    return item


def out(
    rec: Recording,
    assets: list[AudioAsset] | None = None,
    *,
    current: bool = False,
    pause_limit_seconds: int | None = None,
) -> RecordingOut:
    base = RecordingOut.model_validate(
        {
            **{
                k: getattr(rec, k)
                for k in RecordingOut.model_fields
                if k not in ("saved_seconds", "assets", "current")
            },
            "saved_seconds": round(rec.frames_received / rec.native_sample_rate, 2),
            "current": current,
            "assets": [],
        }
    )
    base.assets = [asset_out(a, pause_limit_seconds) for a in assets or []]
    return base


class StartBody(BaseModel):
    # What a browser captures at most; the project's own rate (16 kHz) is checked by the service
    # (D-123). Kept low so no recording can grow beyond what the platform delivers.
    native_sample_rate: int = Field(ge=8000, le=48000)
    # Channels the capture delivers (every one is kept in the original); the server derives
    # channel_handling from it, so the record cannot disagree with the file (D-048). One or two:
    # a phone or laptop microphone, or a stereo headset.
    channel_count: int = Field(ge=1, le=2)
    # What the browser reports for the microphone, which may have more channels than captured.
    device_channel_count: int | None = Field(default=None, ge=1, le=32)
    echo_cancellation: bool | None
    noise_suppression: bool | None
    auto_gain_control: bool | None
    device_label: str = Field(default="", max_length=300)
    user_agent: str = Field(default="", max_length=500)


@router.post("/tasks/{task_id}/recordings", response_model=RecordingOut, status_code=201)
def start_recording(
    task_id: uuid.UUID,
    body: StartBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RecordingOut:
    require_storage(request)  # after input validation: a bad request is 422 even without storage
    return out(
        service.start(
            db, principal, task_id, service.StartInput(**body.model_dump()), client_ip(request)
        )
    )


@router.get("/tasks/{task_id}/recordings", response_model=list[RecordingOut])
def task_recordings(
    task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[RecordingOut]:
    task = tasks.get_task(db, principal, task_id)
    # Replaced recordings only for the people who run the project and the moderator (D-135).
    recs, current = access.listed(db, principal, task)
    # Each recording comes with its files, so the task page can offer Listen and the download
    # without a request per recording. One query for all of them (the task page relied on this
    # since D-092 and showed "No finished recording yet" without it).
    files: dict[uuid.UUID, list[AudioAsset]] = {r.id: [] for r in recs}
    if recs and principal.can_in_project(Perm.RECORDINGS_VIEW, task.project_id):
        for asset in db.scalars(
            select(AudioAsset)
            .where(AudioAsset.recording_id.in_(list(files)), AudioAsset.deleted_at.is_(None))
            .order_by(AudioAsset.kind, AudioAsset.version)
        ):
            files[asset.recording_id].append(asset)
    limit = _pause_limit(db, task.project_id)
    return [out(r, files[r.id], current=r.id == current, pause_limit_seconds=limit) for r in recs]


def _pause_limit(db: Session, project_id: uuid.UUID) -> int | None:
    """The project's pause limit (D-148), for the long pauses of its files."""
    return db.scalar(select(Project.pause_limit_seconds).where(Project.id == project_id))


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
def get_recording(
    recording_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> RecordingOut:
    rec, assets = service.assets_for(db, principal, recording_id)
    project_id = db.scalar(select(Task.project_id).where(Task.id == rec.task_id))
    return out(
        rec,
        assets,
        current=access.current_id(db, rec.task_id) == rec.id,
        pause_limit_seconds=_pause_limit(db, project_id) if project_id else None,
    )


class ChunkOut(BaseModel):
    seq: int
    size_bytes: int
    sha256: str


@router.put("/recordings/{recording_id}/chunks/{seq}", response_model=ChunkOut)
async def put_chunk(
    recording_id: uuid.UUID,
    seq: Annotated[int, Path(ge=0, le=1_000_000)],
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    storage: Storage,
    x_content_sha256: Annotated[str, Header(min_length=64, max_length=64)],
) -> ChunkOut:
    data = await request.body()
    chunk = await run_in_threadpool(
        service.put_chunk,
        db,
        settings,
        storage,
        principal,
        recording_id,
        seq,
        data,
        x_content_sha256,
    )
    return ChunkOut(seq=chunk.seq, size_bytes=chunk.size_bytes, sha256=chunk.sha256)


class ReasonBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/recordings/{recording_id}/interrupted", response_model=RecordingOut)
def interrupted(
    recording_id: uuid.UUID,
    body: ReasonBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RecordingOut:
    return out(
        service.mark_interrupted(db, principal, recording_id, body.reason, client_ip(request))
    )


class CompleteBody(BaseModel):
    chunk_count: int = Field(ge=0, le=1_000_000)


@router.post("/recordings/{recording_id}/complete", response_model=RecordingOut)
def complete(
    recording_id: uuid.UUID,
    body: CompleteBody,
    request: Request,
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RecordingOut:
    require_storage(request)
    rec = service.complete(db, principal, recording_id, body.chunk_count, client_ip(request))
    dispatch_processing(request.app, rec.id, background)
    return out(rec)


@router.post("/recordings/{recording_id}/discard", response_model=RecordingOut)
def discard(
    recording_id: uuid.UUID,
    body: ReasonBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RecordingOut:
    storage = require_storage(request)
    return out(
        service.discard(db, storage, principal, recording_id, body.reason, client_ip(request))
    )


class UrlBody(BaseModel):
    purpose: Literal["play", "download"]


class UrlOut(BaseModel):
    url: str
    expires_in: int


@router.get("/recordings/{recording_id}/consent-form")
def consent_form_file(
    recording_id: uuid.UUID, request: Request, principal: CurrentPrincipal, db: DbSession
) -> Response:
    """The consent record that goes with this recording, as a printable file (D-068)."""
    name, html = consent_form.build(db, principal, recording_id, client_ip(request))
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/assets/{asset_id}/url", response_model=UrlOut)
def asset_url(
    asset_id: uuid.UUID,
    body: UrlBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> UrlOut:
    storage = require_storage(request)
    url, seconds = service.asset_url(
        db, storage, settings, principal, asset_id, body.purpose, client_ip(request)
    )
    return UrlOut(url=url, expires_in=seconds)


class UsageRow(BaseModel):
    project_code: str
    kind: str
    files: int
    bytes: int


@usage_router.get("/storage/usage", response_model=list[UsageRow])
def storage_usage(principal: CurrentPrincipal, db: DbSession) -> list[UsageRow]:
    return [
        UsageRow(project_code=c, kind=k, files=n, bytes=b)
        for c, k, n, b in service.usage(db, principal)
    ]
