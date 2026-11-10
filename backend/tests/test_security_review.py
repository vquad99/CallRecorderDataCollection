"""Fixes from the independent security review of 2026-11-10 (D-064). Each test fails if its fix is
removed.

Requirements: SEC-006, SEC-007, AUTH-008, AUTH-012, ROLE-001, ROLE-007, USER-004
"""

from __future__ import annotations

import inspect
import re
import secrets
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.auth import router as auth_router
from tests import test_recordings
from tests.conftest import (
    Api,
    build_settings,
    link_token,
    make_project,
    make_user,
    read_outbox,
)

COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.yml"
NGINX = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world


def test_the_backend_trusts_forwarded_addresses_only_from_its_web_server() -> None:
    text = COMPOSE.read_text()
    trusted = re.search(r"FORWARDED_ALLOW_IPS:\s*\$\{FORWARDED_ALLOW_IPS:-([^}]+)\}", text)
    web_ip = re.search(r"web:.*?ipv4_address:\s*([0-9.]+)", text, re.S)
    assert trusted, "the backend must name the proxy it trusts"
    assert web_ip, "the web container needs a fixed address"
    assert trusted.group(1) == web_ip.group(1) != "*"


def test_the_web_server_hides_its_version_and_keeps_tokens_out_of_its_log() -> None:
    conf = NGINX.read_text()
    assert "server_tokens off;" in conf
    assert "Strict-Transport-Security" in conf
    log_format = re.search(r"log_format ccp_no_query (.*?);", conf, re.S)
    assert log_format
    assert "$request " not in log_format.group(1)
    assert "$uri" in log_format.group(1)
    assert "access_log /var/log/nginx/access.log ccp_no_query;" in conf
    assert "proxy_set_header X-Request-ID $request_id;" in conf
    # One address towards the API, never the client-supplied chain (a false first entry dodged the
    # per-address sign-in limit on the Render copy, 2026-11-10).
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in conf
    assert "$proxy_add_x_forwarded_for" not in conf


def test_forgot_password_does_its_work_after_answering() -> None:
    # The handler takes no database session: lookup, token and email run as a background task, so
    # the answer takes the same time for known and unknown addresses.
    params = inspect.signature(auth_router.forgot).parameters
    assert "db" not in params
    assert "background" in params


@pytest.mark.db
def test_made_up_session_cookies_share_one_allowance_per_address(migrated_db: str) -> None:
    client = TestClient(
        create_app(build_settings(database_url=migrated_db, rate_limit_reads_per_minute=2))
    )
    statuses = []
    for _ in range(25):
        client.cookies.set("ccp_session", secrets.token_urlsafe(32))
        statuses.append(client.get("/api/v1/auth/me").status_code)
    assert 429 in statuses, "a fresh fake cookie must not reset the limit"
    assert statuses.index(429) == 20  # ten times the per-session allowance


@pytest.mark.db
def test_starting_two_step_sign_in_needs_the_password(db: Any, new_api: Any) -> None:
    make_user(db, "mfa@example.org", ["MODERATOR"])
    api: Api = new_api()
    api.login("mfa@example.org")
    assert api.post("/api/v1/auth/mfa/enroll", json={}).status_code == 422
    wrong = api.post("/api/v1/auth/mfa/enroll", json={"password": "not-the-password"})
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (400, "INVALID_CREDENTIALS")


@pytest.mark.db
def test_changing_an_email_voids_links_sent_to_the_old_address(
    db: Any, new_api: Any, outbox: Path
) -> None:
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    user = make_user(db, "old@example.org", ["MODERATOR"])
    admin: Api = new_api()
    admin.login("root@example.org")
    assert admin.post(f"/api/v1/users/{user.id}/send-password-link").json()["sent"]
    token = link_token(read_outbox(outbox)[-1])
    assert (
        admin.patch(f"/api/v1/users/{user.id}", json={"email": "new@example.org"}).status_code
        == 200
    )
    stranger: Api = new_api()
    stranger.client.get("/api/v1/auth/csrf")
    used = stranger.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "brand-new-pass-123"}
    )
    assert used.status_code == 400


@pytest.mark.db
def test_removing_the_moderator_role_ends_their_task_assignments(world: dict[str, Any]) -> None:
    db = world["db"]
    task_id = world["task"]["id"]
    assert world["mod"].get(f"/api/v1/tasks/{task_id}").status_code == 200
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    root = world["api"]("root@example.org")
    mod_id = world["mod"].get("/api/v1/auth/me").json()["id"]
    changed = root.put(f"/api/v1/users/{mod_id}/roles", json={"roles": ["CLIENT_VIEWER"]})
    assert changed.status_code == 200
    assert world["mod"].get(f"/api/v1/tasks/{task_id}").status_code in (403, 404)
    assert root.get(f"/api/v1/tasks/{task_id}").json()["moderator_name"] is None


@pytest.mark.db
def test_team_emails_and_the_people_picker_are_limited(db: Any, new_api: Any) -> None:
    project = make_project(db, "TEAM")
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[project])
    make_user(db, "free.person@example.org", ["MODERATOR"])
    make_user(db, "boss@example.org", ["SUPER_ADMIN"])
    pa: Api = new_api()
    pa.login("pa@example.org")
    cv: Api = new_api()
    cv.login("cv@example.org")
    members = f"/api/v1/projects/{project.id}/members"
    assert all(m["email"] for m in pa.get(members).json())
    assert all(m["email"] is None for m in cv.get(members).json())
    picker = f"/api/v1/projects/{project.id}/member-candidates"
    assert pa.get(picker, params={"search": "free"}).json() == []
    assert pa.get(picker, params={"search": "@example.org"}).json() == []
    found = pa.get(picker, params={"search": "Free.Person@example.org"}).json()
    assert [c["email"] for c in found] == ["free.person@example.org"]
    assert pa.get(picker, params={"search": "boss@example.org"}).json() == []
