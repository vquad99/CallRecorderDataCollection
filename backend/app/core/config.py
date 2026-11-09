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
        return self

    @property
    def api_docs_enabled(self) -> bool:
        if self.enable_api_docs is None:
            return self.app_env in ("development", "test")
        return self.enable_api_docs

    def secret_values(self) -> list[str]:
        """Values that must never appear in logs or responses."""
        from sqlalchemy.engine import make_url

        values = [self.secret_key.get_secret_value()]
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
