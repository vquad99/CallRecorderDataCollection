"""Migrations run from an empty database; schema follows the conventions.

Requirements: FND-009, FND-026, DB-002, DB-003, DB-006
"""

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db import models  # noqa: F401
from app.db.base import Base
from tests.conftest import alembic_config, reset_schema

pytestmark = pytest.mark.db


def test_upgrade_downgrade_upgrade_from_empty(test_database_url: str) -> None:
    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(test_database_url)
    assert "system_settings" in inspect(engine).get_table_names()
    command.downgrade(cfg, "base")
    assert "system_settings" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "system_settings" in inspect(engine).get_table_names()
    engine.dispose()


def test_migrations_match_models(migrated_db: str) -> None:
    """Every table the models declare exists after migrating (no model without a migration)."""
    engine = create_engine(migrated_db)
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    engine.dispose()


def test_schema_conventions(migrated_db: str) -> None:
    engine = create_engine(migrated_db)
    insp = inspect(engine)
    for table in insp.get_table_names():
        if table == "alembic_version":
            continue
        assert insp.get_pk_constraint(table)["constrained_columns"], f"{table}: no primary key"
        columns = {c["name"]: c for c in insp.get_columns(table)}
        for stamp in ("created_at", "updated_at"):
            assert stamp in columns, f"{table}.{stamp} missing"
            assert not columns[stamp]["nullable"], f"{table}.{stamp} nullable"
        for name, column in columns.items():
            assert "BYTEA" not in str(column["type"]).upper(), f"{table}.{name}: binary column"
    engine.dispose()


def test_value_type_is_constrained(migrated_db: str) -> None:
    engine = create_engine(migrated_db)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO system_settings (key, value_type) VALUES ('a', 'int')"))
    with pytest.raises(Exception, match="value_type_allowed"), engine.begin() as conn:
        conn.execute(text("INSERT INTO system_settings (key, value_type) VALUES ('b', 'json')"))
    engine.dispose()
