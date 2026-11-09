"""Login, sessions, password reset/change, invitations and MFA (AUTH-*)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailSender, EmailSendError, OutgoingEmail
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.auth.models import LoginAttempt, PasswordResetToken, User, UserSession
from app.modules.auth.security import (
    FieldCipher,
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    new_totp_secret,
    totp_step,
    totp_uri,
    verify_password,
)

logger = logging.getLogger("app.auth")

INVALID_CREDENTIALS = "Invalid email or password"
MAX_RESETS_PER_HOUR = 3


def normalize_email(email: str) -> str:
    return email.strip().lower()


def check_password_policy(settings: Settings, password: str, email: str) -> None:
    if len(password) < settings.password_min_length:
        raise AppError(
            f"Password must be at least {settings.password_min_length} characters",
            code="WEAK_PASSWORD",
            status_code=422,
        )
    if len(password) > 128:
        raise AppError(
            "Password must be at most 128 characters", code="WEAK_PASSWORD", status_code=422
        )
    if password.strip().lower() == email.lower():
        raise AppError(
            "Password must not be your email address", code="WEAK_PASSWORD", status_code=422
        )


def _user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("User not found", code="NOT_FOUND", status_code=404)
    return user


# ---------------------------------------------------------------- throttling (AUTH-009)


def _failures_since(
    db: Session, match: ColumnElement[bool], since: datetime
) -> tuple[int, datetime | None]:
    last_success = db.scalar(
        select(func.max(LoginAttempt.created_at)).where(
            match, LoginAttempt.succeeded.is_(True), LoginAttempt.created_at >= since
        )
    )
    start = max(since, last_success) if last_success else since
    count, oldest = db.execute(
        select(func.count(), func.min(LoginAttempt.created_at)).where(
            match, LoginAttempt.succeeded.is_(False), LoginAttempt.created_at > start
        )
    ).one()
    return int(count), oldest


def ensure_not_throttled(db: Session, settings: Settings, email: str, ip: str | None) -> None:
    window = timedelta(minutes=settings.login_window_minutes)
    since = datetime.now(UTC) - window
    checks: list[tuple[ColumnElement[bool], int]] = [
        (LoginAttempt.email == email, settings.login_max_failures_per_account)
    ]
    if ip:
        checks.append((LoginAttempt.ip == ip, settings.login_max_failures_per_ip))
    for match, limit in checks:
        count, oldest = _failures_since(db, match, since)
        if count >= limit:
            retry = int(
                ((oldest or datetime.now(UTC)) + window - datetime.now(UTC)).total_seconds()
            )
            raise AppError(
                "Too many failed sign-in attempts. Try again later.",
                code="RATE_LIMITED",
                status_code=429,
                details=[{"retry_after_seconds": max(retry, 1)}],
            )


def _record_attempt(db: Session, email: str, ip: str | None, succeeded: bool) -> None:
    db.add(LoginAttempt(email=email, ip=ip, succeeded=succeeded))


def _fresh_step(user: User, step: int | None) -> bool:
    """A valid authenticator code from a time step later than the last one accepted (D-050)."""
    return step is not None and (user.mfa_last_step is None or step > user.mfa_last_step)


# ---------------------------------------------------------------- login / logout


@dataclass(frozen=True)
class NewSession:
    user: User
    session_id: uuid.UUID
    token: str
    expires_at: datetime


def login(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    *,
    email: str,
    password: str,
    totp_code: str | None,
    ip: str | None,
    user_agent: str | None,
) -> NewSession:
    email = normalize_email(email)
    ensure_not_throttled(db, settings, email, ip)
    user = db.scalar(select(User).where(User.email == email))
    password_ok = verify_password(user.password_hash if user else None, password)

    if user is None or not password_ok or user.status != "ACTIVE":
        _record_attempt(db, email, ip, succeeded=False)
        audit.record(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else None,
            actor_id=None,
            ip=ip,
            after={"email": email, "reason": "disabled" if user and password_ok else "credentials"},
        )
        db.commit()
        raise AppError(INVALID_CREDENTIALS, code="INVALID_CREDENTIALS", status_code=401)

    step: int | None = None
    if user.mfa_enabled:
        if not totp_code:
            raise AppError(
                "Enter the code from your authenticator app", code="MFA_REQUIRED", status_code=401
            )
        secret = cipher.decrypt(user.mfa_secret_enc or "")
        step = totp_step(secret, totp_code)
        if not _fresh_step(user, step):
            _record_attempt(db, email, ip, succeeded=False)
            audit.record(
                db,
                action="auth.login_failed",
                entity_type="user",
                entity_id=user.id,
                actor_id=None,
                ip=ip,
                after={"email": email, "reason": "mfa"},
            )
            db.commit()
            raise AppError(
                "The authenticator code is not valid", code="MFA_INVALID", status_code=401
            )

    if user.mfa_enabled:
        user.mfa_last_step = step
    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    now = datetime.now(UTC)
    token = new_token()
    expires = now + timedelta(hours=settings.session_absolute_hours)
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(token),
        last_seen_at=now,
        expires_at=expires,
        ip=ip,
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(session)
    user.last_login_at = now
    _record_attempt(db, email, ip, succeeded=True)
    audit.record(
        db, action="auth.login", entity_type="user", entity_id=user.id, actor_id=user.id, ip=ip
    )
    db.commit()
    return NewSession(user=user, session_id=session.id, token=token, expires_at=expires)


def logout(db: Session, session_id: uuid.UUID, user_id: uuid.UUID, ip: str | None) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    audit.record(
        db, action="auth.logout", entity_type="user", entity_id=user_id, actor_id=user_id, ip=ip
    )
    db.commit()


def revoke_sessions(
    db: Session, user_id: uuid.UUID, *, except_session: uuid.UUID | None = None
) -> int:
    stmt = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_session is not None:
        stmt = stmt.where(UserSession.id != except_session)
    result = db.execute(stmt.values(revoked_at=datetime.now(UTC)))
    return int(getattr(result, "rowcount", 0) or 0)


def list_sessions(db: Session, user_id: uuid.UUID) -> list[UserSession]:
    now = datetime.now(UTC)
    return list(
        db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.last_seen_at.desc())
        ).all()
    )


def revoke_own_session(
    db: Session, user_id: uuid.UUID, session_id: uuid.UUID, ip: str | None
) -> None:
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        raise AppError("Session not found", code="NOT_FOUND", status_code=404)
    session.revoked_at = datetime.now(UTC)
    audit.record(
        db,
        action="auth.session_revoked",
        entity_type="session",
        entity_id=session_id,
        actor_id=user_id,
        ip=ip,
    )
    db.commit()


# ---------------------------------------------------------------- password links (reset + invite)


def issue_password_link(
    db: Session, settings: Settings, sender: EmailSender, user: User, *, purpose: str
) -> bool:
    """Create a single-use link and email it. Returns False if the email could not be sent."""
    token = new_token()
    lifetime = (
        timedelta(hours=settings.invite_hours)
        if purpose == "INVITE"
        else timedelta(minutes=settings.password_reset_minutes)
    )
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            purpose=purpose,
            expires_at=datetime.now(UTC) + lifetime,
        )
    )
    db.commit()
    link = f"{settings.public_app_url}/reset-password?token={token}"
    if purpose == "INVITE":
        subject = "You have been invited to Conversation Collection"
        body = (
            f"Hello {user.display_name},\n\nAn account was created for you. Set your password here "
            f"(valid for {settings.invite_hours} hours):\n\n{link}\n"
        )
    else:
        subject = "Reset your Conversation Collection password"
        body = (
            f"Hello {user.display_name},\n\nUse this link to set a new password (valid for "
            f"{settings.password_reset_minutes} minutes):\n\n{link}\n\n"
            "If you did not ask for this, you can ignore this email.\n"
        )
    try:
        sender.send(OutgoingEmail(to=user.email, subject=subject, body=body))
    except EmailSendError:
        return False
    return True


def request_password_reset(
    db: Session, settings: Settings, sender: EmailSender, email: str, ip: str | None
) -> None:
    """Same outcome for known and unknown addresses (no account enumeration)."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or user.status != "ACTIVE":
        return
    recent = db.scalar(
        select(func.count()).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at >= datetime.now(UTC) - timedelta(hours=1),
        )
    )
    if (recent or 0) >= MAX_RESETS_PER_HOUR:
        logger.warning("password_reset_rate_limited", extra={"user_id": str(user.id)})
        return
    audit.record(
        db,
        action="auth.password_reset_requested",
        entity_type="user",
        entity_id=user.id,
        actor_id=None,
        ip=ip,
    )
    if not issue_password_link(db, settings, sender, user, purpose="RESET"):
        logger.error("password_reset_email_failed", extra={"user_id": str(user.id)})


def reset_password(
    db: Session, settings: Settings, token: str, new_password: str, ip: str | None
) -> None:
    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    )
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise AppError("This link is invalid or has expired", code="INVALID_TOKEN", status_code=400)
    user = db.get(User, record.user_id)
    if user is None or user.status != "ACTIVE":
        raise AppError("This link is invalid or has expired", code="INVALID_TOKEN", status_code=400)
    check_password_policy(settings, new_password, user.email)
    user.password_hash = hash_password(new_password)
    record.used_at = now
    # Any other outstanding links for this user stop working too.
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    revoke_sessions(db, user.id)
    audit.record(
        db,
        action="auth.password_reset",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
        after={"purpose": record.purpose},
    )
    db.commit()


def change_password(
    db: Session,
    settings: Settings,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    current: str,
    new: str,
    ip: str | None,
) -> None:
    user = _user(db, user_id)
    # Guessing the password through a signed-in session is throttled like sign-in (AUTH-009).
    ensure_not_throttled(db, settings, user.email, ip)
    if not verify_password(user.password_hash, current):
        _record_attempt(db, user.email, ip, succeeded=False)
        db.commit()
        raise AppError(
            "Current password is not correct", code="INVALID_CREDENTIALS", status_code=400
        )
    check_password_policy(settings, new, user.email)
    user.password_hash = hash_password(new)
    revoke_sessions(db, user.id, except_session=session_id)
    audit.record(
        db,
        action="auth.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
    )
    db.commit()


# ---------------------------------------------------------------- MFA (AUTH-008)


def mfa_enroll(db: Session, cipher: FieldCipher, user_id: uuid.UUID) -> tuple[str, str]:
    user = _user(db, user_id)
    if user.mfa_enabled:
        raise AppError(
            "Two-step sign-in is already on", code="MFA_ALREADY_ENABLED", status_code=409
        )
    secret = new_totp_secret()
    user.mfa_secret_enc = cipher.encrypt(secret)
    db.commit()
    return secret, totp_uri(secret, user.email)


def mfa_confirm(
    db: Session, cipher: FieldCipher, user_id: uuid.UUID, code: str, ip: str | None
) -> None:
    user = _user(db, user_id)
    if user.mfa_enabled or not user.mfa_secret_enc:
        raise AppError("Start enrolment first", code="MFA_NOT_PENDING", status_code=409)
    step = totp_step(cipher.decrypt(user.mfa_secret_enc), code)
    if step is None:
        raise AppError("The authenticator code is not valid", code="MFA_INVALID", status_code=400)
    user.mfa_enabled = True
    user.mfa_last_step = step  # the enrolment code cannot then be used to sign in
    audit.record(
        db,
        action="auth.mfa_enabled",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
    )
    db.commit()


def mfa_disable(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    user_id: uuid.UUID,
    password: str,
    code: str,
    ip: str | None,
) -> None:
    user = _user(db, user_id)
    if not user.mfa_enabled or not user.mfa_secret_enc:
        raise AppError("Two-step sign-in is not on", code="MFA_NOT_ENABLED", status_code=409)
    ensure_not_throttled(db, settings, user.email, ip)
    password_ok = verify_password(user.password_hash, password)
    step = totp_step(cipher.decrypt(user.mfa_secret_enc), code)
    if not password_ok or not _fresh_step(user, step):
        _record_attempt(db, user.email, ip, succeeded=False)
        db.commit()
        raise AppError(
            "Password or code is not correct", code="INVALID_CREDENTIALS", status_code=400
        )
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.mfa_last_step = None
    audit.record(
        db,
        action="auth.mfa_disabled",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
    )
    db.commit()
