"""Project reports (D-094, D-095, D-105): one table per download, as CSV or TSV.

- "progress": one row per task (status, people, recording length, checks, decisions, dates);
- "participants": one row per participant with recorded, approved and payable minutes (D-095).

Recordings themselves are exported as a bundle made in the background: see bundle.py and jobs.py.
Access: exports.create in the project, the project visible to the caller. Every export is audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audio_qc import service as audio_qc
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.exports import minutes
from app.modules.exports.bundle import table
from app.modules.exports.models import TABLE_FORMATS
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from app.modules.projects.service import get_visible as get_visible_project
from app.modules.recordings.models import Recording
from app.modules.tasks.models import Task, TaskAssignment, TaskStatusHistory
from app.modules.telephony.models import Call

REPORTS = ("progress", "participants")


def _iso(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M") if value else ""


def report_project(
    db: Session, principal: Principal, project_id: uuid.UUID, content: str, table_format: str
) -> Project:
    """The project of a report this person may download (EXP-008)."""
    if content not in REPORTS or table_format not in TABLE_FORMATS:
        raise AppError("Choose what to export", code="VALIDATION_ERROR", status_code=422)
    project = get_visible_project(db, principal, project_id)
    if not principal.can_in_project(Perm.EXPORTS_CREATE, project.id):
        raise forbidden()
    return project


def record(
    db: Session,
    principal: Principal,
    project: Project,
    content: str,
    table_format: str,
    ip: str | None,
) -> None:
    audit.record(
        db,
        action="project.exported",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"content": content, "format": table_format},
    )
    db.commit()


def file_name(project: Project, content: str, table_format: str) -> str:
    day = datetime.now(UTC).strftime("%Y%m%d")
    return f"{content}_{project.code}_{day}.{table_format}"


def report(db: Session, project: Project, content: str, table_format: str) -> str:
    if content == "progress":
        return progress_table(db, project, table_format)
    return participants_table(db, project, table_format)


# ---------------------------------------------------------------- progress report


def progress_table(db: Session, project: Project, table_format: str = "csv") -> str:
    rows: list[list[object]] = []
    columns = [
        *[
            "task_code",
            "status",
            "mode",
            "priority",
            "due_date",
            "created_at",
            "participant_a",
            "participant_a_language",
            "participant_b",
            "participant_b_language",
            "moderator",
            "qc_executive",
            "finished_recordings",
            "latest_recording_minutes",
            "automatic_check",
            "qc_decision",
            "approved_at",
            "phone_calls",
            "last_call_state",
        ]
    ]
    # Phone calls per task, and the state of the newest one (D-103): two queries for the project,
    # not two per task.
    call_counts = {
        tid: int(n)
        for tid, n in db.execute(
            select(Call.task_id, func.count())
            .where(Call.project_id == project.id)
            .group_by(Call.task_id)
        ).all()
    }
    last_call: dict[uuid.UUID, str] = {}
    for tid, state in db.execute(
        select(Call.task_id, Call.state)
        .where(Call.project_id == project.id)
        .order_by(Call.dialled_at)
    ).all():
        last_call[tid] = state
    for task in db.scalars(
        select(Task).where(Task.project_id == project.id).order_by(Task.task_code)
    ):
        people = [
            db.get(Participant, pid) for pid in (task.participant_a_id, task.participant_b_id)
        ]

        def assignee(role: str, task_id: uuid.UUID = task.id) -> str:
            a = db.scalar(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.role_code == role,
                    TaskAssignment.active.is_(True),
                )
            )
            user = db.get(User, a.user_id) if a else None
            return user.display_name if user else ""

        finished = (
            db.scalar(
                select(func.count())
                .select_from(Recording)
                .where(Recording.task_id == task.id, Recording.state == "READY")
            )
            or 0
        )
        latest = db.scalar(
            select(Recording)
            .where(Recording.task_id == task.id, Recording.state == "READY")
            .order_by(Recording.started_at.desc())
            .limit(1)
        )
        asset = audio_qc.delivery_asset(db, latest.id) if latest else None
        results = audio_qc.results_for(db, task.id)
        mine = [r for r in results if latest is not None and r.recording_id == latest.id]
        automatic = next((r for r in mine if r.automated), None)
        decision = next((r for r in mine if not r.automated), None)
        approved_at = db.scalar(
            select(func.max(TaskStatusHistory.created_at)).where(
                TaskStatusHistory.task_id == task.id, TaskStatusHistory.to_status == "APPROVED"
            )
        )
        rows.append(
            [
                *(
                    task.task_code,
                    task.status,
                    task.recording_mode,
                    task.priority,
                    task.due_at.date().isoformat() if task.due_at else "",
                    _iso(task.created_at),
                    people[0].participant_code if people[0] else "",
                    people[0].language_code if people[0] else "",
                    people[1].participant_code if people[1] else "",
                    people[1].language_code if people[1] else "",
                    assignee("MODERATOR"),
                    assignee("QC_EXECUTIVE"),
                    finished,
                    round((asset.duration_ms or 0) / 60000, 2) if asset else "",
                    automatic.outcome if automatic else "",
                    decision.outcome if decision else "",
                    _iso(approved_at) if task.status == "APPROVED" else "",
                    call_counts.get(task.id, 0) if task.recording_mode == "TELEPHONY" else "",
                    last_call.get(task.id, ""),
                )
            ]
        )
    return table(columns, rows, table_format)


def participants_table(db: Session, project: Project, table_format: str = "csv") -> str:
    """Minutes per participant (D-095): each conversation is split equally between its two
    participants, so payable minutes are half of the approved conversation minutes."""
    totals = minutes.per_participant(db, project.id)
    people = (
        {p.id: p for p in db.scalars(select(Participant).where(Participant.id.in_(list(totals))))}
        if totals
        else {}
    )
    rows: list[list[object]] = []
    columns = [
        "participant_code",
        "language",
        "conversations_recorded",
        "recorded_minutes",
        "conversations_approved",
        "approved_minutes",
        "payable_minutes",
    ]
    for pid, t in sorted(
        totals.items(), key=lambda kv: people[kv[0]].participant_code if kv[0] in people else ""
    ):
        person = people.get(pid)
        rows.append(
            [
                *(
                    person.participant_code if person else "",
                    person.language_code if person else "",
                    t.conversations,
                    minutes.as_minutes(t.recorded_ms),
                    t.approved_conversations,
                    minutes.as_minutes(t.approved_ms),
                    minutes.as_minutes(t.payable_ms),
                )
            ]
        )
    return table(columns, rows, table_format)
