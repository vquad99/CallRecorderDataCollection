"""Application configuration loaded from environment variables (FND-003).

Every value comes from the environment; nothing secret has a default. ``load_settings`` turns a
validation failure into ``ConfigError`` naming the offending variables without echoing their
values, so an invalid configuration stops startup with a readable message.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

_DB_SCHEME = "postgresql+psycopg://"


class ConfigError(RuntimeError):
    """Raised when the environment does not describe a safe, complete configuration."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: Environment
    database_url: SecretStr
    secret_key: SecretStr
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    log_level: LogLevel = "INFO"
    enable_api_docs: bool | None = None

    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60)
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)

    redis_url: SecretStr | None = None

    # Phase 2: accounts and sessions
    public_app_url: str = "http://localhost:5173"
    data_encryption_key: SecretStr
    session_idle_minutes: int = Field(default=30, ge=5, le=24 * 60)
    session_absolute_hours: int = Field(default=12, ge=1, le=24 * 30)
    cookie_secure: bool | None = None
    password_min_length: int = Field(default=12, ge=8, le=64)
    password_reset_minutes: int = Field(default=30, ge=5, le=24 * 60)
    invite_hours: int = Field(default=72, ge=1, le=24 * 14)
    login_window_minutes: int = Field(default=15, ge=1, le=24 * 60)
    login_max_failures_per_account: int = Field(default=5, ge=1, le=100)
    login_max_failures_per_ip: int = Field(default=20, ge=1, le=1000)
    rate_limit_reads_per_minute: int = Field(default=600, ge=1, le=100_000)
    rate_limit_writes_per_minute: int = Field(default=120, ge=1, le=100_000)

    # Phase 4: object storage (Wasabi in cloud, SeaweedFS locally) and media processing
    storage_endpoint_url: str | None = None
    storage_region: str = "us-east-1"
    storage_bucket: str | None = None
    storage_access_key_id: SecretStr | None = None
    storage_secret_access_key: SecretStr | None = None
    storage_key_prefix: str = ""
    storage_create_bucket: bool = False
    signed_url_seconds: int = Field(default=300, ge=30, le=3600)
    media_work_dir: str = "var/media"
    max_chunk_bytes: int = Field(default=8_000_000, ge=1024, le=64_000_000)
    # Largest request body for every other API call (JSON); larger bodies get 413 (SEC-006).
    # 2.5 MB covers the largest JSON field (user CSV import, 2 000 000 characters) plus encoding.
    max_request_bytes: int = Field(default=2_500_000, ge=10_000, le=64_000_000)
    max_recording_seconds: int = Field(default=4 * 3600, ge=60, le=24 * 3600)

    email_backend: Literal["smtp", "file"] = "file"
    email_from: str = "Conversation Collection <no-reply@localhost>"
    email_file_dir: str = "var/outbox"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None

    @field_validator("data_encryption_key")
    @classmethod
    def _fernet_key(cls, value: SecretStr) -> SecretStr:
        from cryptography.fernet import Fernet

        try:
            Fernet(value.get_secret_value().encode())
        except (ValueError, TypeError):
            raise ValueError("must be a Fernet key (32 url-safe base64-encoded bytes)") from None
        return value

    @field_validator("public_app_url")
    @classmethod
    def _app_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")) or value.endswith("/"):
            raise ValueError("must be scheme://host[:port] without a trailing slash")
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _no_wildcard(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if "*" in origin:
                raise ValueError("wildcard origins are not allowed with credentialed requests")
            if not origin.startswith(("http://", "https://")) or origin.endswith("/"):
                raise ValueError(f"origin must be scheme://host[:port] without a path: {origin}")
        return origins

    @field_validator("secret_key")
    @classmethod
    def _secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("must be at least 32 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def _db_scheme(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(_DB_SCHEME):
            raise ValueError(f"must start with {_DB_SCHEME}")
        return value

    @model_validator(mode="after")
    def _production_rules(self) -> Settings:
        if self.app_env == "production":
            if "change-me" in self.secret_key.get_secret_value():
                raise ValueError("SECRET_KEY still holds the example value")
            insecure = [o for o in self.cors_allowed_origins if not o.startswith("https://")]
            if insecure:
                raise ValueError("production CORS origins must use https")
            if self.enable_api_docs:
                raise ValueError("API docs must be disabled in production")
            if self.redis_url is None:
                raise ValueError("REDIS_URL is required in production")
            if self.email_backend != "smtp" or not self.smtp_host:
                raise ValueError("production needs EMAIL_BACKEND=smtp and SMTP_HOST")
            if not self.public_app_url.startswith("https://"):
                raise ValueError("PUBLIC_APP_URL must use https in production")
            if self.cookie_secure is False:
                raise ValueError("COOKIE_SECURE cannot be false in production")
            if not self.storage_configured:
                raise ValueError("production needs STORAGE_BUCKET and storage keys")
        return self

    @property
    def storage_configured(self) -> bool:
        # The endpoint is optional: unset means Amazon S3 itself; Wasabi and SeaweedFS set it.
        return bool(
            self.storage_bucket and self.storage_access_key_id and self.storage_secret_access_key
        )

    @property
    def cookies_secure(self) -> bool:
        if self.cookie_secure is None:
            return self.app_env not in ("development", "test")
        return self.cookie_secure

    @property
    def api_docs_enabled(self) -> bool:
        if self.enable_api_docs is None:
            return self.app_env in ("development", "test")
        return self.enable_api_docs

    def secret_values(self) -> list[str]:
        """Values that must never appear in logs or responses."""
        from sqlalchemy.engine import make_url

        values = [self.secret_key.get_secret_value(), self.data_encryption_key.get_secret_value()]
        if self.smtp_password is not None:
            values.append(self.smtp_password.get_secret_value())
        if self.storage_secret_access_key is not None:
            values.append(self.storage_secret_access_key.get_secret_value())
        password = make_url(self.database_url.get_secret_value()).password
        if password:
            values.append(str(password))
        if self.redis_url is not None:
            redis_password = make_url(self.redis_url.get_secret_value()).password
            if redis_password:
                values.append(str(redis_password))
        return [v for v in values if len(v) >= 4]


def load_settings() -> Settings:
    """Build settings from the environment or raise ConfigError naming the bad variables."""
    try:
        return Settings()  # values come from the environment
    except ValidationError as exc:
        problems = []
        for err in exc.errors(include_input=False, include_url=False):
            field = ".".join(str(part) for part in err["loc"]) or "configuration"
            problems.append(f"{field.upper()}: {err['msg']}")
        raise ConfigError("Invalid configuration: " + "; ".join(problems)) from None
