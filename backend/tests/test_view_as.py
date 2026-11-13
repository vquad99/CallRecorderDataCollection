"""Super Admin "View as" (D-100): see the app exactly as another user does, change nothing, and
leave every audit entry in the Super Admin's own name. Also the participant's own page for a
Super Admin.

Requirements: ROLE-001, ROLE-010, SEC-007
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import delete, select

from app.modules.audit.models import AuditLog
from app.modules.auth.models import RoleRecord, User, UserRole
from tests import test_recordings
from tests.conftest import make_user

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world


def _admin(world: dict[str, Any]) -> tuple[Any, Any]:
    sa = make_user(world["db"], "sa@example.org", ["SUPER_ADMIN"])
    return sa, world["api"]("sa@example.org")


def _user(world: dict[str, Any], email: str) -> Any:
    return world["db"].scalar(select(User).where(User.email == email))


def test_super_admin_sees_the_app_as_a_moderator_and_changes_nothing(
    world: dict[str, Any],
) -> None:
    sa, api = _admin(world)
    mod = _user(world, "mod@example.org")
    started = api.post("/api/v1/auth/view-as", json={"user_id": str(mod.id)})
    assert started.status_code == 200, started.text
    me = api.get("/api/v1/auth/me").json()
    assert (me["email"], me["roles"]) == ("mod@example.org", ["MODERATOR"])
    assert me["viewer"]["display_name"] == "sa"
    tasks = api.get("/api/v1/tasks").json()["items"]
    assert [t["task_code"] for t in tasks] == [world["task"]["task_code"]], "the moderator's list"

    refused = api.post(f"/api/v1/tasks/{world['task']['id']}/transition", json={"to": "ON_HOLD"})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "VIEW_AS_READ_ONLY"

    entry = world["db"].scalar(select(AuditLog).where(AuditLog.action == "auth.view_as_started"))
    assert entry is not None
    assert entry.actor_id == sa.id

    stopped = api.delete("/api/v1/auth/view-as")
    assert stopped.status_code == 200, stopped.text
    assert (stopped.json()["roles"], stopped.json()["viewer"]) == (["SUPER_ADMIN"], None)
    assert api.get("/api/v1/auth/me").json()["email"] == "sa@example.org"


def test_only_a_super_admin_views_as_someone_else(world: dict[str, Any]) -> None:
    sa, api = _admin(world)
    mod = _user(world, "mod@example.org")
    pa_try = world["pa"].post("/api/v1/auth/view-as", json={"user_id": str(mod.id)})
    assert pa_try.status_code == 403
    assert api.post("/api/v1/auth/view-as", json={"user_id": str(sa.id)}).status_code == 422
    gone = "00000000-0000-0000-0000-000000000001"
    assert api.post("/api/v1/auth/view-as", json={"user_id": gone}).status_code == 404


def test_the_view_ends_when_the_viewer_is_no_longer_super_admin(world: dict[str, Any]) -> None:
    sa, api = _admin(world)
    qc = _user(world, "qc@example.org")
    assert api.post("/api/v1/auth/view-as", json={"user_id": str(qc.id)}).status_code == 200
    db = world["db"]
    role = db.scalar(select(RoleRecord).where(RoleRecord.code == "SUPER_ADMIN"))
    db.execute(delete(UserRole).where(UserRole.user_id == sa.id, UserRole.role_id == role.id))
    db.commit()
    me = api.get("/api/v1/auth/me").json()
    assert (me["email"], me["viewer"], me["roles"]) == ("sa@example.org", None, [])


def test_an_export_while_viewing_is_recorded_under_the_super_admin(world: dict[str, Any]) -> None:
    sa, api = _admin(world)
    pa = _user(world, "pa@example.org")
    assert api.post("/api/v1/auth/view-as", json={"user_id": str(pa.id)}).status_code == 200
    got = api.get(f"/api/v1/projects/{world['project'].id}/export?content=participants")
    assert got.status_code == 200, got.text
    world["db"].expire_all()
    entry = world["db"].scalar(select(AuditLog).where(AuditLog.action == "project.exported"))
    assert entry is not None
    assert entry.actor_id == sa.id
    assert str(pa.id) in (entry.after_summary or ""), "names whose view it was"


def test_super_admin_opens_a_participants_own_page(world: dict[str, Any]) -> None:
    _, api = _admin(world)
    pid = world["project"].id
    a = world["task"]["participant_a"]
    page = api.get(f"/api/v1/projects/{pid}/participants/{a['id']}/page")
    assert page.status_code == 200, page.text
    body = page.json()
    assert (body["participant_code"], body["display_name"]) == (a["participant_code"], "Asha")
    assert body["link_expires_at"] is None
    assert [s["task_code"] for s in body["sessions"]] == [world["task"]["task_code"]]
    assert world["pa"].get(f"/api/v1/projects/{pid}/participants/{a['id']}/page").status_code == 403
