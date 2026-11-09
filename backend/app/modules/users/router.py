"""/api/v1/users and /api/v1/roles (USER-*, ROLE-*). All routes need users.manage."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.permissions import Perm
from app.modules.auth.deps import DbSession, Principal, client_ip, require
from app.modules.auth.models import RoleRecord, User
from app.modules.auth.router import AppSettings
from app.modules.users import service

router = APIRouter(tags=["users"])
Admin = Annotated[Principal, Depends(require(Perm.USERS_MANAGE))]


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    status: str
    roles: list[str]
    mfa_enabled: bool
    password_set: bool
    last_login_at: datetime | None
    created_at: datetime


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        roles=sorted(r.code for r in user.roles),
        mfa_enabled=user.mfa_enabled,
        password_set=user.password_hash is not None,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


@router.get("/users", response_model=UserPage)
def list_users(
    _: Admin,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
    role: Annotated[str | None, Query(max_length=50)] = None,
    status: Literal["ACTIVE", "DISABLED"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> UserPage:
    items, total = service.list_users(
        db, search=search, role=role, status=status, page=page, page_size=page_size
    )
    return UserPage(items=[user_out(u) for u in items], total=total, page=page, page_size=page_size)


class CreateUserBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    roles: list[str] = Field(min_length=1, max_length=6)


class CreatedUser(BaseModel):
    user: UserOut
    invite_sent: bool


@router.post("/users", response_model=CreatedUser, status_code=201)
def create_user(
    body: CreateUserBody, request: Request, admin: Admin, db: DbSession, settings: AppSettings
) -> CreatedUser:
    user, sent = service.create_user(
        db,
        settings,
        request.app.state.email_sender,
        actor_id=admin.user_id,
        email=body.email,
        display_name=body.display_name,
        roles=body.roles,
        ip=client_ip(request),
    )
    return CreatedUser(user=user_out(user), invite_sent=sent)


@router.get("/users/export")
def export_users(_: Admin, db: DbSession) -> Response:
    return Response(
        content=service.export_csv(db),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="users.csv"'},
    )


class ImportBody(BaseModel):
    csv: str = Field(min_length=1, max_length=2_000_000)


class ImportRowOut(BaseModel):
    line: int
    email: str
    display_name: str
    roles: list[str]
    errors: list[str]


class ImportPreview(BaseModel):
    rows: list[ImportRowOut]
    valid_count: int
    invalid_count: int


def _row(r: service.ImportRow) -> ImportRowOut:
    return ImportRowOut(
        line=r.line, email=r.email, display_name=r.display_name, roles=r.roles, errors=r.errors
    )


@router.post("/users/import/preview", response_model=ImportPreview)
def import_preview(body: ImportBody, _: Admin, db: DbSession) -> ImportPreview:
    rows = service.parse_import(db, body.csv)
    valid = sum(1 for r in rows if r.valid)
    return ImportPreview(
        rows=[_row(r) for r in rows], valid_count=valid, invalid_count=len(rows) - valid
    )


class ImportResult(BaseModel):
    created: int
    skipped: list[ImportRowOut]
    invites_failed: int


@router.post("/users/import/confirm", response_model=ImportResult)
def import_confirm(
    body: ImportBody, request: Request, admin: Admin, db: DbSession, settings: AppSettings
) -> ImportResult:
    created, skipped, failed = service.confirm_import(
        db,
        settings,
        request.app.state.email_sender,
        actor_id=admin.user_id,
        text=body.csv,
        ip=client_ip(request),
    )
    return ImportResult(created=created, skipped=[_row(r) for r in skipped], invites_failed=failed)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, _: Admin, db: DbSession) -> UserOut:
    return user_out(service.get_user(db, user_id))


class UpdateUserBody(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID, body: UpdateUserBody, request: Request, admin: Admin, db: DbSession
) -> UserOut:
    return user_out(
        service.update_user(
            db,
            actor_id=admin.user_id,
            user_id=user_id,
            display_name=body.display_name,
            email=body.email,
            ip=client_ip(request),
        )
    )


@router.post("/users/{user_id}/disable", response_model=UserOut)
def disable_user(user_id: uuid.UUID, request: Request, admin: Admin, db: DbSession) -> UserOut:
    return user_out(
        service.set_status(
            db, actor_id=admin.user_id, user_id=user_id, active=False, ip=client_ip(request)
        )
    )


@router.post("/users/{user_id}/enable", response_model=UserOut)
def enable_user(user_id: uuid.UUID, request: Request, admin: Admin, db: DbSession) -> UserOut:
    return user_out(
        service.set_status(
            db, actor_id=admin.user_id, user_id=user_id, active=True, ip=client_ip(request)
        )
    )


class RolesBody(BaseModel):
    roles: list[str] = Field(min_length=1, max_length=6)


@router.put("/users/{user_id}/roles", response_model=UserOut)
def set_roles(
    user_id: uuid.UUID, body: RolesBody, request: Request, admin: Admin, db: DbSession
) -> UserOut:
    return user_out(
        service.set_roles(
            db, actor_id=admin.user_id, user_id=user_id, roles=body.roles, ip=client_ip(request)
        )
    )


class SentOut(BaseModel):
    sent: bool


@router.post("/users/{user_id}/send-password-link", response_model=SentOut)
def send_password_link(
    user_id: uuid.UUID, request: Request, admin: Admin, db: DbSession, settings: AppSettings
) -> SentOut:
    sent = service.send_password_link(
        db,
        settings,
        request.app.state.email_sender,
        actor_id=admin.user_id,
        user_id=user_id,
        ip=client_ip(request),
    )
    return SentOut(sent=sent)


class RevokedOut(BaseModel):
    sessions_revoked: int


@router.post("/users/{user_id}/sessions/revoke", response_model=RevokedOut)
def revoke_sessions(
    user_id: uuid.UUID, request: Request, admin: Admin, db: DbSession
) -> RevokedOut:
    return RevokedOut(
        sessions_revoked=service.revoke_user_sessions(
            db, actor_id=admin.user_id, user_id=user_id, ip=client_ip(request)
        )
    )


class RoleOut(BaseModel):
    code: str
    name: str
    permissions: list[str]


@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: Admin, db: DbSession) -> list[RoleOut]:
    return [
        RoleOut(code=r.code, name=r.name, permissions=sorted(p.code for p in r.permissions))
        for r in db.scalars(select(RoleRecord).order_by(RoleRecord.name)).all()
    ]
