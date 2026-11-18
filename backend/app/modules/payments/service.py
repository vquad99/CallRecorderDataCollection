"""Payments (D-137): what moderators and participants have earned on approved work.

Rates are set per project, in rupees per approved minute, one for moderators and one for
participants; every change is audited. Only APPROVED tasks count, with the length of their
current recording (exports/minutes.py, the same numbers as the Participant minutes report): a
moderator is paid on the full approved minutes of the tasks whose recording they made, a
participant on their equal share of each approved session. The days chosen are approval days in
the report time zone (India).

One row per person and project, since each project has its own rates. Minutes are rounded to two
places first and the amount is those minutes times the rate, rounded to the paisa, so every row
can be checked by hand; a project without a rate shows its minutes with no amount. The amount
uses the project's rate as it is now: a changed rate changes the amounts of work already
approved too (the audit log keeps every rate).

Access: payments.manage in the project (Super Admin: every project; Project Admin: their own).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.csvio import write_table
from app.core.days import day_bounds
from app.core.errors import AppError, forbidden
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.exports import minutes
from app.modules.participants.models import Participant
from app.modules.payments.models import PaymentRate
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable, visible_projects_query

Who = Literal["moderators", "participants"]
PAISA = Decimal("0.01")
NO_RATE = "No rate set"


def _paise(value: Decimal | None) -> Decimal | None:
    """An amount of rupees with exactly two places (2 -> 2.00)."""
    return None if value is None else value.quantize(PAISA)


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(_paise(value))


# ---------------------------------------------------------------- rates


@dataclass(frozen=True)
class Rates:
    project: Project
    moderator_rate: Decimal | None
    participant_rate: Decimal | None
    updated_at: datetime | None
    updated_by: str | None


def payable_projects(db: Session, principal: Principal) -> list[Project]:
    """The projects whose payments this person handles, by code."""
    if not principal.can(Perm.PAYMENTS_MANAGE):
        raise forbidden()
    return [
        p
        for p in db.scalars(visible_projects_query(principal).order_by(Project.code))
        if principal.can_in_project(Perm.PAYMENTS_MANAGE, p.id)
    ]


def _rates_of(db: Session, projects: Iterable[Project]) -> dict[uuid.UUID, PaymentRate]:
    ids = [p.id for p in projects]
    if not ids:
        return {}
    return {
        r.project_id: r
        for r in db.scalars(select(PaymentRate).where(PaymentRate.project_id.in_(ids)))
    }


def _names(db: Session, user_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {u for u in user_ids if u is not None}
    if not ids:
        return {}
    return {
        uid: name
        for uid, name in db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    }


def list_rates(db: Session, principal: Principal) -> list[Rates]:
    projects = payable_projects(db, principal)
    found = _rates_of(db, projects)
    names = _names(db, (r.updated_by for r in found.values()))
    return [_rates(p, found.get(p.id), names) for p in projects]


def _rates(project: Project, rate: PaymentRate | None, names: dict[uuid.UUID, str]) -> Rates:
    return Rates(
        project=project,
        moderator_rate=rate.moderator_rate if rate else None,
        participant_rate=rate.participant_rate if rate else None,
        updated_at=rate.updated_at if rate else None,
        updated_by=names.get(rate.updated_by) if rate and rate.updated_by else None,
    )


def set_rates(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    moderator_rate: Decimal | None,
    participant_rate: Decimal | None,
    ip: str | None,
) -> Rates:
    """Sets a project's two rates (None: no rate); audited as payments.rates_changed."""
    project = get_manageable(db, principal, project_id, Perm.PAYMENTS_MANAGE)
    moderator_rate, participant_rate = _paise(moderator_rate), _paise(participant_rate)
    rate = db.scalar(select(PaymentRate).where(PaymentRate.project_id == project.id))
    before = {
        "moderator_rate": _money(rate.moderator_rate) if rate else None,
        "participant_rate": _money(rate.participant_rate) if rate else None,
    }
    after = {"moderator_rate": _money(moderator_rate), "participant_rate": _money(participant_rate)}
    if before != after:
        if rate is None:
            rate = PaymentRate(project_id=project.id)
            db.add(rate)
        rate.moderator_rate = moderator_rate
        rate.participant_rate = participant_rate
        rate.updated_by = principal.user_id
        audit.record(
            db,
            action="payments.rates_changed",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            actor_id=principal.user_id,
            ip=ip,
            before=before,
            after=after,
        )
        db.commit()
        db.refresh(rate)
    return _rates(project, rate, _names(db, [rate.updated_by] if rate else []))


# ---------------------------------------------------------------- earnings


@dataclass(frozen=True)
class Period:
    project_id: uuid.UUID | None = None
    date_from: date | None = None  # approval days, in the report time zone
    date_to: date | None = None
    search: str | None = None  # part of a name or participant code


@dataclass
class Row:
    """One person in one project: approved tasks (moderators) or sessions (participants), and
    their minutes (a participant's share)."""

    project: Project
    person_id: uuid.UUID
    name: str | None  # a participant's name only for people who may see it
    code: str | None = None  # participants only
    count: int = 0
    ms: int = 0
    rate: Decimal | None = None

    @property
    def minutes(self) -> Decimal:
        return minutes.minutes(self.ms)

    @property
    def amount(self) -> Decimal | None:
        if self.rate is None:
            return None
        return (self.minutes * self.rate).quantize(PAISA, rounding=ROUND_HALF_UP)


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None

    @property
    def count(self) -> int:
        return sum(r.count for r in self.rows)

    @property
    def minutes(self) -> Decimal:
        return sum((r.minutes for r in self.rows), Decimal("0.00"))

    @property
    def amount(self) -> Decimal:
        return sum((r.amount for r in self.rows if r.amount is not None), Decimal("0.00"))

    @property
    def minutes_without_rate(self) -> Decimal:
        return sum((r.minutes for r in self.rows if r.rate is None), Decimal("0.00"))


def _scope(db: Session, principal: Principal, project_id: uuid.UUID | None) -> list[Project]:
    if project_id is None:
        return payable_projects(db, principal)
    return [get_manageable(db, principal, project_id, Perm.PAYMENTS_MANAGE)]


def earnings(db: Session, principal: Principal, who: Who, period: Period, tz_name: str) -> Report:
    """Every moderator's or participant's approved work in the period, one row per person and
    project, by project code and name (participants: by code)."""
    if period.date_from and period.date_to and period.date_from > period.date_to:
        raise AppError(
            "The first day must not be after the last day",
            code="VALIDATION_ERROR",
            status_code=422,
        )
    projects = {p.id: p for p in _scope(db, principal, period.project_id)}
    start, end = day_bounds(period.date_from, period.date_to, tz_name)
    sums: dict[tuple[uuid.UUID, uuid.UUID], list[int]] = {}

    def add(project_id: uuid.UUID, person: uuid.UUID, ms: int) -> None:
        total = sums.setdefault((project_id, person), [0, 0])
        total[0] += 1
        total[1] += ms

    for row in db.execute(minutes.approved_conversations(projects, start, end)):
        if who == "moderators":
            add(row.project_id, row.recorded_by, int(row.ms or 0))
        else:
            for pid in (row.participant_a_id, row.participant_b_id):
                add(row.project_id, pid, minutes.share(row.ms))
    rates = _rates_of(db, projects.values())

    def rate_of(project_id: uuid.UUID) -> Decimal | None:
        found = rates.get(project_id)
        if found is None:
            return None
        return found.moderator_rate if who == "moderators" else found.participant_rate

    rows: list[Row] = []
    if who == "moderators":
        names = _names(db, (person for _, person in sums))
        for (project_id, person), (count, ms) in sums.items():
            rows.append(Row(projects[project_id], person, names.get(person, ""), None, count, ms))
    else:
        people = (
            {
                p.id: p
                for p in db.scalars(
                    select(Participant).where(Participant.id.in_({p for _, p in sums}))
                )
            }
            if sums
            else {}
        )
        for (project_id, person), (count, ms) in sums.items():
            participant = people[person]
            # The name for people who may see participants' details in that project (D-128).
            shown = principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project_id)
            rows.append(
                Row(
                    projects[project_id],
                    person,
                    participant.display_label if shown else None,
                    participant.participant_code,
                    count,
                    ms,
                )
            )
    for r in rows:
        r.rate = rate_of(r.project.id)
    term = (period.search or "").strip().casefold()
    if term:
        rows = [r for r in rows if any(term in (v or "").casefold() for v in (r.name, r.code))]
    rows.sort(key=lambda r: (r.project.code, (r.code or r.name or "").casefold()))
    return Report(rows=rows, date_from=period.date_from, date_to=period.date_to)


# ---------------------------------------------------------------- spreadsheet

_COLUMNS: dict[Who, list[str]] = {
    "moderators": [
        "project",
        "moderator",
        "approved_tasks",
        "approved_minutes",
        "rate_inr_per_minute",
        "amount_inr",
    ],
    "participants": [
        "project",
        "participant_code",
        "name",
        "approved_sessions",
        "payable_minutes",
        "rate_inr_per_minute",
        "amount_inr",
    ],
}


def table(report: Report, who: Who) -> str:
    """The rows and a Total line as a CSV that spreadsheet software opens as UTF-8; every cell
    is made safe (D-088)."""
    lines: list[list[object]] = []
    for r in report.rows:
        person = [r.name or ""] if who == "moderators" else [r.code or "", r.name or ""]
        lines.append(
            [
                r.project.code,
                *person,
                r.count,
                r.minutes,
                "" if r.rate is None else r.rate,
                NO_RATE if r.amount is None else r.amount,
            ]
        )
    blank = [""] if who == "moderators" else ["", ""]
    lines.append(["Total", *blank, report.count, report.minutes, "", report.amount])
    return write_table(_COLUMNS[who], lines, bom=True)


def file_name(db: Session, who: Who, period: Period) -> str:
    project = db.get(Project, period.project_id) if period.project_id else None
    day = datetime.now(UTC).strftime("%Y%m%d")
    return f"payments_{who}_{project.code if project else 'all'}_{day}.csv"


def record_download(
    db: Session, principal: Principal, who: Who, period: Period, rows: int, ip: str | None
) -> None:
    audit.record(
        db,
        action="payments.exported",
        entity_type="project" if period.project_id else "payments",
        entity_id=period.project_id,
        project_id=period.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={
            "who": who,
            "date_from": period.date_from.isoformat() if period.date_from else None,
            "date_to": period.date_to.isoformat() if period.date_to else None,
            "search": period.search or None,
            "rows": rows,
        },
    )
    db.commit()
