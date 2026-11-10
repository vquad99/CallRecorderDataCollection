"""Audio quality check routes (AQC-*, D-079) and the recording details file."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.core.permissions import Perm
from app.core.storage import require_storage
from app.modules.audio_qc import service
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.auth.router import AppSettings

router = APIRouter(tags=["audio-qc"], dependencies=[Depends(require(Perm.TASKS_VIEW))])
metadata_router = APIRouter(
    tags=["recordings"], dependencies=[Depends(require(Perm.RECORDINGS_DOWNLOAD))]
)


class CheckOut(BaseModel):
    code: str
    state: str
    measured: str
    expected: str
    message: str


class ResultOut(BaseModel):
    id: uuid.UUID
    recording_id: uuid.UUID
    asset_id: uuid.UUID | None
    automated: bool
    outcome: str
    reason_code: str | None
    comment: str
    reviewer_name: str | None
    created_at: datetime
    duration_ms: int | None
    silence_pct: float | None
    clip_pct: float | None
    peak_dbfs: float | None
    rms_dbfs: float | None
    dynamic_range_db: float | None
    duplicate_of_recording_id: uuid.UUID | None
    checks: list[CheckOut]


class AudioQcOut(BaseModel):
    task_status: str
    qc_user_id: uuid.UUID | None
    qc_name: str | None
    can_decide: bool
    can_assign: bool
    can_recheck: bool
    reasons: dict[str, list[str]]
    results: list[ResultOut]


class AssignQcBody(BaseModel):
    user_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class DecisionBody(BaseModel):
    outcome: Literal["PASS", "FAIL", "RETURN"]
    reason_code: str | None = Field(default=None, max_length=50)
    comment: str = Field(default="", max_length=2000)


@router.get("/tasks/{task_id}/audio-qc", response_model=AudioQcOut)
def audio_qc(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> AudioQcOut:
    return AudioQcOut.model_validate(service.view(db, principal, task_id))


@router.post("/tasks/{task_id}/assign-qc", response_model=AudioQcOut)
def assign_qc(
    task_id: uuid.UUID,
    body: AssignQcBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> AudioQcOut:
    service.assign_qc(db, principal, task_id, body.user_id, body.reason, client_ip(request))
    return AudioQcOut.model_validate(service.view(db, principal, task_id))


@router.post("/tasks/{task_id}/audio-qc/decision", response_model=AudioQcOut)
def decide(
    task_id: uuid.UUID,
    body: DecisionBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> AudioQcOut:
    service.decide(
        db, principal, task_id, body.outcome, body.reason_code, body.comment, client_ip(request)
    )
    return AudioQcOut.model_validate(service.view(db, principal, task_id))


@router.post("/tasks/{task_id}/audio-qc/recheck", response_model=AudioQcOut)
def recheck(
    task_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> AudioQcOut:
    service.recheck(db, require_storage(request), settings, principal, task_id)
    return AudioQcOut.model_validate(service.view(db, principal, task_id))


@metadata_router.get("/recordings/{recording_id}/metadata")
def recording_metadata(
    recording_id: uuid.UUID, request: Request, principal: CurrentPrincipal, db: DbSession
) -> Response:
    """The details file that goes with the audio and the consent record (D-079)."""
    name, body = service.metadata(db, principal, recording_id, client_ip(request))
    return Response(
        content=json.dumps(body, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
