"""/api/v1/projects/{project_id}/participants (PART-*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AppSettings, Cipher
from app.core.background import dispatch
from app.core.errors import forbidden
from app.core.permissions import Perm
from app.db.paging import Page, PageNumber, PageSize
from app.modules.auth.deps import CurrentPrincipal, DbSession, Principal, client_ip, require
from app.modules.auth.security import FieldCipher
from app.modules.exports import minutes as minutes_report
from app.modules.participants import consent_view, details, manage, service, speakers
from app.modules.participants.models import ConsentStatus, Participant
from app.modules.portal import service as portal
from app.modules.projects.models import Project
from app.modules.tasks import pairing

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


class PairingOut(BaseModel):
    """For people who make tasks (D-143): this participant's conversations in the project that
    count toward the per-speaker limit (tasks not cancelled or rejected), and the participants
    they already share one with."""

    conversations: int
    paired_with: list[uuid.UUID]


class ParticipantOut(BaseModel):
    id: uuid.UUID
    participant_code: str
    language_code: str
    dialect: str
    # The native district (D-121, D-143), shown like the language.
    district: str = ""
    # Speaker details (D-143): shown like the name (null for others, and when not given).
    age: int | None = None
    gender: str | None = None
    current_state: str | None = None
    current_district: str | None = None
    current_pincode: str | None = None
    native_state: str | None = None
    native_pincode: str | None = None
    native_language: str | None = None
    education: str | None = None
    education_medium: str | None = None
    recording_state: str | None = None
    recording_district: str | None = None
    recording_pincode: str | None = None
    # Every speaker detail is given (to everyone who sees the row): a task needs it (D-143).
    speaker_details_complete: bool = False
    # Only in the list, for people who make tasks in the project (D-143).
    pairing: PairingOut | None = None
    display_label: str | None
    phone: str | None
    has_phone: bool
    # True when `phone` holds only the last two digits ("••••••12"), not the number.
    phone_masked: bool
    email: str | None  # only for people who may see contact details
    has_email: bool
    # The participant's own answer on the consent form in this project as it counts now (NONE:
    # no answer yet), and whether they hold a working personal link. Empty when the caller may
    # not see consent.
    consent_status: str | None = None
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
    overview: dict[uuid.UUID, tuple[str, bool]] | None = None,
) -> ParticipantOut:
    v = service.visibility(db, principal, project, p.id, assigned_ids)
    if p.phone_e164_enc is None or not (v.profile or v.contact):
        phone = None
    elif v.contact:
        phone = cipher.decrypt(p.phone_e164_enc)
    else:
        phone = f"{MASK}{p.phone_hint}"
    details = {
        name: getattr(p, name) for name in speakers.FIELDS if name != "district" and v.profile
    }
    return ParticipantOut(
        id=p.id,
        participant_code=p.participant_code,
        language_code=p.language_code,
        dialect=p.dialect,
        district=p.district,
        **details,
        speaker_details_complete=speakers.complete(p),
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
        consent_status=(overview or {}).get(p.id, (None, None))[0] if sees else None,
        link_active=(overview or {}).get(p.id, (None, None))[1] if sees else None,
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
    if principal.can_in_project(Perm.TASKS_ASSIGN, project.id):
        # What the task form needs to say who cannot be paired, and why (D-143).
        counted = pairing.tally(db, project, [p.id for p in items])
        for out in shown:
            out.pairing = PairingOut(
                conversations=counted.conversations.get(out.id, 0),
                paired_with=counted.partners(out.id),
            )
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
    notes: str = Field(default="", max_length=5000)
    # Speaker details (D-143), checked by participants/speakers.py (422 INVALID_SPEAKER_DETAILS
    # naming the field). Null or empty = not given; on PATCH a field left out keeps its value.
    district: str | None = Field(default=None, max_length=100)  # the native district
    age: int | None = None
    gender: str | None = Field(default=None, max_length=20)
    current_state: str | None = Field(default=None, max_length=60)
    current_district: str | None = Field(default=None, max_length=100)
    current_pincode: str | None = Field(default=None, max_length=10)
    native_state: str | None = Field(default=None, max_length=60)
    native_pincode: str | None = Field(default=None, max_length=10)
    native_language: str | None = Field(default=None, max_length=50)
    education: str | None = Field(default=None, max_length=30)
    education_medium: str | None = Field(default=None, max_length=30)
    recording_state: str | None = Field(default=None, max_length=60)
    recording_district: str | None = Field(default=None, max_length=100)
    recording_pincode: str | None = Field(default=None, max_length=10)

    def to_input(self) -> service.ParticipantInput:
        sent = self.model_fields_set
        return service.ParticipantInput(
            display_label=self.display_label,
            phone=self.phone,
            email=self.email,
            language_code=self.language_code,
            dialect=self.dialect,
            notes=self.notes,
            speaker={name: getattr(self, name) for name in speakers.FIELDS if name in sent},
        )


# What staff are told about the consent form once someone joins a project (D-129).
CONSENT_EMAILED = "Consent form emailed."
CONSENT_FORM_MISSING = "Write the project's consent form, then send it."
CONSENT_NO_EMAIL = "No email address: add one with Edit, then email the consent form."
CONSENT_NOT_QUEUED = "The consent form could not be emailed now: use Email consent form again."


def email_consent_forms(
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    principal: Principal,
    project: Project,
    participant_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Everyone who joins a project is emailed their personal consent form for it, after the
    answer (by the worker when there is one), with no one asking for it (D-129). Says, per
    participant, what happened. Nothing is sent while the project has no consent form, nor to
    someone emailed it less than portal.EMAIL_AGAIN_AFTER ago."""
    if not participant_ids:
        return {}
    if not project.consent_text.strip():
        return dict.fromkeys(participant_ids, CONSENT_FORM_MISSING)
    reachable = set(
        db.scalars(
            select(Participant.id).where(
                Participant.id.in_(participant_ids), Participant.email_enc.is_not(None)
            )
        )
    )
    waiting = portal.recently_emailed(db, project.id, reachable)
    to_email = [str(pid) for pid in participant_ids if pid in reachable and pid not in waiting]
    queued = bool(to_email) and dispatch(
        request.app,
        portal.SEND_LINKS_TASK,
        [str(project.id), to_email, str(principal.user_id), client_ip(request)],
        portal.send_links_job,
        background,
    )
    sent = CONSENT_EMAILED if queued else CONSENT_NOT_QUEUED
    said: dict[uuid.UUID, str] = {}
    for pid in participant_ids:
        if pid not in reachable:
            said[pid] = CONSENT_NO_EMAIL
        elif pid in waiting:
            said[pid] = portal.EMAILED_RECENTLY
        else:
            said[pid] = sent
    return said


class AddedOut(ParticipantOut):
    # What happened to their consent form email (D-129), in words for staff.
    consent_email: str


@router.post("", response_model=AddedOut, status_code=201)
def create_participant(
    project_id: uuid.UUID,
    body: ParticipantBody,
    request: Request,
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> AddedOut:
    p = service.create_participant(
        db, settings, cipher, principal, project_id, body.to_input(), client_ip(request)
    )
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    sent = email_consent_forms(request, background, db, principal, project, [p.id])
    return AddedOut(
        **present(db, principal, cipher, project, p).model_dump(), consent_email=sent[p.id]
    )


class LinkBody(BaseModel):
    participant_code: str = Field(min_length=2, max_length=20)


@router.post("/link", response_model=AddedOut, status_code=201)
def link_participant(
    project_id: uuid.UUID,
    body: LinkBody,
    request: Request,
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    db: DbSession,
    cipher: Cipher,
) -> AddedOut:
    p = service.link_existing(db, principal, project_id, body.participant_code, client_ip(request))
    project, _ = service.get_in_project(db, principal, project_id, p.id)
    sent = email_consent_forms(request, background, db, principal, project, [p.id])
    return AddedOut(
        **present(db, principal, cipher, project, p).model_dump(), consent_email=sent[p.id]
    )


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
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    cipher: Cipher,
) -> ImportOut:
    rows = manage.import_csv(
        db, settings, cipher, principal, project_id, body.csv, body.confirm, client_ip(request)
    )
    added = [r.participant_id for r in rows if r.participant_id is not None]
    if added:
        project = db.get_one(Project, project_id)
        sent = email_consent_forms(request, background, db, principal, project, added)
        for r in rows:
            if r.participant_id is not None:
                r.message = f"{r.message}. {sent[r.participant_id]}"
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
    target, results = manage.bulk(
        db,
        principal,
        project_id,
        body.action,
        body.participant_ids,
        body.target_project_id,
        body.reason,
        client_ip(request),
    )
    if target is not None:
        # Assigned to another project: they get that project's consent form (D-129); or the
        # chosen people get this project's form again (D-139).
        chosen = [r.participant_id for r in results if r.ok]
        sent = email_consent_forms(request, background, db, principal, target, chosen)
        for r in results:
            if r.ok:
                r.message = ". ".join(x for x in (r.message, sent[r.participant_id]) if x)
    return BulkOut(
        results=[BulkRow.model_validate(r, from_attributes=True) for r in results],
        done=sum(1 for r in results if r.ok),
        failed=sum(1 for r in results if not r.ok),
    )


# ---------------------------------------------------------------- one consent form (D-074)


class AnswerOut(BaseModel):
    status: ConsentStatus
    answered_at: datetime
    policy_version: str


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
