"""Consent: the one place that reads consent records and decides what they mean (PART-006, D-119,
D-129).

A participant's consent in a project is their own answer on the project's consent form, given on
their personal page (`ConsentRecord.is_own_answer`). It counts at once: there is no staff review,
and once they agree they cannot withdraw (D-129). Someone who answered "I do not agree" may agree
later. Tasks are made only for people who agreed, and calling and recording check it again.

Older records stay readable as history but decide nothing: consent a moderator noted for one task,
and the staff review of an answer. One thing from that review still counts: an "agree" that staff
sent back (review REJECTED) is not agreed - the participant was asked to answer again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.modules.participants.models import ConsentRecord
from app.modules.tasks.models import Task


def word(answer: ConsentRecord | None) -> str | None:
    """What the participant's latest own answer counts as now: GIVEN, REFUSED, WITHDRAWN (only
    before D-129), or None when there is no answer - an "agree" sent back by staff before D-129
    counts as none."""
    if answer is None or (answer.status == "GIVEN" and answer.review_status == "REJECTED"):
        return None
    return answer.status


def agreed(answer: ConsentRecord | None) -> bool:
    return word(answer) == "GIVEN"


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
    def status(self) -> str | None:
        return word(self.latest_own)

    @property
    def may_record(self) -> bool:
        return agreed(self.latest_own)


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


def latest_own_answers(
    db: Session, project_id: uuid.UUID, participant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ConsentRecord]:
    """Each participant's latest own answer on the project's consent form, in one query."""
    if not participant_ids:
        return {}
    rows = db.scalars(
        select(ConsentRecord)
        .where(
            ConsentRecord.project_id == project_id,
            ConsentRecord.participant_id.in_(participant_ids),
            ConsentRecord.is_own_answer,
        )
        .order_by(ConsentRecord.participant_id, ConsentRecord.created_at.desc())
        .ext(distinct_on(ConsentRecord.participant_id))
    )
    return {r.participant_id: r for r in rows}


def latest_own_answer(
    db: Session, participant_id: uuid.UUID, project_id: uuid.UUID
) -> ConsentRecord | None:
    """The participant's own latest answer on the project's consent form."""
    return latest_own_answers(db, project_id, [participant_id]).get(participant_id)
