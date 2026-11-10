"""Participant personal page API (D-067). Public: the personal link's secret, sent in the
X-Portal-Token header, is the only credential. Staff create and revoke links under the project."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.auth.router import AppSettings, Cipher
from app.modules.portal import service

public_router = APIRouter(prefix="/portal", tags=["participant page"])
staff_router = APIRouter(
    prefix="/projects/{project_id}/participants/{participant_id}/portal-link",
    tags=["participant page"],
    dependencies=[Depends(require(Perm.PARTICIPANTS_MANAGE))],
)

Token = Annotated[str, Header(alias="X-Portal-Token", min_length=1, max_length=300)]


class SessionOut(BaseModel):
    task_code: str
    mode: str
    day: datetime
    state: str
    minutes: float | None


class PortalOut(BaseModel):
    participant_code: str
    project_name: str
    language_code: str
    consent_policy_version: str
    consent_text: str
    consent_status: Literal["GIVEN", "REFUSED", "WITHDRAWN"] | None
    consent_at: datetime | None
    sessions: list[SessionOut]
    accepted_minutes: float
    link_expires_at: datetime


@public_router.get("/me", response_model=PortalOut)
def my_page(token: Token, db: DbSession) -> PortalOut:
    return PortalOut.model_validate(service.view(db, token), from_attributes=True)


class ConsentBody(BaseModel):
    decision: Literal["GIVEN", "REFUSED", "WITHDRAWN"]


@public_router.post("/consent", response_model=PortalOut)
def answer_consent(body: ConsentBody, token: Token, request: Request, db: DbSession) -> PortalOut:
    service.answer_consent(db, token, body.decision, client_ip(request))
    return PortalOut.model_validate(service.view(db, token), from_attributes=True)


class LinkOut(BaseModel):
    url: str
    expires_at: datetime


@staff_router.post("", response_model=LinkOut, status_code=201)
def create_link(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> LinkOut:
    url, expires = service.create_link(
        db, settings, principal, project_id, participant_id, client_ip(request)
    )
    return LinkOut(url=url, expires_at=expires)


class EmailedOut(BaseModel):
    sent: bool
    expires_at: datetime


@staff_router.post("/email", response_model=EmailedOut)
def email_link(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> EmailedOut:
    sent, expires = service.email_link(
        db,
        settings,
        cipher,
        request.app.state.email_sender,
        principal,
        project_id,
        participant_id,
        client_ip(request),
    )
    return EmailedOut(sent=sent, expires_at=expires)


@staff_router.delete("", status_code=204)
def revoke_link(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> None:
    service.revoke_link(db, principal, project_id, participant_id, client_ip(request))
