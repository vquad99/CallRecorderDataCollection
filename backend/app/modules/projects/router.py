"""/api/v1/projects (PROJ-*). Permission + membership checks live in the service."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AfterValidator, BaseModel, Field

from app.core.permissions import Perm
from app.modules.auth.deps import CurrentPrincipal, DbSession, client_ip, require
from app.modules.projects import service
from app.modules.projects.models import ASSET_KINDS, Project

# Every project route needs projects.view; finer checks and membership live in the service.
router = APIRouter(
    prefix="/projects", tags=["projects"], dependencies=[Depends(require(Perm.PROJECTS_VIEW))]
)

# Percentages and hour targets always travel with two decimals, whether just saved or re-read.
TwoPlaces = Annotated[Decimal, AfterValidator(lambda v: v.quantize(Decimal("0.01")))]

Status = Literal["DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"]
Mode = Literal["TELEPHONY", "FACE_TO_FACE"]
AssetKind = Literal[
    "PROVIDER_ORIGINAL_TRACK",
    "PROVIDER_ORIGINAL_MIXED",
    "TELEPHONY_FINAL_STEREO",
    "CONSENT_RECORDING",
    "BROWSER_ORIGINAL",
    "FTF_DERIVED_PCM",
    "TRANSCRIPT_FILE",
    "EXPORT_PACKAGE",
]


class LanguageOut(BaseModel):
    language_code: str
    dialect: str


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


class ProjectPage(BaseModel):
    items: list[ProjectSummary]
    total: int
    page: int
    page_size: int


@router.get("", response_model=ProjectPage)
def list_projects(
    principal: CurrentPrincipal,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
    status: Status | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
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

    def to_input(self) -> service.ProjectInput:
        return service.ProjectInput(**self.model_dump())


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
    languages: list[LanguageOut] = Field(max_length=100)


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
        for m, u in service.list_members(db, principal, project_id)
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
