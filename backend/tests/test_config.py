"""Configuration from environment variables; invalid configuration stops startup.

Requirements: FND-003
"""

import pytest

from app.core.config import ConfigError, load_settings
from app.main import create_app
from tests.conftest import TEST_FERNET_KEY, TEST_SECRET, UNREACHABLE_DB

VALID = {
    "APP_ENV": "development",
    "DATABASE_URL": UNREACHABLE_DB,
    "SECRET_KEY": TEST_SECRET,
    "CORS_ALLOWED_ORIGINS": "http://localhost:5173, http://127.0.0.1:5173",
    "DATA_ENCRYPTION_KEY": TEST_FERNET_KEY,
}


def _set(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_valid_environment_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, **VALID)
    settings = load_settings()
    assert settings.app_env == "development"
    assert settings.cors_allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.api_docs_enabled is True


@pytest.mark.parametrize(
    "missing", ["APP_ENV", "DATABASE_URL", "SECRET_KEY", "DATA_ENCRYPTION_KEY"]
)
def test_missing_required_variable_stops_startup(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    _set(monkeypatch, **{k: v for k, v in VALID.items() if k != missing})
    with pytest.raises(ConfigError, match=missing):
        create_app()


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"SECRET_KEY": "too-short"}, "SECRET_KEY"),
        ({"DATABASE_URL": "mysql://u:p@h/db"}, "DATABASE_URL"),
        ({"CORS_ALLOWED_ORIGINS": "*"}, "CORS_ALLOWED_ORIGINS"),
        ({"CORS_ALLOWED_ORIGINS": "http://example.org/"}, "CORS_ALLOWED_ORIGINS"),
        ({"APP_ENV": "prod"}, "APP_ENV"),
        ({"LOG_LEVEL": "VERBOSE"}, "LOG_LEVEL"),
        ({"DB_POOL_SIZE": "0"}, "DB_POOL_SIZE"),
        ({"DATA_ENCRYPTION_KEY": "not-a-fernet-key"}, "DATA_ENCRYPTION_KEY"),
        ({"PUBLIC_APP_URL": "localhost:5173"}, "PUBLIC_APP_URL"),
    ],
)
def test_invalid_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, override: dict[str, str], fragment: str
) -> None:
    _set(monkeypatch, **{**VALID, **override})
    with pytest.raises(ConfigError, match=fragment):
        load_settings()


def test_production_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    base = {
        **VALID,
        "APP_ENV": "production",
        "CORS_ALLOWED_ORIGINS": "https://app.example.org",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "EMAIL_BACKEND": "smtp",
        "SMTP_HOST": "smtp.example.org",
        "PUBLIC_APP_URL": "https://app.example.org",
        "STORAGE_BUCKET": "ccp-prod",
        "STORAGE_ACCESS_KEY_ID": "key-id",
        "STORAGE_SECRET_ACCESS_KEY": "secret-access-key",
    }
    _set(monkeypatch, **base)
    assert load_settings().api_docs_enabled is False

    _set(monkeypatch, CORS_ALLOWED_ORIGINS="http://app.example.org")
    with pytest.raises(ConfigError, match="https"):
        load_settings()

    _set(
        monkeypatch,
        CORS_ALLOWED_ORIGINS="https://app.example.org",
        SECRET_KEY="change-me-change-me-change-me-change-me",
    )
    with pytest.raises(ConfigError, match="example value"):
        load_settings()

    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.delenv("REDIS_URL")
    with pytest.raises(ConfigError, match="REDIS_URL"):
        load_settings()

    _set(
        monkeypatch,
        REDIS_URL="redis://127.0.0.1:1/0",
        TXCONTACT_AGENT_URL="ws://agents.example.org/",
    )
    with pytest.raises(ConfigError, match="TXCONTACT_AGENT_URL must use wss"):
        load_settings()


def test_the_phone_seat_signs_in_at_txcontacts_own_address_unless_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-133: the agent manager is TxContact's own address over WebSocket (the stand-in's when
    TXCONTACT_BASE_URL points at it), unless TXCONTACT_AGENT_URL names another WebSocket address."""
    _set(monkeypatch, **VALID)
    s = load_settings()
    assert s.txcontact_agent_endpoint == "wss://amber.txcontact.com/txagentmanager/"
    assert (s.txcontact_tenant_id, s.txcontact_extension, s.txcontact_seat_login) == (
        "desicrew",
        "",
        True,
    )
    _set(monkeypatch, TXCONTACT_BASE_URL="http://127.0.0.1:8765", TXCONTACT_AGENT_URL="")
    assert load_settings().txcontact_agent_endpoint == "ws://127.0.0.1:8765/txagentmanager/"
    _set(monkeypatch, TXCONTACT_AGENT_URL="wss://agents.example.org/am/")
    assert load_settings().txcontact_agent_endpoint == "wss://agents.example.org/am/"
    _set(monkeypatch, TXCONTACT_AGENT_URL="https://agents.example.org/am/")
    with pytest.raises(ConfigError, match="TXCONTACT_AGENT_URL"):
        load_settings()


def test_storage_keys_are_both_or_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-132: on AWS the server's IAM role reaches S3, so a bucket without keys is set up; one
    key without the other is a mistake."""
    from app.core.storage import S3Storage

    _set(monkeypatch, **VALID, STORAGE_BUCKET="ccp-aws", STORAGE_REGION="ap-south-1")
    monkeypatch.delenv("STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("STORAGE_SECRET_ACCESS_KEY", raising=False)
    role = load_settings()
    assert role.storage_configured is True
    # No keys are handed to boto3: it looks for the role itself (nothing is called here).
    client = S3Storage(role)._client
    assert client.meta.region_name == "ap-south-1"

    # Empty values, as the AWS env file leaves them, count as no keys.
    _set(monkeypatch, STORAGE_ACCESS_KEY_ID="", STORAGE_SECRET_ACCESS_KEY="")
    empty = load_settings()
    assert (empty.storage_configured, empty.storage_keys) == (True, None)

    monkeypatch.setenv("STORAGE_ACCESS_KEY_ID", "key-id")
    assert load_settings().storage_configured is False
    monkeypatch.setenv("STORAGE_SECRET_ACCESS_KEY", "secret-access-key")
    both = load_settings()
    assert (both.storage_configured, both.storage_keys) == (True, ("key-id", "secret-access-key"))


def test_error_message_never_contains_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(
        monkeypatch,
        **{**VALID, "SECRET_KEY": "s3cr3t-short", "DATABASE_URL": "mysql://u:hunter2@h/db"},
    )
    with pytest.raises(ConfigError) as info:
        load_settings()
    assert "s3cr3t-short" not in str(info.value)
    assert "hunter2" not in str(info.value)
