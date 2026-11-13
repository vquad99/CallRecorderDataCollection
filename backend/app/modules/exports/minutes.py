"""Recorded, approved and payable minutes per participant (D-095).

Every conversation has two participants, so each one is credited with half of it: a 5-minute
approved conversation gives each participant 2.5 payable minutes. A conversation's length is the
newest finished recording of its task (the one an export delivers), so a re-recorded task is
counted once. Approved means the task is APPROVED. Lengths stay counted after retention deletes
the file, as on the dashboard.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task

FINAL_KINDS = ("FTF_DERIVED_PCM", "TELEPHONY_DERIVED_PCM", "TELEPHONY_FINAL_STEREO")
SPEAKERS = 2  # one conversation, two participants, credited equally


@dataclass
class Minutes:
    conversations: int = 0
    recorded_ms: int = 0
    approved_conversations: int = 0
    approved_ms: int = 0

    @property
    def payable_ms(self) -> int:
        return self.approved_ms // SPEAKERS


def as_minutes(ms: int) -> float:
    return round(ms / 60000, 2)


def per_participant(
    db: Session, project_id: uuid.UUID, participant_ids: Iterable[uuid.UUID] | None = None
) -> dict[uuid.UUID, Minutes]:
    """Totals per participant in one project, in one query whatever the number of people."""
    newest = (
        select(
            Recording.id.label("recording_id"),
            Recording.task_id,
            func.row_number()
            .over(partition_by=Recording.task_id, order_by=Recording.started_at.desc())
            .label("rank"),
        )
        .where(Recording.state == "READY")
        .subquery()
    )
    length = (
        select(AudioAsset.recording_id, func.max(AudioAsset.duration_ms).label("ms"))
        .where(AudioAsset.kind.in_(FINAL_KINDS))
        .group_by(AudioAsset.recording_id)
        .subquery()
    )
    query = (
        select(Task.participant_a_id, Task.participant_b_id, Task.status, length.c.ms)
        .join(newest, (newest.c.task_id == Task.id) & (newest.c.rank == 1))
        .join(length, length.c.recording_id == newest.c.recording_id)
        .where(Task.project_id == project_id)
    )
    wanted = None if participant_ids is None else set(participant_ids)
    if wanted is not None:
        if not wanted:
            return {}
        query = query.where(Task.participant_a_id.in_(wanted) | Task.participant_b_id.in_(wanted))
    totals: dict[uuid.UUID, Minutes] = {}
    for row in db.execute(query):
        ms = int(row.ms or 0)
        for pid in (row.participant_a_id, row.participant_b_id):
            if wanted is not None and pid not in wanted:
                continue
            t = totals.setdefault(pid, Minutes())
            t.conversations += 1
            t.recorded_ms += ms
            if row.status == "APPROVED":
                t.approved_conversations += 1
                t.approved_ms += ms
    return totals
