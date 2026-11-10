"""Capacity settings editable at runtime; dev seed; append-only audit log.

Requirements: CAP-001, CAP-002, FND-027, SEC-001
"""

from typing import Any

import pytest
from sqlalchemy import select, text

from app.cli import SeedRefused, create_admin, seed_dev
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


def test_a_hosted_check_copy_may_seed_only_when_asked_and_with_a_long_password(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = build_settings(app_env="staging", database_url=migrated_db)
    monkeypatch.setenv("ALLOW_DEMO_SEED", "true")
    with pytest.raises(SeedRefused, match="16 characters"):
        seed_dev(staging, "twelve-chars")
    assert len(seed_dev(staging, "a-much-longer-demo-password")) == 5


def test_the_first_admin_is_created_once_in_any_environment(migrated_db: str, new_api: Any) -> None:
    settings = build_settings(app_env="staging", database_url=migrated_db)
    with pytest.raises(SeedRefused, match="valid email"):
        create_admin(settings, "not an email", "long-enough-password", reset=False)
    with pytest.raises(SeedRefused, match="at least"):
        create_admin(settings, "boss@example.org", "short", reset=False)
    assert (
        create_admin(settings, "Boss@Example.org", "first-password-123", reset=False) == "created"
    )
    assert create_admin(settings, "boss@example.org", "other-password-456", reset=False) == "exists"
    api: Api = new_api()
    assert api.login("boss@example.org", "first-password-123").status_code == 200, "kept"
    assert (
        create_admin(settings, "boss@example.org", "other-password-456", reset=True)
        == "password reset"
    )
    assert new_api().login("boss@example.org", "other-password-456").status_code == 200


def test_platform_database_urls_are_accepted() -> None:
    for given in ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"):
        url = build_settings(database_url=given).database_url.get_secret_value()
        assert url == "postgresql+psycopg://u:p@h:5432/d"


def test_seed_creates_one_account_per_role_and_is_idempotent(
    db: Any, migrated_db: str, new_api: Any
) -> None:
    settings = build_settings(database_url=migrated_db)
    with pytest.raises(SeedRefused, match="DEMO_PASSWORD"):
        seed_dev(settings, "short")
    created = seed_dev(settings, "demo-password-123")
    assert len(created) == 5
    assert seed_dev(settings, "demo-password-123") == []
    assert len(db.scalars(select(User)).all()) == 5
    api: Api = new_api()
    assert api.login("demo.moderator@example.org", "demo-password-123").status_code == 200
    assert [p["code"] for p in api.get("/api/v1/projects").json()["items"]] == ["DEMO"]


def test_audit_log_is_append_only(admin: Api, db: Any) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_logs SET action = 'tampered'"))
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_logs"))
    db.rollback()
