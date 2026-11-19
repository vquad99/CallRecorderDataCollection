"""Project reports (D-094, D-095, D-105): one table per download, as CSV or TSV.

- "progress": one row per task (status, people, recording length, checks, decisions, dates);
- "participants": one row per participant with recorded, approved and payable minutes (D-095).

Recordings themselves are exported as a bundle made in the background: see bundle.py and jobs.py;
one task's bundle is made at once from its page (D-136).
Access: exports.create in the project, the project visible to the caller. Every export is audited.
"""

from __future__ import annotations

import hashlib
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm, Role
from app.core.slots import turn
from app.core.storage import ObjectStorage
from app.modules.audio_qc.models import AudioQcResult
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.auth.security import FieldCipher
from app.modules.exports import bundle, minutes
from app.modules.exports.bundle import table
from app.modules.exports.models import TABLE_FORMATS
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable
from app.modules.recordings.models import (
    DELIVERY_KINDS,
    AudioAsset,
    Recording,
    current_recordings_query,
)
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task, TaskAssignment
from app.modules.telephony.models import Call

REPORTS = ("progress", "participants")
# A task's bundle is held in memory up to this size while it is made, then in MEDIA_WORK_DIR.
SPOOL_BYTES = 8 * 1024 * 1024
# At most this many tasks' bundles are made at once in one process; the rest wait their turn.
BUILD_SLOTS = 2
BUILD_WAIT_SECONDS = 10.0
BUILDS_BUSY = "Another download is being prepared. Try again in a minute."
_builds = threading.BoundedSemaphore(BUILD_SLOTS)


def _iso(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M") if value else ""


def report_project(
    db: Session, principal: Principal, project_id: uuid.UUID, content: str, table_format: str
) -> Project:
    """The project of a report this person may download (EXP-008)."""
    if content not in REPORTS or table_format not in TABLE_FORMATS:
        raise AppError("Choose what to export", code="VALIDATION_ERROR", status_code=422)
    return get_manageable(db, principal, project_id, Perm.EXPORTS_CREATE)


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
    """One row per task. Every column comes from one query over the whole project, so the
    report costs the same dozen queries for ten tasks or ten thousand."""
    columns = [
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
    tasks = list(
        db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.task_code))
    )
    in_project = select(Task.id).where(Task.project_id == project.id)
    people_ids = {pid for t in tasks for pid in (t.participant_a_id, t.participant_b_id)}
    people = (
        {
            pid: (code, language)
            for pid, code, language in db.execute(
                select(
                    Participant.id, Participant.participant_code, Participant.language_code
                ).where(Participant.id.in_(people_ids))
            )
        }
        if people_ids
        else {}
    )
    assignees = {
        (tid, role): name
        for tid, role, name in db.execute(
            select(TaskAssignment.task_id, TaskAssignment.role_code, User.display_name)
            .join(User, User.id == TaskAssignment.user_id)
            .where(TaskAssignment.active.is_(True), TaskAssignment.task_id.in_(in_project))
        )
    }
    finished = {
        tid: int(n)
        for tid, n in db.execute(
            select(Recording.task_id, func.count())
            .where(Recording.state == "READY", Recording.task_id.in_(in_project))
            .group_by(Recording.task_id)
        )
    }
    # The current recording of each task (D-135), its delivery file and its audio QC results.
    latest = {
        tid: rid
        for rid, tid, _ in db.execute(
            current_recordings_query().where(Recording.task_id.in_(in_project))
        )
    }
    latest_ids = list(latest.values())
    delivery_ms: dict[uuid.UUID, int] = {}
    automatic: dict[uuid.UUID, str] = {}
    decision: dict[uuid.UUID, str] = {}
    if latest_ids:
        delivery_ms = {
            rid: int(ms or 0)
            for rid, ms in db.execute(
                select(AudioAsset.recording_id, AudioAsset.duration_ms)
                .where(
                    AudioAsset.recording_id.in_(latest_ids),
                    AudioAsset.kind.in_(DELIVERY_KINDS),
                    AudioAsset.deleted_at.is_(None),
                )
                .ext(distinct_on(AudioAsset.recording_id))
                .order_by(AudioAsset.recording_id, AudioAsset.version.desc())
            )
        }
        # Newest first: the first result seen of each kind is the one that counts.
        for rid, automated, outcome in db.execute(
            select(AudioQcResult.recording_id, AudioQcResult.automated, AudioQcResult.outcome)
            .where(AudioQcResult.recording_id.in_(latest_ids))
            .order_by(AudioQcResult.created_at.desc())
        ):
            (automatic if automated else decision).setdefault(rid, outcome)
    approved_at = dict(db.execute(minutes.approval_times([project.id])).all())
    # Phone calls per task, and the state of the newest one (D-103).
    call_counts = {
        tid: int(n)
        for tid, n in db.execute(
            select(Call.task_id, func.count())
            .where(Call.project_id == project.id)
            .group_by(Call.task_id)
        )
    }
    last_call = dict(
        db.execute(
            select(Call.task_id, Call.state)
            .where(Call.project_id == project.id)
            .ext(distinct_on(Call.task_id))
            .order_by(Call.task_id, Call.dialled_at.desc())
        ).all()
    )
    rows: list[list[object]] = []
    for task in tasks:
        a_code, a_language = people.get(task.participant_a_id, ("", ""))
        b_code, b_language = people.get(task.participant_b_id, ("", ""))
        newest = latest.get(task.id)
        ms = delivery_ms.get(newest) if newest else None
        rows.append(
            [
                task.task_code,
                task.status,
                task.recording_mode,
                task.priority,
                task.due_at.date().isoformat() if task.due_at else "",
                _iso(task.created_at),
                a_code,
                a_language,
                b_code,
                b_language,
                assignees.get((task.id, Role.MODERATOR.value), ""),
                assignees.get((task.id, Role.QC_EXECUTIVE.value), ""),
                finished.get(task.id, 0),
                round(ms / 60000, 2) if ms is not None else "",
                automatic.get(newest, "") if newest else "",
                decision.get(newest, "") if newest else "",
                _iso(approved_at.get(task.id)) if task.status == "APPROVED" else "",
                call_counts.get(task.id, 0) if task.recording_mode == "TELEPHONY" else "",
                last_call.get(task.id, ""),
            ]
        )
    return table(columns, rows, table_format)


def participants_table(db: Session, project: Project, table_format: str = "csv") -> str:
    """Minutes per participant (D-095, D-111): each conversation's length is split equally
    between its two participants; every column is the participant's share."""
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


# ---------------------------------------------------------------- one task's bundle


def task_bundle(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    cipher: FieldCipher,
    principal: Principal,
    task_id: uuid.UUID,
    ip: str | None,
) -> tuple[str, IO[bytes], int]:
    """One task's files as a bundle (D-136): its current recording's delivery file, details file
    and consent record, in the folders and with the tables of a project export. Approved tasks
    only, as the project export's own default. Made at once, while the person waits (BUILD_SLOTS
    at a time, 503 BUSY after BUILD_WAIT_SECONDS): returns the file name, the ZIP (read from the
    start) and its size. Audited as task.exported."""
    task = tasks.get_task(db, principal, task_id)
    project = db.get_one(Project, task.project_id)
    sel = bundle.Selection()  # audio and details, approved tasks, CSV tables
    bundle.check(db, principal, project, sel)
    if task.status != "APPROVED":
        raise AppError(
            "The task's files can be downloaded here once it is approved",
            code="TASK_NOT_APPROVED",
            status_code=409,
        )
    entries = bundle.select_entries(db, project, sel, settings.report_timezone, task_id=task.id)
    if not entries:
        raise AppError(
            "This task has no finished recording", code="NOTHING_TO_EXPORT", status_code=409
        )
    name = bundle.file_name(project, sel, task_code=task.task_code)
    export_id = str(uuid.uuid4())
    made = bundle.Bundle(
        db=db,
        storage=storage,
        cipher=cipher,
        project=project,
        selection=sel,
        entries=entries,
        export_id=export_id,
        requested_by=principal.display_name,
    )
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    with turn(_builds, BUILD_WAIT_SECONDS, BUILDS_BUSY):
        out = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES, dir=str(work))  # noqa: SIM115 - handed on
        digest = hashlib.sha256()
        try:
            for part in made.parts():
                out.write(part)
                digest.update(part)
        except bundle.BundleError as exc:
            out.close()
            raise AppError(str(exc), code="EXPORT_FAILED", status_code=409) from None
        except BaseException:
            out.close()
            raise
    size = out.tell()
    out.seek(0)
    audit.record(
        db,
        action="task.exported",
        entity_type="task",
        entity_id=task_id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={
            "export_id": export_id,
            "file_name": name,
            "bytes": size,
            "sha256": digest.hexdigest(),
        },
    )
    db.commit()
    return name, out, size
