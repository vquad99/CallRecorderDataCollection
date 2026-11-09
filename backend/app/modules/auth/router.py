"""/api/v1/auth routes (AUTH-001..016)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.modules.auth import service
from app.modules.auth.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    CurrentPrincipal,
    DbSession,
    Principal,
    client_ip,
    load_principal,
)
from app.modules.auth.security import FieldCipher, new_token

router = APIRouter(prefix="/auth", tags=["auth"])


def settings_of(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def cipher_of(request: Request) -> FieldCipher:
    cipher: FieldCipher = request.app.state.cipher
    return cipher


AppSettings = Annotated[Settings, Depends(settings_of)]
Cipher = Annotated[FieldCipher, Depends(cipher_of)]


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=10)


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    project_ids: list[uuid.UUID]
    mfa_enabled: bool


def me_from(p: Principal) -> MeOut:
    return MeOut(
        id=p.user_id,
        email=p.email,
        display_name=p.display_name,
        roles=sorted(p.roles),
        permissions=sorted(p.permissions),
        project_ids=sorted(p.project_ids, key=str),
        mfa_enabled=p.mfa_enabled,
    )


def _set_cookie(
    response: Response, settings: Settings, key: str, value: str, *, http_only: bool, max_age: int
) -> None:
    response.set_cookie(
        key,
        value,
        max_age=max_age,
        httponly=http_only,
        secure=settings.cookies_secure,
        samesite="strict",
        path="/",
    )


def _clear_cookies(response: Response, settings: Settings) -> None:
    for key in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(key, path="/", secure=settings.cookies_secure, samesite="strict")


@router.get("/csrf", status_code=204)
def csrf(request: Request, response: Response, settings: AppSettings) -> None:
    """Sets the CSRF cookie a browser needs before its first POST (e.g. sign-in)."""
    if not request.cookies.get(CSRF_COOKIE):
        _set_cookie(
            response, settings, CSRF_COOKIE, new_token(), http_only=False, max_age=12 * 3600
        )


@router.post("/login", response_model=MeOut)
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> MeOut:
    result = service.login(
        db,
        settings,
        cipher,
        email=body.email,
        password=body.password,
        totp_code=body.totp_code,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    max_age = settings.session_absolute_hours * 3600
    _set_cookie(response, settings, SESSION_COOKIE, result.token, http_only=True, max_age=max_age)
    _set_cookie(response, settings, CSRF_COOKIE, new_token(), http_only=False, max_age=max_age)
    return me_from(load_principal(db, result.user, result.session_id))


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> None:
    service.logout(db, principal.session_id, principal.user_id, client_ip(request))
    _clear_cookies(response, settings)


@router.get("/me", response_model=MeOut)
def me(principal: CurrentPrincipal) -> MeOut:
    return me_from(principal)


class ForgotBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)


@router.post("/password/forgot", status_code=202)
def forgot(
    body: ForgotBody, request: Request, db: DbSession, settings: AppSettings
) -> dict[str, str]:
    service.request_password_reset(
        db, settings, request.app.state.email_sender, body.email, client_ip(request)
    )
    return {"status": "If the address belongs to an active account, a reset link has been sent."}


class ResetBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/password/reset", status_code=204)
def reset(body: ResetBody, request: Request, db: DbSession, settings: AppSettings) -> None:
    service.reset_password(db, settings, body.token, body.new_password, client_ip(request))


class ChangeBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/password/change", status_code=204)
def change(
    body: ChangeBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> None:
    service.change_password(
        db,
        settings,
        principal.user_id,
        principal.session_id,
        body.current_password,
        body.new_password,
        client_ip(request),
    )


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool


@router.get("/sessions", response_model=list[SessionOut])
def sessions(principal: CurrentPrincipal, db: DbSession) -> list[SessionOut]:
    return [
        SessionOut(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            ip=s.ip,
            user_agent=s.user_agent,
            current=s.id == principal.session_id,
        )
        for s in service.list_sessions(db, principal.user_id)
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: uuid.UUID, request: Request, principal: CurrentPrincipal, db: DbSession
) -> None:
    service.revoke_own_session(db, principal.user_id, session_id, client_ip(request))


class MfaEnrollOut(BaseModel):
    secret: str
    otpauth_uri: str


@router.post("/mfa/enroll", response_model=MfaEnrollOut)
def mfa_enroll(principal: CurrentPrincipal, db: DbSession, cipher: Cipher) -> MfaEnrollOut:
    secret, uri = service.mfa_enroll(db, cipher, principal.user_id)
    return MfaEnrollOut(secret=secret, otpauth_uri=uri)


class CodeBody(BaseModel):
    code: str = Field(min_length=6, max_length=10)


@router.post("/mfa/confirm", status_code=204)
def mfa_confirm(
    body: CodeBody, request: Request, principal: CurrentPrincipal, db: DbSession, cipher: Cipher
) -> None:
    service.mfa_confirm(db, cipher, principal.user_id, body.code, client_ip(request))


class MfaDisableBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=10)


@router.post("/mfa/disable", status_code=204)
def mfa_disable(
    body: MfaDisableBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
    settings: AppSettings,
) -> None:
    service.mfa_disable(
        db, settings, cipher, principal.user_id, body.password, body.code, client_ip(request)
    )
