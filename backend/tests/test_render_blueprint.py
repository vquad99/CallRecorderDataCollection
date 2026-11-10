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
from tests.conftest import TEST_FERNET_KEY, build_settings

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
    assert web["REAL_IP_HEADER"]["value"] == "CF-Connecting-IP"
    assert web["REAL_IP_FROM"]["value"] == "0.0.0.0/0"
    assert api["PORT"]["value"] == "10000"


def test_each_deploy_migrates_and_bootstraps_before_going_live() -> None:
    # A single command with no quotes or shell operators: Render ran a quoted sh -c as one word.
    assert _service("ccp-api")["preDeployCommand"] == "python -m app.cli prepare-deploy"


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


@pytest.mark.db
def test_the_deploy_step_migrates_creates_the_admin_once_and_skips_demo_data(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = build_settings(app_env="staging", database_url=migrated_db)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.org")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-strong-admin-password")
    monkeypatch.delenv("ALLOW_DEMO_SEED", raising=False)
    assert cli.main(["prepare-deploy"]) == 0
    out = capsys.readouterr().out
    assert "database migrated" in out
    assert "owner@example.org created" in out
    assert "demo account" not in out
    assert cli.main(["prepare-deploy"]) == 0, "a second deploy changes nothing"
    assert "owner@example.org exists" in capsys.readouterr().out


# ------------------------------------------------------------- production (render.production.yaml)

PRODUCTION = yaml.safe_load((ROOT / "render.production.yaml").read_text())


def _prod(name: str) -> dict[str, Any]:
    return next(s for s in PRODUCTION["services"] if s["name"] == name)


def _filled(service: dict[str, Any], entered: dict[str, str]) -> dict[str, str]:
    """The environment Render would give the service: values, generated values, references to the
    database / Redis / another service, and what the owner enters once."""
    env: dict[str, str] = {}
    api = _env(_prod("ccp-prod-api"))
    for key, spec in _env(service).items():
        if "value" in spec:
            env[key] = str(spec["value"])
        elif spec.get("generateValue"):
            env[key] = "generated-" + "x" * 40
        elif "fromDatabase" in spec:
            env[key] = "postgresql://ccp:pw@ccp-prod-db:5432/ccp"
        elif spec.get("fromService", {}).get("type") == "keyvalue":
            env[key] = "redis://ccp-prod-redis:6379"
        elif "envVarKey" in spec.get("fromService", {}):
            source = spec["fromService"]["envVarKey"]
            assert source in api, f"{key} copies {source}, which the API does not have"
            env[key] = entered.get(source) or env.get(source) or "generated-" + "x" * 40
        elif spec.get("sync") is False:
            env[key] = entered[key]
    return env


ENTERED = {
    "DATA_ENCRYPTION_KEY": TEST_FERNET_KEY,
    "PUBLIC_APP_URL": "https://collect.example.org",
    "STORAGE_ACCESS_KEY_ID": "AKIAEXAMPLE",
    "STORAGE_SECRET_ACCESS_KEY": "example-secret",
    "SMTP_HOST": "smtp.example.org",
    "SMTP_USERNAME": "mailer",
    "SMTP_PASSWORD": "mail-secret",
    "EMAIL_FROM": "Conversation Collection <no-reply@example.org>",
    "ADMIN_EMAIL": "owner@example.org",
    "ADMIN_PASSWORD": "a-strong-admin-password",
}


def test_production_is_private_except_the_web_server_and_in_one_region() -> None:
    assert _prod("ccp-prod-web")["type"] == "web"
    assert _prod("ccp-prod-api")["type"] == "pserv"
    assert _prod("ccp-prod-worker")["type"] == "worker"
    redis = _prod("ccp-prod-redis")
    assert redis["ipAllowList"] == [], "Redis: private network only"
    assert redis["maxmemoryPolicy"] == "noeviction", "a queued job is never evicted"
    assert PRODUCTION["databases"][0]["ipAllowList"] == []
    regions = {s["region"] for s in PRODUCTION["services"]} | {
        d["region"] for d in PRODUCTION["databases"]
    }
    assert regions == {"singapore"}
    names = {s["name"] for s in PRODUCTION["services"]} | {
        d["name"] for d in PRODUCTION["databases"]
    }
    staging = {s["name"] for s in BLUEPRINT["services"]} | {
        d["name"] for d in BLUEPRINT["databases"]
    }
    assert not names & staging, "production never shares a service or database with staging"


def test_production_writes_no_secret_and_never_seeds_demo_accounts() -> None:
    api = _env(_prod("ccp-prod-api"))
    for key in SECRETS - {"DEMO_PASSWORD"} | {"SMTP_PASSWORD", "SMTP_USERNAME", "SMTP_HOST"}:
        assert api[key] == {"key": key, "sync": False}, f"{key} must be entered in Render"
    assert "DEMO_PASSWORD" not in api
    assert api["ALLOW_DEMO_SEED"]["value"] == "false"
    assert api["APP_ENV"]["value"] == "production"
    assert api["STORAGE_KEY_PREFIX"]["value"] == "production/", "kept apart from staging/"


@pytest.mark.parametrize("name", ["ccp-prod-api", "ccp-prod-worker"])
def test_production_settings_pass_the_production_rules(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import Settings

    env = _filled(_prod(name), ENTERED)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    settings = Settings()  # values come from the environment
    assert settings.app_env == "production"
    assert settings.email_backend == "smtp"
    assert settings.redis_url is not None
    assert settings.storage_key_prefix == "production/"


def test_the_worker_runs_the_same_code_with_the_api_settings() -> None:
    api, worker = _prod("ccp-prod-api"), _prod("ccp-prod-worker")
    assert worker["dockerfilePath"] == api["dockerfilePath"]
    assert worker["dockerCommand"].startswith("celery -A app.worker worker")
    api_keys = set(_env(api)) - {
        "PORT",
        "FORWARDED_ALLOW_IPS",
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "ALLOW_DEMO_SEED",
    }
    assert api_keys <= set(_env(worker)), "every setting the API has, the worker has too"
