"""Phone-call analytics, the list of every call and its CSV (D-101, D-102, D-103).

Who sees what (D-104):
- Figures and the CSV: people who assign tasks only. Super Admin: every project; Project Admin:
  the projects they manage.
- The list of calls: the same people for their projects; everyone else who can see tasks
  (moderators): their own calls, in projects they belong to, and nothing else.

Figures come from the platform's own call records, so they are exact for calls made here. The
provider's own traffic figure (calls per hour of the day) comes from TxContact's recording service
and is shown only when TxContact answers.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audio_qc.models import AudioQcResult
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task, TaskAssignment
from app.modules.telephony.models import CHECKLIST_ITEMS, Call
from app.modules.telephony.service import checklist_of, mask

MAX_DAYS = 90
# Calls read for one analytics request; a period with more is cut at the newest (and says so).
MAX_CALLS = 50_000
MAX_CSV_ROWS = 20_000
# A call is counted as needing a person in these states.
NEEDS_PERSON = ("NEEDS_MATCH", "FETCH_FAILED")
CLOSED_BY_MODERATOR = ("WAITING_FOR_RECORDING", "NEEDS_MATCH", "FETCH_FAILED", "RECORDED")
REACHED_QC = ("AUDIO_QC", "ADMIN_REVIEW", "APPROVED", "REJECTED", "RETURNED")
DELIVERY_KIND = "TELEPHONY_DERIVED_PCM"


def _check(principal: Principal) -> None:
    if not principal.can(Perm.TASKS_VIEW):
        raise forbidden()


def _check_manager(principal: Principal) -> None:
    """Figures and the spreadsheet are for people who assign tasks (D-104)."""
    if not principal.can(Perm.TASKS_ASSIGN):
        raise forbidden()


def _managed(principal: Principal) -> list[uuid.UUID]:
    return [p for p in principal.project_ids if principal.can_in_project(Perm.TASKS_ASSIGN, p)]


def _visible_project(principal: Principal, project_id: uuid.UUID | None) -> None:
    if project_id is None or principal.is_super_admin:
        return
    if project_id not in principal.project_ids:
        raise AppError("Project not found", code="NOT_FOUND", status_code=404)


def _call_scope(principal: Principal, project_id: uuid.UUID | None) -> list[ColumnElement[bool]]:
    """Conditions limiting a query on Call to what this person may see."""
    _visible_project(principal, project_id)
    conditions: list[ColumnElement[bool]] = []
    if project_id is not None:
        conditions.append(Call.project_id == project_id)
    if principal.is_super_admin:
        return conditions
    own = and_(
        Call.moderator_id == principal.user_id,
        Call.project_id.in_(list(principal.project_ids) or [uuid.UUID(int=0)]),
    )
    managed = _managed(principal)
    conditions.append(or_(Call.project_id.in_(managed), own) if managed else own)
    return conditions


def _stale_before(settings: Settings, now: datetime) -> datetime:
    """A call still "on the call" from before this moment was left open: no call lasts longer
    than the longest recording allowed."""
    return now - timedelta(seconds=settings.max_recording_seconds)


@dataclass
class Day:
    day: str
    calls: int = 0
    recorded: int = 0
    failed: int = 0  # could not be placed, or cancelled
    open: int = 0  # still on the call, being fetched, or waiting for a person
    recorded_minutes: float = 0.0


@dataclass
class _Group:
    calls: int = 0
    recorded: int = 0
    failed: int = 0
    recorded_ms: int = 0
    call_minutes: list[float] = field(default_factory=list)


@dataclass
class Analytics:
    days: int
    truncated: bool
    calls: int
    in_call: int
    stale_calls: int
    recorded: int
    dial_failed: int
    cancelled: int
    waiting_for_recording: int
    needs_person: int
    success_pct: float | None
    avg_call_minutes: float | None
    avg_fetch_minutes: float | None
    recorded_minutes: float
    today_recorded_minutes: float
    target_minutes_per_day: float | None
    funnel: dict[str, int]
    tasks_called: int
    tasks_called_again: int
    calls_per_task: float | None
    tasks_by_status: dict[str, int]
    tasks_not_called: int
    automatic_checks: dict[str, int]
    qc_decisions: dict[str, int]
    checklist: dict[str, int]
    by_day: list[Day]
    by_hour: list[int]  # calls started in each hour of the day, report time zone
    by_moderator: list[dict[str, Any]]
    by_project: list[dict[str, Any]]
    cancel_reasons: dict[str, int]
    problems: dict[str, int]  # failure codes of calls that did not end recorded


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def analytics(
    db: Session,
    principal: Principal,
    settings: Settings,
    *,
    project_id: uuid.UUID | None,
    days: int,
    now: datetime | None = None,
) -> Analytics:
    _check_manager(principal)
    days = max(1, min(MAX_DAYS, days))
    tz = ZoneInfo(settings.report_timezone)
    now = now or datetime.now(UTC)
    today = now.astimezone(tz).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=tz)
    scope = [*_call_scope(principal, project_id), Call.dialled_at >= since]
    calls = list(
        db.scalars(select(Call).where(*scope).order_by(Call.dialled_at.desc()).limit(MAX_CALLS + 1))
    )
    truncated = len(calls) > MAX_CALLS
    calls = calls[:MAX_CALLS]

    # Facts about the recordings and tasks behind these calls: one query each, joined on the
    # same conditions, never a list of ids.
    length_ms = {
        cid: int(ms or 0)
        for cid, ms in db.execute(
            select(Call.id, func.max(AudioAsset.duration_ms))
            .join(AudioAsset, AudioAsset.recording_id == Call.recording_id)
            .where(*scope, AudioAsset.kind == DELIVERY_KIND)
            .group_by(Call.id)
        ).all()
    }
    stored_at = {
        cid: created
        for cid, created in db.execute(
            select(Call.id, Recording.created_at)
            .join(Recording, Recording.id == Call.recording_id)
            .where(*scope)
        ).all()
    }
    task_status = {
        tid: status
        for tid, status in db.execute(
            select(Call.task_id, Task.status).join(Task, Task.id == Call.task_id).where(*scope)
        ).all()
    }
    automatic: dict[uuid.UUID, str] = {}
    decided: dict[uuid.UUID, str] = {}
    for recording_id, automated, outcome in db.execute(
        select(AudioQcResult.recording_id, AudioQcResult.automated, AudioQcResult.outcome)
        .join(Call, Call.recording_id == AudioQcResult.recording_id)
        .where(*scope)
        .order_by(AudioQcResult.created_at)
    ).all():
        (automatic if automated else decided)[recording_id] = outcome  # the newest wins

    stale_before = _stale_before(settings, now)
    by_day = {
        (first_day + timedelta(days=i)).isoformat(): Day(
            (first_day + timedelta(days=i)).isoformat()
        )
        for i in range(days)
    }
    by_hour = [0] * 24
    states: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    problems: Counter[str] = Counter()
    ticks: Counter[str] = Counter()
    per_task: Counter[uuid.UUID] = Counter()
    people: dict[uuid.UUID, _Group] = {}
    projects: dict[uuid.UUID, _Group] = {}
    call_minutes: list[float] = []
    fetch_minutes: list[float] = []
    recorded_ms = today_ms = stale = 0
    for c in calls:
        local = c.dialled_at.astimezone(tz)
        states[c.state] += 1
        by_hour[local.hour] += 1
        per_task[c.task_id] += 1
        person = people.setdefault(c.moderator_id, _Group())
        project = projects.setdefault(c.project_id, _Group())
        d = by_day.get(local.date().isoformat())
        failed = c.state in ("DIAL_FAILED", "CANCELLED")
        ms = length_ms.get(c.id, 0) if c.state == "RECORDED" else 0
        if c.state == "DIALLING" and c.dialled_at < stale_before:
            stale += 1
        for group in (person, project):
            group.calls += 1
            group.recorded += c.state == "RECORDED"
            group.failed += failed
            group.recorded_ms += ms
        if d is not None:
            d.calls += 1
            if c.state == "RECORDED":
                d.recorded += 1
                d.recorded_minutes = round(d.recorded_minutes + ms / 60000, 2)
            elif failed:
                d.failed += 1
            else:
                d.open += 1
        recorded_ms += ms
        if local.date() == today:
            today_ms += ms
        if c.cancel_reason:
            reasons[c.cancel_reason] += 1
        if c.failure_code and c.state != "RECORDED":
            problems[c.failure_code] += 1
        if c.state in CLOSED_BY_MODERATOR and c.closed_at is not None:
            minutes = (c.closed_at - c.dialled_at).total_seconds() / 60
            call_minutes.append(minutes)
            person.call_minutes.append(minutes)
            for item in checklist_of(c):
                ticks[item] += 1
        created = stored_at.get(c.id)
        if created is not None and c.closed_at is not None:
            fetch_minutes.append(max(0.0, (created - c.closed_at).total_seconds() / 60))

    names = (
        {
            uid: name
            for uid, name in db.execute(
                select(User.id, User.display_name).where(User.id.in_(list(people)))
            ).all()
        }
        if people
        else {}
    )
    codes = (
        {
            pid: (code, name)
            for pid, code, name in db.execute(
                select(Project.id, Project.code, Project.name).where(Project.id.in_(list(projects)))
            ).all()
        }
        if projects
        else {}
    )
    recorded_tasks = {c.task_id for c in calls if c.state == "RECORDED"}
    total = len(calls)
    closed = sum(states[s] for s in CLOSED_BY_MODERATOR)
    return Analytics(
        days=days,
        truncated=truncated,
        calls=total,
        in_call=states["DIALLING"] - stale,
        stale_calls=stale,
        recorded=states["RECORDED"],
        dial_failed=states["DIAL_FAILED"],
        cancelled=states["CANCELLED"],
        waiting_for_recording=states["WAITING_FOR_RECORDING"],
        needs_person=sum(states[s] for s in NEEDS_PERSON) + stale,
        success_pct=round(100 * states["RECORDED"] / total, 1) if total else None,
        avg_call_minutes=_avg(call_minutes),
        avg_fetch_minutes=_avg(fetch_minutes),
        recorded_minutes=round(recorded_ms / 60000, 1),
        today_recorded_minutes=round(today_ms / 60000, 1),
        target_minutes_per_day=_target_minutes(db, principal, project_id),
        funnel={
            "dialled": total,
            "accepted": total - states["DIAL_FAILED"],
            "closed": closed,
            "recorded": states["RECORDED"],
            "sent_to_qc": sum(1 for t in recorded_tasks if task_status.get(t) in REACHED_QC),
            "approved": sum(1 for t in recorded_tasks if task_status.get(t) == "APPROVED"),
        },
        tasks_called=len(per_task),
        tasks_called_again=sum(1 for n in per_task.values() if n > 1),
        calls_per_task=round(total / len(per_task), 1) if per_task else None,
        tasks_by_status=_tasks_by_status(db, principal, project_id),
        tasks_not_called=_tasks_not_called(db, principal, project_id),
        automatic_checks=dict(Counter(automatic.values()).most_common()),
        qc_decisions=dict(Counter(decided.values()).most_common()),
        checklist={item: ticks[item] for item in CHECKLIST_ITEMS} | {"closed_calls": closed},
        by_day=list(by_day.values()),
        by_hour=by_hour,
        by_moderator=sorted(
            (
                {
                    "moderator_id": uid,
                    "name": names.get(uid) or "Unknown",
                    "calls": g.calls,
                    "recorded": g.recorded,
                    "failed": g.failed,
                    "recorded_minutes": round(g.recorded_ms / 60000, 1),
                    "avg_call_minutes": _avg(g.call_minutes),
                }
                for uid, g in people.items()
            ),
            key=lambda r: (-int(str(r["calls"])), str(r["name"])),
        ),
        by_project=sorted(
            (
                {
                    "project_id": pid,
                    "code": codes.get(pid, ("", ""))[0],
                    "name": codes.get(pid, ("", ""))[1],
                    "calls": g.calls,
                    "recorded": g.recorded,
                    "failed": g.failed,
                    "recorded_minutes": round(g.recorded_ms / 60000, 1),
                }
                for pid, g in projects.items()
            ),
            key=lambda r: (-int(str(r["calls"])), str(r["code"])),
        ),
        cancel_reasons=dict(reasons.most_common()),
        problems=dict(problems.most_common()),
    )


def _target_minutes(
    db: Session, principal: Principal, project_id: uuid.UUID | None
) -> float | None:
    """The telephony target for a day, in minutes, for the projects this person manages. None
    for people who only see their own calls: a project's target is not theirs alone."""
    if principal.is_super_admin:
        condition: ColumnElement[bool] = Project.status == "ACTIVE"
    else:
        managed = _managed(principal)
        if not managed:
            return None
        condition = Project.id.in_(managed)
    query = select(func.coalesce(func.sum(Project.target_telephony_hours_per_day), 0)).where(
        condition, Project.allows_telephony.is_(True)
    )
    if project_id is not None:
        query = query.where(Project.id == project_id)
    return round(float(db.scalar(query) or 0) * 60, 1)


def _task_scope(principal: Principal, project_id: uuid.UUID | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Task.recording_mode == "TELEPHONY"]
    if project_id is not None:
        conditions.append(Task.project_id == project_id)
    if principal.is_super_admin:
        return conditions
    mine = and_(
        Task.project_id.in_(list(principal.project_ids) or [uuid.UUID(int=0)]),
        exists().where(
            TaskAssignment.task_id == Task.id,
            TaskAssignment.role_code == "MODERATOR",
            TaskAssignment.active.is_(True),
            TaskAssignment.user_id == principal.user_id,
        ),
    )
    managed = _managed(principal)
    conditions.append(or_(Task.project_id.in_(managed), mine) if managed else mine)
    return conditions


def _tasks_by_status(
    db: Session, principal: Principal, project_id: uuid.UUID | None
) -> dict[str, int]:
    rows = db.execute(
        select(Task.status, func.count())
        .where(*_task_scope(principal, project_id))
        .group_by(Task.status)
    ).all()
    return {status: int(n) for status, n in sorted(rows, key=lambda r: -int(r[1]))}


def _tasks_not_called(db: Session, principal: Principal, project_id: uuid.UUID | None) -> int:
    """Phone tasks given to a moderator, or started, that nobody has called yet."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                *_task_scope(principal, project_id),
                Task.status.in_(("ASSIGNED", "IN_PROGRESS")),
                ~exists().where(Call.task_id == Task.id),
            )
        )
        or 0
    )


@dataclass
class CallRow:
    call: Call
    task_code: str
    project_code: str
    moderator_name: str
    stale: bool
    recording_seconds: float | None = None


def _rows(db: Session, calls: list[Call], stale_before: datetime) -> list[CallRow]:
    if not calls:
        return []
    tasks = {
        tid: code
        for tid, code in db.execute(
            select(Task.id, Task.task_code).where(Task.id.in_({c.task_id for c in calls}))
        ).all()
    }
    projects = {
        pid: code
        for pid, code in db.execute(
            select(Project.id, Project.code).where(Project.id.in_({c.project_id for c in calls}))
        ).all()
    }
    names = {
        uid: name
        for uid, name in db.execute(
            select(User.id, User.display_name).where(User.id.in_({c.moderator_id for c in calls}))
        ).all()
    }
    recording_ids = {c.recording_id for c in calls if c.recording_id is not None}
    lengths = (
        {
            rid: int(ms or 0)
            for rid, ms in db.execute(
                select(AudioAsset.recording_id, func.max(AudioAsset.duration_ms))
                .where(AudioAsset.recording_id.in_(recording_ids), AudioAsset.kind == DELIVERY_KIND)
                .group_by(AudioAsset.recording_id)
            ).all()
        }
        if recording_ids
        else {}
    )
    return [
        CallRow(
            c,
            tasks.get(c.task_id, ""),
            projects.get(c.project_id, ""),
            names.get(c.moderator_id, ""),
            c.state == "DIALLING" and c.dialled_at < stale_before,
            round(lengths[c.recording_id] / 1000, 1)
            if c.recording_id is not None and c.recording_id in lengths
            else None,
        )
        for c in calls
    ]


def _state_filter(state: str | None, stale_before: datetime) -> list[ColumnElement[bool]]:
    if state == "NEEDS_PERSON":
        return [
            or_(
                Call.state.in_(NEEDS_PERSON),
                and_(Call.state == "DIALLING", Call.dialled_at < stale_before),
            )
        ]
    return [Call.state == state] if state else []


def list_calls(
    db: Session,
    principal: Principal,
    settings: Settings,
    *,
    project_id: uuid.UUID | None,
    state: str | None,
    page: int,
    page_size: int,
) -> tuple[list[CallRow], int]:
    _check(principal)
    stale_before = _stale_before(settings, datetime.now(UTC))
    conditions = [*_call_scope(principal, project_id), *_state_filter(state, stale_before)]
    total = int(db.scalar(select(func.count()).select_from(Call).where(*conditions)) or 0)
    query: Select[Any] = (
        select(Call)
        .where(*conditions)
        .order_by(Call.dialled_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return _rows(db, list(db.scalars(query)), stale_before), total


CSV_COLUMNS = (
    "started",
    "closed",
    "project",
    "task",
    "moderator",
    "agent_seat",
    "number_ends_in",
    "state",
    "cancel_reason",
    "problem",
    "call_seconds",
    "recording_seconds",
    "a_joined",
    "b_joined",
    "moderator_muted",
    "quality_ok",
    "provider",
    "provider_reference",
    "provider_call",
    "tries_to_fetch",
    "note",
)


def _cell(value: object) -> str:
    """A cell a spreadsheet will not run as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def calls_csv(
    db: Session,
    principal: Principal,
    settings: Settings,
    *,
    project_id: uuid.UUID | None,
    days: int,
    now: datetime | None = None,
) -> tuple[str, int]:
    """Every call of the period as a CSV (newest first, at most MAX_CSV_ROWS) and the row count.
    Times are in the report time zone. No phone numbers: the last two digits only."""
    _check_manager(principal)
    days = max(1, min(MAX_DAYS, days))
    tz = ZoneInfo(settings.report_timezone)
    now = now or datetime.now(UTC)
    since = datetime.combine(
        now.astimezone(tz).date() - timedelta(days=days - 1), datetime.min.time(), tzinfo=tz
    )
    calls = list(
        db.scalars(
            select(Call)
            .where(*_call_scope(principal, project_id), Call.dialled_at >= since)
            .order_by(Call.dialled_at.desc())
            .limit(MAX_CSV_ROWS)
        )
    )

    def local(value: datetime | None) -> str:
        return value.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S") if value else ""

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for row in _rows(db, calls, _stale_before(settings, now)):
        c = row.call
        ticked = checklist_of(c)
        seconds: object = (
            round((c.closed_at - c.dialled_at).total_seconds())
            if c.closed_at is not None and c.state in CLOSED_BY_MODERATOR
            else ""
        )
        writer.writerow(
            [
                _cell(v)
                for v in (
                    local(c.dialled_at),
                    local(c.closed_at),
                    row.project_code,
                    row.task_code,
                    row.moderator_name,
                    c.agent_id,
                    c.phone_hint,
                    "LEFT_OPEN" if row.stale else c.state,
                    c.cancel_reason or "",
                    c.failure_code if c.failure_code and c.state != "RECORDED" else "",
                    seconds,
                    "" if row.recording_seconds is None else row.recording_seconds,
                    *("yes" if item in ticked else "no" for item in CHECKLIST_ITEMS),
                    c.provider,
                    c.provider_reference or "",
                    mask(c.provider_session_id or ""),
                    c.fetch_attempts,
                    c.note,
                )
            ]
        )
    return out.getvalue(), len(calls)


def day_range(days: int, tz_name: str, now: datetime | None = None) -> tuple[date, date]:
    """First and last calendar day of the period, in the provider's time zone."""
    tz = ZoneInfo(tz_name)
    last = (now or datetime.now(UTC)).astimezone(tz).date()
    return last - timedelta(days=max(1, min(MAX_DAYS, days)) - 1), last
