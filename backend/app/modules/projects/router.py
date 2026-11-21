"""/api/v1/projects (PROJ-*). Permission + membership checks live in the service."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.errors import forbidden
from app.core.permissions import Perm
from app.db.paging import Page, PageNumber, PageSize
from app.modules.audio_qc import checklist
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.participants.models import MAX_AGE, MIN_AGE
from app.modules.projects import progress, service, targets
from app.modules.projects.models import (
    DEFAULT_REQUIRED_SPEAKER_DETAILS,
    DEFAULT_SPEAKER_MAX_AGE,
    DEFAULT_SPEAKER_MIN_AGE,
    Project,
)
from app.modules.recordings.models import ASSET_KINDS

# Every project route needs projects.view; finer checks and membership live in the service.
router = APIRouter(
    prefix="/projects", tags=["projects"], dependencies=[Depends(require(Perm.PROJECTS_VIEW))]
)

# Percentages and hour targets always travel with two decimals, whether just saved or re-read.
TwoPlaces = Annotated[Decimal, AfterValidator(lambda v: v.quantize(Decimal("0.01")))]

Status = Literal["DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"]
Mode = Literal["TELEPHONY", "FACE_TO_FACE"]
ConsentMode = Literal["ONLINE", "UPLOAD"]
AssetKind = Literal[
    "PROVIDER_ORIGINAL_TRACK",
    "PROVIDER_ORIGINAL_MIXED",
    "TELEPHONY_FINAL_STEREO",
    "CONSENT_RECORDING",
    "BROWSER_ORIGINAL",
    "FTF_DERIVED_PCM",
    "TELEPHONY_DERIVED_PCM",
    "TRANSCRIPT_FILE",
    "EXPORT_PACKAGE",
]


class LanguageOut(BaseModel):
    language_code: str
    dialect: str


class LanguageIn(BaseModel):
    # Checked like a participant's own language and dialect (D-088): the dialect reaches the
    # participant export, so it is short, plain text.
    language_code: str = Field(max_length=35, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
    dialect: str = Field(default="", max_length=100)


class AudioRuleIO(BaseModel):
    mode: Mode
    sample_rate: int = Field(ge=8000, le=192000)
    bit_depth: Literal[16, 24, 32]
    channels: Literal[1, 2]
    max_silence_pct: TwoPlaces = Field(ge=0, le=100)
    max_clipping_pct: TwoPlaces | None = Field(default=None, ge=0, le=100)
    min_duration_seconds: int = Field(ge=0, le=86400)
    max_duration_seconds: int | None = Field(default=None, ge=1, le=86400)


class RetentionIO(BaseModel):
    asset_kind: AssetKind
    retain_days: int = Field(ge=1, le=36500)


class ChecklistItemIO(BaseModel):
    """One question of the QC checklist (D-146, audio_qc/checklist.py); the key's format and that
    each key is used once are checked by the service (422 INVALID_QC_CHECKLIST)."""

    key: str = Field(min_length=1, max_length=checklist.MAX_KEY)
    question: str = Field(min_length=1, max_length=checklist.MAX_QUESTION)
    scope: Literal["conversation", "speaker"]
    # The answer that fails the recording; null = an observation, recorded, never failing.
    fails_on: Literal["yes", "no"] | None
    required: bool = True


# A reminder line as sent; the service holds it to moderation.MAX_REMINDER_LINE (422
# INVALID_REMINDERS), this only bounds the request.
ReminderLine = Annotated[str, Field(max_length=1000)]
ReminderLines = Annotated[list[ReminderLine], Field(max_length=100)]


class RemindersIO(BaseModel):
    """What the moderator reads before recording and calling (D-147, projects/moderation.py):
    whether to ask each speaker to say their first name and speaker ID, what to talk about, what
    to avoid, and the tips for face-to-face and for phone calls; one line per entry."""

    speaker_id: bool = True
    topics: ReminderLines = []
    avoid: ReminderLines = []
    face_to_face: ReminderLines = []
    telephony: ReminderLines = []


class AgeBandIO(BaseModel):
    """One age band of the targets (D-148): ages from `from` up to, but not including, `to` (the
    band that ends highest also takes `to`), and the percent of speakers wanted in it."""

    model_config = ConfigDict(populate_by_name=True)

    from_: int = Field(alias="from", ge=MIN_AGE, le=MAX_AGE)
    to: int = Field(ge=MIN_AGE, le=MAX_AGE)
    percent: int = Field(ge=0, le=100)


class DistrictIO(BaseModel):
    """A district the speakers should come from (D-148): a state of India and a district."""

    state: str = Field(min_length=1, max_length=60)
    district: str = Field(min_length=1, max_length=200)


# Percents by gender (MALE, FEMALE) or by recording type (FACE_TO_FACE, TELEPHONY); {} = no
# target. The service checks the keys and that they add up to 100 (422 INVALID_TARGETS).
Shares = Annotated[dict[Annotated[str, Field(max_length=20)], int], Field(max_length=10)]
ProgressCounts = Literal["EFFECTIVE", "FULL"]


class ProjectSummary(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: Status
    allows_telephony: bool
    allows_face_to_face: bool
    target_telephony_hours_per_day: TwoPlaces
    target_face_to_face_hours_per_day: TwoPlaces
    created_at: datetime


class ProjectDetail(ProjectSummary):
    description: str
    phone_visibility_policy: str
    consent_policy_version: str
    consent_text: str
    qc_final_approval: bool
    max_conversations_per_speaker: int | None
    unique_pairs: bool
    consent_mode: ConsentMode
    speaker_min_age: int
    speaker_max_age: int
    required_speaker_details: list[str]
    qc_checklist: list[ChecklistItemIO]
    device_fields: list[str]
    recording_reminders: RemindersIO
    pause_limit_seconds: int
    long_pauses_need_review: bool
    progress_counts: ProgressCounts
    target_hours: TwoPlaces | None
    target_speakers: int | None
    target_conversations: int | None
    target_age_bands: list[AgeBandIO]
    target_gender: dict[str, int]
    target_modes: dict[str, int]
    target_districts: list[DistrictIO]
    status_reason: str | None
    status_changed_at: datetime | None
    languages: list[LanguageOut]
    audio_rules: list[AudioRuleIO]
    retention_rules: list[RetentionIO]
    accepts_new_work: bool


def summary(p: Project) -> ProjectSummary:
    return ProjectSummary.model_validate(p, from_attributes=True)


def detail(p: Project) -> ProjectDetail:
    return ProjectDetail(
        **summary(p).model_dump(),
        description=p.description,
        phone_visibility_policy=p.phone_visibility_policy,
        consent_policy_version=p.consent_policy_version,
        consent_text=p.consent_text,
        qc_final_approval=p.qc_final_approval,
        max_conversations_per_speaker=p.max_conversations_per_speaker,
        unique_pairs=p.unique_pairs,
        consent_mode=p.consent_mode,
        speaker_min_age=p.speaker_min_age,
        speaker_max_age=p.speaker_max_age,
        required_speaker_details=list(p.required_speaker_details),
        qc_checklist=[ChecklistItemIO.model_validate(i) for i in p.qc_checklist],
        device_fields=list(p.device_fields),
        recording_reminders=RemindersIO.model_validate(p.recording_reminders),
        pause_limit_seconds=p.pause_limit_seconds,
        long_pauses_need_review=p.long_pauses_need_review,
        progress_counts=p.progress_counts,
        target_hours=p.target_hours,
        target_speakers=p.target_speakers,
        target_conversations=p.target_conversations,
        target_age_bands=[AgeBandIO.model_validate(b) for b in p.target_age_bands],
        target_gender=dict(p.target_gender),
        target_modes=dict(p.target_modes),
        target_districts=[DistrictIO.model_validate(d) for d in p.target_districts],
        status_reason=p.status_reason,
        status_changed_at=p.status_changed_at,
        languages=[
            LanguageOut(language_code=x.language_code, dialect=x.dialect) for x in p.languages
        ],
        audio_rules=[AudioRuleIO.model_validate(r, from_attributes=True) for r in p.audio_rules],
        retention_rules=[
            RetentionIO.model_validate(r, from_attributes=True) for r in p.retention_rules
        ],
        accepts_new_work=p.status == "ACTIVE",
    )


class ProjectPage(Page[ProjectSummary]):
    pass


@router.get("", response_model=ProjectPage)
def list_projects(
    principal: CurrentPrincipal,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
    status: Status | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> ProjectPage:
    items, total = service.list_projects(
        db, principal, search=search, status=status, page=page, page_size=page_size
    )
    return ProjectPage(
        items=[summary(p) for p in items], total=total, page=page, page_size=page_size
    )


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    allows_telephony: bool
    allows_face_to_face: bool
    target_telephony_hours_per_day: Decimal = Field(default=Decimal(0), ge=0, le=10000)
    target_face_to_face_hours_per_day: Decimal = Field(default=Decimal(0), ge=0, le=10000)
    phone_visibility_policy: Literal["ADMINS_ONLY", "ASSIGNED_MODERATOR"] = "ADMINS_ONLY"
    consent_policy_version: str = Field(default="1", min_length=1, max_length=50)
    consent_text: str = Field(default="", max_length=20_000)
    qc_final_approval: bool = False
    # Task rules (D-143): null = no limit on conversations per speaker.
    max_conversations_per_speaker: int | None = Field(default=3, ge=1, le=1000)
    unique_pairs: bool = True
    # How participants give consent (D-144): ONLINE on their personal page, or UPLOAD, a scanned
    # signed form uploaded by staff.
    consent_mode: ConsentMode = "ONLINE"
    # Speaker rules (D-145), set on the project's Rules tab: the ages it takes (any person is 1
    # to 120) and the speaker details needed before a task (field names, participants/speakers.py).
    speaker_min_age: int = Field(default=DEFAULT_SPEAKER_MIN_AGE, ge=MIN_AGE, le=MAX_AGE)
    speaker_max_age: int = Field(default=DEFAULT_SPEAKER_MAX_AGE, ge=MIN_AGE, le=MAX_AGE)
    required_speaker_details: list[Annotated[str, Field(max_length=40)]] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SPEAKER_DETAILS), max_length=50
    )
    # The QC checklist (D-146), set on the Rules tab. Left out: a new project gets the first
    # client's list, and a change keeps the project's own.
    qc_checklist: list[ChecklistItemIO] | None = Field(default=None, max_length=checklist.MAX_ITEMS)
    # What the moderator fills and reads (D-147), set on the Rules tab: the device details asked
    # for each speaker (names from projects/moderation.DEVICE_FIELDS) and the reminders. Left
    # out: a new project gets the first client's, and a change keeps the project's own.
    device_fields: list[Annotated[str, Field(max_length=40)]] | None = Field(
        default=None, max_length=20
    )
    recording_reminders: RemindersIO | None = None
    # Audio and progress (D-148), set on the Rules tab: a silent stretch inside the speech longer
    # than this is a long pause; long pauses ask QC for a listen; what completed minutes count.
    pause_limit_seconds: int = Field(
        default=targets.DEFAULT_PAUSE_LIMIT_SECONDS,
        ge=targets.PAUSE_LIMIT_RANGE[0],
        le=targets.PAUSE_LIMIT_RANGE[1],
    )
    long_pauses_need_review: bool = False
    progress_counts: ProgressCounts = "EFFECTIVE"
    # Targets (D-148), set on the Rules tab; null = no target. The shares left out: a new project
    # gets the first client's, and a change keeps the project's own.
    target_hours: Decimal | None = Field(default=None, ge=0, le=1_000_000, decimal_places=2)
    target_speakers: int | None = Field(
        default=targets.DEFAULT_TARGET_SPEAKERS, ge=1, le=10_000_000
    )
    target_conversations: int | None = Field(
        default=targets.DEFAULT_TARGET_CONVERSATIONS, ge=1, le=10_000_000
    )
    target_age_bands: list[AgeBandIO] | None = Field(default=None, max_length=targets.MAX_BANDS)
    target_gender: Shares | None = None
    target_modes: Shares | None = None
    target_districts: list[DistrictIO] | None = Field(
        default=None, max_length=targets.MAX_DISTRICTS
    )

    def to_input(self) -> service.ProjectInput:
        values = self.model_dump()
        values["required_speaker_details"] = tuple(values["required_speaker_details"])
        for name in ("qc_checklist", "device_fields", "target_districts"):
            if values[name] is not None:
                values[name] = tuple(values[name])
        if self.target_age_bands is not None:
            values["target_age_bands"] = tuple(
                b.model_dump(by_alias=True) for b in self.target_age_bands
            )
        return service.ProjectInput(**values)


class CreateProjectBody(ProjectBody):
    # Left out, the platform gives the next free code: PRJ0001, PRJ0002, ... (D-083).
    code: str | None = Field(
        default=None, min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$"
    )


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(
    body: CreateProjectBody, request: Request, principal: CurrentPrincipal, db: DbSession
) -> ProjectDetail:
    data = ProjectBody(**body.model_dump(exclude={"code"})).to_input()
    return detail(service.create_project(db, principal, body.code, data, client_ip(request)))


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> ProjectDetail:
    return detail(service.get_visible(db, principal, project_id))


@router.get("/{project_id}/progress", response_model=progress.Progress)
def project_progress(
    project_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> progress.Progress:
    """The Progress tab (D-148): completed minutes, conversations and speakers against the
    project's targets; for the people who manage the project (others 403, D-104)."""
    return progress.progress(db, principal, project_id)


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: uuid.UUID,
    body: ProjectBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ProjectDetail:
    return detail(
        service.update_project(db, principal, project_id, body.to_input(), client_ip(request))
    )


class StatusBody(BaseModel):
    status: Status
    reason: str | None = Field(default=None, max_length=1000)


@router.post("/{project_id}/status", response_model=ProjectDetail)
def change_status(
    project_id: uuid.UUID,
    body: StatusBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ProjectDetail:
    return detail(
        service.change_status(
            db, principal, project_id, body.status, body.reason, client_ip(request)
        )
    )


class LanguagesBody(BaseModel):
    languages: list[LanguageIn] = Field(max_length=100)


@router.put("/{project_id}/languages", response_model=ProjectDetail)
def set_languages(
    project_id: uuid.UUID,
    body: LanguagesBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ProjectDetail:
    entries = [(x.language_code, x.dialect) for x in body.languages]
    return detail(service.set_languages(db, principal, project_id, entries, client_ip(request)))


class AudioRulesBody(BaseModel):
    rules: list[AudioRuleIO] = Field(min_length=1, max_length=2)


@router.put("/{project_id}/audio-rules", response_model=ProjectDetail)
def set_audio_rules(
    project_id: uuid.UUID,
    body: AudioRulesBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ProjectDetail:
    rules = [service.AudioRuleInput(**r.model_dump()) for r in body.rules]
    return detail(service.set_audio_rules(db, principal, project_id, rules, client_ip(request)))


class RetentionBody(BaseModel):
    rules: list[RetentionIO] = Field(max_length=len(ASSET_KINDS))


@router.put("/{project_id}/retention", response_model=ProjectDetail)
def set_retention(
    project_id: uuid.UUID,
    body: RetentionBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ProjectDetail:
    rules: list[tuple[str, int]] = [(str(r.asset_kind), r.retain_days) for r in body.rules]
    return detail(service.set_retention(db, principal, project_id, rules, client_ip(request)))


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str | None  # only for people who manage the team (security review 2026-11-10)
    display_name: str
    roles: list[str]
    status: str
    added_at: datetime


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(
    project_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[MemberOut]:
    """The project's team, for the people who run it (D-112): moderators, QC and clients see
    their own work, not who else works on the project."""
    members = service.list_members(db, principal, project_id)  # 404 for a project not theirs
    if not principal.can_in_project(Perm.TASKS_ASSIGN, project_id):
        raise forbidden()
    show_email = principal.can_in_project(Perm.PROJECTS_MEMBERS, project_id)
    return [
        MemberOut(
            user_id=u.id,
            email=u.email if show_email else None,
            display_name=u.display_name,
            roles=sorted(r.code for r in u.roles),
            status=u.status,
            added_at=m.created_at,
        )
        for m, u in members
    ]


class CandidateOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    roles: list[str]


@router.get("/{project_id}/member-candidates", response_model=list[CandidateOut])
def member_candidates(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> list[CandidateOut]:
    return [
        CandidateOut(
            user_id=u.id,
            email=u.email,
            display_name=u.display_name,
            roles=sorted(r.code for r in u.roles),
        )
        for u in service.member_candidates(db, principal, project_id, search)
    ]


class MemberBody(BaseModel):
    user_id: uuid.UUID


@router.post("/{project_id}/members", status_code=204)
def add_member(
    project_id: uuid.UUID,
    body: MemberBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> None:
    service.add_member(db, principal, project_id, body.user_id, client_ip(request))


@router.delete("/{project_id}/members/{user_id}", status_code=204)
def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> None:
    service.remove_member(db, principal, project_id, user_id, client_ip(request))
