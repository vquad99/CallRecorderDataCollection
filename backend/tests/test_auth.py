"""Authentication and account security against a real database.

Requirements: AUTH-001, AUTH-002, AUTH-003, AUTH-004, AUTH-005, AUTH-006, AUTH-007, AUTH-008, AUTH-009, AUTH-010, AUTH-012, AUTH-013, AUTH-014, AUTH-015, SEC-007
"""

import time
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update

from app.modules.audit.models import AuditLog
from app.modules.auth import security
from app.modules.auth.models import User, UserSession
from tests.conftest import TEST_PASSWORD, link_token, make_user, read_outbox

pytestmark = pytest.mark.db


def _actions(db: Any, user_id: Any = None) -> list[str]:
    query = select(AuditLog.action).order_by(AuditLog.created_at)
    if user_id is not None:
        query = query.where(AuditLog.entity_id == str(user_id))
    db.expire_all()
    return list(db.scalars(query).all())


def test_valid_login_sets_secure_cookies_and_returns_profile(db: Any, new_api: Any) -> None:
    make_user(db, "mod@example.org", ["MODERATOR"])
    api = new_api()
    response = api.login("  Mod@Example.org ")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "mod@example.org"
    assert body["roles"] == ["MODERATOR"]
    assert "calls.start" in body["permissions"]
    assert "password" not in str(body).lower()
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("ccp_session="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=strict" in session_cookie
    csrf_cookie = next(c for c in cookies if c.startswith("csrf_token="))
    assert "HttpOnly" not in csrf_cookie
    assert api.get("/api/v1/auth/me").json()["email"] == "mod@example.org"


@pytest.mark.parametrize(
    ("email", "password"),
    [("a@example.org", "wrong-password-123"), ("nobody@example.org", TEST_PASSWORD)],
)
def test_wrong_credentials_fail_with_one_generic_message(
    db: Any, new_api: Any, email: str, password: str
) -> None:
    make_user(db, "a@example.org", ["MODERATOR"])
    response = new_api().login(email, password)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "Invalid email or password"


def test_disabled_user_cannot_log_in(db: Any, new_api: Any) -> None:
    make_user(db, "off@example.org", ["MODERATOR"], status="DISABLED")
    response = new_api().login("off@example.org")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_password_is_stored_as_argon2id(db: Any) -> None:
    user = make_user(db, "hash@example.org", ["MODERATOR"])
    assert user.password_hash.startswith("$argon2id$")
    assert TEST_PASSWORD not in user.password_hash


def test_logout_revokes_the_session(db: Any, new_api: Any) -> None:
    make_user(db, "out@example.org", ["MODERATOR"])
    api = new_api()
    api.login("out@example.org")
    old_cookie = api.client.cookies.get("ccp_session")
    assert api.post("/api/v1/auth/logout").status_code == 204
    api.client.cookies.set("ccp_session", old_cookie)
    response = api.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("field", ["idle", "absolute"])
def test_expired_session_requires_login(db: Any, new_api: Any, field: str) -> None:
    user = make_user(db, f"exp-{field}@example.org", ["MODERATOR"])
    api = new_api()
    api.login(user.email)
    past = datetime.now(UTC) - timedelta(hours=48)
    values = {"last_seen_at": past} if field == "idle" else {"expires_at": past}
    db.execute(update(UserSession).where(UserSession.user_id == user.id).values(**values))
    db.commit()
    response = api.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_unsafe_request_without_csrf_token_is_rejected(db: Any, new_api: Any) -> None:
    make_user(db, "csrf@example.org", ["MODERATOR"])
    api = new_api()
    api.login("csrf@example.org")
    response = api.client.post("/api/v1/auth/logout")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"
    wrong = api.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "not-the-cookie"})
    assert wrong.json()["error"]["code"] == "CSRF_FAILED"


def test_repeated_failures_are_throttled_even_with_the_right_password(
    db: Any, new_api: Any
) -> None:
    make_user(db, "slow@example.org", ["MODERATOR"])
    api = new_api()
    for _ in range(5):
        assert api.login("slow@example.org", "wrong-password-123").status_code == 401
    blocked = api.login("slow@example.org")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert blocked.json()["error"]["details"][0]["retry_after_seconds"] > 0


def test_forgot_password_answers_the_same_and_reset_link_is_single_use(
    db: Any, new_api: Any, outbox: Path
) -> None:
    user = make_user(db, "reset@example.org", ["MODERATOR"])
    api = new_api()
    api.client.get("/api/v1/auth/csrf")
    unknown = api.post("/api/v1/auth/password/forgot", json={"email": "ghost@example.org"})
    known = api.post("/api/v1/auth/password/forgot", json={"email": "reset@example.org"})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    mails = read_outbox(outbox)
    assert len(mails) == 1
    assert "To: reset@example.org" in mails[0]
    token = link_token(mails[0])

    other = new_api()
    other.login("reset@example.org")
    new_password = "brand-new-password-456"
    assert (
        api.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": new_password}
        ).status_code
        == 204
    )
    again = api.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "another-password-789"}
    )
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "INVALID_TOKEN"
    assert other.get("/api/v1/auth/me").status_code == 401, "reset must revoke existing sessions"
    assert new_api().login("reset@example.org", new_password).status_code == 200
    assert "auth.password_reset" in _actions(db, user.id)


def test_expired_reset_link_is_refused(db: Any, new_api: Any, outbox: Path) -> None:
    from app.modules.auth.models import PasswordResetToken

    make_user(db, "late@example.org", ["MODERATOR"])
    api = new_api()
    api.client.get("/api/v1/auth/csrf")
    api.post("/api/v1/auth/password/forgot", json={"email": "late@example.org"})
    token = link_token(read_outbox(outbox)[0])
    db.execute(
        update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db.commit()
    response = api.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": "brand-new-password-456"},
    )
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_weak_password_is_rejected(db: Any, new_api: Any) -> None:
    make_user(db, "weak@example.org", ["MODERATOR"])
    api = new_api()
    api.login("weak@example.org")
    response = api.post(
        "/api/v1/auth/password/change",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"


def test_change_password_keeps_this_session_and_ends_others(db: Any, new_api: Any) -> None:
    user = make_user(db, "change@example.org", ["MODERATOR"])
    first, second = new_api(), new_api()
    first.login(user.email)
    second.login(user.email)
    response = first.post(
        "/api/v1/auth/password/change",
        json={"current_password": TEST_PASSWORD, "new_password": "brand-new-password-456"},
    )
    assert response.status_code == 204
    assert first.get("/api/v1/auth/me").status_code == 200
    assert second.get("/api/v1/auth/me").status_code == 401
    assert "auth.password_changed" in _actions(db, user.id)


def test_user_lists_and_revokes_own_sessions(db: Any, new_api: Any) -> None:
    user = make_user(db, "devices@example.org", ["MODERATOR"])
    laptop, phone = new_api(), new_api()
    laptop.login(user.email)
    phone.login(user.email)
    sessions = laptop.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2
    assert sum(s["current"] for s in sessions) == 1
    other = next(s for s in sessions if not s["current"])
    assert laptop.delete(f"/api/v1/auth/sessions/{other['id']}").status_code == 204
    assert phone.get("/api/v1/auth/me").status_code == 401
    assert laptop.get("/api/v1/auth/me").status_code == 200


def test_mfa_enrol_confirm_login_and_disable(
    db: Any, new_api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Each step uses its own code: a code is accepted once only (D-050). The clock is fixed so the
    # three codes (previous, current and next 30-second step) stay valid for the whole test.
    now = time.time()
    step = int(now // security.TOTP_STEP_SECONDS)
    monkeypatch.setattr(security, "time", types.SimpleNamespace(time=lambda: now))

    def code(offset: int, secret: str) -> str:
        return security._totp_at(secret, step + offset)

    user = make_user(db, "mfa@example.org", ["MODERATOR"])
    api = new_api()
    api.login(user.email)
    secret = api.post("/api/v1/auth/mfa/enroll").json()["secret"]
    assert api.post("/api/v1/auth/mfa/confirm", json={"code": "000000"}).status_code == 400
    assert api.post("/api/v1/auth/mfa/confirm", json={"code": code(-1, secret)}).status_code == 204
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.mfa_enabled
    assert secret not in (stored.mfa_secret_enc or ""), "secret must be stored encrypted"

    fresh = new_api()
    needs_code = fresh.login(user.email)
    assert needs_code.json()["error"]["code"] == "MFA_REQUIRED"
    assert fresh.login(user.email, totp_code="123456").json()["error"]["code"] in {"MFA_INVALID"}
    assert fresh.login(user.email, totp_code=code(0, secret)).status_code == 200

    off = fresh.post(
        "/api/v1/auth/mfa/disable", json={"password": TEST_PASSWORD, "code": code(1, secret)}
    )
    assert off.status_code == 204
    assert {"auth.mfa_enabled", "auth.mfa_disabled"} <= set(_actions(db, user.id))


def test_failed_logins_are_audited(db: Any, new_api: Any) -> None:
    user = make_user(db, "audit@example.org", ["MODERATOR"])
    new_api().login(user.email, "wrong-password-123")
    assert "auth.login_failed" in _actions(db, user.id)


def test_emails_are_unique_ignoring_case(db: Any) -> None:
    from sqlalchemy.exc import IntegrityError

    make_user(db, "case@example.org", ["MODERATOR"])
    with pytest.raises(IntegrityError):
        make_user(db, "CASE@example.org".lower(), ["MODERATOR"])
    db.rollback()
    db.add(User(email="Upper@Example.org", display_name="x"))
    with pytest.raises(IntegrityError, match="email_normalized"):
        db.commit()
    db.rollback()
