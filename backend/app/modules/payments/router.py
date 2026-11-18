"""/api/v1/payments (D-137): rates per project, and what moderators and participants earned."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import AppSettings
from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.payments import service

router = APIRouter(
    prefix="/payments", tags=["payments"], dependencies=[Depends(require(Perm.PAYMENTS_MANAGE))]
)

# Rupees per approved minute: never negative, at most two decimal places.
Rate = Annotated[Decimal, Field(ge=0, le=100_000, max_digits=8, decimal_places=2)]
Search = Annotated[str | None, Query(max_length=100)]


class RatesOut(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    # Rupees per approved minute; null: no rate set yet.
    moderator_rate: Decimal | None
    participant_rate: Decimal | None
    updated_at: datetime | None
    updated_by: str | None


class RatesBody(BaseModel):
    moderator_rate: Rate | None = None
    participant_rate: Rate | None = None


def _rates_out(r: service.Rates) -> RatesOut:
    return RatesOut(
        project_id=r.project.id,
        project_code=r.project.code,
        project_name=r.project.name,
        moderator_rate=r.moderator_rate,
        participant_rate=r.participant_rate,
        updated_at=r.updated_at,
        updated_by=r.updated_by,
    )


class Totals(BaseModel):
    # Approved tasks (moderators) or approved sessions (participants).
    count: int
    minutes: Decimal
    # The sum of the amounts; minutes of projects with no rate are not in it.
    amount: Decimal
    minutes_without_rate: Decimal


class ModeratorRow(BaseModel):
    project_id: uuid.UUID
    project_code: str
    user_id: uuid.UUID
    name: str
    approved_tasks: int
    approved_minutes: Decimal
    rate: Decimal | None
    amount: Decimal | None  # null: the project has no moderator rate yet


class ParticipantRow(BaseModel):
    project_id: uuid.UUID
    project_code: str
    participant_id: uuid.UUID
    participant_code: str
    name: str | None  # for people who may see participants' details (D-128)
    approved_sessions: int
    payable_minutes: Decimal  # the participant's equal share
    rate: Decimal | None
    amount: Decimal | None  # null: the project has no participant rate yet


class PeriodOut(BaseModel):
    timezone: str
    date_from: date | None
    date_to: date | None
    totals: Totals


class ModeratorPayments(PeriodOut):
    rows: list[ModeratorRow]


class ParticipantPayments(PeriodOut):
    rows: list[ParticipantRow]


def _period(
    project_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Search = None,
) -> service.Period:
    return service.Period(
        project_id=project_id, date_from=date_from, date_to=date_to, search=search
    )


PeriodQuery = Annotated[service.Period, Depends(_period)]


def _totals(report: service.Report) -> Totals:
    return Totals(
        count=report.count,
        minutes=report.minutes,
        amount=report.amount,
        minutes_without_rate=report.minutes_without_rate,
    )


@router.get("/rates", response_model=list[RatesOut])
def rates(principal: CurrentPrincipal, db: DbSession) -> list[RatesOut]:
    """One row per project whose payments the caller handles."""
    return [_rates_out(r) for r in service.list_rates(db, principal)]


@router.put("/rates/{project_id}", response_model=RatesOut)
def set_rates(
    project_id: uuid.UUID,
    body: RatesBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RatesOut:
    return _rates_out(
        service.set_rates(
            db,
            principal,
            project_id,
            body.moderator_rate,
            body.participant_rate,
            client_ip(request),
        )
    )


@router.get("/moderators", response_model=ModeratorPayments)
def moderators(
    period: PeriodQuery, principal: CurrentPrincipal, db: DbSession, settings: AppSettings
) -> ModeratorPayments:
    report = service.earnings(db, principal, "moderators", period, settings.report_timezone)
    return ModeratorPayments(
        timezone=settings.report_timezone,
        date_from=report.date_from,
        date_to=report.date_to,
        totals=_totals(report),
        rows=[
            ModeratorRow(
                project_id=r.project.id,
                project_code=r.project.code,
                user_id=r.person_id,
                name=r.name or "",
                approved_tasks=r.count,
                approved_minutes=r.minutes,
                rate=r.rate,
                amount=r.amount,
            )
            for r in report.rows
        ],
    )


@router.get("/participants", response_model=ParticipantPayments)
def participants(
    period: PeriodQuery, principal: CurrentPrincipal, db: DbSession, settings: AppSettings
) -> ParticipantPayments:
    report = service.earnings(db, principal, "participants", period, settings.report_timezone)
    return ParticipantPayments(
        timezone=settings.report_timezone,
        date_from=report.date_from,
        date_to=report.date_to,
        totals=_totals(report),
        rows=[
            ParticipantRow(
                project_id=r.project.id,
                project_code=r.project.code,
                participant_id=r.person_id,
                participant_code=r.code or "",
                name=r.name,
                approved_sessions=r.count,
                payable_minutes=r.minutes,
                rate=r.rate,
                amount=r.amount,
            )
            for r in report.rows
        ],
    )


def _csv(
    who: service.Who,
    period: service.Period,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    report = service.earnings(db, principal, who, period, settings.report_timezone)
    name = service.file_name(db, who, period)
    service.record_download(db, principal, who, period, len(report.rows), client_ip(request))
    return Response(
        content=service.table(report, who),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/moderators/export")
def moderators_csv(
    period: PeriodQuery,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    """The Moderators tab as a CSV with a Total line; audited as payments.exported."""
    return _csv("moderators", period, request, principal, db, settings)


@router.get("/participants/export")
def participants_csv(
    period: PeriodQuery,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    """The Participants tab as a CSV with a Total line; audited as payments.exported."""
    return _csv("participants", period, request, principal, db, settings)
