"""Role-based access control: registry = database = documented matrix; every role against every
protected endpoint by direct HTTP; anonymous calls rejected everywhere.

Requirements: ROLE-001, ROLE-002, ROLE-003, ROLE-004, ROLE-005, ROLE-006, ROLE-007, ROLE-008, ROLE-009, ROLE-010, ROLE-012, AUTH-011
"""

import re
import uuid
from pathlib import Path
from typing import Any

import fastapi.routing as fr
import pytest
from sqlalchemy import select

from app.core.permissions import ROLE_PERMISSIONS, Perm, Role
from app.main import create_app
from app.modules.auth.models import Permission, RolePermission, RoleRecord
from tests.conftest import Api, build_settings, make_project, make_user

ARCHITECTURE = Path(__file__).resolve().parents[2] / "docs" / "ARCHITECTURE.md"
MATRIX_ROLES = [
    Role.SUPER_ADMIN,
    Role.PROJECT_ADMIN,
    Role.MODERATOR,
    Role.QC_EXECUTIVE,
    Role.CLIENT_VIEWER,
]

# Routes anyone may call, and routes any signed-in user may call for themselves.
PUBLIC = {
    ("GET", "/api/v1/version"),
    ("GET", "/api/v1/auth/csrf"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
    # Participant personal page: the link's secret is the credential (tests/test_portal.py).
    ("GET", "/api/v1/portal/me"),
    ("POST", "/api/v1/portal/consent"),
}
SELF_SERVICE_PREFIXES = ("/api/v1/auth/",)


def _route_contexts() -> list[Any]:
    app = create_app(build_settings())
    contexts = []
    for c in fr.iter_route_contexts(app.routes):
        path = c.path or ""
        if path.startswith("/api/v1/") and "docs" not in path and "openapi" not in path:
            contexts.append(c)
    return contexts


def _dependency_permissions(dependant: Any) -> set[str]:
    found: set[str] = set()
    for dep in dependant.dependencies:
        perm = getattr(dep.call, "required_permission", None)
        if perm:
            found.add(perm)
        found |= _dependency_permissions(dep)
    return found


def _expected_has(code: str, cell: str) -> bool:
    cell = cell.strip()
    if cell == "-":
        return False
    if "if granted" in cell or "explicit grant" in cell:
        return False
    if "(R)" in cell:
        return code.endswith(".view")
    return True


def test_registry_matches_documented_matrix() -> None:
    mismatches = []
    in_matrix = False
    for line in ARCHITECTURE.read_text().splitlines():
        if line.startswith("| Capability (permission code)"):
            in_matrix = True
            continue
        if in_matrix and not line.startswith("|"):
            break
        if not in_matrix or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        codes = re.findall(r"`([a-z_]+\.[a-z_]+)`", cells[0])
        for code in codes:
            for role, cell in zip(MATRIX_ROLES, cells[1:], strict=True):
                has = Perm(code) in ROLE_PERMISSIONS[role]
                if has != _expected_has(code, cell):
                    mismatches.append(f"{role.value} {code}: matrix '{cell}', registry {has}")
    assert not mismatches, "\n".join(mismatches)


def test_every_protected_route_declares_a_registry_permission() -> None:
    missing = []
    for ctx in _route_contexts():
        for method in ctx.methods - {"HEAD", "OPTIONS"}:
            if (method, ctx.path) in PUBLIC or ctx.path.startswith(SELF_SERVICE_PREFIXES):
                continue
            perms = _dependency_permissions(ctx.route.dependant)
            if not perms or not perms <= {p.value for p in Perm}:
                missing.append(f"{method} {ctx.path}")
    assert not missing, missing


@pytest.mark.db
def test_registry_matches_database(db: Any) -> None:
    rows = db.execute(
        select(RoleRecord.code, Permission.code)
        .join(RolePermission, RolePermission.role_id == RoleRecord.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
    ).all()
    from_db: dict[str, set[str]] = {}
    for role_code, perm_code in rows:
        from_db.setdefault(role_code, set()).add(perm_code)
    assert from_db == {r.value: {p.value for p in perms} for r, perms in ROLE_PERMISSIONS.items()}


@pytest.mark.db
def test_every_non_public_route_rejects_anonymous_callers(new_api: Any) -> None:
    api: Api = new_api()
    api.client.get("/api/v1/auth/csrf")
    failures = []
    for ctx in _route_contexts():
        for method in sorted(ctx.methods - {"HEAD", "OPTIONS"}):
            if (method, ctx.path) in PUBLIC:
                continue
            path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), ctx.path)
            response = getattr(api, method.lower())(
                path, **({} if method in ("GET", "DELETE") else {"json": {}})
            )
            if response.status_code != 401:
                failures.append(f"{method} {ctx.path} -> {response.status_code}")
    assert not failures, failures


def _endpoints(p1: str, p2: str, other_user: str, n: int) -> list[tuple[str, str, Any, Perm, str]]:
    project_body = {"name": "Renamed", "allows_telephony": True, "allows_face_to_face": True}
    return [
        ("GET", "/api/v1/users", None, Perm.USERS_MANAGE, "global"),
        (
            "POST",
            "/api/v1/users",
            {"email": f"made{n}@example.org", "display_name": "Made", "roles": ["MODERATOR"]},
            Perm.USERS_MANAGE,
            "global",
        ),
        ("GET", "/api/v1/roles", None, Perm.USERS_MANAGE, "global"),
        ("GET", "/api/v1/users/export", None, Perm.USERS_MANAGE, "global"),
        (
            "POST",
            "/api/v1/users/import/preview",
            {"csv": "email,display_name,roles\n"},
            Perm.USERS_MANAGE,
            "global",
        ),
        ("GET", "/api/v1/settings", None, Perm.SETTINGS_MANAGE, "global"),
        (
            "PATCH",
            "/api/v1/settings",
            {"values": {"capacity.staff_accounts": 50}},
            Perm.SETTINGS_MANAGE,
            "global",
        ),
        (
            "POST",
            "/api/v1/projects",
            {**project_body, "code": f"NEW{n}"},
            Perm.PROJECTS_CREATE,
            "global",
        ),
        ("GET", "/api/v1/projects", None, Perm.PROJECTS_VIEW, "global"),
        ("GET", f"/api/v1/projects/{p1}", None, Perm.PROJECTS_VIEW, "member"),
        ("GET", f"/api/v1/projects/{p2}", None, Perm.PROJECTS_VIEW, "non-member"),
        ("PATCH", f"/api/v1/projects/{p1}", project_body, Perm.PROJECTS_MANAGE, "member"),
        ("PATCH", f"/api/v1/projects/{p2}", project_body, Perm.PROJECTS_MANAGE, "non-member"),
        (
            "PUT",
            f"/api/v1/projects/{p1}/languages",
            {"languages": [{"language_code": "hi", "dialect": ""}]},
            Perm.PROJECTS_MANAGE,
            "member",
        ),
        ("GET", f"/api/v1/projects/{p1}/members", None, Perm.PROJECTS_VIEW, "member"),
        ("GET", f"/api/v1/projects/{p1}/participants", None, Perm.PARTICIPANTS_VIEW, "member"),
        (
            "GET",
            f"/api/v1/projects/{p1}/participants/export",
            None,
            Perm.PARTICIPANTS_EXPORT,
            "member",
        ),
        (
            "POST",
            f"/api/v1/projects/{p1}/participants",
            {"display_label": "X", "language_code": "hi"},
            Perm.PARTICIPANTS_MANAGE,
            "member",
        ),
        ("GET", "/api/v1/tasks", None, Perm.TASKS_VIEW, "global"),
        ("GET", "/api/v1/audit-logs", None, Perm.AUDIT_VIEW, "global"),
        ("GET", f"/api/v1/projects/{p1}/member-candidates", None, Perm.PROJECTS_MEMBERS, "member"),
        (
            "POST",
            f"/api/v1/projects/{p1}/members",
            {"user_id": other_user},
            Perm.PROJECTS_MEMBERS,
            "member",
        ),
    ]


@pytest.mark.db
@pytest.mark.parametrize("role", list(Role))
def test_role_against_every_protected_endpoint(role: Role, db: Any, new_api: Any) -> None:
    p1, p2 = make_project(db, "P1"), make_project(db, "P2")
    other = make_user(db, "other@example.org", ["MODERATOR"])
    make_user(
        db, "who@example.org", [role.value], projects=[] if role is Role.SUPER_ADMIN else [p1]
    )
    api: Api = new_api()
    assert api.login("who@example.org").status_code == 200
    held = ROLE_PERMISSIONS[role]
    problems = []
    for n, (method, path, body, perm, scope) in enumerate(
        _endpoints(str(p1.id), str(p2.id), str(other.id), n=0)
    ):
        kwargs = {} if body is None else {"json": body}
        status = getattr(api, method.lower())(path, **kwargs).status_code
        if scope == "non-member" and role is not Role.SUPER_ADMIN and Perm.PROJECTS_VIEW in held:
            expected = {404}  # a project the caller is not a member of is invisible, not forbidden
        elif perm not in held:
            expected = {403}
        else:
            expected = {s for s in range(200, 300)} | {409, 422}
        if status not in expected:
            problems.append(
                f"{method} {path.replace(str(p1.id), 'P1').replace(str(p2.id), 'P2')}: got {status}, perm {perm.value} held={perm in held}"
            )
        del n
    assert not problems, "\n".join(problems)


@pytest.mark.db
def test_client_viewer_project_view_carries_no_internal_fields(db: Any, new_api: Any) -> None:
    p1 = make_project(db, "SHARED")
    make_user(db, "client@example.org", ["CLIENT_VIEWER"], projects=[p1])
    api: Api = new_api()
    api.login("client@example.org")
    body = api.get(f"/api/v1/projects/{p1.id}").json()
    assert "created_by" not in body
    members = api.get(f"/api/v1/projects/{p1.id}/members").json()
    assert all(
        set(m) == {"user_id", "email", "display_name", "roles", "status", "added_at"}
        for m in members
    )
