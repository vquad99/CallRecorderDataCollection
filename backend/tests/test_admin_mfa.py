"""Two-step sign-in is required for Super Admin and Project Admin accounts (D-106): until it is
set up, such an account can do nothing but set it up; other roles are not asked; a lost
authenticator has a way back.

Requirements: AUTH-008, SEC-011
"""

from __future__ import annotations

import time
import types
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import cli
from app.core.config import Settings
from app.main import create_app
from app.modules.audit.models import AuditLog
from app.modules.auth import security
from app.modules.auth.models import User
from tests.conftest import TEST_PASSWORD, Api, build_settings, make_project, make_user

pytestmark = pytest.mark.db


@pytest.fixture
def strict(migrated_db: str) -> Iterator[dict[str, Any]]:
    """An application that asks admins for two-step sign-in, as the live site does."""
    settings = build_settings(database_url=migrated_db, require_admin_mfa=True)
    app = create_app(settings)
    clients: list[TestClient] = []

    def api() -> Api:
        client = TestClient(app)
        clients.append(client)
        return Api(client)

    with app.state.session_factory() as db:
        yield {"app": app, "db": db, "api": api, "settings": settings}
    for client in clients:
        client.close()


@pytest.fixture
def code(monkeypatch: pytest.MonkeyPatch) -> Callable[[int, str], str]:
    """Codes for the previous, current and next 30-second step; the clock stands still, so each
    stays valid for the whole test (a code is accepted once only)."""
    now = time.time()
    step = int(now // security.TOTP_STEP_SECONDS)
    monkeypatch.setattr(security, "time", types.SimpleNamespace(time=lambda: now))
    return lambda offset, secret: security._totp_at(secret, step + offset)


def set_up(api: Api, code: Callable[[int, str], str], offset: int = -1) -> str:
    started = api.post("/api/v1/auth/mfa/enroll", json={"password": TEST_PASSWORD})
    assert started.status_code == 200, started.text
    secret: str = started.json()["secret"]
    done = api.post("/api/v1/auth/mfa/confirm", json={"code": code(offset, secret)})
    assert done.status_code == 204, done.text
    return secret


def test_the_rule_is_on_everywhere_except_development_and_test() -> None:
    def required(**values: Any) -> bool:
        return Settings(**{**build_settings().model_dump(), **values}).admin_mfa_required

    assert required(app_env="test") is False
    assert required(app_env="development") is False
    assert required(app_env="development", require_admin_mfa=True) is True


def test_an_admin_without_two_step_sign_in_can_only_set_it_up(
    strict: dict[str, Any], code: Callable[[int, str], str]
) -> None:
    db = strict["db"]
    project = make_project(db, "TWOSTEP")
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    pa: Api = strict["api"]()
    signed_in = pa.login("pa@example.org")
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["mfa_setup_required"] is True
    me = pa.get("/api/v1/auth/me").json()
    assert (me["mfa_enabled"], me["mfa_setup_required"]) == (False, True)

    # Nothing else answers: no reading, no changing, no way round through other account routes.
    for method, path in [
        ("get", "/api/v1/projects"),
        ("get", f"/api/v1/projects/{project.id}"),
        ("get", "/api/v1/dashboard"),
        ("get", "/api/v1/tasks"),
        ("get", "/api/v1/auth/sessions"),
        ("post", "/api/v1/auth/password/change"),
        ("post", "/api/v1/auth/mfa/disable"),
    ]:
        refused = getattr(pa, method)(path)
        assert refused.status_code == 403, (path, refused.text)
        assert refused.json()["error"]["code"] == "MFA_SETUP_REQUIRED", path

    # Other roles are not asked.
    mod: Api = strict["api"]()
    assert mod.login("mod@example.org").json()["mfa_setup_required"] is False
    assert mod.get("/api/v1/projects").status_code == 200

    # Setting it up opens everything the role has; the next sign-in asks for a code.
    secret = set_up(pa, code)
    assert pa.get("/api/v1/auth/me").json()["mfa_setup_required"] is False
    assert pa.get("/api/v1/projects").json()["total"] == 1
    again: Api = strict["api"]()
    assert again.login("pa@example.org").json()["error"]["code"] == "MFA_REQUIRED"
    assert again.login("pa@example.org", totp_code=code(0, secret)).status_code == 200
    assert again.get("/api/v1/projects").status_code == 200

    # Turning it off (password and a fresh code) is allowed, to move to a new phone: the
    # account is then back to setting it up, and nothing else.
    off = again.post(
        "/api/v1/auth/mfa/disable", json={"password": TEST_PASSWORD, "code": code(1, secret)}
    )
    assert off.status_code == 204, off.text
    assert again.get("/api/v1/projects").json()["error"]["code"] == "MFA_SETUP_REQUIRED"
    assert again.post("/api/v1/auth/logout").status_code == 204


def test_a_role_given_later_brings_the_rule_and_viewing_as_does_not_skip_it(
    strict: dict[str, Any], code: Callable[[int, str], str]
) -> None:
    db = strict["db"]
    project = make_project(db, "LATER")
    sa_user = make_user(db, "sa@example.org", ["SUPER_ADMIN"])
    mod_user = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    pa_user = make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    sa: Api = strict["api"]()
    sa.login("sa@example.org")
    # A Super Admin is under the rule too: no user management, no looking as someone else.
    assert sa.get("/api/v1/users").json()["error"]["code"] == "MFA_SETUP_REQUIRED"
    assert (
        sa.post("/api/v1/auth/view-as", json={"user_id": str(mod_user.id)}).json()["error"]["code"]
        == "MFA_SETUP_REQUIRED"
    )
    set_up(sa, code)
    assert sa.get("/api/v1/users").status_code == 200

    # A moderator works without it; once made Project Admin, their next request is refused.
    mod: Api = strict["api"]()
    mod.login("mod@example.org")
    assert mod.get("/api/v1/projects").status_code == 200
    promoted = sa.put(
        f"/api/v1/users/{mod_user.id}/roles", json={"roles": ["MODERATOR", "PROJECT_ADMIN"]}
    )
    assert promoted.status_code == 200, promoted.text
    assert mod.get("/api/v1/projects").json()["error"]["code"] == "MFA_SETUP_REQUIRED"

    # Looking at the app as an admin who has not set it up is allowed (read-only, and the one
    # looking has two-step sign-in); it does not set anything up for that admin.
    seen = sa.post("/api/v1/auth/view-as", json={"user_id": str(pa_user.id)})
    assert seen.status_code == 200, seen.text
    assert sa.get("/api/v1/projects").status_code == 200
    assert sa.delete("/api/v1/auth/view-as").status_code == 200
    db.expire_all()
    assert db.get(User, pa_user.id).mfa_enabled is False
    assert db.get(User, sa_user.id).mfa_enabled is True


def test_a_lost_authenticator_has_a_way_back(
    strict: dict[str, Any], code: Callable[[int, str], str]
) -> None:
    db = strict["db"]
    sa_user = make_user(db, "sa@example.org", ["SUPER_ADMIN"])
    pa_user = make_user(db, "pa@example.org", ["PROJECT_ADMIN"])
    mod_user = make_user(db, "mod@example.org", ["MODERATOR"])
    sa: Api = strict["api"]()
    sa.login("sa@example.org")
    set_up(sa, code)
    pa: Api = strict["api"]()
    pa.login("pa@example.org")
    set_up(pa, code)
    assert pa.get("/api/v1/projects").status_code == 200

    # Another Super Admin resets it: two-step sign-in off, signed out everywhere, audited.
    reset = sa.post(f"/api/v1/users/{pa_user.id}/mfa/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["sessions_revoked"] == 1
    assert pa.get("/api/v1/auth/me").status_code == 401
    back: Api = strict["api"]()
    assert back.login("pa@example.org").json()["mfa_setup_required"] is True  # password only
    assert back.get("/api/v1/projects").json()["error"]["code"] == "MFA_SETUP_REQUIRED"
    set_up(back, code, offset=0)
    assert back.get("/api/v1/projects").status_code == 200
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.mfa_reset"))
    assert entry is not None
    assert (entry.entity_id, entry.actor_id) == (str(pa_user.id), sa_user.id)

    # Nothing to reset, one's own account, and people who do not manage users.
    assert sa.post(f"/api/v1/users/{mod_user.id}/mfa/reset").json()["error"]["code"] == (
        "MFA_NOT_ENABLED"
    )
    assert sa.post(f"/api/v1/users/{sa_user.id}/mfa/reset").json()["error"]["code"] == (
        "USE_ACCOUNT_PAGE"
    )
    assert back.post(f"/api/v1/users/{sa_user.id}/mfa/reset").status_code == 403

    # The last Super Admin has the server's command line.
    assert cli.reset_mfa(strict["settings"], "SA@example.org").startswith(
        "two-step sign-in is off; 1 session(s) ended"
    )
    assert sa.get("/api/v1/auth/me").status_code == 401
    assert cli.reset_mfa(strict["settings"], "sa@example.org") == (
        "has no two-step sign-in to reset"
    )
    with pytest.raises(cli.SeedRefused):
        cli.reset_mfa(strict["settings"], "nobody@example.org")
    fresh: Api = strict["api"]()
    assert fresh.login("sa@example.org").json()["mfa_setup_required"] is True
    by_server = db.scalars(
        select(AuditLog).where(AuditLog.action == "user.mfa_reset").order_by(AuditLog.created_at)
    ).all()
    assert len(by_server) == 2
    assert by_server[-1].actor_id is None
