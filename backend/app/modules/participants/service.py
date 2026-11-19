"""Participants (PART-*), consent history (PART-006, SEC-010).

Visibility tiers for a participant inside a project:
- identity (code, language, dialect): participants.view, i.e. every member role.
- profile (name, notes): participants.manage, or the moderator assigned to an open task with them.
- contact (phone number): participants.contact AND either participants.manage, or the project policy
  ASSIGNED_MODERATOR with the moderator assigned to an open task with them.
Others see a masked phone ("......12") or nothing.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, exists, or_, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.contact import clean_email, normalize_phone
from app.core.csvio import write_table
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm, Role
from app.db.paging import paginate
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, in_projects
from app.modules.auth.security import FieldCipher
from app.modules.participants.models import (
    ConsentRecord,
    Participant,
    ParticipantPortalLink,
    ParticipantProjectLink,
)
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable
from app.modules.tasks.models import Task, TaskAssignment
from app.modules.tasks.workflow import TERMINAL

CONTACT_COLUMNS = (
    "participant_code",
    "display_label",
    "phone",
    "language_code",
    "dialect",
    "district",
)


def phone_hash(settings: Settings, phone: str) -> str:
    """Keyed hash, so equal numbers are found without storing them readable."""
    return hmac.new(
        settings.secret_key.get_secret_value().encode(), phone.encode(), hashlib.sha256
    ).hexdigest()


def moderator_assigned(
    db: Session, user_id: uuid.UUID, participant_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    TaskAssignment.task_id == Task.id,
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.role_code == Role.MODERATOR.value,
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
            TaskAssignment.role_code == Role.MODERATOR.value,
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


def _require_every_project(db: Session, principal: Principal, participant: Participant) -> None:
    """A participant can belong to several projects, and an edit or a removal changes them in all
    of them: allowed only to someone who manages every one (D-088). Before, an admin of one
    project could change the email the other project's consent links go to."""
    project_ids = db.scalars(
        select(ParticipantProjectLink.project_id).where(
            ParticipantProjectLink.participant_id == participant.id
        )
    ).all()
    if not all(principal.can_in_project(Perm.PARTICIPANTS_MANAGE, pid) for pid in project_ids):
        raise AppError(
            "This participant also belongs to a project you do not manage. "
            "Ask a Super Admin to make this change.",
            code="SHARED_PARTICIPANT",
            status_code=403,
        )


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
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    perm: Perm = Perm.PARTICIPANTS_VIEW,
) -> tuple[Project, Participant]:
    """The participant in a project the caller sees: 404 for anyone not in it, then 403 when the
    caller lacks `perm` in the project."""
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_VIEW)
    participant = db.get(Participant, participant_id)
    if participant is None or not _linked(db, project.id, participant.id):
        raise not_found("Participant")
    if not principal.can_in_project(perm, project.id):
        raise forbidden()
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
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_VIEW)
    query = _in_project(project)
    if search and search.strip():
        term = search.strip()
        by_code = Participant.participant_code.icontains(term, autoescape=True)
        # Only people who may see names can search by name.
        if principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
            query = query.where(
                or_(by_code, Participant.display_label.icontains(term, autoescape=True))
            )
        else:
            query = query.where(by_code)
    items, total = paginate(db, query.order_by(Participant.participant_code), page, page_size)
    return project, items, total


def _in_project(project: Project, *, with_deleted: bool = False) -> Select[Participant]:
    """The project's participants who are not deleted (or all of them, with_deleted)."""
    query = (
        select(Participant)
        .join(ParticipantProjectLink, ParticipantProjectLink.participant_id == Participant.id)
        .where(ParticipantProjectLink.project_id == project.id)
    )
    return query if with_deleted else query.where(Participant.deleted_at.is_(None))


def in_project_by_id(
    db: Session, project: Project, participant_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, Participant]:
    """Those of these participants who are in the project, deleted or not, in one query: what
    get_in_project finds for each, once the caller may see the project's participants."""
    if not participant_ids:
        return {}
    query = _in_project(project, with_deleted=True).where(Participant.id.in_(participant_ids))
    return {p.id: p for p in db.scalars(query)}


@dataclass(frozen=True)
class ParticipantInput:
    display_label: str
    phone: str | None
    language_code: str
    dialect: str
    notes: str
    email: str | None = None
    district: str = ""


def check_language(project: Project, language_code: str, dialect: str) -> None:
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
                in_projects(principal, ParticipantProjectLink.project_id),
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


def require_email(email: str | None) -> str:
    """The email a participant must have (D-128), or 422 EMAIL_REQUIRED."""
    if not email or not email.strip():
        raise AppError(
            "Enter the participant's email address: the consent form is sent there",
            code="EMAIL_REQUIRED",
            status_code=422,
        )
    return email


def create_participant(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    principal: Principal,
    project_id: uuid.UUID,
    data: ParticipantInput,
    ip: str | None,
) -> Participant:
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_MANAGE)
    check_language(project, data.language_code, data.dialect)
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
        district=data.district.strip(),
        notes=data.notes,
        created_by=principal.user_id,
    )
    _apply_phone(participant, settings, cipher, phone)
    # Every participant needs an email: the consent form reaches them by email (D-128).
    participant.email_enc = cipher.encrypt(clean_email(require_email(data.email)))
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
            "has_email": bool(data.email),
        },
    )
    db.commit()
    return participant


def link_existing(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_code: str, ip: str | None
) -> Participant:
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_MANAGE)
    participant = db.scalar(
        select(Participant).where(
            Participant.participant_code == participant_code.strip().upper(),
            Participant.deleted_at.is_(None),
        )
    )
    # Only someone already in one of the caller's projects can be added (no code guessing).
    if participant is None or not (
        principal.is_super_admin
        or db.scalar(
            select(ParticipantProjectLink.id).where(
                ParticipantProjectLink.participant_id == participant.id,
                in_projects(principal, ParticipantProjectLink.project_id),
            )
        )
    ):
        raise not_found("Participant")
    if _linked(db, project.id, participant.id):
        raise AppError("Already in this project", code="ALREADY_LINKED", status_code=409)
    check_language(project, participant.language_code, participant.dialect)
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


def link_candidates(
    db: Session, principal: Principal, project_id: uuid.UUID, search: str | None, limit: int = 50
) -> list[Participant]:
    """People who can be added to this project as they are (D-090): not deleted, not already in
    it, in a project where the caller manages participants (a Super Admin: any project), and
    speaking one of this project's languages when it has a list. Search by code or name."""
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_MANAGE)
    already = select(ParticipantProjectLink.participant_id).where(
        ParticipantProjectLink.project_id == project.id
    )
    query = select(Participant).where(
        Participant.deleted_at.is_(None), Participant.id.not_in(already)
    )
    if not principal.is_super_admin:
        managed = [
            pid
            for pid in principal.project_ids
            if principal.can_in_project(Perm.PARTICIPANTS_MANAGE, pid)
        ]
        visible = select(ParticipantProjectLink.participant_id).where(
            ParticipantProjectLink.project_id.in_(managed)
        )
        query = query.where(Participant.id.in_(visible))
    codes = sorted({lang.language_code for lang in project.languages})
    if codes:
        query = query.where(Participant.language_code.in_(codes))
    if search and search.strip():
        term = search.strip()
        query = query.where(
            or_(
                Participant.participant_code.icontains(term, autoescape=True),
                Participant.display_label.icontains(term, autoescape=True),
            )
        )
    return list(db.scalars(query.order_by(Participant.participant_code).limit(limit)).all())


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
    project, participant = get_in_project(
        db, principal, project_id, participant_id, Perm.PARTICIPANTS_MANAGE
    )
    if participant.deleted_at is not None:
        raise AppError("This participant was deleted", code="PARTICIPANT_DELETED", status_code=409)
    _require_every_project(db, principal, participant)
    check_language(project, data.language_code, data.dialect)
    phone = normalize_phone(data.phone) if data.phone else None
    new_hash = phone_hash(settings, phone) if phone else None
    if new_hash and new_hash != participant.phone_hash:
        _duplicate(db, principal, new_hash, exclude=participant.id)
    before = {
        "display_label": participant.display_label,
        "language_code": participant.language_code,
        "dialect": participant.dialect,
        "district": participant.district,
    }
    phone_changed = new_hash != participant.phone_hash
    participant.display_label = data.display_label.strip()
    participant.language_code = data.language_code
    participant.dialect = data.dialect
    participant.district = data.district.strip()
    participant.notes = data.notes
    if phone_changed:
        _apply_phone(participant, settings, cipher, phone)
    # Email: not sent = keep; otherwise replace. It cannot be removed, and someone saved before
    # it was required gets one with their next correction (D-128).
    email_changed = False
    if data.email is not None or participant.email_enc is None:
        new_email = clean_email(require_email(data.email))
        old_email = cipher.decrypt(participant.email_enc) if participant.email_enc else None
        email_changed = new_email != old_email
        if email_changed:
            participant.email_enc = cipher.encrypt(new_email) if new_email else None
            # A personal link already mailed to the old address stops working (D-088), as staff
            # invitation and reset links do when an email changes (D-064).
            db.execute(
                update(ParticipantPortalLink)
                .where(
                    ParticipantPortalLink.participant_id == participant.id,
                    ParticipantPortalLink.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
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
            "district": participant.district,
            "phone_changed": phone_changed,
            "email_changed": email_changed,
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
    project, participant = get_in_project(
        db, principal, project_id, participant_id, Perm.PARTICIPANTS_MANAGE
    )
    if participant.deleted_at is not None:
        raise AppError(
            "This participant was already deleted", code="PARTICIPANT_DELETED", status_code=409
        )
    _require_every_project(db, principal, participant)
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
    participant.email_enc = None
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


def export_contacts(
    db: Session, cipher: FieldCipher, principal: Principal, project_id: uuid.UUID, ip: str | None
) -> str:
    """Every participant of the project with their phone number, as CSV. Rows are read from the
    database in batches, never all at once."""
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_EXPORT)
    written = 0

    def rows() -> Iterator[list[object]]:
        nonlocal written
        query = _in_project(project).order_by(Participant.participant_code)
        for p in db.scalars(query.execution_options(yield_per=500)):
            written += 1
            yield [
                p.participant_code,
                p.display_label,
                cipher.decrypt(p.phone_e164_enc) if p.phone_e164_enc else "",
                p.language_code,
                p.dialect,
                p.district,
            ]

    out = write_table(CONTACT_COLUMNS, rows())
    audit.record(
        db,
        action="participant.contacts_exported",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"rows": written},
    )
    db.commit()
    return out


def consent_history(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> list[ConsentRecord]:
    project, participant = get_in_project(
        db, principal, project_id, participant_id, Perm.CONSENT_VIEW
    )
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
