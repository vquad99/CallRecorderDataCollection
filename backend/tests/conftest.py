"""Shared fixtures.

Unit tests build Settings directly and point DATABASE_URL at a closed port, so they never touch a
database. Tests marked ``db`` need TEST_DATABASE_URL (a database whose name ends in ``_test``,
FND-010). With REQUIRE_DB_TESTS=1 (CI) a missing test database is an error, never a silent skip.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
UNREACHABLE_DB = "postgresql+psycopg://ccp:unit-test-db-password@127.0.0.1:1/unreachable"
TEST_SECRET = "unit-test-secret-key-0123456789-abcdefghij"

MakeClient = Callable[..., TestClient]

SETTINGS_ENV = [
    "APP_ENV",
    "DATABASE_URL",
    "SECRET_KEY",
    "CORS_ALLOWED_ORIGINS",
    "LOG_LEVEL",
    "ENABLE_API_DOCS",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT_SECONDS",
    "DB_POOL_RECYCLE_SECONDS",
    "DB_CONNECT_TIMEOUT_SECONDS",
    "REDIS_URL",
]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


def build_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": UNREACHABLE_DB,
        "secret_key": TEST_SECRET,
        "cors_allowed_origins": ["http://localhost:5173"],
        "db_connect_timeout_seconds": 2,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def make_client() -> Iterator[MakeClient]:
    clients: list[TestClient] = []

    def _make(app: FastAPI | None = None, **overrides: Any) -> TestClient:
        client = TestClient(app or create_app(build_settings(**overrides)))
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.close()


def assert_test_database_name(url: str) -> None:
    """Refuse any database whose name does not end in _test (FND-010)."""
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against database '{name}': name must end in _test"
        )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            pytest.fail("REQUIRE_DB_TESTS=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set (database tests NOT RUN)")
    assert_test_database_name(url)
    return url


def reset_schema(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def migrated_db(test_database_url: str) -> str:
    """An empty test database upgraded to the latest migration."""
    reset_schema(test_database_url)
    command.upgrade(alembic_config(test_database_url), "head")
    return test_database_url
