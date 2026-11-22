"""Login, sessions, password reset/change, invitations and MFA (AUTH-*)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, and_, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.contact import normalize_email
from app.core.email import EmailSender, EmailSendError, OutgoingEmail
from app.core.errors import AppError, not_found
from app.core.ratelimit import address_key
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
        raise not_found("User")
    return user


# ---------------------------------------------------------------- throttling (AUTH-009)


def _failures_since(
    db: Session, match: ColumnElement[bool], since: datetime, *, reset_on_success: bool = True
) -> tuple[int, datetime | None]:
    last_success = (
        db.scalar(
            select(func.max(LoginAttempt.created_at)).where(
                match, LoginAttempt.succeeded.is_(True), LoginAttempt.created_at >= since
            )
        )
        if reset_on_success
        else None
    )
    start = max(since, last_success) if last_success else since
    count, oldest = db.execute(
        select(func.count(), func.min(LoginAttempt.created_at)).where(
            match, LoginAttempt.succeeded.is_(False), LoginAttempt.created_at > start
        )
    ).one()
    return int(count), oldest


# An account locks for one address after login_max_failures_per_account failures from it, and for
# everyone only after this many times that number from anywhere: a stranger who knows an email can
# no longer keep its owner out with five wrong passwords (security review 2026-11-11, D-088).
ACCOUNT_CEILING_FACTOR = 10

# Wrong authenticator codes after the right password, from any address: an account takes this many
# per window, then nobody signs in to it until the window has passed (security review 2026-11-22).
# Only someone who has the password can add to this count, so a stranger still cannot lock the
# owner out. The owner is emailed at the first one in a window.
MFA_FAILURES_PER_ACCOUNT = 10


def _mfa_key(email: str) -> str:
    """Where wrong codes are counted in login_attempts. Upper case on purpose: every address typed
    at sign-in is stored in lower case (normalize_email), so no typed value can add to this count.
    Recorded without an address, so the per-address counts do not count a wrong code twice."""
    return f"MFA:{email}"


def ensure_not_throttled(
    db: Session, settings: Settings, email: str, ip: str | None, *, codes: bool = False
) -> None:
    """429 when this account or address has failed too often lately. `codes`: the caller checks
    an authenticator code, so the account's count of wrong codes applies too. Changing one's
    password is not held up by it: that is what the owner is told to do."""
    window = timedelta(minutes=settings.login_window_minutes)
    since = datetime.now(UTC) - window
    ip = address_key(ip)  # an IPv6 address counts as its /64
    if ip:
        # One check per address at a time: a burst sent at once could otherwise all read the count
        # before any of its failures was saved. Callers already hold the account lock, so the order
        # is always account, then address (no deadlock). Held until the transaction ends.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"login-ip:{ip}"})
    per_account = settings.login_max_failures_per_account
    # (who, limit, whether a successful sign-in starts the count again)
    checks: list[tuple[ColumnElement[bool], int, bool]]
    if ip:
        checks = [
            (and_(LoginAttempt.email == email, LoginAttempt.ip == ip), per_account, True),
            (LoginAttempt.email == email, per_account * ACCOUNT_CEILING_FACTOR, True),
            # Not reset by a success: signing in to one's own account must not buy more guesses
            # at other accounts from the same address.
            (LoginAttempt.ip == ip, settings.login_max_failures_per_ip, False),
        ]
    else:
        checks = [(LoginAttempt.email == email, per_account, True)]
    if codes:
        checks.append((LoginAttempt.email == _mfa_key(email), MFA_FAILURES_PER_ACCOUNT, False))
    for match, limit, reset in checks:
        count, oldest = _failures_since(db, match, since, reset_on_success=reset)
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


def _account_lock(db: Session, email: str) -> None:
    """Serialise password and authenticator checks for one account until the transaction ends."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"login:{email}"})


def _record_attempt(db: Session, email: str, ip: str | None, succeeded: bool) -> None:
    db.add(LoginAttempt(email=email, ip=address_key(ip), succeeded=succeeded))


def _record_wrong_code(db: Session, settings: Settings, email: str) -> bool:
    """Counts a wrong authenticator code given with the right password. True when it is the first
    one in the window, so the owner is told once, not at every try. Run under the account lock."""
    since = datetime.now(UTC) - timedelta(minutes=settings.login_window_minutes)
    earlier, _ = _failures_since(
        db, LoginAttempt.email == _mfa_key(email), since, reset_on_success=False
    )
    db.add(LoginAttempt(email=_mfa_key(email), ip=None, succeeded=False))
    return earlier == 0


def _warn_owner(settings: Settings, sender: EmailSender, user: User) -> None:
    """Someone has this account's password: tell its owner. A failed email does not change the
    answer to the sign-in; it is logged."""
    body = (
        f"Hello {user.display_name},\n\n"
        "Your password was just entered correctly but the authenticator code was wrong. "
        "If this was not you, change your password:\n\n"
        f"{settings.public_app_url}/forgot-password\n"
    )
    try:
        sender.send(
            OutgoingEmail(
                to=user.email,
                subject="Sign-in attempt on your Conversation Collection account",
                body=body,
            )
        )
    except (EmailSendError, OSError):
        logger.error("wrong_code_warning_failed", extra={"user_id": str(user.id)})


def _typed_email(settings: Settings, email: str, user: User | None) -> dict[str, str | None]:
    """What a failed sign-in records of the typed email: the address when it names an account, and
    otherwise only a keyed fingerprint, so a password typed into the email box is never stored in
    the audit log (it repeats for the same text, which is enough to see a pattern)."""
    if user is not None:
        return {"email": email}
    key = settings.secret_key.get_secret_value().encode()
    return {
        "email": None,
        "fingerprint": hmac.new(key, email.encode(), hashlib.sha256).hexdigest()[:16],
    }


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
    mailer: EmailSender | None = None,
) -> NewSession:
    """`mailer` tells the owner when their password was right but the code was wrong."""
    email = normalize_email(email)
    # One sign-in per account at a time: parallel requests can no longer all read the failure
    # count before any of them records a failure, nor use one authenticator code twice (D-088).
    # Held until this transaction ends.
    _account_lock(db, email)
    ensure_not_throttled(db, settings, email, ip, codes=True)
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
            after={
                **_typed_email(settings, email, user),
                "reason": "disabled" if user and password_ok else "credentials",
            },
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
            first = _record_wrong_code(db, settings, email)
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
            if first and mailer is not None:
                _warn_owner(settings, mailer, user)
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
    """Ends the user's sessions and returns how many could still be used. A session past its
    absolute end is dead for good and is neither touched nor counted. One that only went idle is
    ended too: idleness is measured against the current setting, which may be raised later."""
    now = datetime.now(UTC)
    stmt = update(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    )
    if except_session is not None:
        stmt = stmt.where(UserSession.id != except_session)
    result = db.execute(stmt.values(revoked_at=now))
    return int(getattr(result, "rowcount", 0) or 0)


def list_sessions(db: Session, user_id: uuid.UUID, idle_minutes: int) -> list[UserSession]:
    """The sessions that still work: not signed out, not past their end, not gone idle."""
    now = datetime.now(UTC)
    return list(
        db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                UserSession.last_seen_at > now - timedelta(minutes=idle_minutes),
            )
            .order_by(UserSession.last_seen_at.desc())
        ).all()
    )


def revoke_own_session(
    db: Session, user_id: uuid.UUID, session_id: uuid.UUID, ip: str | None
) -> None:
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        raise not_found("Session")
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
    _account_lock(db, user.email)
    db.refresh(user)  # read again under the lock
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


def mfa_enroll(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    user_id: uuid.UUID,
    password: str,
    ip: str | None,
) -> tuple[str, str]:
    """Start enrolment. Needs the account password, so someone holding only a borrowed session
    cannot bind their own authenticator and lock the owner out (security review 2026-11-10)."""
    user = _user(db, user_id)
    if user.mfa_enabled:
        raise AppError(
            "Two-step sign-in is already on", code="MFA_ALREADY_ENABLED", status_code=409
        )
    _account_lock(db, user.email)
    db.refresh(user)  # read again under the lock
    ensure_not_throttled(db, settings, user.email, ip)
    if not verify_password(user.password_hash, password):
        _record_attempt(db, user.email, ip, succeeded=False)
        db.commit()
        raise AppError("Password is not correct", code="INVALID_CREDENTIALS", status_code=400)
    secret = new_totp_secret()
    user.mfa_secret_enc = cipher.encrypt(secret)
    db.commit()
    return secret, totp_uri(secret, user.email)


def mfa_confirm(
    db: Session,
    cipher: FieldCipher,
    user_id: uuid.UUID,
    code: str,
    ip: str | None,
    *,
    session_id: uuid.UUID,
) -> None:
    """Turns two-step sign-in on and ends every other session of the account: those signed in
    with the password alone, and an admin's would otherwise gain full access here (D-106)."""
    user = _user(db, user_id)
    if user.mfa_enabled or not user.mfa_secret_enc:
        raise AppError("Start enrolment first", code="MFA_NOT_PENDING", status_code=409)
    step = totp_step(cipher.decrypt(user.mfa_secret_enc), code)
    if step is None:
        raise AppError("The authenticator code is not valid", code="MFA_INVALID", status_code=400)
    user.mfa_enabled = True
    user.mfa_last_step = step  # the enrolment code cannot then be used to sign in
    revoked = revoke_sessions(db, user.id, except_session=session_id)
    audit.record(
        db,
        action="auth.mfa_enabled",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
        after={"sessions_revoked": revoked},
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
    _account_lock(db, user.email)
    db.refresh(user)  # read again under the lock
    ensure_not_throttled(db, settings, user.email, ip, codes=True)
    password_ok = verify_password(user.password_hash, password)
    step = totp_step(cipher.decrypt(user.mfa_secret_enc), code)
    if not password_ok or not _fresh_step(user, step):
        _record_attempt(db, user.email, ip, succeeded=False)
        if password_ok:  # the right password with a wrong code counts as at sign-in
            _record_wrong_code(db, settings, user.email)
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
