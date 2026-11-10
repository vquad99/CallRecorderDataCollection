"""The Render Blueprint (render.yaml, D-077) keeps the safety properties of the local stack.

It was validated once against Render's published schema (render.com/schema/render.yaml.json,
2026-11-11, 0 errors); these tests pin what matters to this app so a later edit cannot quietly
make the API public, put a secret in the repository, or change the region.

Requirements: OPS-002, OPS-003, SEC-004, ARCH-004
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from app import cli
from tests.conftest import build_settings

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text())
SECRETS = {
    "DATA_ENCRYPTION_KEY",
    "STORAGE_ACCESS_KEY_ID",
    "STORAGE_SECRET_ACCESS_KEY",
    "ADMIN_PASSWORD",
    "DEMO_PASSWORD",
}


def _service(name: str) -> dict[str, Any]:
    return next(s for s in BLUEPRINT["services"] if s["name"] == name)


def _env(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["key"]: e for e in service["envVars"]}


def test_only_the_web_server_is_public_and_the_database_is_private() -> None:
    assert _service("ccp-web")["type"] == "web"
    assert _service("ccp-api")["type"] == "pserv", "the API is reachable only privately"
    assert BLUEPRINT["databases"][0]["ipAllowList"] == [], "database: private network only"
    regions = {s["region"] for s in BLUEPRINT["services"]} | {
        d["region"] for d in BLUEPRINT["databases"]
    }
    assert regions == {"singapore"}, "same region as the Wasabi bucket"


def test_no_secret_is_written_in_the_repository() -> None:
    env = _env(_service("ccp-api"))
    for key in SECRETS:
        assert env[key] == {"key": key, "sync": False}, f"{key} must be entered in Render"
    assert env["SECRET_KEY"] == {"key": "SECRET_KEY", "generateValue": True}
    assert env["DATABASE_URL"]["fromDatabase"]["property"] == "connectionString"
    assert env["APP_ENV"]["value"] == "staging"
    assert env["ALLOW_DEMO_SEED"]["value"] == "false", "demo accounts only when switched on"


def test_the_web_server_reaches_the_api_on_the_port_it_listens_on() -> None:
    web, api = _env(_service("ccp-web")), _env(_service("ccp-api"))
    listen = re.search(r"listen (\d+);", (ROOT / "frontend" / "nginx.conf").read_text())
    assert listen is not None
    assert web["PORT"]["value"] == listen.group(1)
    assert web["BACKEND_HOSTPORT"]["fromService"] == {
        "type": "pserv",
        "name": "ccp-api",
        "property": "hostport",
    }
    assert "${PORT:-8000}" in (ROOT / "backend" / "Dockerfile").read_text()
    assert api["PORT"]["value"] == "10000"


def test_each_deploy_migrates_and_bootstraps_before_going_live() -> None:
    command = _service("ccp-api")["preDeployCommand"]
    assert command.startswith('sh -c "alembic upgrade head')
    assert "app.cli create-admin" in command
    assert "seed-dev --if-allowed" in command


@pytest.mark.db
def test_the_deploy_step_skips_demo_accounts_unless_switched_on(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = build_settings(app_env="staging", database_url=migrated_db)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.delenv("ALLOW_DEMO_SEED", raising=False)
    assert cli.main(["seed-dev", "--if-allowed"]) == 0
    assert "skipped" in capsys.readouterr().out
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    assert cli.main(["create-admin"]) == 0
    assert "nothing to do" in capsys.readouterr().out
