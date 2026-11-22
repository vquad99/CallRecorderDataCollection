"""Participant personal page API (D-067). Public: the personal link's secret, sent in the
X-Portal-Token header, is the only credential. Staff email and revoke links under the project;
the link itself goes only to the participant's email, never to staff."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from app.api.deps import AppSettings, Cipher, Mailer
from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.portal import service

public_router = APIRouter(prefix="/portal", tags=["participant page"])
staff_router = APIRouter(
    prefix="/projects/{project_id}/participants/{participant_id}/portal-link",
    tags=["participant page"],
    dependencies=[Depends(require(Perm.PARTICIPANTS_MANAGE))],
)

# The participant's page as they see it, for a Super Admin (D-100); read-only, no link needed.
admin_view_router = APIRouter(
    prefix="/projects/{project_id}/participants/{participant_id}/page",
    tags=["participant page"],
    dependencies=[Depends(require(Perm.PARTICIPANTS_VIEW))],
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
    display_name: str
    dialect: str
    phone_hint: str | None
    project_name: str
    language_code: str
    # The form they agreed to when they agreed (D-068), otherwise the project's current one.
    consent_policy_version: str
    consent_text: str
    # Their consent as it counts now (D-129): their answer, or UPLOADED when staff uploaded their
    # signed form in a project that takes them (D-144); empty when there is none yet. consent_at
    # is when it was given (the answer, or the upload).
    consent_status: Literal["GIVEN", "REFUSED", "WITHDRAWN", "UPLOADED"] | None
    consent_at: datetime | None
    sessions: list[SessionOut]
    accepted_minutes: float
    recorded_minutes: float
    payable_minutes: float
    link_expires_at: datetime | None


@public_router.get("/me", response_model=PortalOut)
def my_page(token: Token, db: DbSession) -> PortalOut:
    return PortalOut.model_validate(service.view(db, token), from_attributes=True)


class ConsentBody(BaseModel):
    # Nobody can withdraw consent (D-129): WITHDRAWN is refused with 422.
    decision: Literal["GIVEN", "REFUSED"]


@public_router.post("/consent", response_model=PortalOut)
def answer_consent(
    body: ConsentBody,
    token: Token,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> PortalOut:
    service.answer_consent(db, settings, cipher, token, body.decision, client_ip(request))
    return PortalOut.model_validate(service.view(db, token), from_attributes=True)


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
    mailer: Mailer,
) -> EmailedOut:
    sent, expires = service.email_link(
        db,
        settings,
        cipher,
        mailer,
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


@admin_view_router.get("", response_model=PortalOut)
def admin_view(
    project_id: uuid.UUID, participant_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> PortalOut:
    page = service.view_for_admin(db, principal, project_id, participant_id)
    return PortalOut.model_validate(page, from_attributes=True)
