"""Migrations run from an empty database; schema follows the conventions.

Requirements: FND-009, FND-026, DB-002, DB-003, DB-006
"""

from datetime import UTC, datetime
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


def _participant_row(db: Any, code: str) -> Any:
    """A participant written as SQL, like _project_row: the participants table as it was at an
    older revision (speaker details came with 0033)."""
    return db.execute(
        text(
            "INSERT INTO participants (participant_code, display_label, language_code) "
            "VALUES (:code, 'x', 'hi') RETURNING id"
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

    from app.modules.participants.models import ConsentRecord

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
        ids = [_participant_row(db, f"P90000{i}") for i in (1, 2, 3)]
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


def test_the_audit_action_index_comes_and_goes(test_database_url: str) -> None:
    """0032: the audit viewer filters on action with = and LIKE 'x.%'; the index serves both
    (text_pattern_ops), and going back removes it."""
    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(test_database_url)
    found = text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_audit_logs_action'")
    with engine.begin() as conn:
        assert "(action text_pattern_ops)" in conn.execute(found).scalar_one()
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = conn.execute(
            text("EXPLAIN SELECT id FROM audit_logs WHERE action LIKE 'participant.%'")
        )
        assert "ix_audit_logs_action" in " ".join(line for (line,) in plan)
    command.downgrade(cfg, "0031")
    with engine.begin() as conn:
        assert conn.execute(found).first() is None
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


def test_speaker_details_and_pairing_rules_come_and_go(test_database_url: str) -> None:
    """0033 (D-143): people saved before have no speaker details; the codes, the age range and
    PIN codes are kept valid by the database too; every project gets at most 3 conversations per
    speaker and each pair once; going back removes them."""
    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0032")
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        project_id = _project_row(conn, "MIG")
        person_id = _participant_row(conn, "P900001")
    command.upgrade(cfg, "0033")  # the age check became 1 to 120 with 0035 (D-145)
    with engine.begin() as conn:
        rules = conn.execute(
            text("SELECT max_conversations_per_speaker, unique_pairs FROM projects WHERE id = :p"),
            {"p": project_id},
        ).one()
        assert tuple(rules) == (3, True)
        person = conn.execute(
            text("SELECT age, gender, native_state, recording_pincode, district FROM participants")
        ).one()
        assert tuple(person) == (None, None, None, None, "")
        conn.execute(
            text(
                "UPDATE participants SET age = 60, gender = 'FEMALE', education = 'PHD', "
                "education_medium = 'NON_ENGLISH', current_pincode = '403001' WHERE id = :p"
            ),
            {"p": person_id},
        )
    for column, bad in (
        ("age", 19),
        ("age", 61),
        ("gender", "OTHER"),
        ("education", "SCHOOL"),
        ("education_medium", "HINDI"),
        ("native_pincode", "012345"),
        ("recording_pincode", "40300"),
        ("current_pincode", "40300A"),
    ):
        update = text("UPDATE participants SET " + column + " = :v")  # noqa: S608 - fixed names
        with pytest.raises(Exception, match="ck_participants_"), engine.begin() as conn:
            conn.execute(update, {"v": bad})
    with pytest.raises(Exception, match="max_conversations_range"), engine.begin() as conn:
        conn.execute(text("UPDATE projects SET max_conversations_per_speaker = 0"))
    command.downgrade(cfg, "0032")
    with engine.begin() as conn:
        people = {c["name"] for c in inspect(conn).get_columns("participants")}
        projects = {c["name"] for c in inspect(conn).get_columns("projects")}
    assert {"age", "recording_pincode"}.isdisjoint(people)
    assert "district" in people
    assert {"max_conversations_per_speaker", "unique_pairs"}.isdisjoint(projects)
    engine.dispose()


def test_consent_mode_and_participant_documents_come_and_go(test_database_url: str) -> None:
    """0034 (D-144): every existing project keeps taking consent online; documents keep one
    current file per kind (per project for a consent form, none for an address proof), only PDF,
    JPEG and PNG; going back removes the table and the option."""
    from sqlalchemy.orm import Session

    from tests.conftest import make_user

    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0033")
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        project_id = _project_row(conn, "MIG")
        person_id = _participant_row(conn, "P900001")
    command.upgrade(cfg, "head")
    with Session(engine) as db:
        user_id = make_user(db, "up@example.org", ["PROJECT_ADMIN"]).id
    insert = text(
        "INSERT INTO participant_documents (participant_id, project_id, kind, storage_key, "
        "file_name, content_type, size_bytes, sha256, uploaded_by, replaced_at) VALUES (:person, "
        ":project, :kind, :key, 'f.pdf', :type, :size, 'x', :user, :replaced)"
    )

    def row(key: str, **changes: Any) -> dict[str, Any]:
        values = {
            "person": person_id,
            "project": project_id,
            "kind": "CONSENT_FORM",
            "key": key,
            "type": "application/pdf",
            "size": 10,
            "user": user_id,
            "replaced": None,
        }
        return {**values, **changes}

    with engine.begin() as conn:
        mode = text("SELECT consent_mode FROM projects WHERE id = :p")
        assert conn.execute(mode, {"p": project_id}).scalar_one() == "ONLINE"
        conn.execute(text("UPDATE projects SET consent_mode = 'UPLOAD'"))
        conn.execute(insert, row("a", replaced=datetime.now(UTC)))
        conn.execute(insert, row("b"))
        conn.execute(insert, row("c", kind="ADDRESS_PROOF", project=None, type="image/png"))
    for match, values in (
        ("uq_participant_documents_current_consent_form", row("d")),
        (
            "uq_participant_documents_current_address_proof",
            row("e", kind="ADDRESS_PROOF", project=None),
        ),
        ("project_for_consent_form", row("f", project=None)),
        ("project_for_consent_form", row("g", kind="ADDRESS_PROOF")),
        ("content_type_allowed", row("h", type="text/html", replaced=datetime.now(UTC))),
        ("kind_allowed", row("i", kind="PASSPORT", project=None)),
        ("size_positive", row("j", size=0, replaced=datetime.now(UTC))),
        ("storage_key", row("a", replaced=datetime.now(UTC))),
    ):
        with pytest.raises(Exception, match=match), engine.begin() as conn:
            conn.execute(insert, values)
    with pytest.raises(Exception, match="consent_mode_allowed"), engine.begin() as conn:
        conn.execute(text("UPDATE projects SET consent_mode = 'PAPER'"))
    command.downgrade(cfg, "0033")
    with engine.begin() as conn:
        assert "participant_documents" not in inspect(conn).get_table_names()
        assert "consent_mode" not in {c["name"] for c in inspect(conn).get_columns("projects")}
    engine.dispose()


def test_project_speaker_rules_come_and_go(test_database_url: str) -> None:
    """0035 (D-145): every existing project gets the first client's rules as its own (speakers
    aged 20 to 60, every speaker detail needed); a person's age may be 1 to 120; going back keeps
    the ages saved meanwhile and holds new values to 20 to 60 again."""
    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0034")
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        project_id = _project_row(conn, "MIG")
        person_id = _participant_row(conn, "P900001")
    command.upgrade(cfg, "head")
    every = [
        "age",
        "gender",
        "current_state",
        "current_district",
        "current_pincode",
        "native_state",
        "district",
        "native_pincode",
        "native_language",
        "education",
        "education_medium",
        "recording_state",
        "recording_district",
        "recording_pincode",
    ]
    with engine.begin() as conn:
        rules = conn.execute(
            text(
                "SELECT speaker_min_age, speaker_max_age, required_speaker_details FROM projects "
                "WHERE id = :p"
            ),
            {"p": project_id},
        ).one()
        assert tuple(rules) == (20, 60, every)
        for age in (1, 120, 70):
            conn.execute(
                text("UPDATE participants SET age = :a WHERE id = :p"), {"a": age, "p": person_id}
            )
    for sql, match in (
        ("UPDATE participants SET age = 0", "ck_participants_age_range"),
        ("UPDATE participants SET age = 121", "ck_participants_age_range"),
        ("UPDATE projects SET speaker_min_age = 61", "speaker_age_range"),
        ("UPDATE projects SET speaker_max_age = 121", "speaker_age_range"),
        ("UPDATE projects SET speaker_min_age = 0", "speaker_age_range"),
        ("UPDATE projects SET required_speaker_details = '{}'::jsonb", "required_speaker_details"),
    ):
        with pytest.raises(Exception, match=match), engine.begin() as conn:
            conn.execute(text(sql))
    command.downgrade(cfg, "0034")
    with engine.begin() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("projects")}
        assert {"speaker_min_age", "speaker_max_age", "required_speaker_details"}.isdisjoint(
            columns
        )
        assert conn.execute(text("SELECT age FROM participants")).scalar_one() == 70, "kept"
    with pytest.raises(Exception, match="ck_participants_age_range"), engine.begin() as conn:
        conn.execute(text("UPDATE participants SET age = 75"))
    command.upgrade(cfg, "head")
    engine.dispose()


def test_the_qc_checklist_and_the_consent_fix_come_and_go(test_database_url: str) -> None:
    """0036 (D-146): every existing project gets the first client's QC checklist as its own; a
    decision may keep its answers and send a task back for its consent form (CONSENT_FIX); one
    draft per task; going back moves such tasks back to Audio QC and keeps the decisions."""
    from sqlalchemy.orm import Session

    from app.modules.audio_qc.checklist import DEFAULT_QC_CHECKLIST
    from app.modules.recordings.models import Recording
    from app.modules.tasks.models import Task
    from tests.conftest import make_user

    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0035")
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        project_id = _project_row(conn, "MIG")
        a = _participant_row(conn, "P900001")
        b = _participant_row(conn, "P900002")
    command.upgrade(cfg, "head")
    with Session(engine) as db:
        mod = make_user(db, "mig@example.org", ["MODERATOR"])
        task = Task(
            task_code="T900001",
            project_id=project_id,
            recording_mode="FACE_TO_FACE",
            status="AUDIO_QC",
            priority="NORMAL",
            participant_a_id=a,
            participant_b_id=b,
        )
        db.add(task)
        db.flush()
        recording = Recording(
            task_id=task.id,
            mode="FACE_TO_FACE",
            state="READY",
            created_by=mod.id,
            native_sample_rate=16000,
            channel_count=1,
            channel_handling="mono",
            started_at=datetime.now(UTC),
        )
        db.add(recording)
        db.commit()
        task_id, recording_id = task.id, recording.id
    command.upgrade(cfg, "head")
    decision = text(
        "INSERT INTO audio_qc_results (recording_id, task_id, project_id, automated, outcome, "
        "checklist) VALUES (:r, :t, :p, false, :o, CAST(:c AS jsonb))"
    )
    with engine.begin() as conn:
        saved = conn.execute(
            text("SELECT qc_checklist FROM projects WHERE id = :p"), {"p": project_id}
        ).scalar_one()
        assert saved == list(DEFAULT_QC_CHECKLIST)
        assert saved[20]["question"] == "Is the speaker's volume low?"
        conn.execute(
            decision,
            {"r": recording_id, "t": task_id, "p": project_id, "o": "SEND_BACK_CONSENT", "c": "{}"},
        )
        conn.execute(text("UPDATE tasks SET status = 'CONSENT_FIX' WHERE id = :t"), {"t": task_id})
        conn.execute(
            text("INSERT INTO audio_qc_drafts (task_id, answers) VALUES (:t, '{}'::jsonb)"),
            {"t": task_id},
        )
    for sql, match in (
        ("UPDATE projects SET qc_checklist = '{}'::jsonb", "qc_checklist_list"),
        ("UPDATE tasks SET status = 'CONSENT_LOST'", "ck_tasks_status_allowed"),
        (
            "INSERT INTO audio_qc_drafts (task_id, answers) SELECT id, '{}'::jsonb FROM tasks",
            "uq_audio_qc_drafts_task_id",
        ),
    ):
        with pytest.raises(Exception, match=match), engine.begin() as conn:
            conn.execute(text(sql))
    with pytest.raises(Exception, match="outcome_allowed"), engine.begin() as conn:
        conn.execute(
            decision, {"r": recording_id, "t": task_id, "p": project_id, "o": "MAYBE", "c": None}
        )
    command.downgrade(cfg, "0035")
    with engine.begin() as conn:
        assert "audio_qc_drafts" not in inspect(conn).get_table_names()
        assert "qc_checklist" not in {c["name"] for c in inspect(conn).get_columns("projects")}
        status = text("SELECT status FROM tasks WHERE id = :t")
        assert conn.execute(status, {"t": task_id}).scalar_one() == "AUDIO_QC"
        moved = conn.execute(
            text("SELECT from_status, to_status FROM task_status_history WHERE task_id = :t"),
            {"t": task_id},
        ).one()
        assert tuple(moved) == ("CONSENT_FIX", "AUDIO_QC")
        outcome = text("SELECT outcome FROM audio_qc_results")
        assert conn.execute(outcome).scalar_one() == "SEND_BACK_CONSENT", "kept"
    with pytest.raises(Exception, match="outcome_allowed"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audio_qc_results (recording_id, task_id, project_id, automated, "
                "outcome) VALUES (:r, :t, :p, false, 'SEND_BACK_CONSENT')"
            ),
            {"r": recording_id, "t": task_id, "p": project_id},
        )
    command.upgrade(cfg, "head")
    engine.dispose()


def test_device_details_and_reminders_come_and_go(test_database_url: str) -> None:
    """0037 (D-147): every existing project asks all five device details and gets the first
    client's reminders as its own; one row of device details per task and participant; going back
    drops them."""
    from app.modules.projects.moderation import DEFAULT_DEVICE_FIELDS, DEFAULT_RECORDING_REMINDERS

    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0036")
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        project_id = _project_row(conn, "MIG")
        a = _participant_row(conn, "P900001")
        b = _participant_row(conn, "P900002")
        task_id = conn.execute(
            text(
                "INSERT INTO tasks (task_code, project_id, recording_mode, status, priority, "
                "participant_a_id, participant_b_id) VALUES ('T900001', :p, 'TELEPHONY', "
                "'RECORDED', 'NORMAL', :a, :b) RETURNING id"
            ),
            {"p": project_id, "a": a, "b": b},
        ).scalar_one()
    command.upgrade(cfg, "head")
    detail = text(
        "INSERT INTO task_device_details (task_id, participant_id, device_make, loudspeaker_on) "
        "VALUES (:t, :p, 'Samsung', false)"
    )
    with engine.begin() as conn:
        fields, reminders = conn.execute(
            text("SELECT device_fields, recording_reminders FROM projects WHERE id = :p"),
            {"p": project_id},
        ).one()
        assert fields == list(DEFAULT_DEVICE_FIELDS)
        assert reminders == DEFAULT_RECORDING_REMINDERS
        assert reminders["speaker_id"] is True
        conn.execute(detail, {"t": task_id, "p": a})
        conn.execute(detail, {"t": task_id, "p": b})
    for sql, match in (
        ("UPDATE projects SET device_fields = '{}'::jsonb", "device_fields_list"),
        ("UPDATE projects SET recording_reminders = '[]'::jsonb", "recording_reminders_object"),
        (
            "UPDATE task_device_details SET device_model = repeat('x', 61)",
            "value too long",
        ),
    ):
        with pytest.raises(Exception, match=match), engine.begin() as conn:
            conn.execute(text(sql))
    with pytest.raises(Exception, match="uq_task_device_details_task_id"), engine.begin() as conn:
        conn.execute(detail, {"t": task_id, "p": a})
    command.downgrade(cfg, "0036")
    with engine.begin() as conn:
        assert "task_device_details" not in inspect(conn).get_table_names()
        columns = {c["name"] for c in inspect(conn).get_columns("projects")}
        assert {"device_fields", "recording_reminders"}.isdisjoint(columns)
    command.upgrade(cfg, "head")
    engine.dispose()


def test_effective_speech_and_the_project_targets_come_and_go(test_database_url: str) -> None:
    """0038 (D-148): files made before have no effective speech yet (the backfill measures them);
    every existing project gets the pause limit of 3 s shown only, completed minutes counted as
    effective speech and the first client's targets; going back drops them."""
    from app.modules.projects import targets

    reset_schema(test_database_url)
    cfg = alembic_config(test_database_url)
    command.upgrade(cfg, "0037")
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        project_id = _project_row(conn, "MIG")
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT pause_limit_seconds, long_pauses_need_review, progress_counts,"
                " target_hours, target_speakers, target_conversations, target_age_bands,"
                " target_gender, target_modes, target_districts FROM projects WHERE id = :p"
            ),
            {"p": project_id},
        ).one()
        assert tuple(row) == (
            3,
            False,
            "EFFECTIVE",
            None,
            500,
            600,
            list(targets.DEFAULT_TARGET_AGE_BANDS),
            targets.DEFAULT_TARGET_GENDER,
            targets.DEFAULT_TARGET_MODES,
            [],
        )
        columns = {c["name"]: c for c in inspect(conn).get_columns("audio_assets")}
        for name in ("effective_ms", "longest_pause_ms", "pauses_ms", "speech_error"):
            assert columns[name]["nullable"], name
        indexes = {i["name"] for i in inspect(conn).get_indexes("audio_assets")}
        assert "ix_audio_assets_speech_missing" in indexes
    for sql, match in (
        ("UPDATE projects SET pause_limit_seconds = 0", "pause_limit_range"),
        ("UPDATE projects SET pause_limit_seconds = 31", "pause_limit_range"),
        ("UPDATE projects SET progress_counts = 'SOME'", "progress_counts_allowed"),
        ("UPDATE projects SET target_speakers = 0", "targets_positive"),
        ("UPDATE projects SET target_age_bands = '{}'::jsonb", "target_age_bands_list"),
        ("UPDATE projects SET target_gender = '[]'::jsonb", "target_gender_object"),
        ("UPDATE projects SET target_modes = '[]'::jsonb", "target_modes_object"),
        ("UPDATE projects SET target_districts = '{}'::jsonb", "target_districts_list"),
    ):
        with pytest.raises(Exception, match=match), engine.begin() as conn:
            conn.execute(text(sql))
    command.downgrade(cfg, "0037")
    with engine.begin() as conn:
        project_columns = {c["name"] for c in inspect(conn).get_columns("projects")}
        assert {"pause_limit_seconds", "target_age_bands", "progress_counts"}.isdisjoint(
            project_columns
        )
        asset_columns = {c["name"] for c in inspect(conn).get_columns("audio_assets")}
        assert {"effective_ms", "pauses_ms", "speech_error"}.isdisjoint(asset_columns)
    command.upgrade(cfg, "head")
    engine.dispose()
