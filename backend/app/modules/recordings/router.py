"""Recording, asset-link and storage-usage routes (FTF-*, STOR-*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Path, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.permissions import Perm
from app.core.storage import require_storage
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.auth.router import AppSettings
from app.modules.recordings import service
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.recordings.worker_dispatch import dispatch_processing
from app.modules.tasks import service as tasks

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
    assets: list[AssetOut] = []


def out(rec: Recording, assets: list[AudioAsset] | None = None) -> RecordingOut:
    base = RecordingOut.model_validate(
        {
            **{
                k: getattr(rec, k)
                for k in RecordingOut.model_fields
                if k not in ("saved_seconds", "assets")
            },
            "saved_seconds": round(rec.frames_received / rec.native_sample_rate, 2),
            "assets": [],
        }
    )
    base.assets = [AssetOut.model_validate(a, from_attributes=True) for a in assets or []]
    return base


class StartBody(BaseModel):
    native_sample_rate: int = Field(ge=8000, le=192000)
    # Channels the capture delivers (every one is kept in the original); the server derives
    # channel_handling from it, so the record cannot disagree with the file (D-048).
    channel_count: int = Field(ge=1, le=8)
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
    recs = db.scalars(
        select(Recording).where(Recording.task_id == task.id).order_by(Recording.started_at.desc())
    ).all()
    return [out(r) for r in recs]


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
def get_recording(
    recording_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> RecordingOut:
    rec, assets = service.assets_for(db, principal, recording_id)
    return out(rec, assets)


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
    x_content_sha256: Annotated[str, Header(min_length=64, max_length=64)],
) -> ChunkOut:
    storage = require_storage(request)
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
