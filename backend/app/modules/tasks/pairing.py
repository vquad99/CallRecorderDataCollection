"""Who may be paired in a new task (D-143), per project:

- both speakers have the speaker details the project needs (participants/speakers.py, D-145);
- both are within the project's speaker ages (D-145);
- each speaker has at most `projects.max_conversations_per_speaker` conversations in the project
  (empty = no limit);
- with `projects.unique_pairs`, the same two people (either way round) never share a second task.

A conversation counts while its task is not CANCELLED or REJECTED: a cancelled or rejected task
frees its place. A deleted task is gone (D-115) and counts for nothing. The rules apply to new
tasks only; tasks made before stay as they are.

create_task checks them (the single form and every file row go through it), inside a lock per
project so two tasks made at the same moment cannot both take the last place. The file check
counts the rows before it too (`Tally.add`), so a file cannot pair the same people twice.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.participants import speakers
from app.modules.participants.models import Participant
from app.modules.projects.models import Project
from app.modules.tasks.models import Task

NOT_COUNTED = ("CANCELLED", "REJECTED")


@dataclass
class Tally:
    """The project's rules and the conversations that count against them."""

    project: Project
    conversations: dict[uuid.UUID, int] = field(default_factory=dict)
    # Each pair that shares a counted task, with that task's code.
    pairs: dict[frozenset[uuid.UUID], str] = field(default_factory=dict)

    @property
    def limit(self) -> int | None:
        return self.project.max_conversations_per_speaker

    def add(self, a: uuid.UUID, b: uuid.UUID, task_code: str) -> None:
        for pid in (a, b):
            self.conversations[pid] = self.conversations.get(pid, 0) + 1
        self.pairs.setdefault(frozenset((a, b)), task_code)

    def partners(self, pid: uuid.UUID) -> list[uuid.UUID]:
        """The people this participant already has a counted conversation with."""
        return sorted(
            (other for pair in self.pairs if pid in pair for other in pair - {pid}), key=str
        )


def lock(db: Session, project_id: uuid.UUID) -> None:
    """One new task at a time per project, until the transaction ends."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"task-pairs:{project_id}"}
    )


def tally(
    db: Session, project: Project, participant_ids: Collection[uuid.UUID] | None = None
) -> Tally:
    """The counted conversations of the project, of these participants only when given."""
    result = Tally(project)
    query = select(Task.task_code, Task.participant_a_id, Task.participant_b_id).where(
        Task.project_id == project.id, Task.status.not_in(NOT_COUNTED)
    )
    if participant_ids is not None:
        ids = list(participant_ids)
        if not ids:
            return result
        query = query.where(or_(Task.participant_a_id.in_(ids), Task.participant_b_id.in_(ids)))
    for code, a, b in db.execute(query.order_by(Task.created_at)).all():
        result.add(a, b, code)
    return result


def _people(codes: list[str]) -> str:
    return f"{'Participant' if len(codes) == 1 else 'Participants'} {' and '.join(codes)}"


def check(t: Tally, a: Participant, b: Participant) -> None:
    """422 SPEAKER_DETAILS_MISSING, 422 SPEAKER_AGE_OUT_OF_RANGE, 409 SPEAKER_LIMIT_REACHED or
    409 PAIR_ALREADY_USED, in that order, naming the people; nothing when A and B may be
    paired."""
    incomplete = [p.participant_code for p in (a, b) if not speakers.complete(p, t.project)]
    if incomplete:
        raise AppError(
            f"{_people(incomplete)} {'has' if len(incomplete) == 1 else 'have'} no complete "
            "speaker details yet: add them with Edit.",
            code="SPEAKER_DETAILS_MISSING",
            status_code=422,
            details=[{"participants": incomplete}],
        )
    speakers.check_ages(t.project, (a, b))
    limit = t.limit
    if limit is not None:
        full = [p.participant_code for p in (a, b) if t.conversations.get(p.id, 0) >= limit]
        if full:
            each = "conversation" if limit == 1 else "conversations"
            raise AppError(
                f"{_people(full)} already {'has' if len(full) == 1 else 'have'} {limit} "
                f"{each} in this project, the most for one speaker.",
                code="SPEAKER_LIMIT_REACHED",
                status_code=409,
                details=[{"participants": full, "limit": limit}],
            )
    used = t.pairs.get(frozenset((a.id, b.id))) if t.project.unique_pairs else None
    if used is not None:
        raise AppError(
            f"{a.participant_code} and {b.participant_code} already have a conversation together "
            f"in this project ({used}): each pair of speakers only once.",
            code="PAIR_ALREADY_USED",
            status_code=409,
            details=[{"participants": [a.participant_code, b.participant_code], "task": used}],
        )
