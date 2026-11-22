"""Participant personal page (D-067): a participant has no account; a personal link for one
participant in one project is emailed to them (never shown to staff), and that link opens a page
with the project's consent form and the participant's own sessions.

Security: the link carries a 256-bit secret that is stored only as a hash, expires, can be replaced
or revoked at any time, and is sent to the API in a header (never in an address, so it reaches no
log). The page shows the participant's own details (code, name, language, dialect, the last two
digits of their phone), their own sessions (date, mode, length, state), their minutes (recorded,
accepted, and their payable half of the accepted ones, D-095) and their consent answer - read-only
apart from the consent answer itself; no other speaker, no full phone number, no audio (D-100).
The answer counts at once, and an "I agree" is final: nobody reviews it and it cannot be withdrawn
(D-129). Where the project takes signed forms and staff uploaded theirs, the page says so and
there is nothing to answer (D-144). The form shown with an "I agree" is the text they agreed to,
not the project's newer one (D-068). A wrong, expired or revoked link answers exactly like one
that never existed. A Super Admin can open the same page for any participant, without a link and
without changing anything (D-100).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailSender, EmailSendError, OutgoingEmail
from app.core.errors import AppError, forbidden
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.security import FieldCipher, hash_token, new_token
from app.modules.exports import minutes as minute_totals
from app.modules.participants import consent
from app.modules.participants import service as participants
from app.modules.participants.models import ConsentRecord, Participant, ParticipantPortalLink
from app.modules.projects.models import Project
from app.modules.tasks.models import Task

logger = logging.getLogger("app.portal")

MAX_SESSIONS = 200
# What a participant sees for each task state: no internal workflow words.
SESSION_STATES = {
    "ASSIGNED": "Planned",
    "IN_PROGRESS": "Planned",
    "ON_HOLD": "Planned",
    "RECORDED": "Recorded, being checked",
    "AUDIO_QC": "Recorded, being checked",
    "ADMIN_REVIEW": "Recorded, being checked",
    "CONSENT_FIX": "Recorded, being checked",
    "APPROVED": "Accepted",
    "REJECTED": "Not used",
}
# Each email replaces the link sent before it: a participant is not emailed again this soon.
EMAIL_AGAIN_AFTER = timedelta(minutes=10)
EMAILED_RECENTLY = (
    f"Emailed less than {EMAIL_AGAIN_AFTER // timedelta(minutes=1)} minutes ago: not sent again."
)


def _gone() -> AppError:
    return AppError(
        "This link is not valid any more. Ask the project team for a new one.",
        code="LINK_INVALID",
        status_code=404,
    )


def email_of(participant: Participant) -> str:
    """The participant's email address (encrypted), or 409 NO_EMAIL."""
    if participant.email_enc is None:
        raise AppError(
            "This participant has no email address. Add one with Edit on the Participants page.",
            code="NO_EMAIL",
            status_code=409,
        )
    return participant.email_enc


def check_linkable(participant: Participant) -> None:
    """409 when this participant can no longer be given a personal link."""
    if participant.deleted_at is not None:
        raise AppError("This participant was deleted", code="PARTICIPANT_DELETED", status_code=409)


def _issue(
    db: Session,
    settings: Settings,
    project: Project,
    participant: Participant,
    created_by: uuid.UUID,
    ip: str | None,
) -> tuple[str, datetime]:
    """A new personal link, to be emailed; any earlier link for this participant and project
    stops working."""
    _revoke(db, project.id, participant.id)
    token = new_token()
    expires = datetime.now(UTC) + timedelta(days=settings.portal_link_days)
    db.add(
        ParticipantPortalLink(
            participant_id=participant.id,
            project_id=project.id,
            token_hash=hash_token(token),
            expires_at=expires,
            created_by=created_by,
        )
    )
    audit.record(
        db,
        action="participant.portal_link_created",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=created_by,
        ip=ip,
        after={"expires_at": expires.isoformat(), "shown_to_staff": False},
    )
    db.commit()
    # The secret sits after "#": browsers never send that part to a server.
    return f"{settings.public_app_url}/portal#{token}", expires


def recently_emailed(
    db: Session, project_id: uuid.UUID, participant_ids: Collection[uuid.UUID]
) -> set[uuid.UUID]:
    """Those of these participants emailed a link of this project less than EMAIL_AGAIN_AFTER
    ago that still works: they are not emailed again yet."""
    if not participant_ids:
        return set()
    return set(
        db.scalars(
            select(ParticipantPortalLink.participant_id).where(
                ParticipantPortalLink.project_id == project_id,
                ParticipantPortalLink.participant_id.in_(participant_ids),
                ParticipantPortalLink.shown_to_staff.is_(False),
                ParticipantPortalLink.revoked_at.is_(None),
                ParticipantPortalLink.created_at > datetime.now(UTC) - EMAIL_AGAIN_AFTER,
            )
        )
    )


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
    staff). Returns (sent, expires_at). 409 EMAILED_RECENTLY within EMAIL_AGAIN_AFTER of the
    last email."""
    project, participant = participants.get_in_project(
        db, principal, project_id, participant_id, Perm.PARTICIPANTS_MANAGE
    )
    consent.require_online(project)  # D-144: nothing is emailed where staff upload the form
    email_of(participant)
    check_linkable(participant)
    if recently_emailed(db, project.id, [participant.id]):
        raise AppError(EMAILED_RECENTLY, code="EMAILED_RECENTLY", status_code=409)
    return _email(db, settings, cipher, sender, project, participant, principal.user_id, ip)


def _email(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    sender: EmailSender,
    project: Project,
    participant: Participant,
    actor_id: uuid.UUID,
    ip: str | None,
) -> tuple[bool, datetime]:
    address = cipher.decrypt(email_of(participant))
    url, expires = _issue(db, settings, project, participant, actor_id, ip)
    # Where the link went, as a fingerprint (SECB-02): the log shows it, never the address.
    sent_to = participants.address_fingerprint(settings, address)
    body = (
        "Hello,\n\n"
        f'You are taking part in the project "{project.name}". Please read the consent form '
        "and give your answer on your private page:\n\n"
        f"{url}\n\n"
        "On the same page you can see your recording sessions. The link is personal - do not "
        f"share it. It works until {expires:%d %B %Y}.\n\n"
        "If you did not expect this message, you can ignore it.\n"
    )
    try:
        sender.send(
            OutgoingEmail(
                to=address,
                subject=f"Consent form for {project.name}",
                body=body,
            )
        )
    except EmailSendError:
        # The new link reached nobody: it does not stay working, nor hold back the next try.
        _revoke(db, project.id, participant.id)
        db.commit()
        return False, expires
    audit.record(
        db,
        action="participant.portal_link_emailed",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=actor_id,
        ip=ip,
        after={"to": sent_to},
    )
    db.commit()
    return True, expires


SEND_LINKS_TASK = "portal.send_links"


def send_links_job(
    state: Any, project_id: str, participant_ids: list[str], actor_id: str, ip: str | None
) -> None:
    """Background (D-129): a fresh personal link emailed to each participant who just joined the
    project. Anyone deleted or without an email address is skipped, and anyone emailed a link that
    still works less than EMAIL_AGAIN_AFTER ago (by hand or by another job since this one was
    queued, PART-08): a second email would end the link in the first. A failed email is logged
    and the others still go out."""
    with state.session_factory() as db:
        project = db.get(Project, uuid.UUID(project_id))
        if project is None or consent.takes_uploads(project):
            return  # gone, or switched to signed forms uploaded by staff since (D-144)
        for pid in participant_ids:
            participant = db.get(Participant, uuid.UUID(pid))
            if participant is None:
                continue
            try:
                check_linkable(participant)
                if recently_emailed(db, project.id, [participant.id]):
                    logger.info(
                        "consent_link_skipped",
                        extra={"participant_id": pid, "why": "EMAILED_RECENTLY"},
                    )
                    continue
                sent, _ = _email(
                    db,
                    state.settings,
                    state.cipher,
                    state.email_sender,
                    project,
                    participant,
                    uuid.UUID(actor_id),
                    ip,
                )
            except AppError as exc:
                logger.info("consent_link_skipped", extra={"participant_id": pid, "why": exc.code})
                continue
            except Exception:
                db.rollback()
                logger.exception("consent_link_failed", extra={"participant_id": pid})
                continue
            if not sent:
                logger.warning("consent_link_email_failed", extra={"participant_id": pid})


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
    project, participant = participants.get_in_project(
        db, principal, project_id, participant_id, Perm.PARTICIPANTS_MANAGE
    )
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
    sessions: list[SessionRow]
    accepted_minutes: float
    recorded_minutes: float
    payable_minutes: float
    link_expires_at: datetime | None


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
        raise forbidden()
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    return build_view(db, participant, project, None)


def build_view(
    db: Session, participant: Participant, project: Project, expires: datetime | None
) -> PortalView:
    theirs = (
        Task.project_id == project.id,
        or_(Task.participant_a_id == participant.id, Task.participant_b_id == participant.id),
    )
    # A session's length is its current recording's, as on the minutes (D-095, D-135).
    final = minute_totals.conversations(select(Task.id).where(*theirs)).subquery()
    rows = db.execute(
        select(Task.task_code, Task.recording_mode, Task.status, Task.created_at, final.c.ms)
        .outerjoin(final, final.c.task_id == Task.id)
        .where(*theirs, Task.status.in_(tuple(SESSION_STATES)))
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
    # Their consent as it counts for staff too: a signed form uploaded in a project that takes
    # them reads UPLOADED, with the day it came in (PART-01).
    standing = consent.standings(db, project, [participant.id])[participant.id]
    answer = standing.answer
    if answer is not None and consent.word(answer) in ("GIVEN", "WITHDRAWN"):
        # The form as they answered it, not the project's newer one (D-068, PART-04).
        version, text = answer.policy_version, answer.form_text or project.consent_text
    else:
        # No answer, or "I do not agree": the form an "I agree" would answer now.
        version, text = project.consent_policy_version, project.consent_text
    return PortalView(
        participant_code=participant.participant_code,
        display_name=participant.display_label,
        dialect=participant.dialect,
        phone_hint=participant.phone_hint,
        project_name=project.name,
        language_code=participant.language_code,
        consent_policy_version=version,
        consent_text=text,
        consent_status=standing.status,
        consent_at=standing.at,
        sessions=sessions,
        accepted_minutes=minute_totals.as_minutes(totals.approved_ms) if totals else 0.0,
        recorded_minutes=minute_totals.as_minutes(totals.recorded_ms) if totals else 0.0,
        payable_minutes=minute_totals.as_minutes(totals.payable_ms) if totals else 0.0,
        link_expires_at=expires,
    )


FORM_ON_FILE = (
    "Your signed consent form is on file with the project team: there is nothing to answer here."
)


def answer_consent(
    db: Session,
    settings: Settings,
    cipher: FieldCipher,
    token: str,
    decision: str,
    ip: str | None,
) -> None:
    """The participant's own answer, GIVEN or REFUSED; it counts at once. "I do not agree" can
    become "I agree" later; an "I agree" cannot be changed (D-129), nor can a signed form staff
    uploaded where the project takes them (409 CONSENT_FORM_ON_FILE, PART-01: an answer would
    change nothing, so none is kept). The record says where the link was emailed (SECB-02)."""
    link, participant, project = _resolve(db, token)
    if consent.takes_uploads(project) and consent.signed_forms(db, project.id, [participant.id]):
        raise AppError(FORM_ON_FILE, code="CONSENT_FORM_ON_FILE", status_code=409)
    if not project.consent_text.strip():
        raise AppError(
            "The consent form for this project is not ready yet",
            code="CONSENT_FORM_MISSING",
            status_code=409,
        )
    current = consent.word(consent.latest_own_answer(db, participant.id, project.id))
    if current == decision:
        return  # the same answer again changes nothing
    if current == "GIVEN":
        raise AppError(
            "You have already agreed to this consent form. Your answer cannot be changed.",
            code="ALREADY_AGREED",
            status_code=409,
        )
    # An email change ends every link (D-088), so a working emailed link went to the address on
    # file now: the record names it masked, the audit as a fingerprint (SECB-02). An answer from
    # an address staff put on file for a few minutes then shows in the consent history.
    address = (
        cipher.decrypt(participant.email_enc)
        if participant.email_enc and not link.shown_to_staff
        else None
    )
    if link.shown_to_staff:
        note = "Answered on the participant's personal page, from a link handed out by staff"
    elif address:
        note = (
            "Answered by the participant on their personal page "
            f"(link emailed to {participants.masked_address(address)})"
        )
    else:
        note = "Answered by the participant on their personal page"
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
            note=note,
            form_text=project.consent_text,
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
        after={
            "status": decision,
            "policy_version": project.consent_policy_version,
            "emailed_to": participants.address_fingerprint(settings, address) if address else None,
        },
    )
    db.commit()
