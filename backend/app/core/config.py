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
    # Super Admin and Project Admin accounts must set up two-step sign-in before they can
    # use anything else (D-106). Unset: required everywhere except development and test.
    require_admin_mfa: bool | None = None
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
    # Recovery (H): a recording left UPLOADED this long was never picked up; one PROCESSING this
    # long was abandoned by a stopped process. The sweep runs at start-up and every interval.
    processing_pickup_seconds: int = Field(default=60, ge=5, le=3600)
    # Monitoring (O8): requests and single database queries slower than these are logged as
    # warnings; 0 turns a warning off.
    slow_request_ms: int = Field(default=1000, ge=0, le=600_000)
    slow_query_ms: int = Field(default=250, ge=0, le=600_000)
    processing_stale_minutes: int = Field(default=15, ge=1, le=24 * 60)
    recovery_interval_seconds: int = Field(default=60, ge=0, le=3600)  # 0 = start-up only
    # Largest request body for every other API call (JSON); larger bodies get 413 (SEC-006).
    # 2.5 MB covers the largest JSON field (user CSV import, 2 000 000 characters) plus encoding.
    max_request_bytes: int = Field(default=2_500_000, ge=10_000, le=64_000_000)
    max_recording_seconds: int = Field(default=4 * 3600, ge=60, le=24 * 3600)
    # A participant's personal page link works this many days, then staff issue a new one.
    portal_link_days: int = Field(default=30, ge=1, le=365)
    # Dashboards count calendar days in this time zone (IANA name).
    report_timezone: str = "Asia/Kolkata"

    email_backend: Literal["smtp", "file"] = "file"
    email_from: str = "Conversation Collection <no-reply@localhost>"
    email_file_dir: str = "var/outbox"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None

    # Phone calls through TxContact (D-101). The dialer and the recording API are separate
    # TxContact services with their own sign-in. Unset: phone calls show "Not configured" (GEN-004).
    txcontact_base_url: str = "https://amber.txcontact.com"
    txcontact_dialer_username: str | None = None
    txcontact_dialer_password: SecretStr | None = None
    txcontact_campaign_ref: str = "dc-record-call"
    txcontact_source: str = "webapi"
    txcontact_record_user: str | None = None
    txcontact_record_password: SecretStr | None = None
    # Word sent before the token in the Authorization header; TxContact's API description does not
    # say which one it expects (NOT VERIFIED), so it can be changed without a release.
    txcontact_auth_scheme: str = Field(default="Token", max_length=20)
    # Time zone of the times TxContact reports when they carry none (NOT VERIFIED).
    txcontact_timezone: str = "Asia/Kolkata"
    txcontact_timeout_seconds: int = Field(default=20, ge=1, le=120)
    # After the moderator closes a call, look for its recording for this long before asking a
    # person to pick it or try again.
    telephony_fetch_minutes: int = Field(default=60, ge=5, le=24 * 60)
    # The first look for a closed call's recording waits this long: the provider writes the file
    # after the call ends.
    telephony_first_look_seconds: int = Field(default=30, ge=0, le=600)
    # A participant's phone is not rung over and over: at most this many calls for one task in
    # an hour, counting refused and cancelled ones.
    telephony_max_calls_per_task_per_hour: int = Field(default=6, ge=1, le=100)
    telephony_max_download_bytes: int = Field(default=500_000_000, ge=1_000_000)
    # Export bundles (D-105): how long a finished bundle stays in storage, after how long a
    # job that stopped half-way is tried again, and how long a waiting job is left to the
    # worker it was first sent to before the sweep sends it again.
    export_bundle_hours: int = Field(default=24, ge=1, le=24 * 30)
    export_stale_minutes: int = Field(default=60, ge=1, le=24 * 60)
    export_requeue_seconds: int = Field(default=120, ge=0, le=3600)
    # Operation alerts (D-109): who is told by email when the platform finds something
    # wrong with itself (comma-separated addresses; unset: shown on the status page only),
    # and after how many hours the message is repeated while anything is still wrong.
    alert_email: str | None = None
    alert_repeat_hours: int = Field(default=24, ge=1, le=24 * 7)

    @field_validator("data_encryption_key")
    @classmethod
    def _fernet_key(cls, value: SecretStr) -> SecretStr:
        from cryptography.fernet import Fernet

        keys = [k.strip() for k in value.get_secret_value().split(",") if k.strip()]
        try:
            if not keys:
                raise ValueError
            for key in keys:  # one key, or several for rotation: the first encrypts (D-088)
                Fernet(key.encode())
        except (ValueError, TypeError):
            raise ValueError("must be a Fernet key (32 url-safe base64-encoded bytes)") from None
        return value

    @field_validator("txcontact_base_url")
    @classmethod
    def _txcontact_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")) or value.endswith("/"):
            raise ValueError("must be scheme://host[:port] without a trailing slash")
        return value

    @field_validator("report_timezone", "txcontact_timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("must be an IANA time zone such as Asia/Kolkata") from None
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

    @field_validator("database_url", mode="before")
    @classmethod
    def _db_driver(cls, value: object) -> object:
        # Hosting platforms hand out postgres:// or postgresql:// URLs; the app talks psycopg 3.
        text = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(text, str):
            for prefix in ("postgres://", "postgresql://"):
                if text.startswith(prefix):
                    return _DB_SCHEME + text[len(prefix) :]
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
            if not self.txcontact_base_url.startswith("https://"):
                raise ValueError("TXCONTACT_BASE_URL must use https in production")
        return self

    @property
    def telephony_configured(self) -> bool:
        return bool(
            self.txcontact_dialer_username
            and self.txcontact_dialer_password
            and self.txcontact_record_user
            and self.txcontact_record_password
        )

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
    def admin_mfa_required(self) -> bool:
        if self.require_admin_mfa is None:
            return self.app_env not in ("development", "test")
        return self.require_admin_mfa

    @property
    def api_docs_enabled(self) -> bool:
        if self.enable_api_docs is None:
            return self.app_env in ("development", "test")
        return self.enable_api_docs

    def secret_values(self) -> list[str]:
        """Values that must never appear in logs or responses."""
        from sqlalchemy.engine import make_url

        keys = self.data_encryption_key.get_secret_value()
        values = [self.secret_key.get_secret_value(), keys]
        values += [k.strip() for k in keys.split(",") if k.strip()]  # each rotation key too
        if self.smtp_password is not None:
            values.append(self.smtp_password.get_secret_value())
        if self.storage_secret_access_key is not None:
            values.append(self.storage_secret_access_key.get_secret_value())
        for secret in (self.txcontact_dialer_password, self.txcontact_record_password):
            if secret is not None:
                values.append(secret.get_secret_value())
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
