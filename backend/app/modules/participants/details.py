"""Everything about one participant in one project, for the people who manage participants
(D-104): who added them and when, the projects they are in, their personal link, every session
they were part of with its consent and recording, and the phone calls made to them.

The profile itself (name, phone, email, notes), the consent form and the minutes are put together
by the router with the rules those already have; this module adds the rest. Nothing here is
shown to people who only see a project: PARTICIPANTS_MANAGE in the project is required.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import Perm
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.participants import service
from app.modules.participants.models import (
    ConsentRecord,
    Participant,
    ParticipantPortalLink,
    ParticipantProjectLink,
)
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task, TaskAssignment
from app.modules.telephony.models import Call

FINAL_KINDS = ("FTF_DERIVED_PCM", "TELEPHONY_DERIVED_PCM", "TELEPHONY_FINAL_STEREO")
MAX_SESSIONS = 200


@dataclass
class ProjectRef:
    id: uuid.UUID
    code: str
    name: str


@dataclass
class Removed:
    at: datetime
    by: str | None
    reason: str | None


@dataclass
class Link:
    active: bool
    created_at: datetime
    created_by: str | None
    expires_at: datetime
    last_used_at: datetime | None
    handed_out: bool  # shown to staff to pass on, not only emailed


@dataclass
class SessionRow:
    task_id: uuid.UUID
    task_code: str
    mode: str
    slot: str  # "A" or "B"
    status: str
    created_at: datetime
    other_participant_code: str
    moderator: str | None
    consent_status: str | None
    consent_method: str | None
    consent_at: datetime | None
    recordings: int
    recording_seconds: float | None
    recorded_at: datetime | None
    phone_calls: int


@dataclass
class Calls:
    total: int
    recorded: int
    last_at: datetime | None
    last_state: str | None


@dataclass
class Details:
    project: Project
    participant: Participant
    added_by: str | None
    projects: list[ProjectRef]
    removed: Removed | None
    link: Link | None
    sessions: list[SessionRow]
    sessions_total: int
    calls: Calls | None


def get(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> Details:
    project, participant = service.get_in_project(db, principal, project_id, participant_id)
    if not principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        raise forbidden()

    def name(user_id: uuid.UUID | None) -> str | None:
        user = db.get(User, user_id) if user_id else None
        return user.display_name if user else None

    # The other projects are named only when this person may see them: a project the caller is
    # not part of stays unknown to them.
    linked = db.execute(
        select(Project.id, Project.code, Project.name)
        .join(ParticipantProjectLink, ParticipantProjectLink.project_id == Project.id)
        .where(ParticipantProjectLink.participant_id == participant.id)
        .order_by(Project.code)
    ).all()
    projects = [
        ProjectRef(pid, code, pname)
        for pid, code, pname in linked
        if principal.is_super_admin or pid in principal.project_ids
    ]

    newest_link = db.scalar(
        select(ParticipantPortalLink)
        .where(
            ParticipantPortalLink.participant_id == participant.id,
            ParticipantPortalLink.project_id == project.id,
        )
        .order_by(ParticipantPortalLink.created_at.desc())
        .limit(1)
    )
    now = datetime.now(UTC)
    link = (
        Link(
            active=newest_link.revoked_at is None and newest_link.expires_at > now,
            created_at=newest_link.created_at,
            created_by=name(newest_link.created_by),
            expires_at=newest_link.expires_at,
            last_used_at=newest_link.last_used_at,
            handed_out=newest_link.shown_to_staff,
        )
        if newest_link is not None
        else None
    )

    mine = or_(Task.participant_a_id == participant.id, Task.participant_b_id == participant.id)
    in_project = (Task.project_id == project.id, mine)
    sessions_total = int(db.scalar(select(func.count()).select_from(Task).where(*in_project)) or 0)
    tasks = list(
        db.scalars(
            select(Task).where(*in_project).order_by(Task.created_at.desc()).limit(MAX_SESSIONS)
        )
    )
    task_ids = [t.id for t in tasks]
    others = {
        t.participant_b_id if t.participant_a_id == participant.id else t.participant_a_id
        for t in tasks
    }
    codes = (
        {
            pid: code
            for pid, code in db.execute(
                select(Participant.id, Participant.participant_code).where(
                    Participant.id.in_(others)
                )
            ).all()
        }
        if others
        else {}
    )
    moderators: dict[uuid.UUID, str] = {}
    consents: dict[uuid.UUID, ConsentRecord] = {}
    recorded: dict[uuid.UUID, tuple[int, int | None, datetime | None]] = {}
    call_counts: dict[uuid.UUID, int] = {}
    if task_ids:
        for tid, display_name in db.execute(
            select(TaskAssignment.task_id, User.display_name)
            .join(User, User.id == TaskAssignment.user_id)
            .where(
                TaskAssignment.task_id.in_(task_ids),
                TaskAssignment.role_code == "MODERATOR",
                TaskAssignment.active.is_(True),
            )
        ).all():
            moderators[tid] = display_name
        # The newest consent answer for each session wins (rows come oldest first).
        for record in db.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.participant_id == participant.id,
                ConsentRecord.task_id.in_(task_ids),
            )
            .order_by(ConsentRecord.created_at)
        ):
            if record.task_id is not None:
                consents[record.task_id] = record
        # Finished recordings of each session: how many, and the newest one's length and time.
        length = (
            select(AudioAsset.recording_id, func.max(AudioAsset.duration_ms).label("ms"))
            .where(AudioAsset.kind.in_(FINAL_KINDS))
            .group_by(AudioAsset.recording_id)
            .subquery()
        )
        for tid, started_at, ms in db.execute(
            select(Recording.task_id, Recording.started_at, length.c.ms)
            .outerjoin(length, length.c.recording_id == Recording.id)
            .where(Recording.task_id.in_(task_ids), Recording.state == "READY")
            .order_by(Recording.started_at)
        ).all():
            count = recorded.get(tid, (0, None, None))[0] + 1
            recorded[tid] = (count, int(ms) if ms is not None else None, started_at)
        for tid, n in db.execute(
            select(Call.task_id, func.count())
            .where(Call.task_id.in_(task_ids))
            .group_by(Call.task_id)
        ).all():
            call_counts[tid] = int(n)

    sessions = []
    for t in tasks:
        is_a = t.participant_a_id == participant.id
        consent = consents.get(t.id)
        count, ms, at = recorded.get(t.id, (0, None, None))
        sessions.append(
            SessionRow(
                task_id=t.id,
                task_code=t.task_code,
                mode=t.recording_mode,
                slot="A" if is_a else "B",
                status=t.status,
                created_at=t.created_at,
                other_participant_code=codes.get(
                    t.participant_b_id if is_a else t.participant_a_id, ""
                ),
                moderator=moderators.get(t.id),
                consent_status=consent.status if consent else None,
                consent_method=consent.method if consent else None,
                consent_at=consent.created_at if consent else None,
                recordings=count,
                recording_seconds=round(ms / 1000, 1) if ms is not None else None,
                recorded_at=at,
                phone_calls=call_counts.get(t.id, 0),
            )
        )

    # Phone calls ring participant A: the calls of the sessions where this person is A.
    as_a = (Call.project_id == project.id, Task.participant_a_id == participant.id)
    total, recorded_calls = db.execute(
        select(func.count(), func.count().filter(Call.state == "RECORDED"))
        .select_from(Call)
        .join(Task, Task.id == Call.task_id)
        .where(*as_a)
    ).one()
    last = db.execute(
        select(Call.dialled_at, Call.state)
        .join(Task, Task.id == Call.task_id)
        .where(*as_a)
        .order_by(Call.dialled_at.desc())
        .limit(1)
    ).first()
    calls = (
        Calls(int(total), int(recorded_calls), last[0] if last else None, last[1] if last else None)
        if total
        else None
    )

    return Details(
        project=project,
        participant=participant,
        added_by=name(participant.created_by),
        projects=projects,
        removed=(
            Removed(
                participant.deleted_at, name(participant.deleted_by), participant.deletion_reason
            )
            if participant.deleted_at is not None
            else None
        ),
        link=link,
        sessions=sessions,
        sessions_total=sessions_total,
        calls=calls,
    )
