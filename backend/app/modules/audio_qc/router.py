"""Audio quality check routes (AQC-*, D-079) and the recording details file."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, Storage
from app.core.permissions import Perm
from app.modules.audio_qc import checklist, service
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require

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
    # A pass approves the task: the project has no admin review (D-138).
    pass_approves: bool
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


Answer = Literal["yes", "no"]
Key = Annotated[str, Field(max_length=checklist.MAX_KEY)]
Side = Literal["A", "B"]


class AnswersIO(BaseModel):
    """QC checklist answers (D-146): conversation questions by key, speaker questions by side (A,
    B) and key, and the consent check by side (projects that take signed forms only). A question
    left out, or null, is not answered."""

    conversation: dict[Key, Answer | None] = Field(
        default_factory=dict, max_length=checklist.MAX_ITEMS
    )
    speakers: dict[Side, dict[Key, Answer | None]] = Field(default_factory=dict)
    consent: dict[Side, Answer | None] = Field(default_factory=dict)


class DecisionBody(BaseModel):
    # SEND_BACK_CONSENT (D-146): the audio is fine, a signed consent form is not.
    outcome: Literal["PASS", "FAIL", "SEND_BACK_CONSENT"]
    reason_code: str | None = Field(default=None, max_length=50)
    comment: str = Field(default="", max_length=2000)
    # The QC checklist's answers; needed complete for PASS and SEND_BACK_CONSENT.
    answers: AnswersIO | None = None


class ItemOut(BaseModel):
    key: str
    question: str
    scope: Literal["conversation", "speaker"]
    fails_on: Literal["yes", "no"] | None
    required: bool


class DraftOut(BaseModel):
    answers: AnswersIO
    saved_at: datetime
    saved_by_name: str | None


class RecordedParticipant(BaseModel):
    side: Side
    participant_id: uuid.UUID
    participant_code: str
    answers: dict[str, Answer]
    consent: Answer | None
    consent_form_id: uuid.UUID | None


class Failing(BaseModel):
    key: str
    side: Side | None
    answer: Answer


class RecordedAnswers(BaseModel):
    """A decision's answers as given (D-146): the questions as they read then, who and when."""

    outcome: str
    reason_code: str | None
    comment: str
    reviewer_name: str | None
    decided_at: datetime
    items: list[ItemOut]
    consent_check: bool
    conversation: dict[str, Answer]
    participants: list[RecordedParticipant]
    failing: list[Failing]


class ChecklistOut(BaseModel):
    # The project's QC checklist now.
    items: list[ItemOut]
    # The project takes signed consent forms: QC checks each one (D-144, D-146).
    consent_check: bool
    consent_question: str
    # The caller decides this task's QC and it waits for the decision.
    can_answer: bool
    # Answers not yet sent, for the person who decides (null for everyone else).
    draft: DraftOut | None
    # The newest decision's answers, for everyone who sees the task.
    latest: RecordedAnswers | None


@router.get("/tasks/{task_id}/audio-qc", response_model=AudioQcOut)
def audio_qc(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> AudioQcOut:
    return AudioQcOut.model_validate(service.view(db, principal, task_id))


@router.get("/tasks/{task_id}/audio-qc/checklist", response_model=ChecklistOut)
def qc_checklist(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> ChecklistOut:
    """The QC checklist of a task: its questions, the answers not yet sent and the newest
    decision's answers (D-146)."""
    return ChecklistOut.model_validate(service.checklist_view(db, principal, task_id))


@router.put("/tasks/{task_id}/audio-qc/draft", response_model=DraftOut)
def save_draft(
    task_id: uuid.UUID, body: AnswersIO, principal: CurrentPrincipal, db: DbSession
) -> DraftOut:
    """Keeps the answers while the QC Executive ticks, so a reload keeps them (D-146)."""
    draft = service.save_draft(db, principal, task_id, body.model_dump())
    return DraftOut(
        answers=AnswersIO.model_validate(draft.answers),
        saved_at=draft.updated_at,
        saved_by_name=principal.display_name,
    )


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
        db,
        principal,
        task_id,
        body.outcome,
        body.reason_code,
        body.comment,
        client_ip(request),
        answers=body.answers.model_dump() if body.answers else None,
    )
    return AudioQcOut.model_validate(service.view(db, principal, task_id))


@router.post("/tasks/{task_id}/audio-qc/recheck", response_model=AudioQcOut)
def recheck(
    task_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    storage: Storage,
) -> AudioQcOut:
    service.recheck(db, storage, settings, principal, task_id)
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
