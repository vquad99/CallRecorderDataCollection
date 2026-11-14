"""Who is calling, and may they do this? (AUTH-005, AUTH-011, ROLE-001, ROLE-010, SEC-007)

Every protected route depends on `require(Perm.X)`. The check reads roles and permissions from the
database on each request, so a role change or deactivation applies at the next request.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm, Role
from app.db.session import get_db_session
from app.modules.audit.service import VIEWER_KEY
from app.modules.auth.models import User, UserSession
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
    # This account's role needs two-step sign-in and it is not set up yet (D-106): only the
    # set-up itself is open to it.
    mfa_setup_required: bool = False
    # Set while a Super Admin views the app as this user (D-100): who is really looking.
    viewer_id: uuid.UUID | None = None
    viewer_name: str | None = None

    @property
    def read_only(self) -> bool:
        return self.viewer_id is not None

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
    # Roles and their permissions arrive with the user (selectin loading): no extra queries (O5).
    role_codes = frozenset(r.code for r in user.roles)
    perms = frozenset(p.code for r in user.roles for p in r.permissions)
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
    found = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == hash_token(token))
    ).one_or_none()
    if found is None:
        raise unauthenticated()
    session, user = found
    if session.revoked_at is not None:
        raise unauthenticated()
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    idle_limit = session.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if now >= session.expires_at or now >= idle_limit:
        raise unauthenticated("SESSION_EXPIRED", "Your session has expired. Sign in again.")
    if user.status != "ACTIVE":
        raise unauthenticated()
    if now - session.last_seen_at >= _LAST_SEEN_WRITE_INTERVAL:
        session.last_seen_at = now
        db.commit()
    setup_required = needs_mfa_setup(settings, user)
    if setup_required and (request.method, request.url.path) not in _OPEN_BEFORE_MFA_SETUP:
        raise AppError(
            "Set up two-step sign-in to continue: your role needs it.",
            code="MFA_SETUP_REQUIRED",
            status_code=403,
        )
    if session.view_as_user_id is not None:
        viewed = view_as_target(db, user, session)
        if viewed is not None:
            refuse_changes_while_viewing(request)
            db.info[VIEWER_KEY] = user.id
            return viewing(load_principal(db, viewed, session.id), user)
    return replace(load_principal(db, user, session.id), mfa_setup_required=setup_required)


# Roles that must have two-step sign-in (D-106), and what an account that has not set it up yet
# may still do: see who it is, set it up, and sign out.
MFA_REQUIRED_ROLES = frozenset({Role.SUPER_ADMIN.value, Role.PROJECT_ADMIN.value})
_OPEN_BEFORE_MFA_SETUP = {
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/mfa/enroll"),
    ("POST", "/api/v1/auth/mfa/confirm"),
}


def needs_mfa_setup(settings: Settings, user: User) -> bool:
    return (
        settings.admin_mfa_required
        and not user.mfa_enabled
        and any(r.code in MFA_REQUIRED_ROLES for r in user.roles)
    )


# The only changes allowed while viewing as someone else: stop viewing, and sign out (D-100).
_ALLOWED_WHILE_VIEWING = {("DELETE", "/api/v1/auth/view-as"), ("POST", "/api/v1/auth/logout")}


def view_as_target(db: Session, user: User, session: UserSession) -> User | None:
    """The user this session is viewing as, or None (and the view ended) when the caller is no
    longer a Super Admin or the other account is gone, deactivated or their own."""
    target = db.get(User, session.view_as_user_id) if session.view_as_user_id else None
    still_admin = any(r.code == Role.SUPER_ADMIN.value for r in user.roles)
    if target is None or not still_admin or target.id == user.id or target.status != "ACTIVE":
        session.view_as_user_id = None
        db.commit()
        return None
    return target


def viewing(principal: Principal, viewer: User) -> Principal:
    return replace(principal, viewer_id=viewer.id, viewer_name=viewer.display_name)


def refuse_changes_while_viewing(request: Request) -> None:
    if request.method in _UNSAFE and (request.method, request.url.path) not in (
        _ALLOWED_WHILE_VIEWING
    ):
        raise AppError(
            "You are viewing as someone else, so nothing can be changed. Stop viewing first.",
            code="VIEW_AS_READ_ONLY",
            status_code=403,
        )


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
