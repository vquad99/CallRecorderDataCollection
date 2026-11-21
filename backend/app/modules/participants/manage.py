"""Participant administration in bulk (D-073): add many from a CSV, assign to another project,
remove.

Assigning and removing work one participant at a time through the same checked service functions
as the single actions, so the same permissions, project limits and audit entries apply; one
failing row never stops the others and each row gets its own result. Picking who gets the consent
form again changes nothing, so it reads everyone at once. Everyone who joins a project is emailed
its consent form afterwards (D-129, by the router after the answer).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.contact import clean_email, normalize_phone
from app.core.csvio import read_rows
from app.core.errors import AppError, not_found
from app.core.permissions import Perm
from app.core.storage import ObjectStorage
from app.modules.auth.deps import Principal
from app.modules.auth.security import FieldCipher
from app.modules.participants import consent, service, speakers
from app.modules.participants.models import ParticipantPortalLink
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable

MAX_IMPORT_ROWS = 500
MAX_BULK = 200
# The speaker details (D-143) after the first six; `district` is the native district.
SPEAKER_COLUMNS = tuple(name for name in speakers.FIELDS if name != "district")
COLUMNS = ("name", "phone", "email", "language", "dialect", "district", *SPEAKER_COLUMNS)
ALREADY_AGREED = "Already agreed: no form sent"
DETAILS_MISSING = "speaker details missing: add them with Edit before making tasks"
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
    participant_id: uuid.UUID | None = None


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
    language,dialect[,district and the speaker details] (phone, dialect and the speaker details
    may be empty; email may not, D-128). A speaker detail that is given is checked as on the form
    (D-143); a row without all of them is added, and its result says they are missing."""
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
            given = {field: row.get(field, "") for field in speakers.FIELDS}
            details = speakers.clean_all(given)
            ready, added = "Ready to add", "Added"
            if any(value is None for value in details.values()):
                ready, added = f"{ready} ({DETAILS_MISSING})", f"{added} ({DETAILS_MISSING})"
            if not confirm:
                results.append(RowResult(i, name, True, ready))
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
                    speaker=given,
                ),
                ip,
            )
            results.append(RowResult(i, name, True, added, created.participant_code, created.id))
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
    *,
    storage: ObjectStorage | None = None,
) -> tuple[Project | None, list[BulkResult]]:
    """Assign to another project, remove, or pick who gets this project's consent form again
    (D-139). Returns the project whose consent form goes out (the target when assigning, this
    project for send_consent, None when removing) and each participant's result."""
    project = get_manageable(db, principal, project_id, Perm.PARTICIPANTS_MANAGE)
    target: Project | None = None
    if action == "assign":
        if target_project_id is None or target_project_id == project.id:
            raise AppError("Choose another project", code="TARGET_REQUIRED", status_code=422)
        target = get_manageable(db, principal, target_project_id, Perm.PARTICIPANTS_MANAGE)
    elif action == "send_consent":
        consent.require_online(project)
        target = project
    elif not reason.strip():
        raise AppError("Give a reason for removing", code="REASON_REQUIRED", status_code=422)
    ids = list(dict.fromkeys(participant_ids))
    if action == "send_consent":
        return target, _consent_again(db, project, ids)
    results: list[BulkResult] = []
    for pid in ids:
        code = "?"
        try:
            _, participant = service.get_in_project(db, principal, project.id, pid)
            code = participant.participant_code
            if action == "assign" and target is not None:
                service.link_existing(db, principal, target.id, code, ip)
                message = "Assigned"
            else:
                service.delete_participant(
                    db, principal, project.id, pid, reason, ip, storage=storage
                )
                message = "Removed"
            results.append(BulkResult(pid, code, True, message))
        except AppError as exc:
            db.rollback()
            results.append(BulkResult(pid, code, False, exc.message))
    return target, results


def _consent_again(db: Session, project: Project, ids: list[uuid.UUID]) -> list[BulkResult]:
    """Who gets the project's consent form again (D-139): the chosen people in the project who
    have not agreed. Everyone is read at once and nothing is written."""
    found = service.in_project_by_id(db, project, ids)
    standing = consent.standings(db, project, ids)
    missing = not_found("Participant").message
    results: list[BulkResult] = []
    for pid in ids:
        person = found.get(pid)
        if person is None:
            results.append(BulkResult(pid, "?", False, missing))
        elif standing[pid].consented:
            results.append(BulkResult(pid, person.participant_code, False, ALREADY_AGREED))
        else:
            results.append(BulkResult(pid, person.participant_code, True, ""))
    return results


def consent_overview(
    db: Session, project: Project, participant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, bool]]:
    """Per participant: (consent as it counts now - the answer's word or UPLOADED, D-144 - or
    NONE; has a working link). Two queries for a page, three in a project that takes uploads."""
    standing = consent.standings(db, project, participant_ids)
    linked = (
        set(
            db.scalars(
                select(ParticipantPortalLink.participant_id).where(
                    ParticipantPortalLink.project_id == project.id,
                    ParticipantPortalLink.participant_id.in_(participant_ids),
                    ParticipantPortalLink.revoked_at.is_(None),
                    ParticipantPortalLink.expires_at > datetime.now(UTC),
                )
            )
        )
        if participant_ids
        else set()
    )
    return {pid: (standing[pid].status or "NONE", pid in linked) for pid in participant_ids}
