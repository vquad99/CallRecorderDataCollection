"""User administration: CRUD, roles, deactivation, invitations, CSV import/export, audit.

Requirements: USER-001, USER-002, USER-004, USER-005, USER-006, USER-007, USER-008, USER-009
"""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditLog
from tests.conftest import Api, link_token, make_user, read_outbox

pytestmark = pytest.mark.db


@pytest.fixture
def admin(db: Any, new_api: Any) -> Api:
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    api: Api = new_api()
    assert api.login("root@example.org").status_code == 200
    return api


def _audit(db: Any, action: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)).all())


def test_create_user_sends_invitation_that_sets_a_password(
    admin: Api, db: Any, new_api: Any, outbox: Path
) -> None:
    response = admin.post(
        "/api/v1/users",
        json={
            "email": "New.Person@Example.org",
            "display_name": "New Person",
            "roles": ["QC_EXECUTIVE"],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["invite_sent"] is True
    assert body["user"]["email"] == "new.person@example.org"
    assert body["user"]["password_set"] is False
    invite = read_outbox(outbox)[-1]
    assert "To: new.person@example.org" in invite
    guest = new_api()
    guest.client.get("/api/v1/auth/csrf")
    assert (
        guest.post(
            "/api/v1/auth/password/reset",
            json={"token": link_token(invite), "new_password": "invited-user-password"},
        ).status_code
        == 204
    )
    assert guest.login("new.person@example.org", "invited-user-password").status_code == 200
    assert _audit(db, "user.created")


def test_duplicate_email_is_rejected(admin: Api) -> None:
    body = {"email": "dup@example.org", "display_name": "Dup", "roles": ["MODERATOR"]}
    assert admin.post("/api/v1/users", json=body).status_code == 201
    again = admin.post("/api/v1/users", json={**body, "email": "DUP@example.org"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "EMAIL_TAKEN"


def test_edit_user_and_role_change_is_audited(admin: Api, db: Any) -> None:
    user = make_user(db, "edit@example.org", ["MODERATOR"])
    assert (
        admin.patch(f"/api/v1/users/{user.id}", json={"display_name": "Edited Name"}).json()[
            "display_name"
        ]
        == "Edited Name"
    )
    response = admin.put(
        f"/api/v1/users/{user.id}/roles", json={"roles": ["CLIENT_VIEWER", "QC_EXECUTIVE"]}
    )
    assert response.json()["roles"] == ["CLIENT_VIEWER", "QC_EXECUTIVE"]
    entry = _audit(db, "user.roles_changed")[-1]
    assert '"MODERATOR"' in (entry.before_summary or "")
    assert '"QC_EXECUTIVE"' in (entry.after_summary or "")
    assert entry.actor_id is not None
    bad = admin.put(f"/api/v1/users/{user.id}/roles", json={"roles": ["WIZARD"]})
    assert bad.json()["error"]["code"] == "UNKNOWN_ROLE"


def test_deactivated_user_loses_access_at_the_next_request(
    admin: Api, db: Any, new_api: Any
) -> None:
    user = make_user(db, "leaver@example.org", ["MODERATOR"])
    session = new_api()
    session.login("leaver@example.org")
    assert session.get("/api/v1/auth/me").status_code == 200
    assert admin.post(f"/api/v1/users/{user.id}/disable").json()["status"] == "DISABLED"
    assert session.get("/api/v1/auth/me").status_code == 401
    assert new_api().login("leaver@example.org").status_code == 401
    assert admin.post(f"/api/v1/users/{user.id}/enable").json()["status"] == "ACTIVE"
    assert new_api().login("leaver@example.org").status_code == 200
    assert _audit(db, "user.disabled")
    assert _audit(db, "user.enabled")


def test_admin_cannot_lock_themselves_out(admin: Api) -> None:
    me = admin.get("/api/v1/auth/me").json()
    assert (
        admin.post(f"/api/v1/users/{me['id']}/disable").json()["error"]["code"]
        == "CANNOT_MODIFY_SELF"
    )
    response = admin.put(f"/api/v1/users/{me['id']}/roles", json={"roles": ["MODERATOR"]})
    assert response.json()["error"]["code"] == "CANNOT_MODIFY_SELF"


def test_search_filter_and_paginate(admin: Api, db: Any) -> None:
    for i in range(7):
        make_user(db, f"page{i}@example.org", ["QC_EXECUTIVE" if i % 2 else "MODERATOR"])
    page = admin.get("/api/v1/users", params={"search": "page", "page_size": 3, "page": 2}).json()
    assert page["total"] == 7
    assert [u["email"] for u in page["items"]] == [
        "page3@example.org",
        "page4@example.org",
        "page5@example.org",
    ]
    qc_staff = admin.get("/api/v1/users", params={"role": "QC_EXECUTIVE"}).json()
    assert qc_staff["total"] == 3
    assert admin.get("/api/v1/users", params={"status": "DISABLED"}).json()["total"] == 0


def test_csv_import_preview_then_confirm_imports_only_valid_rows(admin: Api, db: Any) -> None:
    make_user(db, "exists@example.org", ["MODERATOR"])
    csv_text = (
        "email,display_name,roles\n"
        "ok1@example.org,Okay One,MODERATOR\n"
        "ok2@example.org,Okay Two,CLIENT_VIEWER;QC_EXECUTIVE\n"
        "not-an-email,Bad Email,MODERATOR\n"
        "exists@example.org,Already There,MODERATOR\n"
        "norole@example.org,No Role,\n"
        "ok1@example.org,Duplicate,MODERATOR\n"
        "wrong@example.org,Wrong Role,WIZARD\n"
    )
    preview = admin.post("/api/v1/users/import/preview", json={"csv": csv_text}).json()
    assert preview["valid_count"] == 2
    assert preview["invalid_count"] == 5
    errors = {row["line"]: row["errors"] for row in preview["rows"] if row["errors"]}
    assert errors[4] == ["email is not valid"]
    assert errors[5] == ["a user with this email already exists"]
    assert errors[6] == ["at least one role is required"]
    assert errors[7] == ["email appears more than once in the file"]
    assert errors[8] == ["unknown role: WIZARD"]
    assert admin.get("/api/v1/users", params={"search": "ok"}).json()["total"] == 0, (
        "preview must not write"
    )

    result = admin.post("/api/v1/users/import/confirm", json={"csv": csv_text}).json()
    assert result["created"] == 2
    assert len(result["skipped"]) == 5
    assert admin.get("/api/v1/users", params={"search": "ok"}).json()["total"] == 2


def test_csv_import_needs_the_exact_header(admin: Api) -> None:
    response = admin.post("/api/v1/users/import/preview", json={"csv": "mail,name\nx@y.org,X\n"})
    assert response.json()["error"]["code"] == "INVALID_CSV_HEADER"


def test_export_is_admin_only_and_escapes_formulas(admin: Api, db: Any, new_api: Any) -> None:
    make_user(db, "formula@example.org", ["MODERATOR"]).display_name = "=HYPERLINK(1)"
    db.commit()
    response = admin.get("/api/v1/users/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK(1)" in response.text
    make_user(db, "plain@example.org", ["PROJECT_ADMIN"])
    other = new_api()
    other.login("plain@example.org")
    assert other.get("/api/v1/users/export").status_code == 403


def test_each_role_sees_only_permitted_admin_pages(db: Any, new_api: Any) -> None:
    for role in ["PROJECT_ADMIN", "MODERATOR", "QC_EXECUTIVE", "CLIENT_VIEWER"]:
        make_user(db, f"{role.lower()}@example.org", [role])
        api = new_api()
        api.login(f"{role.lower()}@example.org")
        assert api.get("/api/v1/users").status_code == 403, role
        assert api.get("/api/v1/settings").status_code == 403, role


def test_active_accounts_are_limited_by_the_capacity_setting(admin: Api, db: Any) -> None:
    """O10: the staff-account capacity setting is a real limit, raised in Settings."""
    active = admin.get("/api/v1/users?status=ACTIVE&page_size=100").json()["total"]
    assert (
        admin.patch(
            "/api/v1/settings", json={"values": {"capacity.staff_accounts": active + 1}}
        ).status_code
        == 200
    )
    body = {"email": "last.seat@example.org", "display_name": "Last", "roles": ["MODERATOR"]}
    assert admin.post("/api/v1/users", json=body).status_code == 201
    over = admin.post("/api/v1/users", json={**body, "email": "one.too.many@example.org"})
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "CAPACITY_REACHED"
    csv = (
        "email,display_name,roles\nimp1@example.org,Imp,MODERATOR\nimp2@example.org,Imp,MODERATOR\n"
    )
    assert (
        admin.post("/api/v1/users/import/confirm", json={"csv": csv}).json()["error"]["code"]
        == "CAPACITY_REACHED"
    )
    assert admin.get("/api/v1/users?search=imp1").json()["total"] == 0, (
        "an import is all or nothing"
    )
    seat = admin.get("/api/v1/users?search=last.seat").json()["items"][0]
    assert admin.post(f"/api/v1/users/{seat['id']}/disable").status_code == 200
    assert (
        admin.post("/api/v1/users", json={**body, "email": "one.too.many@example.org"}).status_code
        == 201
    )
    assert (
        admin.post(f"/api/v1/users/{seat['id']}/enable").json()["error"]["code"]
        == "CAPACITY_REACHED"
    )
    assert (
        admin.patch(
            "/api/v1/settings", json={"values": {"capacity.staff_accounts": active + 5}}
        ).status_code
        == 200
    )
    assert admin.post(f"/api/v1/users/{seat['id']}/enable").status_code == 200, (
        "raising the setting is enough"
    )
