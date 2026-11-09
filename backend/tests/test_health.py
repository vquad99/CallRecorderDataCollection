"""Liveness and readiness checks.

Requirements: FND-007
"""

import time

import pytest

from tests.conftest import MakeClient, build_settings


def test_live_is_ok(make_client: MakeClient) -> None:
    response = make_client().get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_fails_clearly_when_database_is_down(make_client: MakeClient) -> None:
    started = time.monotonic()
    response = make_client().get("/health/ready")
    assert time.monotonic() - started < 10
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "error", "redis": "not_configured"},
    }
    assert "unit-test-db-password" not in response.text


@pytest.mark.db
def test_ready_is_ok_with_database(test_database_url: str, make_client: MakeClient) -> None:
    response = make_client(database_url=test_database_url).get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "not_configured"},
    }


@pytest.mark.db
def test_ready_fails_when_configured_redis_is_down(
    test_database_url: str, make_client: MakeClient
) -> None:
    response = make_client(database_url=test_database_url, redis_url="redis://127.0.0.1:1/0").get(
        "/health/ready"
    )
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "redis": "error"}


def test_settings_used_for_ready_are_the_app_settings() -> None:
    settings = build_settings()
    assert settings.redis_url is None
