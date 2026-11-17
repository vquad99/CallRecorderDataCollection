"""/api/v1/projects/{project_id}/participants (PART-*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, Cipher
from app.core.background import dispatch
from app.core.errors import forbidden
from app.core.permissions import Perm
from app.db.paging import Page, PageNumber, PageSize
from app.modules.auth.deps import CurrentPrincipal, DbSession, Principal, client_ip, require
from app.modules.auth.security import FieldCipher
from app.modules.exports import minutes as minutes_report
from app.modules.participants import consent_view, details, manage, service
from app.modules.participants.models import ConsentStatus, Participant
from app.modules.portal import service as portal
from app.modules.projects.models import Project

router = APIRouter(
    prefix="/projects/{project_id}/participants",
    tags=["participants"],
    dependencies=[Depends(require(Perm.PARTICIPANTS_VIEW))],
)

MASK = "••••••"


class MinutesOut(BaseModel):
    """This participant's share of the minutes in this project (D-095, D-111): every
    conversation's length is split equally between its two participants."""

    conversations: int
    recorded_minutes: float
    approved_conversations: int
    approved_minutes: float
    payable_minutes: float


def minutes_out(t: minutes_report.Minutes | None) -> MinutesOut:
    t = t or minutes_report.Minutes()
    return MinutesOut(
        conversations=t.conversations,
        recorded_minutes=minutes_report.as_minutes(t.recorded_ms),
        approved_conversations=t.approved_conversations,
        approved_minutes=minutes_report.as_minutes(t.approved_ms),
        payable_minutes=minutes_report.as_minutes(t.payable_ms),
    )


class ParticipantOut(BaseModel):
    id: uuid.UUID
    participant_code: str
    language_code: str
    dialect: str
    district: str = ""
    display_label: str | None
    phone: str | None
    has_phone: bool
    # True when `phone` holds only the last two digits ("••••••12"), not the number.
    phone_masked: bool
    email: str | None  # only for people who may see contact details
    has_email: bool
    # The participant's own answer on the consent form in this project, its staff review, and
    # whether they hold a working personal link. Empty when the caller may not see consent.
    consent_status: str | None = None
    consent_review: str | None = None
    link_active: bool | None = None
    # Only for people who may export the project (the same people who get the minutes report).
    minutes: MinutesOut | None = None
    notes: str | None
    deleted: bool
    consent_visible: bool  # whether this caller may open the person's consent history
    created_at: datetime


def present(
    db: DbSession,
    principal: Principal,
    cipher: FieldCipher,
    project: Project,
    p: Participant,
    assigned_ids: set[uuid.UUID] | None = None,
    overview: dict[uuid.UUID, tuple[str, str | None, bool]] | None = None,
) -> ParticipantOut:
    v = service.visibility(db, principal, project, p.id, assigned_ids)
    if p.phone_e164_enc is None or not (v.profile or v.contact):
        phone = None
    elif v.contact:
        phone = cipher.decrypt(p.phone_e164_enc)
    else:
        phone = f"{MASK}{p.phone_hint}"
    return ParticipantOut(
        id=p.id,
        participant_code=p.participant_code,
        language_code=p.language_code,
        dialect=p.dialect,
        district=p.district,
        display_label=p.display_label if v.profile else None,
        phone=phone,
        has_phone=p.phone_e164_enc is not None,
        phone_masked=phone is not None and not v.contact,
        email=cipher.decrypt(p.email_enc) if p.email_enc and v.contact else None,
        has_email=p.email_enc is not None,
        notes=p.notes if v.notes else None,
        deleted=p.deleted_at is not None,
        consent_visible=(
            sees := v.profile and principal.can_in_project(Perm.CONSENT_VIEW, project.id)
        ),
        consent_status=(overview or {}).get(p.id, (None, None, None))[0] if sees else None,
        consent_review=(overview or {}).get(p.id, (None, None, None))[1] if sees else None,
        link_active=(overview or {}).get(p.id, (None, None, None))[2] if sees else None,
        created_at=p.created_at,
    )


class ParticipantPage(Page[ParticipantOut]):
    pass


@router.get("", response_model=ParticipantPage)
def list_participants(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> ParticipantPage:
    project, items, total = service.list_participants(
        db, principal, project_id, search=search, page=page, page_size=page_size
    )
    # The whole list is for the people who manage participants (D-112); everyone else meets
    # the participants of their own tasks on those tasks.
    if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        raise forbidden()
    assigned = service.assigned_participants(db, principal.user_id, project.id)
    overview = manage.consent_overview(db, project, [p.id for p in items])
    shown = [present(db, principal, cipher, project, p, assigned, overview) for p in items]
    if principal.can_in_project(Perm.EXPORTS_CREATE, project.id):
        totals = minutes_report.per_participant(db, project.id, [p.id for p in items])
        for out in shown:
            out.minutes = minutes_out(totals.get(out.id))
    return ParticipantPage(
        items=shown,
        total=total,
        page=page,
        page_size=page_size,
    )


class ParticipantBody(BaseModel):
    display_label: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    language_code: str = Field(
        min_length=2, max_length=35, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
    )
    dialect: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=5000)

    def to_input(self) -> service.ParticipantInput:
        return service.ParticipantInput(**self.model_dump())


@router.post("", response_model=ParticipantOut, status_code=201)
def create_participant(
    project_id: uuid.UUID,
    body: ParticipantBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.create_participant(
        db, settings, cipher, principal, project_id, body.to_input(), client_ip(request)
    )
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


class LinkBody(BaseModel):
    participant_code: str = Field(min_length=2, max_length=20)


@router.post("/link", response_model=ParticipantOut, status_code=201)
def link_participant(
    project_id: uuid.UUID,
    body: LinkBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.link_existing(db, principal, project_id, body.participant_code, client_ip(request))
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


class CandidateOut(BaseModel):
    id: uuid.UUID
    participant_code: str
    display_label: str | None
    language_code: str
    dialect: str


@router.get("/link-candidates", response_model=list[CandidateOut])
def link_candidates(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[CandidateOut]:
    """Existing participants from the caller's other projects, to add here (D-090)."""
    return [
        CandidateOut.model_validate(p, from_attributes=True)
        for p in service.link_candidates(db, principal, project_id, search)
    ]


@router.get("/export")
def export_contacts(
    project_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> Response:
    return Response(
        content=service.export_contacts(db, cipher, principal, project_id, client_ip(request)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="participants.csv"'},
    )


@router.get("/{participant_id}", response_model=ParticipantOut)
def get_participant(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> ParticipantOut:
    project, p = service.get_in_project(db, principal, project_id, participant_id)
    return present(db, principal, cipher, project, p)


@router.patch("/{participant_id}", response_model=ParticipantOut)
def correct_participant(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: ParticipantBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.correct_participant(
        db,
        settings,
        cipher,
        principal,
        project_id,
        participant_id,
        body.to_input(),
        client_ip(request),
    )
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


class DeleteBody(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/{participant_id}/delete", response_model=ParticipantOut)
def delete_participant(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: DeleteBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> ParticipantOut:
    p = service.delete_participant(
        db, principal, project_id, participant_id, body.reason, client_ip(request)
    )
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    return present(db, principal, cipher, project, p)


class ConsentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID | None
    status: ConsentStatus
    method: str
    policy_version: str
    captured_by: uuid.UUID | None  # empty: the participant answered the form themselves
    note: str
    review_status: str | None = None
    review_note: str = ""
    created_at: datetime


@router.get("/{participant_id}/consent", response_model=list[ConsentOut])
def consent_history(
    project_id: uuid.UUID, participant_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[ConsentOut]:
    return [
        ConsentOut.model_validate(r, from_attributes=True)
        for r in service.consent_history(db, principal, project_id, participant_id)
    ]


# ---------------------------------------------------------------- bulk work (D-073)


class ImportBody(BaseModel):
    csv: str = Field(min_length=1, max_length=500_000)
    confirm: bool = False


class ImportRow(BaseModel):
    line: int
    name: str
    ok: bool
    message: str
    participant_code: str | None


class ImportOut(BaseModel):
    rows: list[ImportRow]
    ready: int
    created: int


@router.post("/import", response_model=ImportOut)
def import_participants(
    project_id: uuid.UUID,
    body: ImportBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> ImportOut:
    rows = manage.import_csv(
        db, settings, cipher, principal, project_id, body.csv, body.confirm, client_ip(request)
    )
    return ImportOut(
        rows=[ImportRow.model_validate(r, from_attributes=True) for r in rows],
        ready=sum(1 for r in rows if r.ok),
        created=sum(1 for r in rows if r.participant_code),
    )


class BulkBody(BaseModel):
    action: Literal["assign", "remove", "send_consent"]
    participant_ids: list[uuid.UUID] = Field(min_length=1, max_length=manage.MAX_BULK)
    target_project_id: uuid.UUID | None = None
    reason: str = Field(default="", max_length=1000)


class BulkRow(BaseModel):
    participant_id: uuid.UUID
    participant_code: str
    ok: bool
    message: str


class BulkOut(BaseModel):
    results: list[BulkRow]
    done: int
    failed: int


@router.post("/bulk", response_model=BulkOut)
def bulk_action(
    project_id: uuid.UUID,
    body: BulkBody,
    request: Request,
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    db: DbSession,
) -> BulkOut:
    ip = client_ip(request)
    results = manage.bulk(
        db,
        principal,
        project_id,
        body.action,
        body.participant_ids,
        body.target_project_id,
        body.reason,
        ip,
    )
    to_email = [r for r in results if r.ok] if body.action == "send_consent" else []
    if to_email and not dispatch(
        request.app,
        portal.SEND_LINKS_TASK,
        [str(project_id), [str(r.participant_id) for r in to_email], str(principal.user_id), ip],
        portal.send_links_job,
        background,
    ):
        for r in to_email:
            r.ok, r.message = False, "The emails could not be queued; try again in a moment"
    return BulkOut(
        results=[BulkRow.model_validate(r, from_attributes=True) for r in results],
        done=sum(1 for r in results if r.ok),
        failed=sum(1 for r in results if not r.ok),
    )


class ReviewBody(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(default="", max_length=1000)


@router.post("/{participant_id}/consent-review", response_model=ConsentOut)
def review_consent(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: ReviewBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ConsentOut:
    record = manage.review_consent(
        db, principal, project_id, participant_id, body.decision, body.note, client_ip(request)
    )
    return ConsentOut.model_validate(record, from_attributes=True)


# ---------------------------------------------------------------- one consent form (D-074)


class AnswerOut(BaseModel):
    status: ConsentStatus
    answered_at: datetime
    policy_version: str
    review_status: str | None
    review_note: str
    reviewed_at: datetime | None


class ConsentFormOut(BaseModel):
    participant_code: str
    project_code: str
    project_name: str
    form_text: str
    form_version: str
    answered: bool
    current: AnswerOut | None
    earlier: list[AnswerOut]


@router.get("/{participant_id}/consent-form", response_model=ConsentFormOut)
def consent_form(
    project_id: uuid.UUID, participant_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> ConsentFormOut:
    return ConsentFormOut.model_validate(
        consent_view.get(db, principal, project_id, participant_id), from_attributes=True
    )


@router.get("/{participant_id}/consent-form/file")
def consent_form_file(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> Response:
    name, html = consent_view.as_file(db, principal, project_id, participant_id, client_ip(request))
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ------------------------------------------------- everything about one participant (D-104)


class ProjectRefOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class RemovedOut(BaseModel):
    at: datetime
    by: str | None
    reason: str | None


class LinkOut(BaseModel):
    active: bool
    created_at: datetime
    created_by: str | None
    expires_at: datetime
    last_used_at: datetime | None
    handed_out: bool


class SessionOut(BaseModel):
    task_id: uuid.UUID
    task_code: str
    mode: str
    slot: Literal["A", "B"]
    status: str
    created_at: datetime
    other_participant_code: str
    moderator: str | None
    consent_status: str | None
    consent_method: str | None
    consent_at: datetime | None
    recordings: int
    recording_seconds: float | None
    recorded_at: datetime | None
    phone_calls: int


class ParticipantCallsOut(BaseModel):
    total: int
    recorded: int
    last_at: datetime | None
    last_state: str | None


class ParticipantDetailsOut(BaseModel):
    participant: ParticipantOut
    updated_at: datetime
    added_by: str | None
    projects: list[ProjectRefOut]
    removed: RemovedOut | None
    link: LinkOut | None
    # The consent form and its answers; empty for someone who may not see consent.
    consent_form: ConsentFormOut | None
    sessions: list[SessionOut]
    sessions_total: int
    # Only for people who may export the project (the same rule as the list).
    minutes: MinutesOut | None
    calls: ParticipantCallsOut | None


@router.get("/{participant_id}/details", response_model=ParticipantDetailsOut)
def participant_details(
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> ParticipantDetailsOut:
    """One answer with everything the platform holds about a participant in this project, for
    the people who manage participants there."""
    d = details.get(db, principal, project_id, participant_id)
    overview = manage.consent_overview(db, d.project, [d.participant.id])
    shown = present(db, principal, cipher, d.project, d.participant, None, overview)
    can_export = principal.can_in_project(Perm.EXPORTS_CREATE, d.project.id)
    if can_export:
        totals = minutes_report.per_participant(db, d.project.id, [d.participant.id])
        shown.minutes = minutes_out(totals.get(d.participant.id))
    form = (
        ConsentFormOut.model_validate(
            consent_view.get(db, principal, project_id, participant_id), from_attributes=True
        )
        if shown.consent_visible
        else None
    )
    return ParticipantDetailsOut(
        participant=shown,
        updated_at=d.participant.updated_at,
        added_by=d.added_by,
        projects=[ProjectRefOut(**vars(p)) for p in d.projects],
        removed=RemovedOut(**vars(d.removed)) if d.removed else None,
        link=LinkOut(**vars(d.link)) if d.link else None,
        consent_form=form,
        sessions=[SessionOut(**vars(s)) for s in d.sessions],
        sessions_total=d.sessions_total,
        minutes=shown.minutes,
        calls=ParticipantCallsOut(**vars(d.calls)) if d.calls else None,
    )
