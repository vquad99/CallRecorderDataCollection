"""Recorded, approved and payable minutes per participant (D-095, D-111), and the approved
conversations payments are made on (D-137).

Every conversation has two participants, and its length is split equally between them (owner,
2026-11-15): a 5-minute conversation gives each participant 2.5 recorded minutes, and 2.5
approved and payable minutes once the task is approved. A conversation's length is its task's
current recording (the newest finished one, the one an export delivers, D-135), so a re-recorded
task is counted once. Approved means the task is APPROVED. Lengths stay counted after retention
deletes the file, as on the dashboard.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.recordings.models import Recording, current_recordings, final_length_subquery
from app.modules.tasks.models import Task, TaskStatusHistory

SPEAKERS = 2  # one conversation, two participants, credited equally
_MS_PER_MINUTE = Decimal(60000)
_HUNDREDTH = Decimal("0.01")


@dataclass
class Minutes:
    conversations: int = 0
    recorded_ms: int = 0
    approved_conversations: int = 0
    approved_ms: int = 0

    @property
    def payable_ms(self) -> int:
        # Each participant's share of the approved conversations (already split equally).
        return self.approved_ms


def minutes(ms: int) -> Decimal:
    """Milliseconds as minutes, two places, half up: the one rounding every page and file uses."""
    return (Decimal(ms) / _MS_PER_MINUTE).quantize(_HUNDREDTH, rounding=ROUND_HALF_UP)


def as_minutes(ms: int) -> float:
    return float(minutes(ms))


def share(ms: int | None) -> int:
    """One participant's equal share of a conversation's length."""
    return int(ms or 0) // SPEAKERS


def conversations() -> Select[*tuple[Any, ...]]:
    """One row per task with a finished recording: (task_id, project_id, status,
    participant_a_id, participant_b_id, recorded_by, ms), from the task's current recording, who
    made it and its length."""
    current = current_recordings()
    length = final_length_subquery()
    return (
        select(
            Task.id.label("task_id"),
            Task.project_id,
            Task.status,
            Task.participant_a_id,
            Task.participant_b_id,
            Recording.created_by.label("recorded_by"),
            length.c.ms,
        )
        .join(current, current.c.task_id == Task.id)
        .join(Recording, Recording.id == current.c.recording_id)
        .join(length, length.c.recording_id == current.c.recording_id)
    )


def approved_conversations(
    project_ids: Iterable[uuid.UUID], start: datetime | None, end: datetime | None
) -> Select[*tuple[Any, ...]]:
    """conversations() of APPROVED tasks in these projects, approved at or after `start` and
    before `end` (either may be left open). A task is approved once: APPROVED is final."""
    approved = (
        select(TaskStatusHistory.task_id, func.max(TaskStatusHistory.created_at).label("at"))
        .where(TaskStatusHistory.to_status == "APPROVED")
        .group_by(TaskStatusHistory.task_id)
        .subquery()
    )
    query = (
        conversations()
        .join(approved, approved.c.task_id == Task.id)
        .where(Task.status == "APPROVED", Task.project_id.in_(list(project_ids)))
    )
    if start is not None:
        query = query.where(approved.c.at >= start)
    if end is not None:
        query = query.where(approved.c.at < end)
    return query


def per_participant(
    db: Session, project_id: uuid.UUID, participant_ids: Iterable[uuid.UUID] | None = None
) -> dict[uuid.UUID, Minutes]:
    """Totals per participant in one project, in one query whatever the number of people."""
    query = conversations().where(Task.project_id == project_id)
    wanted = None if participant_ids is None else set(participant_ids)
    if wanted is not None:
        if not wanted:
            return {}
        query = query.where(Task.participant_a_id.in_(wanted) | Task.participant_b_id.in_(wanted))
    totals: dict[uuid.UUID, Minutes] = {}
    for row in db.execute(query):
        ms = share(row.ms)
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
