"""Participants (PART-*), consent history (PART-006, SEC-010).

Visibility tiers for a participant inside a project:
- identity (code, language, dialect): participants.view, i.e. every member role.
- profile (name, notes): participants.manage, or the moderator assigned to an open task with them.
- contact (phone number): participants.contact AND either participants.manage, or the project policy
  ASSIGNED_MODERATOR with the moderator assigned to an open task with them.
Others see a masked phone ("......12") or nothing.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.security import FieldCipher
from app.modules.participants.models import ConsentRecord, Participant, ParticipantProjectLink
from app.modules.projects.models import Project
from app.modules.projects.service import get_visible as get_visible_project
from app.modules.tasks.models import Task, TaskAssignment
from app.modules.tasks.workflow import TERMINAL

_PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")
_PHONE_JUNK = re.compile(r"[\s\-().]")


def normalize_phone(raw: str) -> str:
    phone = _PHONE_JUNK.sub("", raw.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not _PHONE.match(phone):
        raise AppError(
            "Phone number must be in international format, e.g. +91 98765 43210",
            code="INVALID_PHONE",
            status_code=422,
        )
    return phone


def phone_hash(settings: Settings, phone: str) -> str:
    """Keyed hash, so equal numbers are found without storing them readable."""
    return hmac.new(
        settings.secret_key.get_secret_value().encode(), phone.encode(), hashlib.sha256
    ).hexdigest()


def not_found() -> AppError:
    return AppError("Participant not found", code="NOT_FOUND", status_code=404)


def moderator_assigned(
    db: Session, user_id: uuid.UUID, participant_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    TaskAssignment.task_id == Task.id,
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.role_code == "MODERATOR",
                    TaskAssignment.active.is_(True),
                    Task.project_id == project_id,
                    Task.status.not_in(TERMINAL),
                    or_(
                        Task.participant_a_id == participant_id,
                        Task.participant_b_id == participant_id,
                    ),
                )
            )
        )
    )


def assigned_participants(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> set[uuid.UUID]:
    """Everyone on this moderator's open tasks in the project, in one query (for lists, O5)."""
    rows = db.execute(
        select(Task.participant_a_id, Task.participant_b_id)
        .join(TaskAssignment, TaskAssignment.task_id == Task.id)
        .where(
            TaskAssignment.user_id == user_id,
            TaskAssignment.role_code == "MODERATOR",
            TaskAssignment.active.is_(True),
            Task.project_id == project_id,
            Task.status.not_in(TERMINAL),
        )
    ).all()
    return {pid for row in rows for pid in row}


@dataclass(frozen=True)
class Visibility:
    profile: bool
    contact: bool
    notes: bool


def visibility(
    db: Session,
    principal: Principal,
    project: Project,
    participant_id: uuid.UUID,
    assigned_ids: set[uuid.UUID] | None = None,
) -> Visibility:
    """`assigned_ids` (from assigned_participants) answers the moderator question for a whole
    list at once; without it, one query answers it for this person."""
    manager = principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id)
    if manager:
        assigned = False
    elif assigned_ids is not None:
        assigned = participant_id in assigned_ids
    else:
        assigned = moderator_assigned(db, principal.user_id, participant_id, project.id)
    profile = manager or assigned
    contact = principal.can_in_project(Perm.PARTICIPANTS_CONTACT, project.id) and (
        manager or (assigned and project.phone_visibility_policy == "ASSIGNED_MODERATOR")
    )
    return Visibility(
        profile=profile, contact=contact, notes=profile and principal.can(Perm.NOTES_VIEW)
    )


def _require(principal: Principal, perm: Perm, project: Project) -> None:
    if not principal.can_in_project(perm, project.id):
        raise forbidden()


def _linked(db: Session, project_id: uuid.UUID, participant_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(ParticipantProjectLink.id).where(
                ParticipantProjectLink.project_id == project_id,
                ParticipantProjectLink.participant_id == participant_id,
            )
        )
    )


def get_in_project(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> tuple[Project, Participant]:
    project = get_visible_project(db, principal, project_id)
    _require(principal, Perm.PARTICIPANTS_VIEW, project)
    participant = db.get(Participant, participant_id)
    if participant is None or not _linked(db, project.id, participant.id):
        raise not_found()
    return project, participant


def list_participants(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    *,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[Project, list[Participant], int]:
    project = get_visible_project(db, principal, project_id)
    _require(principal, Perm.PARTICIPANTS_VIEW, project)
    query = (
        select(Participant)
        .join(ParticipantProjectLink, ParticipantProjectLink.participant_id == Participant.id)
        .where(ParticipantProjectLink.project_id == project.id, Participant.deleted_at.is_(None))
    )
    if search:
        like = f"%{search.strip().lower()}%"
        # Only people who may see names can search by name.
        if principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
            query = query.where(
                or_(
                    func.lower(Participant.participant_code).like(like),
                    func.lower(Participant.display_label).like(like),
                )
            )
        else:
            query = query.where(func.lower(Participant.participant_code).like(like))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Participant.participant_code).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return project, list(items), int(total)


@dataclass(frozen=True)
class ParticipantInput:
    display_label: str
    phone: str | None
    language_code: str
    dialect: str
    notes: str


def _check_language(project: Project, language_code: str, dialect: str) -> None:
    if project.languages and (language_code, dialect) not in {
        (x.language_code, x.dialect) for x in project.languages
    }:
        allowed = ", ".join(f"{x.language_code}/{x.dialect or '-'}" for x in project.languages)
        raise AppError(
            f"Language and dialect must be one of the project's: {allowed}",
            code="LANGUAGE_NOT_IN_PROJECT",
            status_code=422,
        )


def _duplicate(
    db: Session, principal: Principal, digest: str, exclude: uuid.UUID | None = None
) -> None:
    query = select(Participant).where(
        Participant.phone_hash == digest, Participant.deleted_at.is_(None)
    )
    if exclude is not None:
        query = query.where(Participant.id != exclude)
    existing = db.scalar(query)
    if existing is None:
        return
    visible = principal.is_super_admin or bool(
        db.scalar(
            select(ParticipantProjectLink.id).where(
                ParticipantProjectLink.participant_id == existing.id,
                ParticipantProjectLink.project_id.in_(principal.project_ids or [uuid.UUID(int=0)]),
            )
        )
    )
    if not visible:
        # One person keeps one participant ID across projects, so a duplicate has to be refused;
        # every refusal that touches another project is audited, so probing numbers is visible.
        audit.record(
            db,
            action="participant.duplicate_refused",
            entity_type="participant",
            entity_id=existing.id,
            actor_id=principal.user_id,
            ip=None,
        )
        db.commit()
    raise AppError(
        "A participant with this phone number already exists",
        code="DUPLICATE_PARTICIPANT",
        status_code=409,
        details=[{"participant_code": existing.participant_code}] if visible else None,
    )


def _apply_phone(
    p: Participant, settings: Settings, cipher: FieldCipher, phone: str | None
) -> None:
    if phone is None:
        p.phone_e164_enc = p.phone_hash = p.phone_hint = None
        return
    p.phone_e164_enc = cipher.encrypt(phone)
    p.phone_hash = phone_hash(settings, phone)
    p.phone_hint = phone[-2:]


def create_participant(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    principal: Principal,
    project_id: uuid.UUID,
    data: ParticipantInput,
    ip: str | None,
) -> Participant:
    project = get_visible_project(db, principal, project_id)
    _require(principal, Perm.PARTICIPANTS_MANAGE, project)
    _check_language(project, data.language_code, data.dialect)
    phone = normalize_phone(data.phone) if data.phone else None
    if phone:
        _duplicate(db, principal, phone_hash(settings, phone))
    code = f"P{db.scalar(text("SELECT nextval('participant_code_seq')")):06d}"
    participant = Participant(
        id=uuid.uuid4(),
        participant_code=code,
        display_label=data.display_label.strip(),
        language_code=data.language_code,
        dialect=data.dialect,
        notes=data.notes,
        created_by=principal.user_id,
    )
    _apply_phone(participant, settings, cipher, phone)
    db.add(participant)
    db.add(ParticipantProjectLink(participant_id=participant.id, project_id=project.id))
    audit.record(
        db,
        action="participant.created",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={
            "participant_code": code,
            "language_code": data.language_code,
            "has_phone": phone is not None,
        },
    )
    db.commit()
    return participant


def link_existing(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_code: str, ip: str | None
) -> Participant:
    project = get_visible_project(db, principal, project_id)
    _require(principal, Perm.PARTICIPANTS_MANAGE, project)
    participant = db.scalar(
        select(Participant).where(
            Participant.participant_code == participant_code.strip().upper(),
            Participant.deleted_at.is_(None),
        )
    )
    if participant is None:
        raise not_found()
    if not principal.is_super_admin and not db.scalar(
        select(ParticipantProjectLink.id).where(
            ParticipantProjectLink.participant_id == participant.id,
            ParticipantProjectLink.project_id.in_(principal.project_ids or [uuid.UUID(int=0)]),
        )
    ):
        raise not_found()
    if _linked(db, project.id, participant.id):
        raise AppError("Already in this project", code="ALREADY_LINKED", status_code=409)
    _check_language(project, participant.language_code, participant.dialect)
    db.add(ParticipantProjectLink(participant_id=participant.id, project_id=project.id))
    audit.record(
        db,
        action="participant.linked",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return participant


def correct_participant(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    data: ParticipantInput,
    ip: str | None,
) -> Participant:
    project, participant = get_in_project(db, principal, project_id, participant_id)
    _require(principal, Perm.PARTICIPANTS_MANAGE, project)
    if participant.deleted_at is not None:
        raise AppError("This participant was deleted", code="PARTICIPANT_DELETED", status_code=409)
    _check_language(project, data.language_code, data.dialect)
    phone = normalize_phone(data.phone) if data.phone else None
    new_hash = phone_hash(settings, phone) if phone else None
    if new_hash and new_hash != participant.phone_hash:
        _duplicate(db, principal, new_hash, exclude=participant.id)
    before = {
        "display_label": participant.display_label,
        "language_code": participant.language_code,
        "dialect": participant.dialect,
    }
    phone_changed = new_hash != participant.phone_hash
    participant.display_label = data.display_label.strip()
    participant.language_code = data.language_code
    participant.dialect = data.dialect
    participant.notes = data.notes
    if phone_changed:
        _apply_phone(participant, settings, cipher, phone)
    audit.record(
        db,
        action="participant.corrected",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        before=before,
        after={
            "display_label": participant.display_label,
            "language_code": participant.language_code,
            "dialect": participant.dialect,
            "phone_changed": phone_changed,
        },
    )
    db.commit()
    return participant


def delete_participant(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    reason: str,
    ip: str | None,
) -> Participant:
    """Removes personal data now (PART-009); the row stays so tasks and audit keep their links."""
    project, participant = get_in_project(db, principal, project_id, participant_id)
    _require(principal, Perm.PARTICIPANTS_MANAGE, project)
    if participant.deleted_at is not None:
        raise AppError(
            "This participant was already deleted", code="PARTICIPANT_DELETED", status_code=409
        )
    busy = db.execute(
        select(Task.task_code, Task.project_id).where(
            Task.status.not_in(TERMINAL),
            or_(Task.participant_a_id == participant.id, Task.participant_b_id == participant.id),
        )
    ).first()
    if busy:
        # Name the task only when the caller can see it (no other project's codes leak).
        where = (
            f"open task {busy.task_code}"
            if principal.is_super_admin or busy.project_id in principal.project_ids
            else "an open task in another project"
        )
        raise AppError(
            f"Participant is on {where}; cancel or finish it first",
            code="PARTICIPANT_IN_OPEN_TASK",
            status_code=409,
        )
    participant.display_label = f"Deleted participant {participant.participant_code}"
    participant.notes = ""
    participant.phone_e164_enc = participant.phone_hash = participant.phone_hint = None
    participant.deleted_at = datetime.now(UTC)
    participant.deleted_by = principal.user_id
    participant.deletion_reason = reason.strip()
    audit.record(
        db,
        action="participant.deleted",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"reason": participant.deletion_reason},
    )
    db.commit()
    return participant


def _safe_cell(value: str) -> str:
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def export_contacts(
    db: Session, cipher: FieldCipher, principal: Principal, project_id: uuid.UUID, ip: str | None
) -> str:
    project = get_visible_project(db, principal, project_id)
    _require(principal, Perm.PARTICIPANTS_EXPORT, project)
    _, items, _ = list_participants(
        db, principal, project.id, search=None, page=1, page_size=1_000_000
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["participant_code", "display_label", "phone", "language_code", "dialect"])
    for p in items:
        phone = cipher.decrypt(p.phone_e164_enc) if p.phone_e164_enc else ""
        writer.writerow(
            [
                p.participant_code,
                _safe_cell(p.display_label),
                _safe_cell(phone),
                p.language_code,
                p.dialect,
            ]
        )
    audit.record(
        db,
        action="participant.contacts_exported",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"rows": len(items)},
    )
    db.commit()
    return out.getvalue()


def consent_history(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> list[ConsentRecord]:
    project, participant = get_in_project(db, principal, project_id, participant_id)
    _require(principal, Perm.CONSENT_VIEW, project)
    if not visibility(db, principal, project, participant.id).profile:
        # Matrix: consent.view is "A" for a Moderator - only people on their own open tasks (D-049).
        raise forbidden()
    return list(
        db.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.participant_id == participant.id,
                ConsentRecord.project_id == project.id,
            )
            .order_by(ConsentRecord.created_at.desc())
        ).all()
    )
