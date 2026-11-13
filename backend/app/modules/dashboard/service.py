"""Progress and operations dashboard (DASH-001..006, owner 2026-11-10).

One read-only summary, shaped by who asks:

- client  (no tasks.view, e.g. Client Viewer): progress only - hours collected and approved, against
  the project's daily targets, per mode and per day. No people, no queues, no personal data.
- worker  (tasks.view without tasks.assign, e.g. Moderator, QC Executive): their own work only
  (tasks assigned to them and recordings they made), with no project targets.
- manager (Super Admin, or tasks.assign in the project, e.g. Project Admin): the whole project plus
  the operational picture - tasks by status, queues that need attention, output per moderator and
  storage used.

Scope is the caller's projects (all for a Super Admin); a project the caller cannot see answers 404,
exactly like a project that does not exist. Hours come from each ready recording's final file (the
mono face-to-face WAV or the stereo telephony WAV), counted once per recording, and stay counted
after retention deletes the file. Days are calendar days in REPORT_TIMEZONE (IST by default).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audio_qc.models import AudioQcResult
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task, TaskAssignment

View = Literal["client", "worker", "manager"]

FINAL_KINDS = ("FTF_DERIVED_PCM", "TELEPHONY_DERIVED_PCM", "TELEPHONY_FINAL_STEREO")
MODES = ("FACE_TO_FACE", "TELEPHONY")
MAX_PROJECTS = 200  # the project picker; a Super Admin with more narrows by project
MAX_TEAM = 25  # busiest moderators shown to managers
STALE_UPLOAD = timedelta(hours=2)  # a recording still "recording" after this needs a look


@dataclass
class ModeTotals:
    mode: str
    recorded_hours: float = 0.0
    approved_hours: float = 0.0
    recordings: int = 0
    target_hours_per_day: float = 0.0


@dataclass
class Day:
    day: date
    recorded_hours: float = 0.0
    approved_hours: float = 0.0


@dataclass
class Summary:
    view: View
    timezone: str
    project_id: uuid.UUID | None
    projects: list[dict[str, Any]]
    recorded_hours: float
    approved_hours: float
    recordings: int
    target_hours_per_day: float
    today_hours: float
    by_mode: list[ModeTotals]
    daily: list[Day]
    tasks_total: int
    tasks_approved: int
    tasks_by_status: dict[str, int] | None = None
    queues: dict[str, int] | None = None
    team: list[dict[str, Any]] | None = None
    storage_bytes: int | None = None
    qc: dict[str, int] | None = field(default=None)


def _view(principal: Principal, project_ids: list[uuid.UUID]) -> View:
    if principal.is_super_admin:
        return "manager"
    if not principal.can(Perm.TASKS_VIEW):
        return "client"
    if principal.can(Perm.TASKS_ASSIGN) and project_ids:
        return "manager"
    return "worker"


def _hours(ms: Any) -> float:
    return round(float(ms or 0) / 3_600_000, 2)


def summary(
    db: Session,
    principal: Principal,
    *,
    project_id: uuid.UUID | None,
    days: int,
    timezone: str,
) -> Summary:
    if not principal.can(Perm.DASHBOARD_VIEW):
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    projects_q = select(Project.id, Project.code, Project.name).order_by(Project.code)
    if not principal.is_super_admin:
        projects_q = projects_q.where(Project.id.in_(principal.project_ids or [uuid.UUID(int=0)]))
    projects = [
        {"id": r.id, "code": r.code, "name": r.name}
        for r in db.execute(projects_q.limit(MAX_PROJECTS))
    ]
    if project_id is not None:
        visible = principal.is_super_admin or project_id in principal.project_ids
        if not visible or db.get(Project, project_id) is None:
            raise AppError("Item not found", code="NOT_FOUND", status_code=404)
        scope = [project_id]
    elif principal.is_super_admin:
        scope = None  # every project
    else:
        scope = list(principal.project_ids) or [uuid.UUID(int=0)]
    view = _view(principal, scope or [])

    def in_scope(query: Any) -> Any:  # any Select over tasks (row types vary)
        query = query.where(Task.project_id.in_(scope)) if scope is not None else query
        if view == "worker":
            mine = exists().where(
                TaskAssignment.task_id == Task.id,
                TaskAssignment.user_id == principal.user_id,
                TaskAssignment.active.is_(True),
            )
            query = query.where(or_(mine, Recording.created_by == principal.user_id))
        return query

    tz = ZoneInfo(timezone)
    today = datetime.now(UTC).astimezone(tz).date()
    first_day = today - timedelta(days=days - 1)
    final = (
        select(AudioAsset.recording_id, func.max(AudioAsset.duration_ms).label("ms"))
        .where(AudioAsset.kind.in_(FINAL_KINDS))
        .group_by(AudioAsset.recording_id)
        .subquery()
    )
    approved = Task.status == "APPROVED"
    day = func.date(func.timezone(timezone, Recording.started_at)).label("day")
    base = (
        select(
            Recording.mode,
            func.sum(final.c.ms).label("ms"),
            func.sum(case((approved, final.c.ms), else_=0)).label("approved_ms"),
            func.count().label("n"),
        )
        .join(final, final.c.recording_id == Recording.id)
        .join(Task, Task.id == Recording.task_id)
        .where(Recording.state == "READY")
    )
    by_mode = {m: ModeTotals(m) for m in MODES}
    for row in db.execute(in_scope(base.group_by(Recording.mode))):
        t = by_mode[row.mode]
        t.recorded_hours, t.approved_hours, t.recordings = (
            _hours(row.ms),
            _hours(row.approved_ms),
            int(row.n),
        )
    series = {
        first_day + timedelta(days=i): Day(first_day + timedelta(days=i)) for i in range(days)
    }
    window_start = datetime.combine(first_day, datetime.min.time(), tz)
    for row in db.execute(
        in_scope(
            base.add_columns(day)
            .where(Recording.started_at >= window_start)
            .group_by(Recording.mode, day)
        )
    ):
        if row.day in series:
            series[row.day].recorded_hours = round(
                series[row.day].recorded_hours + _hours(row.ms), 2
            )
            series[row.day].approved_hours = round(
                series[row.day].approved_hours + _hours(row.approved_ms), 2
            )

    # Daily targets: the projects' own targets for the modes they allow.
    targets_q = select(
        func.coalesce(
            func.sum(
                case((Project.allows_face_to_face, Project.target_face_to_face_hours_per_day))
            ),
            0,
        ),
        func.coalesce(
            func.sum(case((Project.allows_telephony, Project.target_telephony_hours_per_day))), 0
        ),
    )
    if scope is not None:
        targets_q = targets_q.where(Project.id.in_(scope))
    ftf_target, tel_target = db.execute(targets_q).one()
    if view != "worker":
        # Moderators and QC see their own work only, never the project's targets (owner
        # 2026-11-11: "QC do not require project progress, only their work progress").
        by_mode["FACE_TO_FACE"].target_hours_per_day = float(ftf_target or 0)
        by_mode["TELEPHONY"].target_hours_per_day = float(tel_target or 0)

    status_q = in_scope(
        select(Task.status, func.count(func.distinct(Task.id)))
        .select_from(Task)
        .outerjoin(Recording, Recording.task_id == Task.id)
        .group_by(Task.status)
    )
    statuses = {s: int(n) for s, n in db.execute(status_q)}
    result = Summary(
        view=view,
        timezone=timezone,
        project_id=project_id,
        projects=projects,
        recorded_hours=round(sum(t.recorded_hours for t in by_mode.values()), 2),
        approved_hours=round(sum(t.approved_hours for t in by_mode.values()), 2),
        recordings=sum(t.recordings for t in by_mode.values()),
        target_hours_per_day=sum(t.target_hours_per_day for t in by_mode.values()),
        today_hours=series[today].recorded_hours,
        by_mode=list(by_mode.values()),
        daily=list(series.values()),
        tasks_total=sum(statuses.values()),
        tasks_approved=statuses.get("APPROVED", 0),
    )
    if view == "client":
        return result
    result.tasks_by_status = statuses
    result.qc = {
        "passed": statuses.get("APPROVED", 0),
        "rejected": statuses.get("REJECTED", 0),
        "returned": statuses.get("RETURNED", 0),
        "waiting": statuses.get("AUDIO_QC", 0),
    }
    # What the automatic check said about the recordings now waiting for a QC decision (D-079).
    latest_auto = in_scope(
        select(AudioQcResult.task_id, AudioQcResult.outcome)
        .select_from(AudioQcResult)
        .join(Task, Task.id == AudioQcResult.task_id)
        .join(Recording, Recording.id == AudioQcResult.recording_id)
        .where(Task.status == "AUDIO_QC", AudioQcResult.automated.is_(True))
        .distinct(AudioQcResult.task_id)
        .order_by(AudioQcResult.task_id, AudioQcResult.created_at.desc())
    ).subquery()
    automatic = {
        outcome: int(n)
        for outcome, n in db.execute(
            select(latest_auto.c.outcome, func.count()).group_by(latest_auto.c.outcome)
        )
    }
    result.qc.update(
        {
            "auto_pass": automatic.get("PASS", 0),
            "auto_review": automatic.get("NEEDS_REVIEW", 0),
            "auto_fail": automatic.get("FAIL", 0),
        }
    )
    if view != "manager":
        return result

    stale_before = datetime.now(UTC) - STALE_UPLOAD
    queue_q = in_scope(
        select(
            func.count().filter(Recording.state.in_(("UPLOADED", "PROCESSING"))),
            func.count().filter(Recording.state == "FAILED"),
            func.count().filter(Recording.state == "INTERRUPTED"),
            func.count().filter(
                and_(Recording.state == "RECORDING", Recording.updated_at < stale_before)
            ),
        )
        .select_from(Recording)
        .join(Task, Task.id == Recording.task_id)
    )
    processing, failed, interrupted, stale = db.execute(queue_q).one()
    result.queues = {
        "waiting_for_qc": statuses.get("AUDIO_QC", 0),
        "processing": int(processing),
        "failed_processing": int(failed),
        "interrupted": int(interrupted),
        "stale_uploads": int(stale),
        "on_hold": statuses.get("ON_HOLD", 0),
    }
    team_q = in_scope(
        select(User.display_name, func.count().label("n"), func.sum(final.c.ms).label("ms"))
        .select_from(Recording)
        .join(final, final.c.recording_id == Recording.id)
        .join(Task, Task.id == Recording.task_id)
        .join(User, User.id == Recording.created_by)
        .where(Recording.state == "READY")
        .group_by(User.id, User.display_name)
        .order_by(func.sum(final.c.ms).desc())
        .limit(MAX_TEAM)
    )
    result.team = [
        {"name": r.display_name, "recordings": int(r.n), "recorded_hours": _hours(r.ms)}
        for r in db.execute(team_q)
    ]
    storage_q = select(func.coalesce(func.sum(AudioAsset.size_bytes), 0)).where(
        AudioAsset.deleted_at.is_(None)
    )
    if scope is not None:
        storage_q = storage_q.where(AudioAsset.project_id.in_(scope))
    result.storage_bytes = int(db.scalar(storage_q) or 0)
    return result
