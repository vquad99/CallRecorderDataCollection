"""Structured JSON logs with request IDs and no secrets; request ID middleware.

Requirements: FND-004, FND-005
"""

import json
import logging

import pytest

from app.main import create_app
from tests.conftest import TEST_SECRET, MakeClient, build_settings


def _lines(captured: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in captured.splitlines() if line.startswith("{")]


def test_request_log_is_json_with_request_id(
    capsys: pytest.CaptureFixture[str], make_client: MakeClient
) -> None:
    client = make_client()
    response = client.get("/health/live")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32

    records = _lines(capsys.readouterr().out)
    access = [r for r in records if r["message"] == "request"]
    assert access, "no access log line"
    assert access[-1]["request_id"] == request_id
    assert access[-1]["path"] == "/health/live"
    assert access[-1]["status"] == 200
    assert "duration_ms" in access[-1]


def test_incoming_request_id_is_kept_when_valid(make_client: MakeClient) -> None:
    client = make_client()
    assert (
        client.get("/health/live", headers={"X-Request-ID": "abc-123_XYZ.9"}).headers[
            "X-Request-ID"
        ]
        == "abc-123_XYZ.9"
    )
    replaced = client.get("/health/live", headers={"X-Request-ID": "bad id <script>"})
    assert replaced.headers["X-Request-ID"] != "bad id <script>"


def test_secret_values_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    create_app(build_settings(database_url="postgresql+psycopg://ccp:db-pass-xyz@127.0.0.1:1/x"))
    logging.getLogger("test").warning("leak %s and %s", TEST_SECRET, "db-pass-xyz")
    out = capsys.readouterr().out
    assert TEST_SECRET not in out
    assert "db-pass-xyz" not in out
    assert "***" in out
