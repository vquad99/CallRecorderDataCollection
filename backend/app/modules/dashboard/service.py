"""Progress and operations dashboard (DASH-001..006, owner 2026-11-10).

One read-only summary, shaped by who asks:

- client  (no tasks.view, e.g. Client Viewer): progress only - hours collected and approved, against
  the project's daily targets, per mode and per day. No people, no queues, no personal data.
- worker  (tasks.view without tasks.assign, e.g. Moderator, QC Executive): their own work only
  (tasks assigned to them and recordings they made), with no project targets.
- manager (Super Admin, or tasks.assign in the project, e.g. Project Admin): the whole project plus
  the operational picture - tasks by status, queues that need attention, output per moderator and
  storage used, and the phone calls (placed, recorded, failed, waiting for a person).

Filters (DASH-002): project, recording mode, language, dialect, task status, staff (managers
only: a person's assigned tasks and the recordings they made) and days. Without chosen days the
totals count everything and the per-day series shows the last N days, as before; with a first
and last day, every figure counts only recordings started on those days (tasks: created on
them) and the series shows exactly those days. The answer also lists what can be chosen.

Scope is the caller's projects (all for a Super Admin); a project the caller cannot see answers 404,
exactly like a project that does not exist. Hours come from each task's current recording (its
newest finished one, D-135: the one QC checks, an export delivers and the Progress tab counts), from
its final file (the mono face-to-face WAV or the stereo telephony WAV), and stay counted after
retention deletes the file. A take the moderator replaced with Record again or Call again is not
counted, except in the moderators' output, which shows every finished take they made. Days are
calendar days in REPORT_TIMEZONE (IST by default).

Daily targets are the projects' own: of the chosen project, or else of every live (ACTIVE)
project in view; a paused, finished or archived project's target is not today's work.

Effective speech (D-148) is shown next to the hours: the time someone speaks in those recordings.
Completed hours follow each project's `progress_counts`: the approved recordings' effective speech
(EFFECTIVE) or their full length (FULL); over several projects, each adds its own. A recording
whose effective speech is not measured yet counts as none (`effective_pending` says how many).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, exists, func, or_, select, union_all
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.days import check_days, day_bounds
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm
from app.modules.audio_qc.models import AudioQcResult
from app.modules.auth.deps import Principal, in_projects
from app.modules.auth.models import User
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from app.modules.recordings.models import (
    AudioAsset,
    Recording,
    current_recordings,
    current_recordings_query,
    final_length_subquery,
)
from app.modules.tasks.models import TASK_STATUSES, Task, TaskAssignment
from app.modules.telephony.models import Call

View = Literal["client", "worker", "manager"]

MODES = ("FACE_TO_FACE", "TELEPHONY")
MAX_PROJECTS = 200  # the project picker; a Super Admin with more narrows by project
MAX_TEAM = 25  # busiest moderators shown to managers
STALE_UPLOAD = timedelta(hours=2)  # a recording still "recording" after this needs a look
MAX_RANGE_DAYS = 366  # the longest span of chosen days
MAX_OPTIONS = 200  # entries in a filter's list


@dataclass(frozen=True)
class Filters:
    mode: str | None = None
    language: str | None = None
    dialect: str | None = None
    district: str | None = None
    status: str | None = None
    staff_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class ModeTotals:
    mode: str
    recorded_hours: float = 0.0
    approved_hours: float = 0.0
    effective_hours: float = 0.0
    approved_effective_hours: float = 0.0
    completed_hours: float = 0.0
    recordings: int = 0
    target_hours_per_day: float = 0.0
    effective_pending: int = 0


@dataclass
class Day:
    day: date
    recorded_hours: float = 0.0
    approved_hours: float = 0.0
    completed_hours: float = 0.0


@dataclass
class Summary:
    view: View
    timezone: str
    project_id: uuid.UUID | None
    projects: list[dict[str, Any]]
    recorded_hours: float
    approved_hours: float
    effective_hours: float
    approved_effective_hours: float
    completed_hours: float
    effective_pending: int
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
    # Phone calls, for managers: placed, recorded, could not be placed, waiting for a person.
    calls: dict[str, int] | None = None
    # What can be chosen in the filters: languages and dialects spoken in these projects,
    # and (managers) the people who work on their tasks.
    options: dict[str, Any] = field(default_factory=dict)
    date_from: date | None = None
    date_to: date | None = None


def _view(principal: Principal) -> View:
    if principal.is_super_admin:
        return "manager"
    if not principal.can(Perm.TASKS_VIEW):
        return "client"
    return "manager" if principal.can(Perm.TASKS_ASSIGN) else "worker"


def _hours(ms: Any) -> float:
    return round(float(ms or 0) / 3_600_000, 2)


def summary(
    db: Session,
    principal: Principal,
    *,
    project_id: uuid.UUID | None,
    days: int,
    timezone: str,
    filters: Filters | None = None,
) -> Summary:
    f = filters or Filters()
    if not principal.can(Perm.DASHBOARD_VIEW):
        raise forbidden()
    projects_q = (
        select(Project.id, Project.code, Project.name)
        .where(in_projects(principal, Project.id))
        .order_by(Project.code)
    )
    projects = [
        {"id": r.id, "code": r.code, "name": r.name}
        for r in db.execute(projects_q.limit(MAX_PROJECTS))
    ]
    if project_id is not None:
        visible = principal.is_super_admin or project_id in principal.project_ids
        if not visible or db.get(Project, project_id) is None:
            raise not_found("Item")
        scope = [project_id]
    elif principal.is_super_admin:
        scope = None  # every project
    else:
        scope = sorted(principal.project_ids)
    view = _view(principal)
    if f.mode is not None and f.mode not in MODES:
        raise _invalid("Choose face-to-face or telephony")
    if f.status is not None and f.status not in TASK_STATUSES:
        raise _invalid("That is not a task status")
    if f.staff_id is not None and view != "manager":
        # Other people's work is for those who run the project.
        raise forbidden()

    today = datetime.now(UTC).astimezone(ZoneInfo(timezone)).date()
    chosen_days = f.date_from is not None or f.date_to is not None
    check_days(f.date_from, f.date_to)  # before any arithmetic on them (D-160)
    # Without chosen days: the last N days up to today.
    last_day = f.date_to or today
    first_day = f.date_from or last_day - timedelta(days=days - 1)
    range_start, range_end = day_bounds(first_day, last_day, timezone)
    if chosen_days:
        if (last_day - first_day).days >= MAX_RANGE_DAYS:
            raise _invalid(f"Choose at most {MAX_RANGE_DAYS} days")
        days = (last_day - first_day).days + 1

    # What narrows the tasks themselves: project, mode, status, and who speaks.
    on_task: list[Any] = []
    if scope is not None:
        on_task.append(Task.project_id.in_(scope))
    if f.mode:
        on_task.append(Task.recording_mode == f.mode)
    if f.status:
        on_task.append(Task.status == f.status)
    if f.language or f.dialect or f.district:
        speaks: list[Any] = [Participant.id.in_([Task.participant_a_id, Task.participant_b_id])]
        if f.language:
            speaks.append(Participant.language_code == f.language)
        if f.dialect:
            speaks.append(Participant.dialect == f.dialect)
        if f.district:
            speaks.append(Participant.district == f.district)
        on_task.append(exists().where(*speaks))

    def works_on(user_id: uuid.UUID) -> Any:
        return exists().where(
            TaskAssignment.task_id == Task.id,
            TaskAssignment.user_id == user_id,
            TaskAssignment.active.is_(True),
        )

    def in_scope(query: Any, when: str | None = None) -> Any:
        """Narrows any Select over tasks and recordings (row types vary). `when` says which
        day counts for the chosen days: "recorded" (the recording started) or "created" (the
        task was created); without chosen days nothing is cut by time here."""
        query = query.where(*on_task)
        if view == "worker":
            query = query.where(
                or_(works_on(principal.user_id), Recording.created_by == principal.user_id)
            )
        if f.staff_id is not None:
            query = query.where(or_(works_on(f.staff_id), Recording.created_by == f.staff_id))
        if chosen_days and when == "recorded":
            query = query.where(
                Recording.started_at >= range_start, Recording.started_at < range_end
            )
        if chosen_days and when == "created":
            query = query.where(Task.created_at >= range_start, Task.created_at < range_end)
        return query

    # Lengths of the recordings of the tasks in view only (every task's for a Super Admin's
    # unfiltered view), with their effective speech (D-148), and each task's current recording
    # (D-135): a replaced take is not counted again.
    in_view = select(Task.id).where(*on_task) if on_task else None
    final = final_length_subquery(in_view)
    current = (
        current_recordings(in_view)
        if in_view is not None
        else current_recordings_query().subquery()
    )
    approved = Task.status == "APPROVED"
    # Completed (D-148): each project counts its approved recordings as its `progress_counts`
    # says, effective speech or the full length; a total over several projects adds each
    # project's own completed hours. Effective speech not measured yet counts as none.
    counted = case((Project.progress_counts == "FULL", final.c.ms), else_=final.c.effective_ms)
    day = func.date(func.timezone(timezone, Recording.started_at)).label("day")
    base = (
        select(
            Recording.mode,
            func.sum(final.c.ms).label("ms"),
            func.sum(case((approved, final.c.ms), else_=0)).label("approved_ms"),
            func.sum(final.c.effective_ms).label("effective_ms"),
            func.sum(case((approved, final.c.effective_ms), else_=0)).label("approved_eff_ms"),
            func.sum(case((approved, counted), else_=0)).label("completed_ms"),
            func.count().filter(final.c.effective_ms.is_(None)).label("pending"),
            func.count().label("n"),
        )
        .join(final, final.c.recording_id == Recording.id)
        .join(current, current.c.recording_id == Recording.id)
        .join(Task, Task.id == Recording.task_id)
        .join(Project, Project.id == Task.project_id)
        .where(Recording.state == "READY")
    )
    by_mode = {m: ModeTotals(m) for m in MODES}
    for row in db.execute(in_scope(base.group_by(Recording.mode), "recorded")):
        t = by_mode[row.mode]
        t.recorded_hours, t.approved_hours, t.recordings = (
            _hours(row.ms),
            _hours(row.approved_ms),
            int(row.n),
        )
        t.effective_hours = _hours(row.effective_ms)
        t.approved_effective_hours = _hours(row.approved_eff_ms)
        t.completed_hours = _hours(row.completed_ms)
        t.effective_pending = int(row.pending)
    series = {
        first_day + timedelta(days=i): Day(first_day + timedelta(days=i)) for i in range(days)
    }
    for row in db.execute(
        in_scope(
            base.add_columns(day)
            .where(Recording.started_at >= range_start, Recording.started_at < range_end)
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
            series[row.day].completed_hours = round(
                series[row.day].completed_hours + _hours(row.completed_ms), 2
            )

    # Daily targets: the projects' own targets for the modes they allow; over several projects,
    # the live ones only (a chosen project shows its own, whatever its status).
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
    if project_id is None:
        targets_q = targets_q.where(Project.status == "ACTIVE")
    ftf_target, tel_target = db.execute(targets_q).one()
    if view != "worker":
        # Moderators and QC see their own work only, never the project's targets (owner
        # 2026-11-11: "QC do not require project progress, only their work progress").
        # A target belongs to a project and a mode: one chosen mode leaves the other's out;
        # the other filters do not change it.
        if f.mode in (None, "FACE_TO_FACE"):
            by_mode["FACE_TO_FACE"].target_hours_per_day = float(ftf_target or 0)
        if f.mode in (None, "TELEPHONY"):
            by_mode["TELEPHONY"].target_hours_per_day = float(tel_target or 0)

    status_q = in_scope(
        select(Task.status, func.count(func.distinct(Task.id)))
        .select_from(Task)
        .outerjoin(Recording, Recording.task_id == Task.id)
        .group_by(Task.status),
        "created",
    )
    statuses = {s: int(n) for s, n in db.execute(status_q)}
    result = Summary(
        view=view,
        timezone=timezone,
        project_id=project_id,
        projects=projects,
        recorded_hours=round(sum(t.recorded_hours for t in by_mode.values()), 2),
        approved_hours=round(sum(t.approved_hours for t in by_mode.values()), 2),
        effective_hours=round(sum(t.effective_hours for t in by_mode.values()), 2),
        approved_effective_hours=round(
            sum(t.approved_effective_hours for t in by_mode.values()), 2
        ),
        completed_hours=round(sum(t.completed_hours for t in by_mode.values()), 2),
        effective_pending=sum(t.effective_pending for t in by_mode.values()),
        recordings=sum(t.recordings for t in by_mode.values()),
        target_hours_per_day=sum(t.target_hours_per_day for t in by_mode.values()),
        today_hours=series[today].recorded_hours if today in series else 0.0,
        by_mode=list(by_mode.values()),
        daily=list(series.values()),
        tasks_total=sum(statuses.values()),
        tasks_approved=statuses.get("APPROVED", 0),
        date_from=first_day if chosen_days else None,
        date_to=last_day if chosen_days else None,
    )
    result.options = _options(db, scope, with_staff=view == "manager")
    if view == "client":
        return result
    result.tasks_by_status = statuses
    result.qc = {
        "passed": statuses.get("APPROVED", 0),
        "rejected": statuses.get("REJECTED", 0),
        "waiting": statuses.get("AUDIO_QC", 0),
    }
    # What the automatic check said about the recordings now waiting for a QC decision (D-079).
    latest_auto = in_scope(
        select(AudioQcResult.task_id, AudioQcResult.outcome)
        .select_from(AudioQcResult)
        .join(Task, Task.id == AudioQcResult.task_id)
        .join(Recording, Recording.id == AudioQcResult.recording_id)
        .where(Task.status == "AUDIO_QC", AudioQcResult.automated.is_(True))
        .ext(distinct_on(AudioQcResult.task_id))
        .order_by(AudioQcResult.task_id, AudioQcResult.created_at.desc()),
        "recorded",
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
        .join(Task, Task.id == Recording.task_id),
        "recorded",
    )
    processing, failed, interrupted, stale = db.execute(queue_q).one()
    result.queues = {
        "waiting_for_qc": statuses.get("AUDIO_QC", 0),
        "processing": int(processing),
        "failed_processing": int(failed),
        "interrupted": int(interrupted),
        "stale_uploads": int(stale),
        "on_hold": statuses.get("ON_HOLD", 0),
        # Sent back by QC for a new signed consent form (D-146).
        "consent_forms_to_fix": statuses.get("CONSENT_FIX", 0),
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
        .limit(MAX_TEAM),
        "recorded",
    )
    result.team = [
        {"name": r.display_name, "recordings": int(r.n), "recorded_hours": _hours(r.ms)}
        for r in db.execute(team_q)
    ]
    storage_q = in_scope(
        select(func.coalesce(func.sum(AudioAsset.size_bytes), 0))
        .select_from(AudioAsset)
        .join(Recording, Recording.id == AudioAsset.recording_id)
        .join(Task, Task.id == Recording.task_id)
        .where(AudioAsset.deleted_at.is_(None)),
        "recorded",
    )
    result.storage_bytes = int(db.scalar(storage_q) or 0)

    # Phone calls (DASH-001): by the day they were dialled; a chosen person is the moderator.
    calls_q = (
        select(
            func.count(),
            func.count().filter(Call.state == "RECORDED"),
            func.count().filter(Call.state == "DIAL_FAILED"),
            func.count().filter(Call.state.in_(("NEEDS_MATCH", "FETCH_FAILED"))),
            func.count().filter(Call.state.in_(("DIALLING", "WAITING_FOR_RECORDING"))),
        )
        .select_from(Call)
        .join(Task, Task.id == Call.task_id)
        .where(*on_task)
    )
    if f.staff_id is not None:
        calls_q = calls_q.where(Call.moderator_id == f.staff_id)
    if chosen_days:
        calls_q = calls_q.where(Call.dialled_at >= range_start, Call.dialled_at < range_end)
    placed, recorded, dial_failed, needs_person, open_calls = db.execute(calls_q).one()
    result.calls = {
        "placed": int(placed),
        "recorded": int(recorded),
        "could_not_be_placed": int(dial_failed),
        "needs_a_person": int(needs_person),
        "open": int(open_calls),
    }
    return result


def _invalid(message: str) -> AppError:
    return AppError(message, code="VALIDATION_ERROR", status_code=422)


def _options(db: Session, scope: list[uuid.UUID] | None, *, with_staff: bool) -> dict[str, Any]:
    """What the filters offer: the languages and dialects of the people on these projects'
    tasks, and, for managers, the staff on those tasks."""
    in_projects = [Task.project_id.in_(scope)] if scope is not None else []
    # Each task's two people as one list, read once: joining the tasks on IN (a, b) instead
    # probes the participants twice for every task.
    speakers = union_all(
        select(Task.participant_a_id.label("pid")).where(*in_projects),
        select(Task.participant_b_id.label("pid")).where(*in_projects),
    ).subquery()
    spoken = db.execute(
        select(Participant.language_code, Participant.dialect, Participant.district)
        .where(Participant.id.in_(select(speakers.c.pid)))
        .distinct()
        .limit(MAX_OPTIONS * 2)
    ).all()
    options: dict[str, Any] = {
        "languages": sorted({code for code, _, _ in spoken})[:MAX_OPTIONS],
        "dialects": sorted({dialect for _, dialect, _ in spoken if dialect})[:MAX_OPTIONS],
        # D-121: the districts of the people on these tasks.
        "districts": sorted({district for _, _, district in spoken if district})[:MAX_OPTIONS],
    }
    if with_staff:
        staff = db.execute(
            select(User.id, User.display_name)
            .join(TaskAssignment, TaskAssignment.user_id == User.id)
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(TaskAssignment.active.is_(True), *in_projects)
            .distinct()
            .order_by(User.display_name)
            .limit(MAX_OPTIONS)
        ).all()
        options["staff"] = [{"id": uid, "name": name} for uid, name in staff]
    return options
