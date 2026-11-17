"""Migrations run from an empty database; schema follows the conventions.

Requirements: FND-009, FND-026, DB-002, DB-003, DB-006
"""

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select, text

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


def test_returned_tasks_leave_the_removed_status(test_database_url: str) -> None:
    """0026 (D-118): a task still at RETURNED goes back to ASSIGNED (DRAFT when nobody records
    it), with a history entry by the platform; a task on hold from RETURNED resumes there too."""
    from sqlalchemy.orm import Session

    from app.modules.participants.models import Participant
    from app.modules.tasks.models import Task, TaskAssignment, TaskStatusHistory
    from tests.conftest import make_project, make_user

    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(test_database_url)
    with Session(engine) as db:
        project = make_project(db, "MIG")
        mod = make_user(db, "mig@example.org", ["MODERATOR"], projects=[project])
        a, b = (
            Participant(participant_code=code, display_label=code, language_code="hi")
            for code in ("P900001", "P900002")
        )
        db.add_all([a, b])
        db.flush()
        tasks = {
            code: Task(
                task_code=code,
                project_id=project.id,
                recording_mode="FACE_TO_FACE",
                status="DRAFT",
                priority="NORMAL",
                participant_a_id=a.id,
                participant_b_id=b.id,
            )
            for code in ("T900001", "T900002", "T900003")
        }
        db.add_all(tasks.values())
        db.flush()
        db.add(TaskAssignment(task_id=tasks["T900001"].id, user_id=mod.id, role_code="MODERATOR"))
        db.commit()
    command.downgrade(cfg, "0025")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE tasks SET status = 'RETURNED', reason_code = 'RE_RECORD' "
                "WHERE task_code IN ('T900001', 'T900002')"
            )
        )
        conn.execute(
            text(
                "UPDATE tasks SET status = 'ON_HOLD', held_from = 'RETURNED' "
                "WHERE task_code = 'T900003'"
            )
        )
    command.upgrade(cfg, "head")
    with Session(engine) as db:
        found = {t.task_code: t for t in db.scalars(select(Task))}
        assert (found["T900001"].status, found["T900001"].reason_code) == ("ASSIGNED", None)
        assert found["T900002"].status == "DRAFT", "nobody is assigned to record it"
        assert (found["T900003"].status, found["T900003"].held_from) == ("ON_HOLD", "DRAFT")
        moved = db.scalars(
            select(TaskStatusHistory).where(TaskStatusHistory.from_status == "RETURNED")
        ).all()
        assert sorted(h.to_status for h in moved) == ["ASSIGNED", "DRAFT"]
        assert all(h.actor_id is None and "D-118" in h.comment for h in moved)
    engine.dispose()
