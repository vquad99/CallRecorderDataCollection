"""Participant personal page (D-067): a participant has no account; a staff member creates a
personal link for one participant in one project, and that link opens a page with the project's
consent form and the participant's own sessions.

Security: the link carries a 256-bit secret that is stored only as a hash, expires, can be replaced
or revoked at any time, and is sent to the API in a header (never in an address, so it reaches no
log). The page shows the participant's own details (code, name, language, dialect, the last two
digits of their phone), their own sessions (date, mode, length, state), their minutes (recorded,
accepted, and their payable half of the accepted ones, D-095) and their consent answer - read-only
apart from the consent answer itself; no other speaker, no full phone number, no audio (D-100).
A wrong, expired or revoked link answers exactly like one that never existed. A Super Admin can
open the same page for any participant, without a link and without changing anything (D-100).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailSender, EmailSendError, OutgoingEmail
from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.security import FieldCipher, hash_token, new_token
from app.modules.exports import minutes as minute_totals
from app.modules.participants import service as participants
from app.modules.participants.models import ConsentRecord, Participant, ParticipantPortalLink
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task

FINAL_KINDS = ("FTF_DERIVED_PCM", "TELEPHONY_DERIVED_PCM", "TELEPHONY_FINAL_STEREO")
MAX_SESSIONS = 200
# What a participant sees for each task state: no internal workflow words.
SESSION_STATES = {
    "ASSIGNED": "Planned",
    "IN_PROGRESS": "Planned",
    "ON_HOLD": "Planned",
    "RETURNED": "To be recorded again",
    "RECORDED": "Recorded, being checked",
    "AUDIO_QC": "Recorded, being checked",
    "ADMIN_REVIEW": "Recorded, being checked",
    "APPROVED": "Accepted",
    "REJECTED": "Not used",
}


def _gone() -> AppError:
    return AppError(
        "This link is not valid any more. Ask the project team for a new one.",
        code="LINK_INVALID",
        status_code=404,
    )


def create_link(
    db: Session,
    settings: Settings,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    ip: str | None,
    *,
    shown_to_staff: bool,
) -> tuple[str, datetime]:
    """A new personal link; any earlier link for this participant and project stops working.
    shown_to_staff: the caller sees the link (to hand it over), as opposed to only emailing it."""
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    if participant.deleted_at is not None:
        raise AppError("This participant was deleted", code="PARTICIPANT_DELETED", status_code=409)
    _revoke(db, project.id, participant.id)
    token = new_token()
    expires = datetime.now(UTC) + timedelta(days=settings.portal_link_days)
    db.add(
        ParticipantPortalLink(
            participant_id=participant.id,
            project_id=project.id,
            token_hash=hash_token(token),
            expires_at=expires,
            created_by=principal.user_id,
            shown_to_staff=shown_to_staff,
        )
    )
    audit.record(
        db,
        action="participant.portal_link_created",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"expires_at": expires.isoformat(), "shown_to_staff": shown_to_staff},
    )
    db.commit()
    # The secret sits after "#": browsers never send that part to a server.
    return f"{settings.public_app_url}/portal#{token}", expires


def email_link(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    sender: EmailSender,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    ip: str | None,
) -> tuple[bool, datetime]:
    """Create a fresh personal link and email it to the participant (the link is not shown to
    staff). Returns (sent, expires_at)."""
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    if participant.email_enc is None:
        raise AppError("This participant has no email address", code="NO_EMAIL", status_code=409)
    url, expires = create_link(
        db, settings, principal, project_id, participant_id, ip, shown_to_staff=False
    )
    body = (
        "Hello,\n\n"
        f'You are taking part in the project "{project.name}". Please read the consent form '
        "and give your answer on your private page:\n\n"
        f"{url}\n\n"
        "On the same page you can see your recording sessions and withdraw your consent at any "
        f"time. The link is personal - do not share it. It works until {expires:%d %B %Y}.\n\n"
        "If you did not expect this message, you can ignore it.\n"
    )
    try:
        sender.send(
            OutgoingEmail(
                to=cipher.decrypt(participant.email_enc),
                subject=f"Consent form for {project.name}",
                body=body,
            )
        )
    except EmailSendError:
        return False, expires
    audit.record(
        db,
        action="participant.portal_link_emailed",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return True, expires


def _revoke(db: Session, project_id: uuid.UUID, participant_id: uuid.UUID) -> int:
    rows = db.execute(
        update(ParticipantPortalLink)
        .where(
            ParticipantPortalLink.project_id == project_id,
            ParticipantPortalLink.participant_id == participant_id,
            ParticipantPortalLink.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
        .returning(ParticipantPortalLink.id)
    ).all()
    return len(rows)


def revoke_link(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    ip: str | None,
) -> None:
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    if _revoke(db, project.id, participant.id):
        audit.record(
            db,
            action="participant.portal_link_revoked",
            entity_type="participant",
            entity_id=participant.id,
            project_id=project.id,
            actor_id=principal.user_id,
            ip=ip,
        )
    db.commit()


def _resolve(db: Session, token: str) -> tuple[ParticipantPortalLink, Participant, Project]:
    if not 20 <= len(token) <= 200:
        raise _gone()
    link = db.scalar(
        select(ParticipantPortalLink).where(ParticipantPortalLink.token_hash == hash_token(token))
    )
    now = datetime.now(UTC)
    if link is None or link.revoked_at is not None or link.expires_at <= now:
        raise _gone()
    participant = db.get(Participant, link.participant_id)
    project = db.get(Project, link.project_id)
    if participant is None or project is None or participant.deleted_at is not None:
        raise _gone()
    return link, participant, project


@dataclass
class SessionRow:
    task_code: str
    mode: str
    day: datetime
    state: str
    minutes: float | None


@dataclass
class PortalView:
    participant_code: str
    display_name: str
    dialect: str
    phone_hint: str | None
    project_name: str
    language_code: str
    consent_policy_version: str
    consent_text: str
    consent_status: str | None
    consent_at: datetime | None
    consent_review: str | None
    consent_review_note: str
    sessions: list[SessionRow]
    accepted_minutes: float
    recorded_minutes: float
    payable_minutes: float
    link_expires_at: datetime | None


def own_consent(
    db: Session, participant_id: uuid.UUID, project_id: uuid.UUID
) -> ConsentRecord | None:
    """The participant's own latest answer on the form (project-wide, not tied to one task)."""
    return db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.participant_id == participant_id,
            ConsentRecord.project_id == project_id,
            ConsentRecord.task_id.is_(None),
            ConsentRecord.captured_by.is_(None),
        )
        .order_by(ConsentRecord.created_at.desc())
        .limit(1)
    )


def view(db: Session, token: str) -> PortalView:
    link, participant, project = _resolve(db, token)
    link.last_used_at = datetime.now(UTC)
    db.commit()
    return build_view(db, participant, project, link.expires_at)


def view_for_admin(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> PortalView:
    """The participant's own page as they see it, for a Super Admin (D-100); read-only."""
    if not principal.is_super_admin:
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    return build_view(db, participant, project, None)


def build_view(
    db: Session, participant: Participant, project: Project, expires: datetime | None
) -> PortalView:
    final = (
        select(Recording.task_id, func.max(AudioAsset.duration_ms).label("ms"))
        .join(AudioAsset, AudioAsset.recording_id == Recording.id)
        .where(Recording.state == "READY", AudioAsset.kind.in_(FINAL_KINDS))
        .group_by(Recording.task_id)
        .subquery()
    )
    rows = db.execute(
        select(Task.task_code, Task.recording_mode, Task.status, Task.created_at, final.c.ms)
        .outerjoin(final, final.c.task_id == Task.id)
        .where(
            Task.project_id == project.id,
            or_(Task.participant_a_id == participant.id, Task.participant_b_id == participant.id),
            Task.status.in_(tuple(SESSION_STATES)),
        )
        .order_by(Task.created_at.desc())
        .limit(MAX_SESSIONS)
    ).all()
    sessions = [
        SessionRow(
            task_code=r.task_code,
            mode=r.recording_mode,
            day=r.created_at,
            state=SESSION_STATES[r.status],
            minutes=round(r.ms / 60000, 1) if r.ms else None,
        )
        for r in rows
    ]
    totals = minute_totals.per_participant(db, project.id, [participant.id]).get(participant.id)
    answer = own_consent(db, participant.id, project.id)
    return PortalView(
        participant_code=participant.participant_code,
        display_name=participant.display_label,
        dialect=participant.dialect,
        phone_hint=participant.phone_hint,
        project_name=project.name,
        language_code=participant.language_code,
        consent_policy_version=project.consent_policy_version,
        consent_text=project.consent_text,
        consent_status=answer.status if answer else None,
        consent_at=answer.created_at if answer else None,
        consent_review=answer.review_status if answer else None,
        consent_review_note=answer.review_note
        if answer and answer.review_status == "REJECTED"
        else "",
        sessions=sessions,
        accepted_minutes=minute_totals.as_minutes(totals.approved_ms) if totals else 0.0,
        recorded_minutes=minute_totals.as_minutes(totals.recorded_ms) if totals else 0.0,
        payable_minutes=minute_totals.as_minutes(totals.payable_ms) if totals else 0.0,
        link_expires_at=expires,
    )


def answer_consent(db: Session, token: str, decision: str, ip: str | None) -> None:
    """The participant's own answer: GIVEN, REFUSED, or WITHDRAWN after having given it."""
    link, participant, project = _resolve(db, token)
    if not project.consent_text.strip():
        raise AppError(
            "The consent form for this project is not ready yet",
            code="CONSENT_FORM_MISSING",
            status_code=409,
        )
    current = own_consent(db, participant.id, project.id)
    if decision == "WITHDRAWN" and (current is None or current.status != "GIVEN"):
        raise AppError(
            "There is no consent to withdraw", code="NOTHING_TO_WITHDRAW", status_code=409
        )
    rejected = current is not None and current.review_status == "REJECTED"
    if current is not None and current.status == decision and not rejected:
        return  # the same answer again changes nothing
    db.add(
        ConsentRecord(
            participant_id=participant.id,
            project_id=project.id,
            task_id=None,
            status=decision,
            method="DIGITAL",
            policy_version=project.consent_policy_version,
            captured_by=None,
            link_shown_to=link.created_by if link.shown_to_staff else None,
            note=(
                "Answered on the participant's personal page, from a link handed out by staff"
                if link.shown_to_staff
                else "Answered by the participant on their personal page"
            ),
            form_text=project.consent_text,
            review_status="PENDING" if decision == "GIVEN" else None,
        )
    )
    audit.record(
        db,
        action="consent.self_recorded",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=None,
        ip=ip,
        after={"status": decision, "policy_version": project.consent_policy_version},
    )
    db.commit()
