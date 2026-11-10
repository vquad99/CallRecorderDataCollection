"""Monitoring signals (owner's list, O8): database use on every request log line, warnings for
slow requests and slow queries (statement shape only, never values), storage in readiness.

Requirements: FND-005, FND-007, OPS-006
"""

from __future__ import annotations

import logging
from typing import Any

import boto3
import pytest
from moto import mock_aws

from app.main import create_app
from tests.conftest import Api, build_settings, make_user

pytestmark = pytest.mark.db


def _request_records(caplog: pytest.LogCaptureFixture, message: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == message]


def test_every_request_line_says_how_much_database_work_it_did(
    db: Any, new_api: Any, caplog: pytest.LogCaptureFixture
) -> None:
    make_user(db, "obs@example.org", ["SUPER_ADMIN"])
    api: Api = new_api()
    api.login("obs@example.org")
    caplog.set_level(logging.INFO)
    api.get("/api/v1/projects")
    line = [
        r
        for r in _request_records(caplog, "request")
        if r.__dict__.get("path") == "/api/v1/projects"
    ][-1]
    assert line.__dict__["db_queries"] >= 1
    assert line.__dict__["db_ms"] >= 0
    csrf = [
        r
        for r in _request_records(caplog, "request")
        if r.__dict__.get("path") == "/api/v1/auth/csrf"
    ]
    assert all(r.__dict__["db_queries"] == 0 for r in csrf)


def test_slow_requests_and_slow_queries_are_warnings_without_values(
    migrated_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    from fastapi.testclient import TestClient

    app = create_app(build_settings(database_url=migrated_db, slow_request_ms=1, slow_query_ms=0))
    logging.getLogger().addHandler(caplog.handler)  # create_app resets the log set-up
    with app.state.session_factory() as db:
        make_user(db, "slow@example.org", ["SUPER_ADMIN"])
    caplog.set_level(logging.INFO)
    api = Api(TestClient(app))
    api.login("slow@example.org")  # a password check takes well over 1 ms
    slow = _request_records(caplog, "slow_request")
    assert any(r.__dict__.get("path") == "/api/v1/auth/login" for r in slow)
    assert not _request_records(caplog, "slow_query"), "0 turns the query warning off"

    caplog.clear()
    noisy = create_app(build_settings(database_url=migrated_db, slow_query_ms=1))
    logging.getLogger().addHandler(caplog.handler)
    with noisy.state.engine.connect() as conn:
        from sqlalchemy import text

        conn.execute(text("SELECT pg_sleep(0.01), :secret"), {"secret": "participant-phone-123"})
    queries = _request_records(caplog, "slow_query")
    assert queries
    assert "pg_sleep" in queries[0].__dict__["statement"]
    assert "participant-phone-123" not in str(queries[0].__dict__)


def test_readiness_reports_storage(migrated_db: str) -> None:
    from fastapi.testclient import TestClient

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="ccp-ready")
        common = {
            "database_url": migrated_db,
            "storage_access_key_id": "k",
            "storage_secret_access_key": "s",
        }
        ok = TestClient(create_app(build_settings(storage_bucket="ccp-ready", **common)))
        assert ok.get("/health/ready").json()["checks"]["storage"] == "ok"
        missing = TestClient(create_app(build_settings(storage_bucket="no-such-bucket", **common)))
        response = missing.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["storage"] == "error"
