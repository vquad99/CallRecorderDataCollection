"""API input and output hardening (owner's test list, Option B).

Request size limits, NUL characters, injection strings in every search and filter, fields a client
must not be able to set, error answers that echo nothing back, and protective headers on every API
answer including errors.

Requirements: SEC-006, SEC-007, SEC-011, SEC-013, ROLE-010, PART-002, TASK-002
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from tests.conftest import Api, make_participant, make_project, make_user

pytestmark = pytest.mark.db


@pytest.fixture
def admin(db: Any, new_api: Any) -> Api:
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    api: Api = new_api()
    assert api.login("root@example.org").status_code == 200
    return api


def _error(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


# ------------------------------------------------------------------------------------ size limits


def test_oversized_json_is_refused_before_it_is_read(admin: Api) -> None:
    big = {"email": "x@example.org", "password": "p" * 3_000_000}
    response = admin.post("/api/v1/auth/login", json=big)
    assert _error(response) == (413, "PAYLOAD_TOO_LARGE")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


def test_oversized_body_without_a_declared_length_is_refused(admin: Api) -> None:
    def stream() -> Iterator[bytes]:
        for _ in range(40):
            yield b"x" * 100_000  # 4 MB in pieces, no Content-Length header

    response = admin.client.post(
        "/api/v1/auth/password/forgot",
        content=stream(),
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": admin.client.cookies.get("csrf_token") or "",
        },
    )
    assert _error(response) == (413, "PAYLOAD_TOO_LARGE")


def test_audio_chunks_have_their_own_larger_limit(admin: Api) -> None:
    rid = "00000000-0000-0000-0000-000000000000"
    too_big = admin.put(
        f"/api/v1/recordings/{rid}/chunks/0",
        content=b"\0" * 8_000_004,
        headers={"Content-Type": "application/octet-stream", "X-Content-SHA256": "0" * 64},
    )
    assert _error(too_big) == (413, "PAYLOAD_TOO_LARGE")
    under = admin.put(
        f"/api/v1/recordings/{rid}/chunks/0",
        content=b"\0" * 3_000_000,  # over the JSON limit, under the chunk limit: reaches the route
        headers={"Content-Type": "application/octet-stream", "X-Content-SHA256": "0" * 64},
    )
    # Past the size check: answered by the route (no storage in this test app, or no recording).
    assert under.status_code in (404, 503), under.text


# ------------------------------------------------------------------------------- NUL characters


def test_nul_characters_are_refused_not_a_server_error(admin: Api, db: Any, new_api: Any) -> None:
    project = make_project(db, "NUL")
    anonymous: Api = new_api()
    anonymous.client.get("/api/v1/auth/csrf")
    attempts = {
        "query": admin.get("/api/v1/users", params={"search": "a\x00b"}),
        "json body": admin.post(
            f"/api/v1/projects/{project.id}/participants",
            json={"display_label": "A\u0000B", "language_code": "hi"},
        ),
        "sign-in, not signed in": anonymous.login("x\u0000@example.org"),
    }
    results = {k: _error(r) for k, r in attempts.items()}
    assert results == dict.fromkeys(attempts, (422, "VALIDATION_ERROR")), results
    literal = admin.post(
        f"/api/v1/projects/{project.id}/participants",
        json={"display_label": "back\\u0000slash", "language_code": "hi"},
    )
    assert literal.status_code == 201, "a backslash followed by u0000 is ordinary text"
    assert literal.json()["display_label"] == "back\\u0000slash"


# ------------------------------------------------------------------------------ injection strings

PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    '" OR ""="',
    "\\",
    "%' OR 1=1 --",
    "😀 ünïcödé",
    "a" * 200,
]


def test_injection_strings_in_every_search_and_filter(admin: Api, db: Any) -> None:
    project = make_project(db, "INJ")
    make_participant(admin, project.id, "Asha")
    endpoints = {
        "/api/v1/users": ["search", "role"],
        "/api/v1/projects": ["search"],
        f"/api/v1/projects/{project.id}/participants": ["search"],
        f"/api/v1/projects/{project.id}/member-candidates": ["search"],
        "/api/v1/audit-logs": ["action", "entity_type", "entity_id"],
        "/api/v1/tasks": ["status", "mode"],
    }
    problems = []
    for path, params in endpoints.items():
        for param in params:
            for payload in PAYLOADS:
                response = admin.get(path, params={param: payload})
                if response.status_code >= 500:
                    problems.append(f"{path}?{param}={payload!r}: {response.status_code}")
                elif response.status_code == 200 and "OR" in payload:
                    body = response.json()
                    items = body["items"] if isinstance(body, dict) else body
                    if items:
                        problems.append(f"{path}?{param}={payload!r}: returned {len(items)} rows")
    assert db.execute(text("SELECT count(*) FROM users")).scalar() >= 1, "users table intact"
    assert not problems, "\n".join(problems)


# -------------------------------------------------------------------- fields a client cannot set


def test_fields_owned_by_the_server_cannot_be_set_by_a_client(
    admin: Api, db: Any, new_api: Any
) -> None:
    project = make_project(db, "MASS")
    moderator = make_user(db, "m@example.org", ["MODERATOR"], projects=[project])
    a = make_participant(admin, project.id, "Asha")
    b = make_participant(admin, project.id, "Bina")
    forged_id = "11111111-1111-1111-1111-111111111111"

    task = admin.post(
        "/api/v1/tasks",
        json={
            "project_id": str(project.id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": a["id"],
            "participant_b_id": b["id"],
            "id": forged_id,
            "status": "APPROVED",
            "task_code": "T999999",
            "created_by": str(moderator.id),
        },
    ).json()
    assert task["id"] != forged_id
    assert task["status"] in ("DRAFT", "ASSIGNED")
    assert task["task_code"] != "T999999"

    person = admin.post(
        f"/api/v1/projects/{project.id}/participants",
        json={
            "display_label": "Chandra",
            "language_code": "hi",
            "participant_code": "P999999",
            "deleted": True,
            "id": forged_id,
        },
    ).json()
    assert (person["participant_code"], person["deleted"]) != ("P999999", True)
    assert person["id"] != forged_id

    changed = admin.patch(
        f"/api/v1/users/{moderator.id}",
        json={"display_name": "Mod", "roles": ["SUPER_ADMIN"], "status": "DISABLED"},
    ).json()
    assert changed["roles"] == ["MODERATOR"], "roles change only through PUT .../roles"
    assert changed["status"] == "ACTIVE", "status changes only through disable / enable"

    renamed = admin.patch(
        f"/api/v1/projects/{project.id}",
        json={
            "name": "Renamed",
            "allows_telephony": True,
            "allows_face_to_face": True,
            "code": "HIJACK",
            "status": "ARCHIVED",
        },
    ).json()
    assert (renamed["code"], renamed["status"]) == ("MASS", "ACTIVE")


# --------------------------------------------------------------------------------- error answers


def test_errors_never_echo_what_was_sent(admin: Api) -> None:
    secret = "my-secret-password-value-0001"
    anonymous_bad = admin.post("/api/v1/auth/login", json={"email": secret, "password": [secret]})
    assert anonymous_bad.status_code == 422
    assert secret not in anonymous_bad.text
    wrong_type = admin.post("/api/v1/users", json={"email": {"$ne": secret}, "roles": secret})
    assert wrong_type.status_code == 422
    assert secret not in wrong_type.text


def test_protective_headers_on_every_kind_of_api_answer(admin: Api, new_api: Any) -> None:
    anonymous: Api = new_api()
    answers = {
        "200": admin.get("/api/v1/auth/me"),
        "401": anonymous.get("/api/v1/auth/me"),
        "403": admin.client.post("/api/v1/projects", json={}),  # no CSRF header
        "404": admin.get("/api/v1/projects/00000000-0000-0000-0000-000000000000"),
        "422": admin.get("/api/v1/projects/not-an-id"),
    }
    expected = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "cache-control": "no-store",
        "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    }
    problems = []
    for status, response in answers.items():
        assert str(response.status_code) == status, (status, response.status_code)
        for name, value in expected.items():
            if response.headers.get(name) != value:
                problems.append(f"{status}: {name}={response.headers.get(name)!r}")
        if not response.headers.get("x-request-id"):
            problems.append(f"{status}: no request ID")
    assert not problems, "\n".join(problems)
