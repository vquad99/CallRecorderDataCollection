"""Migrations run from an empty database; schema follows the conventions.

Requirements: FND-009, FND-026, DB-002, DB-003, DB-006
"""

from typing import Any

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


def _project_row(db: Any, code: str) -> Any:
    """A project written as SQL: the projects table as it was at an older revision, whatever
    columns came later."""
    return db.execute(
        text(
            "INSERT INTO projects (code, name, status, allows_telephony, allows_face_to_face) "
            "VALUES (:code, :code, 'ACTIVE', true, true) RETURNING id"
        ),
        {"code": code},
    ).scalar_one()


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


def test_answers_waiting_for_review_are_accepted(test_database_url: str) -> None:
    """0027 (D-129): an own consent answer waiting for review counts as accepted, one staff sent
    back keeps that mark, a consent recorded by staff is left alone; consent.capture leaves
    every role (and comes back on downgrade)."""
    from sqlalchemy.orm import Session

    from app.modules.participants.models import ConsentRecord, Participant

    grants = (
        "SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
        "WHERE p.code = 'consent.capture'"
    )
    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0026")
    engine = create_engine(test_database_url)
    with Session(engine) as db:
        project_id = _project_row(db, "MIG")
        # Written as SQL: the users table as it was at 0026, whatever columns came later.
        staff_id = db.execute(
            text(
                "INSERT INTO users (email, display_name) VALUES ('mig@example.org', 'mig') "
                "RETURNING id"
            )
        ).scalar_one()
        people = [
            Participant(participant_code=f"P90000{i}", display_label="x", language_code="hi")
            for i in (1, 2, 3)
        ]
        db.add_all(people)
        db.flush()
        ids = [p.id for p in people]
        for pid, review, staff in zip(
            ids, ("PENDING", "REJECTED", "PENDING"), (None, None, staff_id), strict=True
        ):
            db.add(
                ConsentRecord(
                    participant_id=pid,
                    project_id=project_id,
                    task_id=None,
                    status="GIVEN",
                    method="DIGITAL" if staff is None else "WRITTEN",
                    policy_version="1",
                    captured_by=staff,
                    review_status=review,
                )
            )
        db.commit()
    with engine.begin() as conn:
        assert conn.execute(text(grants)).scalar_one() == 2  # Super Admin and Moderator
    command.upgrade(cfg, "head")
    with Session(engine) as db:
        reviews = {r.participant_id: r.review_status for r in db.scalars(select(ConsentRecord))}
        assert [reviews[i] for i in ids] == ["APPROVED", "REJECTED", "PENDING"]
    with engine.begin() as conn:
        assert conn.execute(text(grants)).scalar_one() == 0
        gone = conn.execute(text("SELECT count(*) FROM permissions WHERE code = 'consent.capture'"))
        assert gone.scalar_one() == 0
    command.downgrade(cfg, "0026")
    with engine.begin() as conn:
        assert conn.execute(text(grants)).scalar_one() == 2
    engine.dispose()


def test_the_seat_password_column_comes_and_goes(test_database_url: str) -> None:
    """0028 (D-130): the phone seat's password gets its own column, for the encrypted value only;
    going back removes it."""
    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(test_database_url)

    def columns() -> dict[str, str]:
        return {c["name"]: str(c["type"]) for c in inspect(engine).get_columns("users")}

    assert columns()["telephony_password_enc"] == "TEXT"
    command.downgrade(cfg, "0027")
    assert "telephony_password_enc" not in columns()
    command.upgrade(cfg, "head")
    assert "telephony_password_enc" in columns()
    engine.dispose()


def test_telephony_rules_at_the_old_default_become_stereo(test_database_url: str) -> None:
    """0029 (D-134): a telephony rule still at the old default of 1 channel becomes 2; one a
    project set to 2 and every face-to-face rule are left alone; going back makes phone rules 1."""
    from sqlalchemy.orm import Session

    from app.modules.projects.models import ProjectAudioRule

    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0028")
    engine = create_engine(test_database_url)
    with Session(engine) as db:
        for code, phone_channels in (("OLD", 1), ("SET", 2)):
            project_id = _project_row(db, code)
            db.add_all(
                ProjectAudioRule(
                    project_id=project_id,
                    mode=mode,
                    sample_rate=16000,
                    bit_depth=16,
                    channels=channels,
                    max_silence_pct=25,
                    min_duration_seconds=0,
                )
                for mode, channels in (("TELEPHONY", phone_channels), ("FACE_TO_FACE", 1))
            )
        db.commit()

    def channels() -> dict[tuple[str, str], int]:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT p.code, r.mode, r.channels FROM project_audio_rules r "
                    "JOIN projects p ON p.id = r.project_id"
                )
            )
            return {(code, mode): n for code, mode, n in rows}

    command.upgrade(cfg, "head")
    assert channels() == {
        ("OLD", "TELEPHONY"): 2,
        ("OLD", "FACE_TO_FACE"): 1,
        ("SET", "TELEPHONY"): 2,
        ("SET", "FACE_TO_FACE"): 1,
    }
    command.downgrade(cfg, "0028")
    assert set(channels().values()) == {1}
    engine.dispose()


def test_payments_and_the_qc_final_approval_option_come_and_go(test_database_url: str) -> None:
    """0030 (D-137): payment rates and payments.manage for the Super Admin and the Project
    Admin; 0031 (D-138): every project starts with "QC pass is the final approval" off."""
    from sqlalchemy.orm import Session

    grants = (
        "SELECT r.code FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
        "JOIN roles r ON r.id = rp.role_id WHERE p.code = 'payments.manage' ORDER BY r.code"
    )
    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0029")
    engine = create_engine(test_database_url)
    with Session(engine) as db:
        project_id = _project_row(db, "MIG")
        db.commit()
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        assert [r for (r,) in conn.execute(text(grants))] == ["PROJECT_ADMIN", "SUPER_ADMIN"]
        assert (
            conn.execute(
                text("SELECT qc_final_approval FROM projects WHERE id = :p"), {"p": project_id}
            ).scalar_one()
            is False
        )
        conn.execute(
            text("INSERT INTO payment_rates (project_id, moderator_rate) VALUES (:p, 2.5)"),
            {"p": project_id},
        )
    command.downgrade(cfg, "0029")
    with engine.begin() as conn:
        assert list(conn.execute(text(grants))) == []
        assert "payment_rates" not in inspect(conn).get_table_names()
        columns = {c["name"] for c in inspect(conn).get_columns("projects")}
        assert "qc_final_approval" not in columns
    engine.dispose()
