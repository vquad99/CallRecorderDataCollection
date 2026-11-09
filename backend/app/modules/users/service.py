"""User administration (USER-001..009). Every role and status change is audited."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailSender
from app.core.errors import AppError
from app.core.permissions import Role
from app.modules.audit import service as audit
from app.modules.auth import service as auth_service
from app.modules.auth.models import RoleRecord, User, UserRole

MAX_IMPORT_ROWS = 1000
IMPORT_COLUMNS = ("email", "display_name", "roles")


def not_found() -> AppError:
    return AppError("User not found", code="NOT_FOUND", status_code=404)


def clean_email(raw: str) -> str:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise AppError(
            "Email address is not valid", code="INVALID_EMAIL", status_code=422
        ) from None


def _roles_by_code(db: Session, codes: list[str]) -> list[RoleRecord]:
    wanted = sorted(set(codes))
    if not wanted:
        raise AppError("At least one role is required", code="ROLE_REQUIRED", status_code=422)
    found = list(db.scalars(select(RoleRecord).where(RoleRecord.code.in_(wanted))).all())
    missing = set(wanted) - {r.code for r in found}
    if missing:
        raise AppError(
            f"Unknown role: {', '.join(sorted(missing))}", code="UNKNOWN_ROLE", status_code=422
        )
    return found


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found()
    return user


def list_users(
    db: Session,
    *,
    search: str | None,
    role: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    query = select(User)
    if search:
        like = f"%{search.strip().lower()}%"
        query = query.where(or_(User.email.like(like), func.lower(User.display_name).like(like)))
    if role:
        query = query.where(
            User.id.in_(
                select(UserRole.user_id)
                .join(RoleRecord, RoleRecord.id == UserRole.role_id)
                .where(RoleRecord.code == role)
            )
        )
    if status:
        query = query.where(User.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(User.email).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), int(total)


def create_user(
    db: Session,
    settings: Settings,
    sender: EmailSender,
    *,
    actor_id: uuid.UUID,
    email: str,
    display_name: str,
    roles: list[str],
    ip: str | None,
) -> tuple[User, bool]:
    email = clean_email(email)
    if db.scalar(select(User.id).where(User.email == email)):
        raise AppError("A user with this email already exists", code="EMAIL_TAKEN", status_code=409)
    role_records = _roles_by_code(db, roles)
    user = User(id=uuid.uuid4(), email=email, display_name=display_name.strip(), status="ACTIVE")
    user.roles = role_records
    db.add(user)
    audit.record(
        db,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=ip,
        after={
            "email": email,
            "display_name": user.display_name,
            "roles": sorted(r.code for r in role_records),
        },
    )
    db.commit()
    sent = auth_service.issue_password_link(db, settings, sender, user, purpose="INVITE")
    return user, sent


def update_user(
    db: Session,
    *,
    actor_id: uuid.UUID,
    user_id: uuid.UUID,
    display_name: str | None,
    email: str | None,
    ip: str | None,
) -> User:
    user = get_user(db, user_id)
    before = {"email": user.email, "display_name": user.display_name}
    if email is not None:
        new_email = clean_email(email)
        if new_email != user.email and db.scalar(select(User.id).where(User.email == new_email)):
            raise AppError(
                "A user with this email already exists", code="EMAIL_TAKEN", status_code=409
            )
        user.email = new_email
    if display_name is not None:
        user.display_name = display_name.strip()
    after = {"email": user.email, "display_name": user.display_name}
    if after != before:
        audit.record(
            db,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            ip=ip,
            before=before,
            after=after,
        )
    db.commit()
    return user


def set_status(
    db: Session, *, actor_id: uuid.UUID, user_id: uuid.UUID, active: bool, ip: str | None
) -> User:
    user = get_user(db, user_id)
    if user.id == actor_id and not active:
        raise AppError(
            "You cannot disable your own account", code="CANNOT_MODIFY_SELF", status_code=409
        )
    new_status = "ACTIVE" if active else "DISABLED"
    if user.status != new_status:
        before = user.status
        user.status = new_status
        revoked = 0 if active else auth_service.revoke_sessions(db, user.id)
        audit.record(
            db,
            action="user.enabled" if active else "user.disabled",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            ip=ip,
            before={"status": before},
            after={"status": new_status, "sessions_revoked": revoked},
        )
    db.commit()
    return user


def set_roles(
    db: Session, *, actor_id: uuid.UUID, user_id: uuid.UUID, roles: list[str], ip: str | None
) -> User:
    user = get_user(db, user_id)
    role_records = _roles_by_code(db, roles)
    new_codes = sorted(r.code for r in role_records)
    old_codes = sorted(r.code for r in user.roles)
    if (
        user.id == actor_id
        and Role.SUPER_ADMIN.value in old_codes
        and Role.SUPER_ADMIN.value not in new_codes
    ):
        raise AppError(
            "You cannot remove your own Super Admin role",
            code="CANNOT_MODIFY_SELF",
            status_code=409,
        )
    if new_codes != old_codes:
        user.roles = role_records
        audit.record(
            db,
            action="user.roles_changed",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            ip=ip,
            before={"roles": old_codes},
            after={"roles": new_codes},
        )
    db.commit()
    return user


def send_password_link(
    db: Session,
    settings: Settings,
    sender: EmailSender,
    *,
    actor_id: uuid.UUID,
    user_id: uuid.UUID,
    ip: str | None,
) -> bool:
    user = get_user(db, user_id)
    if user.status != "ACTIVE":
        raise AppError("The account is disabled", code="USER_DISABLED", status_code=409)
    purpose = "INVITE" if user.password_hash is None else "RESET"
    audit.record(
        db,
        action="user.password_link_sent",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=ip,
        after={"purpose": purpose},
    )
    return auth_service.issue_password_link(db, settings, sender, user, purpose=purpose)


def revoke_user_sessions(
    db: Session, *, actor_id: uuid.UUID, user_id: uuid.UUID, ip: str | None
) -> int:
    user = get_user(db, user_id)
    count = auth_service.revoke_sessions(db, user.id)
    audit.record(
        db,
        action="user.sessions_revoked",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=ip,
        after={"sessions_revoked": count},
    )
    db.commit()
    return count


# -------------------------------------------------------------- CSV import / export (USER-005/006)


@dataclass
class ImportRow:
    line: int
    email: str
    display_name: str
    roles: list[str]
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def parse_import(db: Session, text: str) -> list[ImportRow]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    if tuple(header) != IMPORT_COLUMNS:
        raise AppError(
            f"CSV header must be exactly: {','.join(IMPORT_COLUMNS)}",
            code="INVALID_CSV_HEADER",
            status_code=422,
        )
    known_roles = set(db.scalars(select(RoleRecord.code)).all())
    existing = set(db.scalars(select(User.email)).all())
    rows: list[ImportRow] = []
    seen: set[str] = set()
    for index, raw in enumerate(reader, start=2):
        if index - 1 > MAX_IMPORT_ROWS:
            raise AppError(
                f"At most {MAX_IMPORT_ROWS} rows per import", code="TOO_MANY_ROWS", status_code=422
            )
        values = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        roles = [r.strip().upper() for r in values.get("roles", "").split(";") if r.strip()]
        row = ImportRow(
            line=index,
            email=values.get("email", ""),
            display_name=values.get("display_name", ""),
            roles=roles,
        )
        try:
            row.email = clean_email(row.email)
        except AppError:
            row.errors.append("email is not valid")
        if not row.display_name:
            row.errors.append("display_name is required")
        elif len(row.display_name) > 200:
            row.errors.append("display_name is longer than 200 characters")
        if not roles:
            row.errors.append("at least one role is required")
        unknown = [r for r in roles if r not in known_roles]
        if unknown:
            row.errors.append(f"unknown role: {', '.join(unknown)}")
        if row.email in existing:
            row.errors.append("a user with this email already exists")
        if row.email in seen:
            row.errors.append("email appears more than once in the file")
        seen.add(row.email)
        rows.append(row)
    return rows


def confirm_import(
    db: Session,
    settings: Settings,
    sender: EmailSender,
    *,
    actor_id: uuid.UUID,
    text: str,
    ip: str | None,
) -> tuple[int, list[ImportRow], int]:
    rows = parse_import(db, text)
    created = 0
    invites_failed = 0
    for row in rows:
        if not row.valid:
            continue
        _, sent = create_user(
            db,
            settings,
            sender,
            actor_id=actor_id,
            email=row.email,
            display_name=row.display_name,
            roles=row.roles,
            ip=ip,
        )
        created += 1
        invites_failed += 0 if sent else 1
    return created, [r for r in rows if not r.valid], invites_failed


def _safe_cell(value: str) -> str:
    """Stop spreadsheet formula injection in exported cells."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def export_csv(db: Session) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["email", "display_name", "status", "roles", "last_login_at", "created_at"])
    for user in db.scalars(select(User).order_by(User.email)).all():
        writer.writerow(
            [
                _safe_cell(user.email),
                _safe_cell(user.display_name),
                user.status,
                ";".join(sorted(r.code for r in user.roles)),
                user.last_login_at.isoformat() if user.last_login_at else "",
                user.created_at.isoformat(),
            ]
        )
    return out.getvalue()
