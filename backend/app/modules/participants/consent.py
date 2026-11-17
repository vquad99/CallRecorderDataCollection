"""Consent: the one place that reads consent records and decides what they mean (PART-006, D-119).

A participant's consent reaches the platform in two ways:
- noted: the moderator records it for one task (one session), with how it was given;
- own answer: the participant answers the project's consent form on their personal page
  (`ConsentRecord.is_own_answer`), which staff then review.

For a task, each side (A, B) has the newest noted record and the newest own answer. The newest
of the two is the participant's current word:
- recording may start when that word is "given" and, if it is an own answer, staff have not sent
  it back (review REJECTED);
- the participant is not called when that word is a refusal or a withdrawal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.participants.models import ConsentRecord
from app.modules.tasks.models import Task

SAYS_NO = frozenset({"REFUSED", "WITHDRAWN"})


@dataclass
class SideConsent:
    side: str  # "A" or "B"
    participant_id: uuid.UUID
    noted: list[ConsentRecord] = field(default_factory=list)  # for this task, oldest first
    own: list[ConsentRecord] = field(default_factory=list)  # own answers, oldest first

    @property
    def latest_noted(self) -> ConsentRecord | None:
        return self.noted[-1] if self.noted else None

    @property
    def latest_own(self) -> ConsentRecord | None:
        return self.own[-1] if self.own else None

    @property
    def newest(self) -> ConsentRecord | None:
        """The participant's current word: the newer of the noted record and the own answer."""
        words = [r for r in (self.latest_noted, self.latest_own) if r is not None]
        return max(words, key=lambda r: r.created_at) if words else None

    @property
    def may_record(self) -> bool:
        word = self.newest
        return (
            word is not None
            and word.status == "GIVEN"
            and not (word.is_own_answer and word.review_status == "REJECTED")
        )

    @property
    def says_no(self) -> bool:
        word = self.newest
        return word is not None and word.status in SAYS_NO


def for_task(db: Session, task: Task) -> list[SideConsent]:
    """Both sides of a task with their consent records, in one query."""
    sides = [
        SideConsent("A", task.participant_a_id),
        SideConsent("B", task.participant_b_id),
    ]
    by_participant = {s.participant_id: s for s in sides}
    for record in db.scalars(
        select(ConsentRecord)
        .where(
            ConsentRecord.participant_id.in_(list(by_participant)),
            ConsentRecord.project_id == task.project_id,
            or_(ConsentRecord.task_id == task.id, ConsentRecord.is_own_answer),
        )
        .order_by(ConsentRecord.created_at)
    ):
        side = by_participant[record.participant_id]
        (side.own if record.is_own_answer else side.noted).append(record)
    return sides


def missing(sides: list[SideConsent]) -> list[str]:
    """The sides without consent to record (D-119)."""
    return [s.side for s in sides if not s.may_record]


def refused(sides: list[SideConsent]) -> list[str]:
    """The sides whose current word is a refusal or a withdrawal: they are not called."""
    return [s.side for s in sides if s.says_no]


def latest_own_answer(
    db: Session, participant_id: uuid.UUID, project_id: uuid.UUID
) -> ConsentRecord | None:
    """The participant's own latest answer on the project's consent form."""
    return db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.participant_id == participant_id,
            ConsentRecord.project_id == project_id,
            ConsentRecord.is_own_answer,
        )
        .order_by(ConsentRecord.created_at.desc())
        .limit(1)
    )
