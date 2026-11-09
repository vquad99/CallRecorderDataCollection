"""/api/v1/projects/{project_id}/participants (PART-*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, Principal, client_ip, require
from app.modules.auth.router import AppSettings, Cipher
from app.modules.auth.security import FieldCipher
from app.modules.participants import service
from app.modules.participants.models import Participant
from app.modules.projects.models import Project

router = APIRouter(
    prefix="/projects/{project_id}/participants",
    tags=["participants"],
    dependencies=[Depends(require(Perm.PARTICIPANTS_VIEW))],
)

MASK = "••••••"


class ParticipantOut(BaseModel):
    id: uuid.UUID
    participant_code: str
    language_code: str
    dialect: str
    display_label: str | None
    phone: str | None
    has_phone: bool
    notes: str | None
    deleted: bool
    created_at: datetime


def present(
    db: DbSession, principal: Principal, cipher: FieldCipher, project: Project, p: Participant
) -> ParticipantOut:
    v = service.visibility(db, principal, project, p.id)
    if p.phone_e164_enc is None:
        phone = None
    elif v.contact:
        phone = cipher.decrypt(p.phone_e164_enc)
    else:
        phone = f"{MASK}{p.phone_hint}"
    return ParticipantOut(
        id=p.id,
        participant_code=p.participant_code,
        language_code=p.language_code,
        dialect=p.dialect,
        display_label=p.display_label if v.profile else None,
        phone=phone if v.profile or v.contact else None,
        has_phone=p.phone_e164_enc is not None,
        notes=p.notes if v.notes else None,
        deleted=p.deleted_at is not None,
        created_at=p.created_at,
    )


class ParticipantPage(BaseModel):
    items: list[ParticipantOut]
    total: int
    page: int
    page_size: int


@router.get("", response_model=ParticipantPage)
def list_participants(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ParticipantPage:
    project, items, total = service.list_participants(
        db, principal, project_id, search=search, page=page, page_size=page_size
    )
    return ParticipantPage(
        items=[present(db, principal, cipher, project, p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


class ParticipantBody(BaseModel):
    display_label: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    language_code: str = Field(
        min_length=2, max_length=35, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
    )
    dialect: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=5000)

    def to_input(self) -> service.ParticipantInput:
        return service.ParticipantInput(**self.model_dump())


@router.post("", response_model=ParticipantOut, status_code=201)
def create_participant(
    project_id: uuid.UUID,
    body: ParticipantBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.create_participant(
        db, settings, cipher, principal, project_id, body.to_input(), client_ip(request)
    )
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


class LinkBody(BaseModel):
    participant_code: str = Field(min_length=2, max_length=20)


@router.post("/link", response_model=ParticipantOut, status_code=201)
def link_participant(
    project_id: uuid.UUID,
    body: LinkBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.link_existing(db, principal, project_id, body.participant_code, client_ip(request))
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


@router.get("/export")
def export_contacts(
    project_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> Response:
    return Response(
        content=service.export_contacts(db, cipher, principal, project_id, client_ip(request)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="participants.csv"'},
    )


@router.get("/{participant_id}", response_model=ParticipantOut)
def get_participant(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> ParticipantOut:
    project, p = service.get_in_project(db, principal, project_id, participant_id)
    return present(db, principal, cipher, project, p)


@router.patch("/{participant_id}", response_model=ParticipantOut)
def correct_participant(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: ParticipantBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.correct_participant(
        db,
        settings,
        cipher,
        principal,
        project_id,
        participant_id,
        body.to_input(),
        client_ip(request),
    )
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


class DeleteBody(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/{participant_id}/delete", response_model=ParticipantOut)
def delete_participant(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: DeleteBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.delete_participant(
        db, principal, project_id, participant_id, body.reason, client_ip(request)
    )
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


class ConsentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID | None
    status: Literal["GIVEN", "REFUSED", "WITHDRAWN"]
    method: str
    policy_version: str
    captured_by: uuid.UUID
    note: str
    created_at: datetime


@router.get("/{participant_id}/consent", response_model=list[ConsentOut])
def consent_history(
    project_id: uuid.UUID, participant_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[ConsentOut]:
    return [
        ConsentOut.model_validate(r, from_attributes=True)
        for r in service.consent_history(db, principal, project_id, participant_id)
    ]
