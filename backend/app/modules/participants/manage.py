"""Participant administration in bulk (D-073): add many from a CSV, assign to another project,
remove, send consent forms, and review the participants' own consent answers.

Every bulk action works one participant at a time through the same checked service functions as
the single actions, so the same permissions, project limits and audit entries apply; one failing
row never stops the others and each row gets its own result.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailSender
from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.security import FieldCipher
from app.modules.participants import service
from app.modules.participants.models import ConsentRecord, ParticipantPortalLink
from app.modules.portal import service as portal
from app.modules.projects.models import Project
from app.modules.projects.service import get_visible as get_visible_project

MAX_IMPORT_ROWS = 500
MAX_BULK = 200
COLUMNS = ("name", "phone", "email", "language", "dialect")
_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


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
    language,dialect (phone, email and dialect may be empty)."""
    project = get_visible_project(db, principal, project_id)
    if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    if "name" not in header or "language" not in header:
        raise AppError(
            "The first line must name the columns: name,phone,email,language,dialect",
            code="INVALID_CSV",
            status_code=422,
        )
    rows = list(reader)
    if len(rows) > MAX_IMPORT_ROWS:
        raise AppError(
            f"At most {MAX_IMPORT_ROWS} participants per file",
            code="TOO_MANY_ROWS",
            status_code=422,
        )
    results: list[RowResult] = []
    seen_phones: set[str] = set()
    for i, raw in enumerate(rows, start=2):
        # csv puts values beyond the header under the key None, as a list (D-088: was a 500).
        extra = raw.pop(None, None)
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        name = row.get("name", "")
        try:
            if extra:
                raise AppError(
                    "This line has more values than the first line has columns",
                    code="INVALID_ROW",
                    status_code=422,
                )
            if not name:
                raise AppError("Name is missing", code="INVALID_ROW", status_code=422)
            if len(name) > 200:
                raise AppError("Name is too long", code="INVALID_ROW", status_code=422)
            language = row.get("language", "")
            if not _LANGUAGE.match(language):
                raise AppError("Language code is not valid", code="INVALID_ROW", status_code=422)
            service._check_language(project, language, row.get("dialect", ""))
            phone = service.normalize_phone(row["phone"]) if row.get("phone") else None
            if phone:
                if phone in seen_phones:
                    raise AppError(
                        "Phone number repeated in this file", code="INVALID_ROW", status_code=422
                    )
                seen_phones.add(phone)
            if row.get("email"):
                service.clean_email(row["email"])
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
    settings: Settings,
    cipher: FieldCipher,
    sender: EmailSender,
    principal: Principal,
    project_id: uuid.UUID,
    action: str,
    participant_ids: list[uuid.UUID],
    target_project_id: uuid.UUID | None,
    reason: str,
    ip: str | None,
) -> list[BulkResult]:
    project = get_visible_project(db, principal, project_id)
    if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    if action == "assign":
        if target_project_id is None or target_project_id == project.id:
            raise AppError("Choose another project", code="TARGET_REQUIRED", status_code=422)
        target = get_visible_project(db, principal, target_project_id)
        if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, target.id):
            raise AppError(
                "You do not have permission to do this", code="FORBIDDEN", status_code=403
            )
    if action == "remove" and not reason.strip():
        raise AppError("Give a reason for removing", code="REASON_REQUIRED", status_code=422)
    results: list[BulkResult] = []
    for pid in dict.fromkeys(participant_ids):
        code = "?"
        try:
            _, participant = service.get_in_project(db, principal, project.id, pid)
            code = participant.participant_code
            if action == "assign":
                assert target_project_id is not None  # noqa: S101
                service.link_existing(db, principal, target_project_id, code, ip)
                message = "Assigned"
            elif action == "remove":
                service.delete_participant(db, principal, project.id, pid, reason, ip)
                message = "Removed"
            else:
                sent, _ = portal.email_link(
                    db, settings, cipher, sender, principal, project.id, pid, ip
                )
                if not sent:
                    raise AppError("The email could not be sent", code="EMAIL_FAILED")
                message = "Consent form sent"
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
    project, participant = service.get_in_project(db, principal, project_id, participant_id)
    if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    answer = portal.own_consent(db, participant.id, project.id)
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
            ConsentRecord.task_id.is_(None),
            ConsentRecord.captured_by.is_(None),
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
