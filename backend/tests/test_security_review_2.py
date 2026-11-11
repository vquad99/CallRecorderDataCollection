"""Fixes from the security review of 2026-11-11 (D-088), one test per fix.

Requirements: AUTH-006, AUTH-008, AUTH-009, SEC-005, SEC-006
"""

from typing import Any

import pytest
from cryptography.fernet import Fernet

from app.core.errors import AppError
from app.core.ratelimit import address_key
from app.modules.auth import security
from app.modules.auth import service as auth_service
from tests.conftest import TEST_PASSWORD, build_settings, make_user

# ---------------------------------------------------------------- no database


def test_password_hashing_fits_a_small_server_and_waits_its_turn(monkeypatch: Any) -> None:
    """A burst of parallel sign-ins could need 64 MiB each; now 19 MiB, at most two at once."""
    params = security._hasher
    assert (params.memory_cost, params.time_cost, params.parallelism) == (19456, 2, 1)
    assert security.HASH_SLOTS == 2
    monkeypatch.setattr(security, "HASH_WAIT_SECONDS", 0.05)
    for _ in range(security.HASH_SLOTS):
        security._slots.acquire()  # every slot busy
    try:
        with pytest.raises(AppError) as busy:
            security.hash_password("a-long-password-123")
        assert (busy.value.status_code, busy.value.code) == (503, "BUSY")
    finally:
        for _ in range(security.HASH_SLOTS):
            security._slots.release()
    assert security.verify_password(security.hash_password("x" * 14), "x" * 14)


def test_an_authenticator_code_in_another_script_is_refused_not_a_crash() -> None:
    assert security.totp_step("JBSWY3DPEHPK3PXP", "١٢٣٤٥٦") is None


def test_an_ipv6_address_counts_as_its_network() -> None:
    assert address_key("2001:db8:1:2:aaaa::1") == address_key("2001:db8:1:2:bbbb::9")
    assert address_key("2001:db8:1:2:aaaa::1") == "2001:db8:1:2::/64"
    assert address_key("2001:db8:1:3::1") != address_key("2001:db8:1:2::1")
    assert address_key("203.0.113.9") == "203.0.113.9"
    assert address_key("::ffff:203.0.113.9") == "203.0.113.9"


def test_the_encryption_key_can_be_rotated() -> None:
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    stored = security.FieldCipher(old).encrypt("+919876543210")
    both = security.FieldCipher(f"{new},{old}")
    assert both.decrypt(stored) == "+919876543210"
    rotated = both.rotate(stored)
    assert security.FieldCipher(new).decrypt(rotated) == "+919876543210"
    with pytest.raises(ValueError, match="cannot be read"):
        security.FieldCipher(old).decrypt(rotated)
    settings = build_settings(data_encryption_key=f"{new},{old}")
    assert new in settings.secret_values()
    assert old in settings.secret_values()
    with pytest.raises(ValueError, match="Fernet key"):
        build_settings(data_encryption_key=f"{new},not-a-key")


# ---------------------------------------------------------------- with the database


def _login(app: Any, db: Any, email: str, password: str, ip: str) -> Any:
    return auth_service.login(
        db,
        app.state.settings,
        app.state.cipher,
        email=email,
        password=password,
        totp_code=None,
        ip=ip,
        user_agent=None,
    )


@pytest.mark.db
def test_a_stranger_cannot_lock_the_owner_out(db_app: Any, db: Any) -> None:
    """Five wrong passwords lock the account for the address they came from, not for everyone."""
    make_user(db, "owner@example.org", ["SUPER_ADMIN"])
    db.commit()
    limit = db_app.state.settings.login_max_failures_per_account
    for _ in range(limit):
        with pytest.raises(AppError):
            _login(db_app, db, "owner@example.org", "wrong-password-0", "203.0.113.50")
    with pytest.raises(AppError) as locked:
        _login(db_app, db, "owner@example.org", TEST_PASSWORD, "203.0.113.50")
    assert locked.value.code == "RATE_LIMITED"
    assert _login(db_app, db, "owner@example.org", TEST_PASSWORD, "198.51.100.7").user.email == (
        "owner@example.org"
    )


@pytest.mark.db
def test_signing_in_to_ones_own_account_does_not_reset_the_address_count(
    db_app: Any, db: Any
) -> None:
    make_user(db, "insider@example.org", ["MODERATOR"])
    db.commit()
    ip = "203.0.113.60"
    per_ip = db_app.state.settings.login_max_failures_per_ip
    for n in range(per_ip - 1):
        with pytest.raises(AppError):
            _login(db_app, db, f"target{n}@example.org", "guess-guess-guess", ip)
    _login(db_app, db, "insider@example.org", TEST_PASSWORD, ip)
    with pytest.raises(AppError):
        _login(db_app, db, "target-last@example.org", "guess-guess-guess", ip)
    with pytest.raises(AppError) as blocked:
        _login(db_app, db, "insider@example.org", TEST_PASSWORD, ip)
    assert blocked.value.code == "RATE_LIMITED"


@pytest.mark.db
def test_correcting_a_participants_email_ends_their_personal_link(
    db_app: Any, db: Any, new_api: Any
) -> None:
    from tests.conftest import make_participant, make_project

    project = make_project(db, "LINKS")
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    db.commit()
    pa = new_api()
    pa.login("pa@example.org")
    p = make_participant(pa, project.id, "Asha")
    base = f"/api/v1/projects/{project.id}/participants/{p['id']}"
    token = pa.post(f"{base}/portal-link").json()["url"].split("#", 1)[1]
    visitor = new_api()
    assert visitor.get("/api/v1/portal/me", headers={"X-Portal-Token": token}).status_code == 200
    fixed = pa.patch(
        base,
        json={"display_label": "Asha", "language_code": "hi", "email": "asha.new@example.org"},
    )
    assert fixed.status_code == 200, fixed.text
    assert visitor.get("/api/v1/portal/me", headers={"X-Portal-Token": token}).status_code == 404
