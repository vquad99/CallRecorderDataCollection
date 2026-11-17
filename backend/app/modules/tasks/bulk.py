"""Add many tasks from a CSV file (D-083).

Each row goes through the same create_task and assign_moderator service functions as the single
form, so the same permissions, project limits and audit entries apply; a failing row never stops
the others and every row gets its own result. Check first (confirm=False), then add.

Columns: participant_a,participant_b,mode,priority,due_date,moderator
- participant_a, participant_b: participant codes such as P000001 (required); both must have
  agreed to the project's consent form (D-129), which the check already says.
- mode: face_to_face or telephony; empty = face_to_face, or the project's only mode.
- priority: low, normal, high or urgent; empty = normal.
- due_date: YYYY-MM-DD; may be empty.
- moderator: the moderator's email; empty leaves the task in Draft for assigning later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contact import normalize_email
from app.core.csvio import read_rows
from app.core.errors import AppError
from app.core.permissions import Perm, Role
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.participants.models import Participant, ParticipantProjectLink
from app.modules.projects.models import Project
from app.modules.projects.service import ensure_accepts_new_work, get_manageable
from app.modules.tasks import service

MAX_IMPORT_ROWS = 500
COLUMNS = ("participant_a", "participant_b", "mode", "priority", "due_date", "moderator")
MODES = {"FACE_TO_FACE": "FACE_TO_FACE", "FACE-TO-FACE": "FACE_TO_FACE", "TELEPHONY": "TELEPHONY"}
PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")


@dataclass
class RowResult:
    line: int
    pair: str
    ok: bool
    message: str
    task_code: str | None = None


def _bad(message: str) -> AppError:
    return AppError(message, code="INVALID_ROW", status_code=422)


def _participant(db: Session, project_id: uuid.UUID, code: str, side: str) -> Participant:
    if not code:
        raise _bad(f"Participant {side} is missing")
    found = db.scalar(
        select(Participant)
        .join(ParticipantProjectLink, ParticipantProjectLink.participant_id == Participant.id)
        .where(
            ParticipantProjectLink.project_id == project_id,
            Participant.participant_code == code.upper(),
            Participant.deleted_at.is_(None),
        )
    )
    if found is None:
        raise _bad(f"Participant {side} ({code}) is not in this project")
    return found


def _mode(project: Project, value: str) -> str:
    if not value:
        if project.allows_face_to_face:
            return "FACE_TO_FACE"
        return "TELEPHONY"
    mode = MODES.get(value.strip().upper().replace(" ", "_"))
    if mode is None:
        raise _bad("Mode must be face_to_face or telephony")
    if (mode == "TELEPHONY" and not project.allows_telephony) or (
        mode == "FACE_TO_FACE" and not project.allows_face_to_face
    ):
        raise _bad("This project does not allow that recording mode")
    return mode


def _due(value: str) -> datetime | None:
    if not value:
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise _bad("Due date must be written YYYY-MM-DD") from None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _moderator(db: Session, project_id: uuid.UUID, email: str) -> User | None:
    if not email:
        return None
    not_member = _bad(f"Moderator {email} is not a member of this project")
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        raise not_member
    try:
        return service.require_member_with_role(db, project_id, user.id, Role.MODERATOR)
    except AppError as exc:
        if exc.code == "NOT_PROJECT_MEMBER":
            raise not_member from None
        raise _bad(f"{email} is not an active moderator") from None


def import_csv(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    text: str,
    confirm: bool,
    ip: str | None,
) -> list[RowResult]:
    project = get_manageable(db, principal, project_id, Perm.TASKS_ASSIGN)
    ensure_accepts_new_work(project)
    rows = read_rows(
        text,
        COLUMNS,
        required=("participant_a", "participant_b"),
        max_rows=MAX_IMPORT_ROWS,
        noun="tasks",
    )
    results: list[RowResult] = []
    for csv_row in rows:
        i, row = csv_row.line, csv_row.values
        pair = f"{row.get('participant_a', '')} + {row.get('participant_b', '')}"
        try:
            if csv_row.extra:
                raise _bad("This line has more values than the first line has columns")
            a = _participant(db, project.id, row.get("participant_a", ""), "A")
            b = _participant(db, project.id, row.get("participant_b", ""), "B")
            if a.id == b.id:
                raise _bad("Participant A and B must be different people")
            service.require_agreed(db, project.id, [a, b], status_code=422)
            mode = _mode(project, row.get("mode", ""))
            if mode == "TELEPHONY" and not (a.phone_e164_enc and b.phone_e164_enc):
                raise _bad("Telephony tasks need a phone number for both participants")
            priority = (row.get("priority") or "NORMAL").upper()
            if priority not in PRIORITIES:
                raise _bad("Priority must be low, normal, high or urgent")
            due_at = _due(row.get("due_date", ""))
            moderator = _moderator(db, project.id, row.get("moderator", ""))
            if not confirm:
                results.append(RowResult(i, pair, True, "Ready to add"))
                continue
            task = service.create_task(
                db,
                principal,
                project.id,
                service.TaskInput(
                    recording_mode=mode,
                    participant_a_id=a.id,
                    participant_b_id=b.id,
                    priority=priority,
                    due_at=due_at,
                ),
                ip,
            )
            message = "Added"
            if moderator is not None:
                try:
                    service.assign_moderator(db, principal, task.id, moderator.id, None, ip)
                    message = f"Added and assigned to {moderator.email}"
                except AppError as exc:
                    db.rollback()
                    message = f"Added, but not assigned: {exc.message}"
            results.append(RowResult(i, pair, True, message, task.task_code))
        except AppError as exc:
            db.rollback()
            results.append(RowResult(i, pair, False, exc.message))
    return results
