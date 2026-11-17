"""Participant administration in bulk (D-073): add many from a CSV, assign to another project,
remove, send consent forms, and review the participants' own consent answers.

Every bulk action works one participant at a time through the same checked service functions as
the single actions, so the same permissions, project limits and audit entries apply; one failing
row never stops the others and each row gets its own result. Consent forms are checked here and
emailed after the answer (by the worker when there is one): sending hundreds of emails must not
hold the request open.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.contact import clean_email, normalize_phone
from app.core.csvio import read_rows
from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.security import FieldCipher
from app.modules.participants import service
from app.modules.participants.consent import latest_own_answer
from app.modules.participants.models import ConsentRecord, ParticipantPortalLink
from app.modules.portal import service as portal
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable

MAX_IMPORT_ROWS = 500
MAX_BULK = 200
COLUMNS = ("name", "phone", "email", "language", "dialect", "district")
_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def _bad(message: str) -> AppError:
    return AppError(message, code="INVALID_ROW", status_code=422)


@dataclass
class RowResult:
    line: int
    name: str
    ok: bool
    message: str
    participant_code: str | None = None


def import_csv(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    principal: Principal,
    project_id: uuid.UUID,
    text: str,
    confirm: bool,
    ip: str | None,
) -> list[RowResult]:
    """Check every row; with confirm, create the rows that passed. Header: name,phone,email,
    language,dialect[,district] (phone, dialect and district may be empty; email may not,
    D-128)."""
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_MANAGE)
    rows = read_rows(
        text,
        COLUMNS,
        required=("name", "language"),
        max_rows=MAX_IMPORT_ROWS,
        noun="participants",
    )
    results: list[RowResult] = []
    seen_phones: set[str] = set()
    for csv_row in rows:
        i, row = csv_row.line, csv_row.values
        name = row.get("name", "")
        try:
            if csv_row.extra:
                raise _bad("This line has more values than the first line has columns")
            if not name:
                raise _bad("Name is missing")
            if len(name) > 200:
                raise _bad("Name is too long")
            language = row.get("language", "")
            if not _LANGUAGE.match(language):
                raise _bad("Language code is not valid")
            service.check_language(project, language, row.get("dialect", ""))
            phone = normalize_phone(row["phone"]) if row.get("phone") else None
            if phone:
                if phone in seen_phones:
                    raise _bad("Phone number repeated in this file")
                seen_phones.add(phone)
            if not row.get("email"):
                raise _bad("Email is missing")
            clean_email(row["email"])
            if len(row.get("district", "")) > 100:
                raise _bad("District is too long")
            if not confirm:
                results.append(RowResult(i, name, True, "Ready to add"))
                continue
            created = service.create_participant(
                db,
                settings,
                cipher,
                principal,
                project.id,
                service.ParticipantInput(
                    display_label=name,
                    phone=row.get("phone") or None,
                    language_code=language,
                    dialect=row.get("dialect", ""),
                    notes="",
                    email=row.get("email") or None,
                    district=row.get("district", ""),
                ),
                ip,
            )
            results.append(RowResult(i, name, True, "Added", created.participant_code))
        except AppError as exc:
            db.rollback()
            results.append(RowResult(i, name, False, exc.message))
    return results


@dataclass
class BulkResult:
    participant_id: uuid.UUID
    participant_code: str
    ok: bool
    message: str


def bulk(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    action: str,
    participant_ids: list[uuid.UUID],
    target_project_id: uuid.UUID | None,
    reason: str,
    ip: str | None,
) -> list[BulkResult]:
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_MANAGE)
    target: Project | None = None
    if action == "assign":
        if target_project_id is None or target_project_id == project.id:
            raise AppError("Choose another project", code="TARGET_REQUIRED", status_code=422)
        target = get_manageable(db, principal, target_project_id, Perm.PARTICIPANTS_MANAGE)
    if action == "remove" and not reason.strip():
        raise AppError("Give a reason for removing", code="REASON_REQUIRED", status_code=422)
    results: list[BulkResult] = []
    for pid in dict.fromkeys(participant_ids):
        code = "?"
        try:
            _, participant = service.get_in_project(db, principal, project.id, pid)
            code = participant.participant_code
            if target is not None:
                service.link_existing(db, principal, target.id, code, ip)
                message = "Assigned"
            elif action == "remove":
                service.delete_participant(db, principal, project.id, pid, reason, ip)
                message = "Removed"
            else:
                # Checked now; emailed after the answer (portal.send_links_job).
                portal.email_of(participant)
                portal.check_linkable(participant)
                message = "Consent form will be emailed"
            results.append(BulkResult(pid, code, True, message))
        except AppError as exc:
            db.rollback()
            results.append(BulkResult(pid, code, False, exc.message))
    return results


def review_consent(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    decision: str,
    note: str,
    ip: str | None,
) -> ConsentRecord:
    """Approve or reject the participant's own latest "agree" answer."""
    project, participant = service.get_in_project(
        db, principal, project_id, participant_id, Perm.PARTICIPANTS_MANAGE
    )
    answer = latest_own_answer(db, participant.id, project.id)
    if answer is None or answer.status != "GIVEN":
        raise AppError(
            "There is no consent answer to review", code="NOTHING_TO_REVIEW", status_code=409
        )
    if answer.link_shown_to == principal.user_id:
        # They could have opened the link and answered themselves (D-088).
        raise AppError(
            "You handed this participant their link, so another administrator must review "
            "this answer",
            code="SAME_PERSON",
            status_code=409,
        )
    if decision == "REJECTED" and not note.strip():
        raise AppError(
            "Say why, so the participant knows what to correct",
            code="NOTE_REQUIRED",
            status_code=422,
        )
    answer.review_status = decision
    answer.review_note = note.strip()
    answer.reviewed_by = principal.user_id
    answer.reviewed_at = datetime.now(UTC)
    audit.record(
        db,
        action=f"consent.review_{decision.lower()}",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return answer


def consent_overview(
    db: Session, project: Project, participant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None, bool]]:
    """Per participant: (own answer, review, has a working link). Two queries for a page."""
    if not participant_ids:
        return {}
    newest = (
        select(
            ConsentRecord.participant_id,
            func.max(ConsentRecord.created_at).label("at"),
        )
        .where(
            ConsentRecord.project_id == project.id,
            ConsentRecord.participant_id.in_(participant_ids),
            ConsentRecord.is_own_answer,
        )
        .group_by(ConsentRecord.participant_id)
        .subquery()
    )
    answers = {
        r.participant_id: (r.status, r.review_status)
        for r in db.execute(
            select(
                ConsentRecord.participant_id, ConsentRecord.status, ConsentRecord.review_status
            ).join(
                newest,
                (newest.c.participant_id == ConsentRecord.participant_id)
                & (newest.c.at == ConsentRecord.created_at),
            )
        )
    }
    linked = set(
        db.scalars(
            select(ParticipantPortalLink.participant_id).where(
                ParticipantPortalLink.project_id == project.id,
                ParticipantPortalLink.participant_id.in_(participant_ids),
                ParticipantPortalLink.revoked_at.is_(None),
                ParticipantPortalLink.expires_at > datetime.now(UTC),
            )
        )
    )
    out = {}
    for pid in participant_ids:
        status, review = answers.get(pid, ("NONE", None))
        out[pid] = (status, review, pid in linked)
    return out
