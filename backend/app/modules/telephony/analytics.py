"""Phone-call analytics and the list of every call (D-101, D-102).

Who sees what:
- Super Admin: every project.
- People who assign tasks in a project (Project Admin): every call in that project.
- Everyone else who can see tasks (moderators): their own calls only.

Figures come from the platform's own call records, so they are exact for calls made here. The
provider's own traffic figure (calls per hour of the day) comes from TxContact's recording service
and is shown only when TxContact answers.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task
from app.modules.telephony.models import Call

MAX_DAYS = 90
# A call is counted as needing a person in these states.
NEEDS_PERSON = ("NEEDS_MATCH", "FETCH_FAILED")


def _scoped(principal: Principal, query: Select[Any], project_id: uuid.UUID | None) -> Select[Any]:
    """Limit a query on Call to what this person may see."""
    if project_id is not None:
        if not principal.is_super_admin and project_id not in principal.project_ids:
            raise AppError("Project not found", code="NOT_FOUND", status_code=404)
        query = query.where(Call.project_id == project_id)
    if principal.is_super_admin:
        return query
    managed = [p for p in principal.project_ids if principal.can_in_project(Perm.TASKS_ASSIGN, p)]
    own = Call.moderator_id == principal.user_id
    if managed:
        return query.where((Call.project_id.in_(managed)) | own)
    return query.where(own)


def _check(principal: Principal) -> None:
    if not principal.can(Perm.TASKS_VIEW):
        raise forbidden()


@dataclass
class Day:
    day: str
    calls: int = 0
    recorded: int = 0
    failed: int = 0  # could not be placed, or cancelled
    open: int = 0  # still on the call, being fetched, or waiting for a person


@dataclass
class ModeratorRow:
    moderator_id: uuid.UUID
    name: str
    calls: int = 0
    recorded: int = 0
    failed: int = 0
    call_minutes: list[float] = field(default_factory=list)


@dataclass
class Analytics:
    days: int
    calls: int
    in_call: int
    recorded: int
    dial_failed: int
    cancelled: int
    waiting_for_recording: int
    needs_person: int
    success_pct: float | None
    avg_call_minutes: float | None
    avg_fetch_minutes: float | None
    recorded_minutes: float
    by_day: list[Day]
    by_hour: list[int]  # calls started in each hour of the day, report time zone
    by_moderator: list[dict[str, Any]]
    cancel_reasons: dict[str, int]
    problems: dict[str, int]  # failure codes of calls that did not end recorded


def analytics(
    db: Session,
    principal: Principal,
    *,
    project_id: uuid.UUID | None,
    days: int,
    tz_name: str,
    now: datetime | None = None,
) -> Analytics:
    _check(principal)
    days = max(1, min(MAX_DAYS, days))
    tz = ZoneInfo(tz_name)
    now = now or datetime.now(UTC)
    first_day = now.astimezone(tz).date() - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=tz)
    calls = list(
        db.scalars(_scoped(principal, select(Call), project_id).where(Call.dialled_at >= since))
    )
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
    call_minutes: list[float] = []
    people: dict[uuid.UUID, ModeratorRow] = {}
    for c in calls:
        local = c.dialled_at.astimezone(tz)
        states[c.state] += 1
        by_hour[local.hour] += 1
        d = by_day.get(local.date().isoformat())
        row = people.setdefault(c.moderator_id, ModeratorRow(c.moderator_id, ""))
        row.calls += 1
        failed = c.state in ("DIAL_FAILED", "CANCELLED")
        if d is not None:
            d.calls += 1
            if c.state == "RECORDED":
                d.recorded += 1
            elif failed:
                d.failed += 1
            else:
                d.open += 1
        if c.state == "RECORDED":
            row.recorded += 1
        elif failed:
            row.failed += 1
        if c.cancel_reason:
            reasons[c.cancel_reason] += 1
        if c.failure_code and c.state != "RECORDED":
            problems[c.failure_code] += 1
        if c.closed_at is not None and c.state != "DIAL_FAILED" and c.cancel_reason is None:
            minutes = (c.closed_at - c.dialled_at).total_seconds() / 60
            call_minutes.append(minutes)
            row.call_minutes.append(minutes)

    recording_ids = [c.recording_id for c in calls if c.recording_id is not None]
    fetch_minutes: list[float] = []
    recorded_ms = 0
    if recording_ids:
        made = dict(
            db.execute(
                select(Recording.id, Recording.created_at).where(Recording.id.in_(recording_ids))
            ).all()
        )
        for c in calls:
            created = made.get(c.recording_id) if c.recording_id else None
            if created is not None and c.closed_at is not None:
                fetch_minutes.append(max(0.0, (created - c.closed_at).total_seconds() / 60))
        recorded_ms = int(
            db.scalar(
                select(func.coalesce(func.sum(AudioAsset.duration_ms), 0)).where(
                    AudioAsset.recording_id.in_(recording_ids),
                    AudioAsset.kind == "TELEPHONY_DERIVED_PCM",
                    AudioAsset.deleted_at.is_(None),
                )
            )
            or 0
        )
    if people:
        for uid, name in db.execute(
            select(User.id, User.display_name).where(User.id.in_(list(people)))
        ).all():
            people[uid].name = name

    def avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    total = len(calls)
    return Analytics(
        days=days,
        calls=total,
        in_call=states["DIALLING"],
        recorded=states["RECORDED"],
        dial_failed=states["DIAL_FAILED"],
        cancelled=states["CANCELLED"],
        waiting_for_recording=states["WAITING_FOR_RECORDING"],
        needs_person=sum(states[s] for s in NEEDS_PERSON),
        success_pct=round(100 * states["RECORDED"] / total, 1) if total else None,
        avg_call_minutes=avg(call_minutes),
        avg_fetch_minutes=avg(fetch_minutes),
        recorded_minutes=round(recorded_ms / 60000, 1),
        by_day=list(by_day.values()),
        by_hour=by_hour,
        by_moderator=sorted(
            (
                {
                    "moderator_id": r.moderator_id,
                    "name": r.name or "Unknown",
                    "calls": r.calls,
                    "recorded": r.recorded,
                    "failed": r.failed,
                    "avg_call_minutes": avg(r.call_minutes),
                }
                for r in people.values()
            ),
            key=lambda r: (-int(r["calls"]), str(r["name"])),
        ),
        cancel_reasons=dict(reasons.most_common()),
        problems=dict(problems.most_common()),
    )


@dataclass
class CallRow:
    call: Call
    task_code: str
    project_code: str
    moderator_name: str


def list_calls(
    db: Session,
    principal: Principal,
    *,
    project_id: uuid.UUID | None,
    state: str | None,
    page: int,
    page_size: int,
) -> tuple[list[CallRow], int]:
    _check(principal)
    query = _scoped(principal, select(Call), project_id)
    if state == "NEEDS_PERSON":
        query = query.where(Call.state.in_(NEEDS_PERSON))
    elif state:
        query = query.where(Call.state == state)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    calls = list(
        db.scalars(
            query.order_by(Call.dialled_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    tasks = dict(
        db.execute(
            select(Task.id, Task.task_code).where(Task.id.in_([c.task_id for c in calls]))
        ).all()
    )
    projects = dict(
        db.execute(
            select(Project.id, Project.code).where(Project.id.in_([c.project_id for c in calls]))
        ).all()
    )
    names = dict(
        db.execute(
            select(User.id, User.display_name).where(User.id.in_([c.moderator_id for c in calls]))
        ).all()
    )
    return [
        CallRow(
            c,
            tasks.get(c.task_id, ""),
            projects.get(c.project_id, ""),
            names.get(c.moderator_id, ""),
        )
        for c in calls
    ], total


def day_range(days: int, tz_name: str, now: datetime | None = None) -> tuple[date, date]:
    """First and last calendar day of the period, in the provider's time zone."""
    tz = ZoneInfo(tz_name)
    last = (now or datetime.now(UTC)).astimezone(tz).date()
    return last - timedelta(days=max(1, min(MAX_DAYS, days)) - 1), last
