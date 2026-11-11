"""Project-level exports (D-094).

One download per project, in one of four forms:
- "audio": the delivery WAV of each recording, in a ZIP;
- "metadata": the details file (JSON) and consent record (HTML) of each recording, in a ZIP;
- "both": audio and metadata together, in a ZIP;
- "progress": one CSV row per task (status, people, recording length, checks, decisions, dates).

Every ZIP also holds manifest.csv, one row per recording with its files and checksum. Recordings
are the newest finished one of each task, from approved tasks only unless the caller asks for
every finished recording. Files are read from storage part by part and streamed out, so a large
project never sits in the server's memory. Access: exports.create in the project (Project Admin,
Client Viewer, Super Admin), the project visible to the caller. Every export is audited.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm
from app.core.storage import ObjectStorage
from app.modules.audio_qc import service as audio_qc
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from app.modules.projects.service import get_visible as get_visible_project
from app.modules.recordings import consent_form
from app.modules.recordings.models import Recording
from app.modules.tasks.models import Task, TaskAssignment, TaskStatusHistory

CONTENTS = ("audio", "metadata", "both", "progress")
SCOPES = ("approved", "finished")
MAX_RECORDINGS = 5000  # one export; more is split by asking for a smaller scope


@dataclass(frozen=True)
class Entry:
    task_id: uuid.UUID
    recording_id: uuid.UUID
    task_code: str
    audio_key: str | None
    audio_size: int
    audio_sha256: str | None
    duration_ms: int | None


@dataclass(frozen=True)
class Plan:
    project: Project
    content: str
    scope: str
    entries: list[Entry]
    total_bytes: int


def _safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _iso(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M") if value else ""


def plan(
    db: Session, principal: Principal, project_id: uuid.UUID, content: str, scope: str
) -> Plan:
    if content not in CONTENTS or scope not in SCOPES:
        raise AppError("Choose what to export", code="VALIDATION_ERROR", status_code=422)
    project = get_visible_project(db, principal, project_id)
    if not principal.can_in_project(Perm.EXPORTS_CREATE, project.id):
        raise forbidden()
    entries: list[Entry] = []
    if content != "progress":
        statuses = ("APPROVED",) if scope == "approved" else None
        query = select(Task).where(Task.project_id == project.id).order_by(Task.task_code)
        if statuses:
            query = query.where(Task.status.in_(statuses))
        for task in db.scalars(query):
            rec = db.scalar(
                select(Recording)
                .where(Recording.task_id == task.id, Recording.state == "READY")
                .order_by(Recording.started_at.desc())
                .limit(1)
            )
            if rec is None:
                continue
            asset = audio_qc.delivery_asset(db, rec.id)
            entries.append(
                Entry(
                    task_id=task.id,
                    recording_id=rec.id,
                    task_code=task.task_code,
                    audio_key=asset.storage_key if asset else None,
                    audio_size=int(asset.size_bytes or 0) if asset else 0,
                    audio_sha256=asset.sha256 if asset else None,
                    duration_ms=asset.duration_ms if asset else None,
                )
            )
            if len(entries) > MAX_RECORDINGS:
                raise AppError(
                    f"More than {MAX_RECORDINGS} recordings: export approved ones only, or ask "
                    "for a split export",
                    code="TOO_LARGE",
                    status_code=422,
                )
    total = sum(e.audio_size for e in entries) if content in ("audio", "both") else 0
    return Plan(project=project, content=content, scope=scope, entries=entries, total_bytes=total)


def record(db: Session, principal: Principal, p: Plan, ip: str | None) -> None:
    audit.record(
        db,
        action="project.exported",
        entity_type="project",
        entity_id=p.project.id,
        project_id=p.project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"content": p.content, "scope": p.scope, "recordings": len(p.entries)},
    )
    db.commit()


def file_name(p: Plan) -> str:
    day = datetime.now(UTC).strftime("%Y%m%d")
    if p.content == "progress":
        return f"progress_{p.project.code}_{day}.csv"
    return f"{p.content}_{p.project.code}_{day}.zip"


# ---------------------------------------------------------------- progress report


def progress_csv(db: Session, project: Project) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
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
        ]
    )
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
        writer.writerow(
            [
                _safe_cell(v)
                for v in (
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
                )
            ]
        )
    return out.getvalue()


# ---------------------------------------------------------------- ZIP, streamed


class _Sink:
    """A write-only target for ZipFile; what was written is taken out piece by piece."""

    def __init__(self) -> None:
        self._parts: list[bytes] = []

    def write(self, data: bytes, /) -> int:
        self._parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    def take(self) -> bytes:
        data = b"".join(self._parts)
        self._parts.clear()
        return data


def stream_zip(
    p: Plan, storage: ObjectStorage, open_session: Callable[[], Session]
) -> Iterator[bytes]:
    """The export ZIP, produced while it is sent. Metadata is read in its own database session,
    since the request's session may already be closed while the file is still streaming."""
    sink = _Sink()
    with_audio = p.content in ("audio", "both")
    with_meta = p.content in ("metadata", "both")
    manifest = io.StringIO()
    writer = csv.writer(manifest)
    writer.writerow(
        [
            "task_code",
            "recording_id",
            "audio_file",
            "audio_sha256",
            "duration_seconds",
            "metadata_file",
            "consent_file",
        ]
    )
    zf = zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=1)
    with open_session() as db:
        for e in p.entries:
            stem = f"{e.task_code}_{str(e.recording_id)[:8]}"
            audio_name = meta_name = consent_name = ""
            if with_audio and e.audio_key:
                audio_name = f"audio/{stem}.wav"
                with zf.open(
                    zipfile.ZipInfo(audio_name, _zip_time()), "w", force_zip64=True
                ) as dest:
                    for part in storage.iter_bytes(e.audio_key):
                        dest.write(part)
                        chunk = sink.take()
                        if chunk:
                            yield chunk
            if with_meta:
                rec = db.get(Recording, e.recording_id)
                task = db.get(Task, e.task_id)
                project = db.get(Project, p.project.id)
                if rec is not None and task is not None and project is not None:
                    meta_name = f"metadata/{stem}.json"
                    body = json.dumps(
                        audio_qc.metadata_body(db, rec, task, project), indent=2
                    ).encode()
                    zf.writestr(zipfile.ZipInfo(meta_name, _zip_time()), body)
                    consent_name = f"consent/{stem}.html"
                    html = consent_form.render(db, rec, task, project).encode()
                    zf.writestr(zipfile.ZipInfo(consent_name, _zip_time()), html)
            writer.writerow(
                [
                    _safe_cell(v)
                    for v in (
                        e.task_code,
                        e.recording_id,
                        audio_name,
                        e.audio_sha256 if audio_name else "",
                        round((e.duration_ms or 0) / 1000, 1) if e.duration_ms else "",
                        meta_name,
                        consent_name,
                    )
                ]
            )
            chunk = sink.take()
            if chunk:
                yield chunk
    zf.writestr(zipfile.ZipInfo("manifest.csv", _zip_time()), manifest.getvalue().encode())
    zf.close()
    yield sink.take()


def _zip_time() -> tuple[int, int, int, int, int, int]:
    now = datetime.now(UTC)
    return (now.year, now.month, now.day, now.hour, now.minute, now.second)
