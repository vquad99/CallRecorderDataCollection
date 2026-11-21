"""Project management (PROJ-*). Super Admin sees every project; others only member projects."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm, Role
from app.db.paging import paginate
from app.modules.audio_qc import checklist
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, in_projects
from app.modules.auth.models import RoleRecord, User, UserRole
from app.modules.participants import speakers
from app.modules.projects import delivery, moderation, targets
from app.modules.projects.models import (
    DEFAULT_REQUIRED_SPEAKER_DETAILS,
    DEFAULT_SPEAKER_MAX_AGE,
    DEFAULT_SPEAKER_MIN_AGE,
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
# Telephony: stereo (D-134). TxContact (D-101) delivers its recordings as WAV, 16 kHz, stereo, and
# the delivery file keeps both channels; with 1 here every phone recording failed the automatic
# check. Face-to-face stays mono: the recorder keeps one channel (D-041).
DEFAULT_AUDIO = {
    "TELEPHONY": {"sample_rate": 16000, "bit_depth": 16, "channels": 2},
    "FACE_TO_FACE": {"sample_rate": 16000, "bit_depth": 16, "channels": 1},
}
DEFAULT_MAX_SILENCE_PCT = Decimal("25")


def visible_projects_query(principal: Principal) -> Select[Project]:
    return select(Project).where(in_projects(principal, Project.id))


def get_visible(db: Session, principal: Principal, project_id: uuid.UUID) -> Project:
    """404 for projects the caller is not a member of (no existence leak)."""
    if not principal.can(Perm.PROJECTS_VIEW):
        raise forbidden()
    project = db.get(Project, project_id)
    if project is None or not (principal.is_super_admin or project.id in principal.project_ids):
        raise not_found("Project")
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
    if search and search.strip():
        term = search.strip()
        query = query.where(
            or_(
                Project.code.icontains(term, autoescape=True),
                Project.name.icontains(term, autoescape=True),
            )
        )
    if status:
        query = query.where(Project.status == status)
    return paginate(
        db, query.order_by(Project.created_at.desc(), Project.code.desc()), page, page_size
    )


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
    # A QC pass approves the task, with no admin review (D-138). Tasks already waiting for admin
    # review stay there when this changes.
    qc_final_approval: bool = False
    # Task rules (D-143): at most this many conversations per speaker (None = no limit), and
    # each pair of speakers only once. They apply to tasks made from now on.
    max_conversations_per_speaker: int | None = 3
    unique_pairs: bool = True
    # ONLINE or UPLOAD (D-144): how participants give consent. Changing it changes nothing
    # already stored; an uploaded form counts only while the project is UPLOAD.
    consent_mode: str = "ONLINE"
    # Speaker rules (D-145): the ages the project takes and the speaker details a person needs
    # before a task (participants/speakers.py). People already in the project keep their
    # details; the rules are checked when someone joins, is corrected or is put on a task.
    speaker_min_age: int = DEFAULT_SPEAKER_MIN_AGE
    speaker_max_age: int = DEFAULT_SPEAKER_MAX_AGE
    required_speaker_details: tuple[str, ...] = DEFAULT_REQUIRED_SPEAKER_DETAILS
    # The QC checklist (D-146): None keeps the project's own (a new project gets the first
    # client's list). Decisions already made keep the questions as they read then.
    qc_checklist: tuple[dict[str, Any], ...] | None = None
    # What the moderator fills and reads (D-147): the device details asked for each speaker and
    # the reminders shown before recording. None keeps the project's own (a new project gets the
    # first client's); details already filled stay as they are.
    device_fields: tuple[str, ...] | None = None
    recording_reminders: dict[str, Any] | None = None
    # Audio and progress (D-148, projects/targets.py): the pause limit, whether long pauses ask QC
    # for a listen, and what counts as completed minutes (EFFECTIVE or FULL).
    pause_limit_seconds: int = targets.DEFAULT_PAUSE_LIMIT_SECONDS
    long_pauses_need_review: bool = False
    progress_counts: str = targets.DEFAULT_PROGRESS_COUNTS
    # Targets (D-148): None = no target. The shares are kept when left out, like the checklist (a
    # new project gets the first client's).
    target_hours: Decimal | None = None
    target_speakers: int | None = targets.DEFAULT_TARGET_SPEAKERS
    target_conversations: int | None = targets.DEFAULT_TARGET_CONVERSATIONS
    target_age_bands: tuple[dict[str, Any], ...] | None = None
    target_gender: dict[str, Any] | None = None
    target_modes: dict[str, Any] | None = None
    target_districts: tuple[dict[str, Any], ...] | None = None
    # How exports are laid out and named (D-149, projects/delivery.py): None keeps the project's
    # own (a new project gets the client's delivery format). Exports already made stay as made.
    export_layout: str | None = None
    speaker_id_style: str | None = None
    conversation_id_style: str | None = None
    audio_name_pattern: str | None = None


def _one_of(choices: tuple[str, ...]) -> Callable[[Any], object]:
    """A choice the API has already held to these values (a Literal), kept as it is."""

    def clean(value: Any) -> object:
        if value not in choices:
            raise AppError(
                f"Choose one of: {', '.join(choices)}", code="VALIDATION_ERROR", status_code=422
            )
        return value

    return clean


# Settings a PATCH that leaves them out keeps (D-146, D-147, D-148, D-149), with how each is
# checked.
_KEPT_WHEN_LEFT_OUT: dict[str, Callable[[Any], object]] = {
    "qc_checklist": checklist.clean,
    "device_fields": moderation.clean_device_fields,
    "recording_reminders": moderation.clean_reminders,
    "target_age_bands": targets.clean_age_bands,
    "target_gender": targets.clean_gender,
    "target_modes": targets.clean_modes,
    "target_districts": targets.clean_districts,
    "export_layout": _one_of(delivery.EXPORT_LAYOUTS),
    "speaker_id_style": _one_of(delivery.SPEAKER_ID_STYLES),
    "conversation_id_style": _one_of(delivery.CONVERSATION_ID_STYLES),
    "audio_name_pattern": delivery.clean_audio_name_pattern,
}
# Long settings an audit entry carries only when they changed.
_AUDITED_WHEN_CHANGED = (
    "qc_checklist",
    "recording_reminders",
    "target_age_bands",
    "target_districts",
)


def _values(data: ProjectInput) -> dict[str, object]:
    """The project's columns from the input, checked (D-145): the youngest age is not above the
    oldest, and the required details are known ones, each once, in the form's order; the QC
    checklist's items are well formed (D-146), the device details known ones and the reminders
    within their limits (D-147), the targets' shares add up (D-148), the audio file name is made of
    known tokens (D-149). A setting of _KEPT_WHEN_LEFT_OUT left out is not among them."""
    if data.speaker_min_age > data.speaker_max_age:
        raise AppError(
            f"The youngest speaker age ({data.speaker_min_age}) is above the oldest "
            f"({data.speaker_max_age})",
            code="INVALID_AGE_RANGE",
            status_code=422,
            details=[{"field": "speaker_min_age"}],
        )
    values: dict[str, object] = {
        **data.__dict__,
        "required_speaker_details": speakers.clean_required(data.required_speaker_details),
    }
    for name, clean in _KEPT_WHEN_LEFT_OUT.items():
        given = values[name]
        if given is None:
            del values[name]
        else:
            values[name] = clean(given)
    return values


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
        "qc_final_approval": p.qc_final_approval,
        "max_conversations_per_speaker": p.max_conversations_per_speaker,
        "unique_pairs": p.unique_pairs,
        "consent_mode": p.consent_mode,
        "speaker_min_age": p.speaker_min_age,
        "speaker_max_age": p.speaker_max_age,
        "required_speaker_details": list(p.required_speaker_details),
        "qc_checklist": list(p.qc_checklist),
        "device_fields": list(p.device_fields),
        "recording_reminders": dict(p.recording_reminders),
        "pause_limit_seconds": p.pause_limit_seconds,
        "long_pauses_need_review": p.long_pauses_need_review,
        "progress_counts": p.progress_counts,
        "target_hours": None if p.target_hours is None else str(p.target_hours),
        "target_speakers": p.target_speakers,
        "target_conversations": p.target_conversations,
        "target_age_bands": list(p.target_age_bands),
        "target_gender": dict(p.target_gender),
        "target_modes": dict(p.target_modes),
        "target_districts": list(p.target_districts),
        "export_layout": p.export_layout,
        "speaker_id_style": p.speaker_id_style,
        "conversation_id_style": p.conversation_id_style,
        "audio_name_pattern": p.audio_name_pattern,
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
    values = {
        "qc_checklist": checklist.default_checklist(),
        "device_fields": list(moderation.DEFAULT_DEVICE_FIELDS),
        "recording_reminders": moderation.default_reminders(),
        "target_age_bands": targets.default_age_bands(),
        "target_gender": dict(targets.DEFAULT_TARGET_GENDER),
        "target_modes": dict(targets.DEFAULT_TARGET_MODES),
        "target_districts": [],
        "export_layout": delivery.DEFAULT_EXPORT_LAYOUT,
        "speaker_id_style": delivery.DEFAULT_SPEAKER_ID_STYLE,
        "conversation_id_style": delivery.DEFAULT_CONVERSATION_ID_STYLE,
        "audio_name_pattern": delivery.DEFAULT_AUDIO_NAME_PATTERN,
        **_values(data),
    }
    project = Project(
        id=uuid.uuid4(), code=code, status="DRAFT", created_by=principal.user_id, **values
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
    values = _values(data)
    before = _snapshot(project)
    for key, value in values.items():
        setattr(project, key, value)
    _ensure_default_audio_rules(project)
    after = _snapshot(project)
    for name in _AUDITED_WHEN_CHANGED:
        if after[name] == before[name]:
            # Long: the entry carries it only when it changed (D-146, D-147).
            del after[name], before[name]
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
        raise not_found("User")
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
        raise not_found("Member")
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
        if search and search.strip():
            term = search.strip()
            query = query.where(
                or_(
                    User.email.icontains(term, autoescape=True),
                    User.display_name.icontains(term, autoescape=True),
                )
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
