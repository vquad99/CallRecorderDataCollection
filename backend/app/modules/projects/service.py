"""Project management (PROJ-*). Super Admin sees every project; others only member projects."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm, Role
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import RoleRecord, User, UserRole
from app.modules.projects.models import (
    Project,
    ProjectAudioRule,
    ProjectLanguage,
    ProjectMembership,
    ProjectRetentionRule,
)

# Allowed lifecycle moves (PROJ-009). Reopening a completed or archived project needs a reason.
TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"ACTIVE", "ARCHIVED"},
    "ACTIVE": {"PAUSED", "COMPLETED", "ARCHIVED"},
    "PAUSED": {"ACTIVE", "ARCHIVED"},
    "COMPLETED": {"ACTIVE", "ARCHIVED"},
    "ARCHIVED": {"ACTIVE"},
}
REASON_REQUIRED = {
    ("ARCHIVED", "ACTIVE"),
    ("COMPLETED", "ACTIVE"),
    ("ACTIVE", "ARCHIVED"),
    ("PAUSED", "ARCHIVED"),
}

# Format defaults come from the specification (spec 4.1 / 4.2). Silence 25 % is the spec's initial
# QC rule (QC-001). No clipping or duration limit is invented: they stay unset until configured.
# Telephony: one channel (D-103). The specification asked for A-left/B-right stereo, but the phone
# provider in use (TxContact, D-101) records the whole call together; with 2 here every phone
# recording failed the automatic check and QC had to justify each pass. A project sets 2 on its
# Audio rules tab once the provider delivers one speaker per channel.
DEFAULT_AUDIO = {
    "TELEPHONY": {"sample_rate": 16000, "bit_depth": 16, "channels": 1},
    "FACE_TO_FACE": {"sample_rate": 16000, "bit_depth": 16, "channels": 1},
}
DEFAULT_MAX_SILENCE_PCT = Decimal("25")


def not_found() -> AppError:
    return AppError("Project not found", code="NOT_FOUND", status_code=404)


def visible_projects_query(principal: Principal):  # type: ignore[no-untyped-def]
    query = select(Project)
    if not principal.is_super_admin:
        query = query.where(Project.id.in_(principal.project_ids or [uuid.UUID(int=0)]))
    return query


def get_visible(db: Session, principal: Principal, project_id: uuid.UUID) -> Project:
    """404 for projects the caller is not a member of (no existence leak)."""
    if not principal.can(Perm.PROJECTS_VIEW):
        raise forbidden()
    project = db.get(Project, project_id)
    if project is None or not (principal.is_super_admin or project.id in principal.project_ids):
        raise not_found()
    return project


def get_manageable(
    db: Session, principal: Principal, project_id: uuid.UUID, perm: Perm = Perm.PROJECTS_MANAGE
) -> Project:
    project = get_visible(db, principal, project_id)
    if not principal.can_in_project(perm, project.id):
        raise forbidden()
    return project


def ensure_accepts_new_work(project: Project) -> None:
    """Called before any new task or recording is created for a project (PROJ-010)."""
    if project.status != "ACTIVE":
        raise AppError(
            f"Project {project.code} is {project.status.lower()} and cannot receive new work",
            code="PROJECT_NOT_ACCEPTING_WORK",
            status_code=409,
        )


def list_projects(
    db: Session,
    principal: Principal,
    *,
    search: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Project], int]:
    if not principal.can(Perm.PROJECTS_VIEW):
        raise forbidden()
    query = visible_projects_query(principal)
    if search:
        like = f"%{search.strip().lower()}%"
        query = query.where(
            or_(func.lower(Project.code).like(like), func.lower(Project.name).like(like))
        )
    if status:
        query = query.where(Project.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Project.code).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), int(total)


@dataclass(frozen=True)
class ProjectInput:
    name: str
    description: str
    allows_telephony: bool
    allows_face_to_face: bool
    target_telephony_hours_per_day: Decimal
    target_face_to_face_hours_per_day: Decimal
    phone_visibility_policy: str
    consent_policy_version: str
    consent_text: str = ""


def _check_modes(data: ProjectInput) -> None:
    if not (data.allows_telephony or data.allows_face_to_face):
        raise AppError("Allow at least one recording mode", code="MODE_REQUIRED", status_code=422)
    if not data.allows_telephony and data.target_telephony_hours_per_day > 0:
        raise AppError(
            "Telephony target needs telephony allowed", code="MODE_NOT_ALLOWED", status_code=422
        )
    if not data.allows_face_to_face and data.target_face_to_face_hours_per_day > 0:
        raise AppError(
            "Face-to-face target needs face-to-face allowed",
            code="MODE_NOT_ALLOWED",
            status_code=422,
        )


def _snapshot(p: Project) -> dict[str, object]:
    return {
        "name": p.name,
        "description": p.description,
        "allows_telephony": p.allows_telephony,
        "allows_face_to_face": p.allows_face_to_face,
        "target_telephony_hours_per_day": str(p.target_telephony_hours_per_day),
        "target_face_to_face_hours_per_day": str(p.target_face_to_face_hours_per_day),
        "phone_visibility_policy": p.phone_visibility_policy,
        "consent_policy_version": p.consent_policy_version,
        "consent_text": p.consent_text,
    }


def _ensure_default_audio_rules(project: Project) -> None:
    have = {r.mode for r in project.audio_rules}
    for mode, allowed in (
        ("TELEPHONY", project.allows_telephony),
        ("FACE_TO_FACE", project.allows_face_to_face),
    ):
        if allowed and mode not in have:
            project.audio_rules.append(
                ProjectAudioRule(
                    mode=mode,
                    **DEFAULT_AUDIO[mode],
                    max_silence_pct=DEFAULT_MAX_SILENCE_PCT,
                    max_clipping_pct=None,
                    min_duration_seconds=0,
                    max_duration_seconds=None,
                )
            )


def next_project_code(db: Session) -> str:
    """The next free PRJnnnn code; skips a number someone already typed by hand (D-083)."""
    while True:
        code = f"PRJ{db.scalar(text("SELECT nextval('project_code_seq')")):04d}"
        if not db.scalar(select(Project.id).where(Project.code == code)):
            return code


def create_project(
    db: Session, principal: Principal, code: str | None, data: ProjectInput, ip: str | None
) -> Project:
    if not principal.can(Perm.PROJECTS_CREATE):
        raise forbidden()
    code = code.strip().upper() if code else next_project_code(db)
    if db.scalar(select(Project.id).where(Project.code == code)):
        raise AppError(
            "A project with this code already exists", code="PROJECT_CODE_TAKEN", status_code=409
        )
    _check_modes(data)
    project = Project(
        id=uuid.uuid4(), code=code, status="DRAFT", created_by=principal.user_id, **data.__dict__
    )
    project.audio_rules = []
    _ensure_default_audio_rules(project)
    db.add(project)
    audit.record(
        db,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"code": code, **_snapshot(project)},
    )
    db.commit()
    return project


def update_project(
    db: Session, principal: Principal, project_id: uuid.UUID, data: ProjectInput, ip: str | None
) -> Project:
    project = get_manageable(db, principal, project_id)
    if project.status == "ARCHIVED":
        raise AppError(
            "Reopen the project before editing it", code="PROJECT_ARCHIVED", status_code=409
        )
    _check_modes(data)
    before = _snapshot(project)
    for key, value in data.__dict__.items():
        setattr(project, key, value)
    _ensure_default_audio_rules(project)
    after = _snapshot(project)
    if after != before:
        audit.record(
            db,
            action="project.updated",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            actor_id=principal.user_id,
            ip=ip,
            before=before,
            after=after,
        )
    db.commit()
    return project


def change_status(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    new_status: str,
    reason: str | None,
    ip: str | None,
) -> Project:
    project = get_manageable(db, principal, project_id)
    old = project.status
    if new_status not in TRANSITIONS.get(old, set()):
        raise AppError(
            f"Cannot change status from {old} to {new_status}",
            code="INVALID_TRANSITION",
            status_code=409,
        )
    if (old, new_status) in REASON_REQUIRED and not (reason and reason.strip()):
        raise AppError(
            "A reason is required for this change", code="REASON_REQUIRED", status_code=422
        )
    project.status = new_status
    project.status_reason = reason.strip() if reason else None
    project.status_changed_at = datetime.now(UTC)
    audit.record(
        db,
        action="project.status_changed",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        before={"status": old},
        after={"status": new_status, "reason": project.status_reason},
    )
    db.commit()
    return project


def set_languages(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    entries: list[tuple[str, str]],
    ip: str | None,
) -> Project:
    project = get_manageable(db, principal, project_id)
    unique = sorted({(code.strip(), dialect.strip()) for code, dialect in entries})
    before = sorted((lang.language_code, lang.dialect) for lang in project.languages)
    # Keep the rows that stay: replacing them would insert a duplicate before the old row is
    # deleted (the unit of work inserts first) and fail on the unique key.
    current = {(lang.language_code, lang.dialect): lang for lang in project.languages}
    project.languages = [
        current.get((c, d)) or ProjectLanguage(language_code=c, dialect=d) for c, d in unique
    ]
    audit.record(
        db,
        action="project.languages_changed",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        before={"languages": before},
        after={"languages": unique},
    )
    db.commit()
    return project


@dataclass(frozen=True)
class AudioRuleInput:
    mode: str
    sample_rate: int
    bit_depth: int
    channels: int
    max_silence_pct: Decimal
    max_clipping_pct: Decimal | None
    min_duration_seconds: int
    max_duration_seconds: int | None


def set_audio_rules(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    rules: list[AudioRuleInput],
    ip: str | None,
) -> Project:
    project = get_manageable(db, principal, project_id)
    allowed = {
        m
        for m, ok in (
            ("TELEPHONY", project.allows_telephony),
            ("FACE_TO_FACE", project.allows_face_to_face),
        )
        if ok
    }
    modes = [r.mode for r in rules]
    if len(set(modes)) != len(modes):
        raise AppError("Each mode may appear once", code="DUPLICATE_MODE", status_code=422)
    if set(modes) != allowed:
        raise AppError(
            f"Give exactly one rule per allowed mode: {', '.join(sorted(allowed))}",
            code="MODE_NOT_ALLOWED",
            status_code=422,
        )
    for r in rules:
        if r.max_duration_seconds is not None and r.max_duration_seconds < r.min_duration_seconds:
            raise AppError(
                "Maximum duration is below the minimum", code="INVALID_DURATION", status_code=422
            )
    before = [
        {"mode": a.mode, "sample_rate": a.sample_rate, "channels": a.channels}
        for a in project.audio_rules
    ]
    existing = {a.mode: a for a in project.audio_rules}
    for r in rules:
        target = existing.get(r.mode)
        if target is None:
            project.audio_rules.append(ProjectAudioRule(**r.__dict__))
        else:
            for key, value in r.__dict__.items():
                setattr(target, key, value)
    audit.record(
        db,
        action="project.audio_rules_changed",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        before={"rules": before},
        after={"rules": [{k: str(v) for k, v in r.__dict__.items()} for r in rules]},
    )
    db.commit()
    return project


def set_retention(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    rules: list[tuple[str, int]],
    ip: str | None,
) -> Project:
    project = get_manageable(db, principal, project_id)
    kinds = [k for k, _ in rules]
    if len(set(kinds)) != len(kinds):
        raise AppError("Each asset kind may appear once", code="DUPLICATE_KIND", status_code=422)
    before = {r.asset_kind: r.retain_days for r in project.retention_rules}
    current = {r.asset_kind: r for r in project.retention_rules}
    kept = []
    for kind, days in rules:  # update rows in place for the same reason as set_languages
        row = current.get(kind) or ProjectRetentionRule(asset_kind=kind, retain_days=days)
        row.retain_days = days
        kept.append(row)
    project.retention_rules = kept
    audit.record(
        db,
        action="project.retention_changed",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        before=before,
        after=dict(rules),
    )
    db.commit()
    return project


def list_members(
    db: Session, principal: Principal, project_id: uuid.UUID
) -> list[tuple[ProjectMembership, User]]:
    project = get_visible(db, principal, project_id)
    rows = db.execute(
        select(ProjectMembership, User)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.project_id == project.id)
        .order_by(User.email)
    ).all()
    return [(m, u) for m, u in rows]


def add_member(
    db: Session, principal: Principal, project_id: uuid.UUID, user_id: uuid.UUID, ip: str | None
) -> None:
    project = get_manageable(db, principal, project_id, Perm.PROJECTS_MEMBERS)
    user = db.get(User, user_id)
    if user is None:
        raise AppError("User not found", code="NOT_FOUND", status_code=404)
    if user.status != "ACTIVE":
        raise AppError("Disabled users cannot be added", code="USER_DISABLED", status_code=409)
    exists = db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.project_id == project.id, ProjectMembership.user_id == user.id
        )
    )
    if exists:
        raise AppError("Already a member", code="ALREADY_MEMBER", status_code=409)
    db.add(ProjectMembership(project_id=project.id, user_id=user.id, added_by=principal.user_id))
    audit.record(
        db,
        action="project.member_added",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"user_id": str(user.id), "email": user.email},
    )
    db.commit()


def remove_member(
    db: Session, principal: Principal, project_id: uuid.UUID, user_id: uuid.UUID, ip: str | None
) -> None:
    project = get_manageable(db, principal, project_id, Perm.PROJECTS_MEMBERS)
    membership = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project.id, ProjectMembership.user_id == user_id
        )
    )
    if membership is None:
        raise AppError("Not a member", code="NOT_FOUND", status_code=404)
    db.delete(membership)
    audit.record(
        db,
        action="project.member_removed",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        before={"user_id": str(user_id)},
    )
    db.commit()


def member_candidates(
    db: Session, principal: Principal, project_id: uuid.UUID, search: str | None, limit: int = 20
) -> list[User]:
    """Active users who are not yet members, for the team picker (needs projects.members).

    A Super Admin may search by part of a name or email. Anyone else must type the person's full
    email address, so the picker cannot be used to list every account on the platform (security
    review 2026-11-10), and Super Admins are never offered (they see every project already).
    """
    project = get_manageable(db, principal, project_id, Perm.PROJECTS_MEMBERS)
    query = select(User).where(
        User.status == "ACTIVE",
        User.id.not_in(
            select(ProjectMembership.user_id).where(ProjectMembership.project_id == project.id)
        ),
    )
    if principal.is_super_admin:
        if search:
            like = f"%{search.strip().lower()}%"
            query = query.where(
                or_(User.email.like(like), func.lower(User.display_name).like(like))
            )
    else:
        wanted = (search or "").strip().lower()
        if "@" not in wanted:
            return []
        super_admins = (
            select(UserRole.user_id)
            .join(RoleRecord)
            .where(RoleRecord.code == Role.SUPER_ADMIN.value)
        )
        query = query.where(User.email == wanted, User.id.not_in(super_admins))
    return list(db.scalars(query.order_by(User.email).limit(limit)).all())
