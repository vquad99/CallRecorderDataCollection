"""Who is calling, and may they do this? (AUTH-005, AUTH-011, ROLE-001, ROLE-010, SEC-007)

Every protected route depends on `require(Perm.X)`. The check reads roles and permissions from the
database on each request, so a role change or deactivation applies at the next request.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm, Role
from app.db.session import get_db_session
from app.modules.auth.models import Permission, RolePermission, User, UserRole, UserSession
from app.modules.auth.security import hash_token, tokens_equal
from app.modules.projects.models import ProjectMembership

SESSION_COOKIE = "ccp_session"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_LAST_SEEN_WRITE_INTERVAL = timedelta(seconds=60)

DbSession = Annotated[Session, Depends(get_db_session)]


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    session_id: uuid.UUID
    email: str
    display_name: str
    roles: frozenset[str]
    permissions: frozenset[str]
    project_ids: frozenset[uuid.UUID]
    mfa_enabled: bool

    @property
    def is_super_admin(self) -> bool:
        return Role.SUPER_ADMIN.value in self.roles

    def can(self, perm: Perm) -> bool:
        return perm.value in self.permissions

    def can_in_project(self, perm: Perm, project_id: uuid.UUID) -> bool:
        return self.can(perm) and (self.is_super_admin or project_id in self.project_ids)


def unauthenticated(code: str = "UNAUTHENTICATED", message: str = "Sign in required") -> AppError:
    return AppError(message, code=code, status_code=401)


def forbidden() -> AppError:
    return AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def load_principal(db: Session, user: User, session_id: uuid.UUID) -> Principal:
    roles = frozenset(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)).all())
    role_codes = frozenset(r.code for r in user.roles)
    perms = frozenset(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(roles))
            .distinct()
        ).all()
    )
    projects = frozenset(
        db.scalars(
            select(ProjectMembership.project_id).where(ProjectMembership.user_id == user.id)
        ).all()
    )
    return Principal(
        user_id=user.id,
        session_id=session_id,
        email=user.email,
        display_name=user.display_name,
        roles=role_codes,
        permissions=perms,
        project_ids=projects,
        mfa_enabled=user.mfa_enabled,
    )


def current_principal(request: Request, db: DbSession) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthenticated()
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None or session.revoked_at is not None:
        raise unauthenticated()
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    idle_limit = session.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if now >= session.expires_at or now >= idle_limit:
        raise unauthenticated("SESSION_EXPIRED", "Your session has expired. Sign in again.")
    user = db.get(User, session.user_id)
    if user is None or user.status != "ACTIVE":
        raise unauthenticated()
    if now - session.last_seen_at >= _LAST_SEEN_WRITE_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return load_principal(db, user, session.id)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require(perm: Perm) -> Callable[[Principal], Principal]:
    def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.can(perm):
            raise forbidden()
        return principal

    dependency.required_permission = perm.value  # type: ignore[attr-defined]  # read by tests
    return dependency


def csrf_protect(request: Request) -> None:
    """Double-submit check on every state-changing request under /api/v1."""
    if request.method not in _UNSAFE:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not tokens_equal(cookie, header):
        raise AppError("Missing or invalid CSRF token", code="CSRF_FAILED", status_code=403)
