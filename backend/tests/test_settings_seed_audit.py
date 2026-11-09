"""Capacity settings editable at runtime; dev seed; append-only audit log.

Requirements: CAP-001, CAP-002, FND-027, SEC-001
"""

from typing import Any

import pytest
from sqlalchemy import select, text

from app.cli import SeedRefused, seed_dev
from app.modules.auth.models import User
from tests.conftest import Api, build_settings, make_user

pytestmark = pytest.mark.db


@pytest.fixture
def admin(db: Any, new_api: Any) -> Api:
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    api: Api = new_api()
    api.login("root@example.org")
    return api


def test_capacity_targets_are_seeded_and_editable_without_restart(admin: Api) -> None:
    settings = {s["key"]: s["value"] for s in admin.get("/api/v1/settings").json()}
    assert settings == {
        "capacity.concurrent_conferences": 50,
        "capacity.face_to_face_hours_per_day": 125,
        "capacity.participants_per_conversation": 2,
        "capacity.staff_accounts": 50,
        "capacity.telephony_hours_per_day": 125,
        "capacity.total_hours_per_day": 250,
    }
    updated = admin.patch(
        "/api/v1/settings", json={"values": {"capacity.total_hours_per_day": 300}}
    )
    assert {s["key"]: s["value"] for s in updated.json()}["capacity.total_hours_per_day"] == 300
    assert {s["key"]: s["value"] for s in admin.get("/api/v1/settings").json()}[
        "capacity.total_hours_per_day"
    ] == 300
    assert (
        admin.patch("/api/v1/settings", json={"values": {"capacity.unknown": 1}}).json()["error"][
            "code"
        ]
        == "UNKNOWN_SETTING"
    )
    assert (
        admin.patch(
            "/api/v1/settings", json={"values": {"capacity.participants_per_conversation": 3}}
        ).json()["error"]["code"]
        == "OUT_OF_RANGE"
    )


def test_no_capacity_literal_in_application_code() -> None:
    from pathlib import Path

    app_dir = Path(__file__).resolve().parent.parent / "app"
    for path in app_dir.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        text_ = path.read_text()
        assert "= 250" not in text_, f"capacity literal in {path}"
        assert "= 125" not in text_, f"capacity literal in {path}"


def test_seed_refuses_outside_development(migrated_db: str) -> None:
    # Production settings cannot even be built without SMTP and Redis; staging proves the guard.
    with pytest.raises(SeedRefused, match="refuses"):
        seed_dev(
            build_settings(app_env="staging", database_url=migrated_db), "long-enough-password"
        )


def test_seed_creates_one_account_per_role_and_is_idempotent(
    db: Any, migrated_db: str, new_api: Any
) -> None:
    settings = build_settings(database_url=migrated_db)
    with pytest.raises(SeedRefused, match="DEMO_PASSWORD"):
        seed_dev(settings, "short")
    created = seed_dev(settings, "demo-password-123")
    assert len(created) == 6
    assert seed_dev(settings, "demo-password-123") == []
    assert len(db.scalars(select(User)).all()) == 6
    api: Api = new_api()
    assert api.login("demo.moderator@example.test", "demo-password-123").status_code == 200
    assert [p["code"] for p in api.get("/api/v1/projects").json()["items"]] == ["DEMO"]


def test_audit_log_is_append_only(admin: Api, db: Any) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_logs SET action = 'tampered'"))
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_logs"))
    db.rollback()
