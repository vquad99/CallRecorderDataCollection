"""Audit-log viewer scope, rate limits, input validation on every write route, escalation attempts.

Requirements: SEC-001, SEC-005, SEC-006, SEC-011
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import Api, build_settings, make_project, make_user

pytestmark = pytest.mark.db


def test_audit_viewer_is_scoped(db: Any, new_api: Any) -> None:
    mine, other = make_project(db, "MINE"), make_project(db, "OTHER")
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[mine])
    make_user(db, "mod@example.org", ["MODERATOR"], projects=[mine])
    root, pa, mod = new_api(), new_api(), new_api()
    for api, email in ((root, "root"), (pa, "pa"), (mod, "mod")):
        api.login(f"{email}@example.org")
    for pid in (mine.id, other.id):
        root.put(
            f"/api/v1/projects/{pid}/languages",
            json={"languages": [{"language_code": "hi", "dialect": ""}]},
        )
    everything = root.get("/api/v1/audit-logs", params={"action": "project"}).json()
    assert {e["project_id"] for e in everything["items"]} == {str(mine.id), str(other.id)}
    scoped = pa.get("/api/v1/audit-logs", params={"action": "project"}).json()
    assert {e["project_id"] for e in scoped["items"]} == {str(mine.id)}
    assert scoped["items"][0]["actor_email"] == "root@example.org"
    assert mod.get("/api/v1/audit-logs").status_code == 403


def test_write_rate_limit_returns_429(migrated_db: str) -> None:
    client = TestClient(
        create_app(build_settings(database_url=migrated_db, rate_limit_writes_per_minute=3))
    )
    client.get("/api/v1/auth/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("csrf_token") or ""}
    codes = [
        client.post(
            "/api/v1/auth/password/forgot", json={"email": "x@example.org"}, headers=headers
        ).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [202, 202, 202]
    assert codes[3] == 429
    blocked = client.post(
        "/api/v1/auth/password/forgot", json={"email": "x@example.org"}, headers=headers
    )
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    client.close()


def test_every_write_route_rejects_malformed_bodies(db: Any, new_api: Any) -> None:
    import re
    import uuid

    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    api: Api = new_api()
    api.login("root@example.org")
    schema = api.client.app.openapi()  # type: ignore[attr-defined]
    failures = []
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            if "requestBody" not in op:
                continue
            ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
            props = schema["components"]["schemas"][ref].get("properties", {})
            body = {name: {"not": ["valid"]} for name in props}
            url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
            response = getattr(api, method)(url, json=body)
            if (
                response.status_code != 422
                or response.json()["error"]["code"] != "VALIDATION_ERROR"
            ):
                failures.append(f"{method.upper()} {path} -> {response.status_code}")
    assert not failures, failures


def test_escalation_attempts_fail(db: Any, new_api: Any) -> None:
    mine, other = make_project(db, "MINE"), make_project(db, "OTHER")
    pa_user = make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[mine])
    mod_user = make_user(db, "mod@example.org", ["MODERATOR"], projects=[mine])
    pa, mod = new_api(), new_api()
    pa.login("pa@example.org")
    mod.login("mod@example.org")
    assert (
        pa.put(f"/api/v1/users/{pa_user.id}/roles", json={"roles": ["SUPER_ADMIN"]}).status_code
        == 403
    )
    assert (
        pa.post(
            f"/api/v1/projects/{other.id}/members", json={"user_id": str(pa_user.id)}
        ).status_code
        == 404
    )
    assert (
        mod.post(
            f"/api/v1/projects/{mine.id}/members", json={"user_id": str(mod_user.id)}
        ).status_code
        == 403
    )
    assert (
        mod.patch("/api/v1/settings", json={"values": {"capacity.staff_accounts": 1}}).status_code
        == 403
    )
