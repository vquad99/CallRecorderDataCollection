"""Alembic environment: runs migrations online against DATABASE_URL (FND-009, DB-003)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        return explicit
    from app.core.config import load_settings

    return load_settings().database_url.get_secret_value()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) migrations are not supported; run against a database.")
run_migrations_online()
