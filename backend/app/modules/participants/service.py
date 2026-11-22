"""Participants (PART-*), consent history (PART-006, SEC-010).

Visibility tiers for a participant inside a project:
- identity (code, language, dialect, native district, whether the speaker details are complete):
  participants.view, i.e. every member role.
- profile (name, notes, speaker details - D-143): participants.manage, or the moderator assigned to
  an open task with them.
- contact (phone number): participants.contact AND either participants.manage, or the project policy
  ASSIGNED_MODERATOR with the moderator assigned to an open task with them.
Others see a masked phone ("......12") or nothing.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import Select, exists, func, or_, select, text, tuple_, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.contact import clean_email, normalize_phone
from app.core.csvio import write_table
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm, Role
from app.core.storage import ObjectStorage
from app.db.paging import paginate
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal, in_projects
from app.modules.auth.security import FieldCipher
from app.modules.participants import speakers
from app.modules.participants.models import (
    ADDRESS_PROOF,
    ConsentRecord,
    Participant,
    ParticipantDocument,
    ParticipantPortalLink,
    ParticipantProjectLink,
)
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable
from app.modules.tasks.models import Task, TaskAssignment
from app.modules.tasks.workflow import TERMINAL

logger = logging.getLogger(__name__)

CONTACT_COLUMNS = (
    "participant_code",
    "display_label",
    "phone",
    "language_code",
    "dialect",
    "district",
)
# What a removed participant's address proofs are called from then on (PART-07).
REMOVED_PROOF_NAME = "address_proof"


def phone_hash(settings: Settings, phone: str) -> str:
    """Keyed hash, so equal numbers are found without storing them readable."""
    return hmac.new(
        settings.secret_key.get_secret_value().encode(), phone.encode(), hashlib.sha256
    ).hexdigest()


def address_fingerprint(settings: Settings, email: str) -> str:
    """A participant's email address as the audit log keeps it: a keyed hash (like phone_hash),
    first 16 hex characters. Two entries with the same address show the same fingerprint, so the
    log proves where a consent link went without holding a readable address (SECB-02)."""
    return hmac.new(
        settings.secret_key.get_secret_value().encode(),
        email.strip().casefold().encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


def masked_address(email: str) -> str:
    """An address as staff may see it in a consent record: "ka•••@example.org"."""
    local, _, domain = email.strip().rpartition("@")
    return f"{local[:2]}•••@{domain}" if local else "•••"


def moderator_assigned(
    db: Session,
    user_id: uuid.UUID,
    participant_id: uuid.UUID,
    project_id: uuid.UUID,
    statuses: Collection[str] | None = None,
) -> bool:
    """The user moderates a task of the project with this participant: an open one (not approved,
    rejected or cancelled), or one in `statuses` when given."""
    status = Task.status.in_(statuses) if statuses is not None else Task.status.not_in(TERMINAL)
    return bool(
        db.scalar(
            select(
                exists().where(
                    TaskAssignment.task_id == Task.id,
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.role_code == Role.MODERATOR.value,
                    TaskAssignment.active.is_(True),
                    Task.project_id == project_id,
                    status,
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
    # Speaker details given, by field name (speakers.FIELDS, the native district as `district`),
    # as typed; checked here. On a correction, a field left out keeps its stored value (D-143).
    speaker: Mapping[str, object] = field(default_factory=dict)


def _apply_speaker(p: Participant, given: Mapping[str, object], project: Project) -> list[str]:
    """Stores the given speaker details (422 INVALID_SPEAKER_DETAILS for a wrong one); returns
    the names of the fields that changed. An age that changes must be within the project's
    speaker ages (422 SPEAKER_AGE_OUT_OF_RANGE, D-145); an age kept as it was is not checked
    again (it may have been saved in another project), a task checks it."""
    values = speakers.clean_all(given)
    age = values.get("age")
    if isinstance(age, int) and age != p.age:
        speakers.check_age(project, age)
    changed = []
    for name, value in values.items():
        stored = "" if name == "district" and value is None else value
        if getattr(p, name) != stored:
            setattr(p, name, stored)
            changed.append(name)
    return changed


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


def refuse_duplicate_phone(
    db: Session, principal: Principal, digest: str, exclude: uuid.UUID | None = None
) -> None:
    """409 DUPLICATE_PARTICIPANT when someone (not removed) already has this phone number
    (`digest` from phone_hash), named by code when the caller may see them."""
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


def refuse_same_person(
    db: Session, cipher: FieldCipher, project: Project, name: str, email: str
) -> None:
    """409 DUPLICATE_PARTICIPANT when the project already has someone (not removed) with this
    name and this email address, both compared without case (PART-05). The phone is optional, so
    it cannot be the only check; a family sharing one address (different names) is still allowed.
    `email` is the address as clean_email gives it."""
    wanted = email.casefold()
    same_name = _in_project(project).where(
        # Both sides lower-cased by the database, so they follow the same rules.
        func.lower(Participant.display_label) == func.lower(name.strip()),
        Participant.email_enc.is_not(None),
    )
    for existing in db.scalars(same_name.order_by(Participant.participant_code)):
        stored = existing.email_enc
        if stored is not None and cipher.decrypt(stored).casefold() == wanted:
            raise AppError(
                f"Already in this project as {existing.participant_code}",
                code="DUPLICATE_PARTICIPANT",
                status_code=409,
                details=[{"participant_code": existing.participant_code}],
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
        refuse_duplicate_phone(db, principal, phone_hash(settings, phone))
    participant = Participant(
        id=uuid.uuid4(),
        display_label=data.display_label.strip(),
        language_code=data.language_code,
        dialect=data.dialect,
        district="",
        notes=data.notes,
        created_by=principal.user_id,
    )
    _apply_speaker(participant, data.speaker, project)
    # Every participant needs an email: the consent form reaches them by email (D-128). The same
    # name with the same address is someone already here (PART-05).
    email = clean_email(require_email(data.email))
    refuse_same_person(db, cipher, project, participant.display_label, email)
    code = f"P{db.scalar(text("SELECT nextval('participant_code_seq')")):06d}"
    participant.participant_code = code
    _apply_phone(participant, settings, cipher, phone)
    participant.email_enc = cipher.encrypt(email)
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
            "speaker_details_complete": speakers.complete(participant, project),
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
    speakers.check_ages(project, [participant])  # the project's speaker ages (D-145)
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
    it, in a project where the caller manages participants (a Super Admin: any project),
    speaking one of this project's languages and dialects when it has a list (the exact pairs
    link_existing takes, PART-10), and within its speaker ages (D-145). Search by code or
    name."""
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
    pairs = sorted({(x.language_code, x.dialect) for x in project.languages})
    if pairs:
        query = query.where(tuple_(Participant.language_code, Participant.dialect).in_(pairs))
    # Within the project's speaker ages, or no age yet (D-145): link_existing refuses the others.
    query = query.where(
        or_(
            Participant.age.is_(None),
            Participant.age.between(project.speaker_min_age, project.speaker_max_age),
        )
    )
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
        refuse_duplicate_phone(db, principal, new_hash, exclude=participant.id)
    # The append-only audit log never holds the person's name or native district: a removal has
    # to erase them everywhere (PART-009). It names what changed, not the values (D-143, PART-07).
    before: dict[str, object] = {
        "language_code": participant.language_code,
        "dialect": participant.dialect,
    }
    old_name = participant.display_label
    phone_changed = new_hash != participant.phone_hash
    participant.display_label = data.display_label.strip()
    participant.language_code = data.language_code
    participant.dialect = data.dialect
    speaker_changed = _apply_speaker(participant, data.speaker, project)
    participant.notes = data.notes
    if phone_changed:
        _apply_phone(participant, settings, cipher, phone)
    after: dict[str, object] = {
        "language_code": participant.language_code,
        "dialect": participant.dialect,
        "name_changed": participant.display_label != old_name,
        "phone_changed": phone_changed,
    }
    # Email: not sent = keep; otherwise replace. It cannot be removed, and someone saved before
    # it was required gets one with their next correction (D-128).
    email_changed = False
    if data.email is not None or participant.email_enc is None:
        new_email = clean_email(require_email(data.email))
        old_email = cipher.decrypt(participant.email_enc) if participant.email_enc else None
        email_changed = new_email != old_email
        if email_changed:
            participant.email_enc = cipher.encrypt(new_email)
            # Where consent links go from now on, as a fingerprint (SECB-02): an address staff
            # put on file for a while shows in the log, never readable.
            before["email"] = address_fingerprint(settings, old_email) if old_email else None
            after["email"] = address_fingerprint(settings, new_email)
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
            **after,
            "email_changed": email_changed,
            # Which speaker details changed (the native district as `district`), not their
            # values (D-143).
            "speaker_details_changed": speaker_changed,
            "speaker_details_complete": speakers.complete(participant, project),
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
    *,
    storage: ObjectStorage | None = None,
) -> Participant:
    """Removes personal data now (PART-009); the row stays so tasks and audit keep their links.
    Their address proofs go too, files and all (D-144); signed consent forms stay, as the record of
    consent for what was recorded, like consent records. A file storage cannot delete now is left
    to the storage-orphans command (O12)."""
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
    _apply_speaker(participant, dict.fromkeys(speakers.FIELDS), project)  # personal too (D-143)
    participant.deleted_at = datetime.now(UTC)
    participant.deleted_by = principal.user_id
    participant.deletion_reason = reason.strip()
    # The row stays as the record that a proof was held; its file name often carries the person's
    # name ("Aadhaar_Priya.pdf"), so it goes with the file (PART-07).
    proofs = list(
        db.scalars(
            update(ParticipantDocument)
            .where(
                ParticipantDocument.participant_id == participant.id,
                ParticipantDocument.kind == ADDRESS_PROOF,
                ParticipantDocument.removed_at.is_(None),
            )
            .values(removed_at=participant.deleted_at, file_name=REMOVED_PROOF_NAME)
            .returning(ParticipantDocument.storage_key)
        )
    )
    audit.record(
        db,
        action="participant.deleted",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"reason": participant.deletion_reason, "address_proofs_removed": len(proofs)},
    )
    db.commit()
    for key in proofs:
        try:
            if storage is not None:
                storage.delete(key)
        except (BotoCoreError, ClientError):  # the storage-orphans command removes it later
            logger.warning(
                "address_proof_not_deleted", extra={"participant_id": str(participant.id)}
            )
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
