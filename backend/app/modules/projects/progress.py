"""A project's progress against its targets (D-148): the Progress tab,
`GET /projects/{id}/progress`.

For the people who manage the project (`projects.manage`, like the other tabs, D-104). Everything
comes from three set-based queries over this project's tasks only (D-142), whatever its size: the
tasks by status and mode with their finished conversations (lengths and effective speech from
exports/minutes.py), the speakers of approved conversations grouped by their details, and the
people registered in the project with those who reached the conversations-per-speaker limit.

Definitions (also on the page):
- Completed: the approved conversations' effective speech, or their full length, as the project's
  `progress_counts` says. A conversation is its task's current recording (D-135). Effective speech
  not measured yet counts as nothing until the backfill measures it (`not_measured`).
- Recorded: finished conversations not approved yet (not rejected or cancelled).
- Speakers: distinct participants with at least one approved conversation. Age bands, gender and
  districts are shares of these speakers, each counted once, with their details as they are now;
  "Not given" holds people without that detail. Face-to-face and phone are shares of the approved
  conversations.
- Variance: the actual percent minus the target percent, in percentage points.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import case, func, null, select, union, union_all
from sqlalchemy.orm import Session

from app.modules.auth.deps import Principal
from app.modules.exports import minutes
from app.modules.participants.models import Participant, ParticipantProjectLink
from app.modules.projects import targets
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable
from app.modules.tasks.models import Task
from app.modules.tasks.pairing import NOT_COUNTED

NOT_STARTED = ("DRAFT", "ASSIGNED")
IN_PROGRESS = ("IN_PROGRESS", "RECORDED", "ON_HOLD", "CONSENT_FIX")
WAITING_QC = ("AUDIO_QC", "ADMIN_REVIEW")
MAX_DISTRICT_ROWS = 30  # districts shown when the project lists none
OTHER, NOT_GIVEN = "OTHER", "NOT_GIVEN"
GENDER_WORDS = {"MALE": "Male", "FEMALE": "Female"}
MODE_WORDS = {"FACE_TO_FACE": "Face-to-face", "TELEPHONY": "Phone call"}


class Row(BaseModel):
    key: str
    label: str
    count: int
    percent: float  # of the whole basis, "Not given" included
    target_percent: float | None
    variance: float | None  # percent - target_percent, percentage points


class Share(BaseModel):
    basis: str  # "speakers" or "conversations"
    total: int
    has_target: bool
    rows: list[Row]


class Completed(BaseModel):
    counts: str  # EFFECTIVE or FULL (the project's progress_counts)
    completed_ms: int
    target_hours: float | None
    percent_of_target: float | None
    approved_conversations: int
    approved_ms: int
    approved_effective_ms: int
    not_measured: int  # approved conversations whose effective speech is not measured yet
    recorded_conversations: int
    recorded_ms: int
    recorded_effective_ms: int
    # Effective speech as a share of the finished audio (approved and waiting), measured files only.
    effective_share_pct: float | None


class Conversations(BaseModel):
    approved: int
    target: int | None
    percent_of_target: float | None
    not_started: int
    in_progress: int
    waiting_qc: int
    rejected: int
    cancelled: int
    by_status: dict[str, int]


class Speakers(BaseModel):
    with_approved: int
    target: int | None
    percent_of_target: float | None
    registered: int
    limit: int | None
    at_limit: int | None


class Progress(BaseModel):
    project_id: uuid.UUID
    pause_limit_seconds: int
    completed: Completed
    conversations: Conversations
    speakers: Speakers
    age_bands: Share
    gender: Share
    modes: Share
    districts: Share


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _of_target(value: float, target: float | None) -> float | None:
    return None if not target else round(100 * value / target, 1)


def _row(key: str, label: str, count: int, total: int, target: float | None) -> Row:
    percent = _pct(count, total)
    return Row(
        key=key,
        label=label,
        count=count,
        percent=percent,
        target_percent=None if target is None else round(target, 1),
        variance=None if target is None else round(percent - target, 1),
    )


def _rest(rows: list[Row], counts: dict[str, int], total: int, other: str) -> list[Row]:
    """The rows, then the others (named `other`) and "Not given", when anyone is in them."""
    for key, label in ((OTHER, other), (NOT_GIVEN, "Not given")):
        if counts.get(key):
            rows.append(_row(key, label, counts[key], total, None))
    return rows


def _band_label(band: dict[str, int]) -> str:
    return f"{band['from']}-{band['to']}"


def _age_share(people: list[Any], bands: list[dict[str, int]], total: int) -> Share:
    counts: dict[str, int] = {}
    for p in people:
        index = targets.band_of(p.age, bands)
        key = NOT_GIVEN if p.age is None else (OTHER if index is None else str(index))
        counts[key] = counts.get(key, 0) + int(p.n)
    rows = [
        _row(_band_label(b), _band_label(b), counts.get(str(i), 0), total, float(b["percent"]))
        for i, b in enumerate(bands)
    ]
    if not bands:  # no age target: nothing to group by
        return Share(basis="speakers", total=total, has_target=False, rows=[])
    rows = _rest(rows, counts, total, "Other ages")
    return Share(basis="speakers", total=total, has_target=True, rows=rows)


def _gender_share(people: list[Any], wanted: dict[str, int], total: int) -> Share:
    counts: dict[str, int] = {}
    for p in people:
        key = p.gender if p.gender in GENDER_WORDS else NOT_GIVEN
        counts[key] = counts.get(key, 0) + int(p.n)
    rows = [
        _row(code, words, counts.get(code, 0), total, _target(wanted, code))
        for code, words in GENDER_WORDS.items()
    ]
    return Share(
        basis="speakers",
        total=total,
        has_target=bool(wanted),
        rows=_rest(rows, counts, total, "Other"),
    )


def _target(wanted: dict[str, int], key: str) -> float | None:
    return float(wanted[key]) if wanted and key in wanted else None


def _most_written(spellings: dict[str, int]) -> str:
    """The spelling most people have; on a tie, the first in order (capitals first)."""
    return min(spellings, key=lambda written: (-spellings[written], written))


def _district_share(people: list[Any], wanted: list[dict[str, str]], total: int) -> Share:
    counts: dict[str, int] = {}
    if wanted:
        for p in people:
            index = targets.district_of(p.native_state, p.district, wanted)
            key = NOT_GIVEN if not p.district else (OTHER if index is None else str(index))
            counts[key] = counts.get(key, 0) + int(p.n)
        each = 100 / len(wanted)
        rows = [
            _row(
                f"{d['state']}|{d['district']}",
                f"{d['district']} ({d['state']})",
                counts.get(str(i), 0),
                total,
                each,
            )
            for i, d in enumerate(wanted)
        ]
        rows = _rest(rows, counts, total, "Other districts")
        return Share(basis="speakers", total=total, has_target=True, rows=rows)
    # No districts listed: the speakers' own districts, the most common first; one district
    # whatever its spaces and capitals, named as most people wrote it.
    spellings: dict[str, dict[str, int]] = {}
    for p in people:
        if not p.district:
            counts[NOT_GIVEN] = counts.get(NOT_GIVEN, 0) + int(p.n)
            continue
        written = " ".join(p.district.split())
        seen = spellings.setdefault(written.lower(), {})
        seen[written] = seen.get(written, 0) + int(p.n)
    found = {key: (_most_written(seen), sum(seen.values())) for key, seen in spellings.items()}
    ordered = sorted(found.items(), key=lambda kv: (-kv[1][1], kv[0]))
    rows = [_row(k, label, n, total, None) for k, (label, n) in ordered[:MAX_DISTRICT_ROWS]]
    counts[OTHER] = sum(n for _, (_, n) in ordered[MAX_DISTRICT_ROWS:])
    rows = _rest(rows, counts, total, "Other districts")
    return Share(basis="speakers", total=total, has_target=False, rows=rows)


def progress(db: Session, principal: Principal, project_id: uuid.UUID) -> Progress:
    """The Progress tab: completed minutes, conversations and speakers against the project's
    targets, and the shares by age band, gender, recording type and district (module docstring)."""
    project: Project = get_manageable(db, principal, project_id)
    in_project = Task.project_id == project.id

    # 1. Tasks by status and mode, with their finished conversations (each task's current
    # recording; cancelled and rejected ones left out).
    finished = minutes.conversations(
        select(Task.id).where(in_project, Task.status.not_in(NOT_COUNTED))
    ).subquery()
    measured = finished.c.effective_ms.is_not(None)
    rows = db.execute(
        select(
            Task.status,
            Task.recording_mode.label("mode"),
            func.count().label("tasks"),
            func.count(finished.c.task_id).label("n"),
            func.coalesce(func.sum(finished.c.ms), 0).label("ms"),
            func.coalesce(func.sum(finished.c.effective_ms), 0).label("effective_ms"),
            func.count(finished.c.task_id).filter(~measured).label("not_measured"),
            func.coalesce(func.sum(case((measured, finished.c.ms), else_=0)), 0).label(
                "measured_ms"
            ),
        )
        .select_from(Task)
        .outerjoin(finished, finished.c.task_id == Task.id)
        .where(in_project)
        .group_by(Task.status, Task.recording_mode)
    ).all()
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row.status] = statuses.get(row.status, 0) + int(row.tasks)

    def total(field: str, *, is_approved: bool | None = None, mode: str | None = None) -> int:
        return sum(
            int(getattr(row, field))
            for row in rows
            if (is_approved is None or (row.status == "APPROVED") == is_approved)
            and (mode is None or row.mode == mode)
        )

    approved_ms = total("ms", is_approved=True)
    approved_effective = total("effective_ms", is_approved=True)
    completed_ms = approved_ms if project.progress_counts == "FULL" else approved_effective
    target_hours = targets.hours_target(project.target_hours)
    measured_ms = total("measured_ms")
    completed = Completed(
        counts=project.progress_counts,
        completed_ms=completed_ms,
        target_hours=target_hours,
        percent_of_target=_of_target(completed_ms / 3_600_000, target_hours),
        approved_conversations=total("n", is_approved=True),
        approved_ms=approved_ms,
        approved_effective_ms=approved_effective,
        not_measured=total("not_measured", is_approved=True),
        recorded_conversations=total("n", is_approved=False),
        recorded_ms=total("ms", is_approved=False),
        recorded_effective_ms=total("effective_ms", is_approved=False),
        effective_share_pct=_pct(total("effective_ms"), measured_ms) if measured_ms else None,
    )
    approved_count = statuses.get("APPROVED", 0)
    conversations = Conversations(
        approved=approved_count,
        target=project.target_conversations,
        percent_of_target=_of_target(approved_count, project.target_conversations),
        not_started=sum(statuses.get(s, 0) for s in NOT_STARTED),
        in_progress=sum(statuses.get(s, 0) for s in IN_PROGRESS),
        waiting_qc=sum(statuses.get(s, 0) for s in WAITING_QC),
        rejected=statuses.get("REJECTED", 0),
        cancelled=statuses.get("CANCELLED", 0),
        by_status=statuses,
    )

    # 2. The speakers of approved conversations, grouped by the details the shares need.
    sides = union(
        select(Task.participant_a_id.label("pid")).where(in_project, Task.status == "APPROVED"),
        select(Task.participant_b_id.label("pid")).where(in_project, Task.status == "APPROVED"),
    ).subquery()
    people = list(
        db.execute(
            select(
                Participant.age,
                Participant.gender,
                Participant.native_state,
                Participant.district,
                func.count().label("n"),
            )
            .where(Participant.id.in_(select(sides.c.pid)))
            .group_by(
                Participant.age,
                Participant.gender,
                Participant.native_state,
                Participant.district,
            )
        )
    )
    with_approved = sum(int(p.n) for p in people)

    # 3. The people registered in the project, and who reached the conversations-per-speaker
    # limit (D-143: cancelled and rejected tasks do not count), in one round trip.
    registered = (
        select(func.count())
        .select_from(ParticipantProjectLink)
        .join(Participant, Participant.id == ParticipantProjectLink.participant_id)
        .where(ParticipantProjectLink.project_id == project.id, Participant.deleted_at.is_(None))
        .scalar_subquery()
    )
    limit = project.max_conversations_per_speaker
    at_limit_q: Any = null()
    if limit is not None:
        counted = (in_project, Task.status.not_in(NOT_COUNTED))
        each = union_all(
            select(Task.participant_a_id.label("pid")).where(*counted),
            select(Task.participant_b_id.label("pid")).where(*counted),
        ).subquery()
        full = select(each.c.pid).group_by(each.c.pid).having(func.count() >= limit).subquery()
        at_limit_q = select(func.count()).select_from(full).scalar_subquery()
    registered_n, at_limit = db.execute(select(registered, at_limit_q)).one()

    modes = [
        _row(
            mode,
            words,
            total("n", is_approved=True, mode=mode),
            completed.approved_conversations,
            _target(project.target_modes, mode),
        )
        for mode, words in MODE_WORDS.items()
    ]
    return Progress(
        project_id=project.id,
        pause_limit_seconds=project.pause_limit_seconds,
        completed=completed,
        conversations=conversations,
        speakers=Speakers(
            with_approved=with_approved,
            target=project.target_speakers,
            percent_of_target=_of_target(with_approved, project.target_speakers),
            registered=int(registered_n or 0),
            limit=limit,
            at_limit=None if at_limit is None else int(at_limit),
        ),
        age_bands=_age_share(people, list(project.target_age_bands), with_approved),
        gender=_gender_share(people, dict(project.target_gender), with_approved),
        modes=Share(
            basis="conversations",
            total=completed.approved_conversations,
            has_target=bool(project.target_modes),
            rows=modes,
        ),
        districts=_district_share(people, list(project.target_districts), with_approved),
    )
