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
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
UNREACHABLE_DB = "postgresql+psycopg://ccp:unit-test-db-password@127.0.0.1:1/unreachable"
TEST_SECRET = "unit-test-secret-key-0123456789-abcdefghij"
# Encryption key for this test run only: generated fresh, never stored anywhere.
TEST_FERNET_KEY = Fernet.generate_key().decode()

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
    "DATA_ENCRYPTION_KEY",
    "PUBLIC_APP_URL",
    "EMAIL_BACKEND",
    "SMTP_HOST",
    "COOKIE_SECURE",
    "EMAIL_FILE_DIR",
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
        "data_encryption_key": TEST_FERNET_KEY,
        # Tests are not throttled unless a test sets its own limit.
        "rate_limit_reads_per_minute": 100_000,
        "rate_limit_writes_per_minute": 100_000,
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


# ---------------------------------------------------------------- Phase 2: accounts on a real database

TEST_PASSWORD = "correct-horse-battery-staple"


class Api:
    """TestClient wrapper that sends the CSRF header from its own cookie, like the browser does."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        token = self.client.cookies.get("csrf_token")
        if token:
            headers["X-CSRF-Token"] = token
        return headers

    def get(self, url: str, **kw: Any) -> Any:
        return self.client.get(url, **kw)

    def post(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.post(
            url, json=json, headers=self._headers(kw.pop("headers", None)), **kw
        )

    def put(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.put(url, json=json, headers=self._headers(kw.pop("headers", None)), **kw)

    def patch(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.patch(
            url, json=json, headers=self._headers(kw.pop("headers", None)), **kw
        )

    def delete(self, url: str, **kw: Any) -> Any:
        return self.client.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def login(self, email: str, password: str = TEST_PASSWORD, totp_code: str | None = None) -> Any:
        self.client.get("/api/v1/auth/csrf")
        body: dict[str, Any] = {"email": email, "password": password}
        if totp_code:
            body["totp_code"] = totp_code
        return self.post("/api/v1/auth/login", json=body)


@pytest.fixture
def outbox(tmp_path: Path) -> Path:
    return tmp_path / "outbox"


@pytest.fixture
def db_app(migrated_db: str, outbox: Path) -> FastAPI:
    return create_app(build_settings(database_url=migrated_db, email_file_dir=str(outbox)))


@pytest.fixture
def db(db_app: FastAPI) -> Iterator[Any]:
    with db_app.state.session_factory() as session:
        yield session


@pytest.fixture
def new_api(db_app: FastAPI) -> Iterator[Callable[[], Api]]:
    clients: list[TestClient] = []

    def _make() -> Api:
        client = TestClient(db_app)
        clients.append(client)
        return Api(client)

    yield _make
    for client in clients:
        client.close()


def make_user(
    db: Any,
    email: str,
    roles: list[str],
    *,
    password: str | None = TEST_PASSWORD,
    status: str = "ACTIVE",
    projects: list[Any] | None = None,
) -> Any:
    from sqlalchemy import select as _select

    from app.modules.auth.models import RoleRecord, User
    from app.modules.auth.security import hash_password
    from app.modules.projects.models import ProjectMembership

    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password(password) if password else None,
        status=status,
    )
    user.roles = list(db.scalars(_select(RoleRecord).where(RoleRecord.code.in_(roles))).all())
    db.add(user)
    db.flush()
    for project in projects or []:
        db.add(ProjectMembership(user_id=user.id, project_id=project.id))
    db.commit()
    return user


def make_project(db: Any, code: str, status: str = "ACTIVE") -> Any:
    from app.modules.projects.models import Project

    project = Project(
        code=code,
        name=f"Project {code}",
        status=status,
        allows_telephony=True,
        allows_face_to_face=True,
    )
    db.add(project)
    db.commit()
    return project


def read_outbox(outbox: Path) -> list[str]:
    """Decoded messages as a mail client would show them: headers plus plain-text body."""
    from email import message_from_bytes, policy

    if not outbox.exists():
        return []
    messages = []
    for path in sorted(outbox.glob("*.eml"), key=lambda p: p.stat().st_mtime):
        msg = message_from_bytes(path.read_bytes(), policy=policy.default)
        headers = "".join(f"{k}: {v}\n" for k, v in msg.items())
        messages.append(headers + "\n" + msg.get_content())
    return messages


def link_token(email_text: str) -> str:
    import re as _re

    match = _re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", email_text)
    assert match, "no password link in email"
    return match.group(1)


# ---------------------------------------------------------------- Phase 3: participants and tasks


def make_participant(
    api: Api, project_id: Any, label: str, phone: str | None = None, lang: str = "hi"
) -> Any:
    body: dict[str, Any] = {"display_label": label, "language_code": lang}
    if phone:
        body["phone"] = phone
    response = api.post(f"/api/v1/projects/{project_id}/participants", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(db: Any, task_id: Any, status: str, held_from: str | None = None) -> None:
    """Test-only shortcut to put a task in a given state."""
    from sqlalchemy import update as _update

    from app.modules.tasks.models import Task

    db.execute(_update(Task).where(Task.id == task_id).values(status=status, held_from=held_from))
    db.commit()
