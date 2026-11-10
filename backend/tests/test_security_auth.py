"""Sign-in and session security beyond tests/test_auth.py (owner's test list, Option B).

Session fixation, tokens at rest, rights that change mid-session, one-time codes used once,
password guessing through signed-in endpoints, account enumeration, and reset links that cannot be
pointed at another host.

Requirements: AUTH-002, AUTH-003, AUTH-005, AUTH-006, AUTH-007, AUTH-008, AUTH-009, AUTH-011, AUTH-013, ROLE-010, SEC-011
"""

from __future__ import annotations

import time
import types
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.modules.auth import security
from tests.conftest import (
    TEST_FERNET_KEY,
    TEST_PASSWORD,
    Api,
    link_token,
    make_project,
    make_user,
    read_outbox,
)

pytestmark = pytest.mark.db


def test_a_session_id_planted_before_sign_in_is_never_used(db: Any, new_api: Any) -> None:
    make_user(db, "fix@example.org", ["MODERATOR"])
    api: Api = new_api()
    planted = "attacker-chosen-session-value-0123456789"
    api.client.cookies.set("ccp_session", planted)
    signed_in = api.login("fix@example.org")
    assert signed_in.status_code == 200
    issued = signed_in.cookies.get("ccp_session")  # the value the server sets in its answer
    assert issued
    assert issued != planted
    attacker: Api = new_api()
    attacker.client.cookies.set("ccp_session", planted)
    assert attacker.get("/api/v1/auth/me").status_code == 401


def test_session_tokens_are_stored_only_as_hashes(db: Any, new_api: Any) -> None:
    make_user(db, "hash@example.org", ["MODERATOR"])
    api: Api = new_api()
    api.login("hash@example.org")
    token = api.client.cookies.get("ccp_session") or ""
    row = db.execute(text("SELECT * FROM sessions")).mappings().one()
    assert token not in " ".join(str(v) for v in row.values())
    assert row["token_hash"] == security.hash_token(token)


def test_a_removed_role_stops_working_at_the_next_request(db: Any, new_api: Any) -> None:
    project = make_project(db, "RIGHTS")
    make_user(db, "boss@example.org", ["SUPER_ADMIN"])
    target = make_user(db, "lead@example.org", ["PROJECT_ADMIN"], projects=[project])
    lead: Api = new_api()
    lead.login("lead@example.org")
    assert lead.get("/api/v1/audit-logs").status_code == 200
    boss: Api = new_api()
    boss.login("boss@example.org")
    changed = boss.put(f"/api/v1/users/{target.id}/roles", json={"roles": ["MODERATOR"]})
    assert changed.status_code == 200, changed.text
    assert lead.get("/api/v1/audit-logs").status_code == 403, "same session, role gone"


def test_removal_from_a_project_hides_it_at_the_next_request(db: Any, new_api: Any) -> None:
    project = make_project(db, "LEAVE")
    make_user(db, "boss@example.org", ["SUPER_ADMIN"])
    member = make_user(db, "member@example.org", ["MODERATOR"], projects=[project])
    api: Api = new_api()
    api.login("member@example.org")
    assert api.get(f"/api/v1/projects/{project.id}").status_code == 200
    boss: Api = new_api()
    boss.login("boss@example.org")
    assert boss.delete(f"/api/v1/projects/{project.id}/members/{member.id}").status_code == 204
    assert api.get(f"/api/v1/projects/{project.id}").status_code == 404


def test_an_administrator_can_end_every_session_of_a_user(db: Any, new_api: Any) -> None:
    make_user(db, "boss@example.org", ["SUPER_ADMIN"])
    target = make_user(db, "lost.laptop@example.org", ["MODERATOR"])
    devices = [new_api(), new_api()]
    for device in devices:
        device.login("lost.laptop@example.org")
        assert device.get("/api/v1/auth/me").status_code == 200
    boss: Api = new_api()
    boss.login("boss@example.org")
    assert boss.post(f"/api/v1/users/{target.id}/sessions/revoke").status_code == 200
    assert [d.get("/api/v1/auth/me").status_code for d in devices] == [401, 401]


def test_a_password_reset_ends_every_open_session(db: Any, new_api: Any, outbox: Path) -> None:
    make_user(db, "reset@example.org", ["MODERATOR"])
    old: Api = new_api()
    old.login("reset@example.org")
    anon: Api = new_api()
    anon.client.get("/api/v1/auth/csrf")
    anon.post("/api/v1/auth/password/forgot", json={"email": "reset@example.org"})
    token = link_token(read_outbox(outbox)[-1])
    done = anon.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": "a-brand-new-passphrase-2026"},
    )
    assert done.status_code == 204, done.text
    assert old.get("/api/v1/auth/me").status_code == 401


def test_reset_links_point_at_the_configured_site_whatever_the_request_host(
    db: Any, new_api: Any, outbox: Path, db_app: Any
) -> None:
    make_user(db, "host@example.org", ["MODERATOR"])
    api: Api = new_api()
    api.client.get("/api/v1/auth/csrf")
    api.post(
        "/api/v1/auth/password/forgot",
        json={"email": "host@example.org"},
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"},
    )
    message = read_outbox(outbox)[-1]
    assert "evil.example" not in message
    assert f"{db_app.state.settings.public_app_url}/reset-password?token=" in message


def test_sign_in_failures_look_the_same_for_every_cause(db: Any, new_api: Any) -> None:
    make_user(db, "known@example.org", ["MODERATOR"])
    make_user(db, "off@example.org", ["MODERATOR"], status="DISABLED")
    answers = []
    for email, password in (
        ("nobody@example.org", "whatever-password-1"),
        ("known@example.org", "wrong-password-123"),
        ("off@example.org", None),
    ):
        api: Api = new_api()
        r = api.login(email, password) if password else api.login(email)
        error = dict(r.json()["error"])
        error.pop("request_id", None)
        answers.append((r.status_code, error))
    assert answers[0] == answers[1] == answers[2], answers


def test_an_unknown_email_still_costs_a_full_password_check(
    db: Any, new_api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No timing shortcut that would reveal which addresses have accounts."""
    calls: list[str] = []
    real = security._hasher

    class Counting:
        def verify(self, hashed: str, password: str) -> bool:
            calls.append(hashed)
            return real.verify(hashed, password)

        def __getattr__(self, name: str) -> Any:
            return getattr(real, name)

    monkeypatch.setattr(security, "_hasher", Counting())
    api: Api = new_api()
    assert api.login("nobody@example.org", "whatever-password-1").status_code == 401
    assert len(calls) == 1
    assert calls[0].startswith("$argon2id$")


def _frozen_clock(monkeypatch: pytest.MonkeyPatch, at: float) -> None:
    monkeypatch.setattr(security, "time", types.SimpleNamespace(time=lambda: at))


def test_an_authenticator_code_is_accepted_only_once(
    db: Any, new_api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(db, "otp@example.org", ["MODERATOR"])
    now = time.time()
    step = int(now // security.TOTP_STEP_SECONDS)
    _frozen_clock(monkeypatch, now)
    api: Api = new_api()
    api.login("otp@example.org")
    secret = api.post("/api/v1/auth/mfa/enroll", json={"password": TEST_PASSWORD}).json()["secret"]
    confirm_code = security._totp_at(secret, step - 1)
    assert api.post("/api/v1/auth/mfa/confirm", json={"code": confirm_code}).status_code == 204

    def sign_in(code: str) -> int:
        fresh: Api = new_api()
        return int(fresh.login("otp@example.org", totp_code=code).status_code)

    assert sign_in(confirm_code) == 401, "the enrolment code cannot be replayed to sign in"
    current = security._totp_at(secret, step)
    assert sign_in(current) == 200
    assert sign_in(current) == 401, "an intercepted code cannot be used a second time"
    assert sign_in(security._totp_at(secret, step + 1)) == 200, "the next code still works"


def test_guessing_authenticator_codes_is_throttled(
    db: Any, new_api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = make_user(db, "guess@example.org", ["MODERATOR"])
    now = time.time()
    _frozen_clock(monkeypatch, now)
    secret = security.new_totp_secret()
    user.mfa_enabled = True
    user.mfa_secret_enc = security.FieldCipher(TEST_FERNET_KEY).encrypt(secret)
    db.commit()
    api: Api = new_api()
    for _ in range(5):
        assert api.login("guess@example.org", totp_code="000000").status_code == 401
    right = security._totp_at(secret, int(now // security.TOTP_STEP_SECONDS))
    assert api.login("guess@example.org", totp_code=right).status_code == 429


def test_guessing_the_password_through_a_signed_in_session_is_throttled(
    db: Any, new_api: Any
) -> None:
    make_user(db, "stolen@example.org", ["MODERATOR"])
    api: Api = new_api()
    api.login("stolen@example.org")
    for _ in range(5):
        r = api.post(
            "/api/v1/auth/password/change",
            json={"current_password": "guess-number-x", "new_password": "unused-new-pass-2026"},
        )
        assert r.status_code == 400
    blocked = api.post(
        "/api/v1/auth/password/change",
        json={
            "current_password": "correct-horse-battery-staple",
            "new_password": "unused-new-pass-2026",
        },
    )
    assert blocked.status_code == 429


def test_sessions_list_shows_only_the_callers_own(db: Any, new_api: Any) -> None:
    make_user(db, "a@example.org", ["MODERATOR"])
    make_user(db, "b@example.org", ["MODERATOR"])
    a: Api = new_api()
    b: Api = new_api()
    a.login("a@example.org")
    b.login("b@example.org")
    mine = {s["id"] for s in a.get("/api/v1/auth/sessions").json()}
    theirs = (
        db.execute(
            text(
                "SELECT s.id FROM sessions s JOIN users u ON u.id = s.user_id"
                " WHERE u.email = 'b@example.org'"
            )
        )
        .scalars()
        .all()
    )
    assert mine
    assert not mine & {str(t) for t in theirs}
    other = str(theirs[0])
    assert a.delete(f"/api/v1/auth/sessions/{other}").status_code == 404
    assert b.get("/api/v1/auth/me").status_code == 200, "someone else's session is untouched"
