"""A project's progress against its targets (D-148): the Progress tab,
`GET /projects/{id}/progress`, with what is still needed to finish it (D-153).

For the people who manage the project (`projects.manage`, like the other tabs, D-104). Everything
comes from three set-based queries over this project's tasks and people only (D-142), whatever its
size: the tasks by status and mode with their finished conversations (lengths and effective speech
from exports/minutes.py), the people of the project (the speakers of approved conversations and
everyone registered) grouped by their details, and the people registered with those who reached
the conversations-per-speaker limit and the conversations they may still give.

Definitions (also on the page):
- Completed: the approved conversations' effective speech, or their full length, as the project's
  `progress_counts` says. A conversation is its task's current recording (D-135). Effective speech
  not measured yet counts as nothing until the backfill measures it (`not_measured`).
- Recorded: finished conversations not approved yet (not rejected or cancelled).
- Speakers: distinct participants with at least one approved conversation. Age bands, gender and
  districts are shares of these speakers, each counted once, with their details as they are now;
  "Not given" holds people without that detail. Face-to-face and phone are shares of the approved
  conversations, shown only for a project made before D-153 that records both.
- Variance: the actual percent minus the target percent, in percentage points.

Still needed (D-153), from the targets:
- A group's target: the speakers target shared out by the age band's percent times the gender's
  percent (or by the district's equal share), in whole people that add up to the target
  (targets.split, the largest remainder).
- Done: speakers with an approved conversation in the group (the basis above). Registered: people
  registered in the project (not removed) with details in the group and no approved conversation
  yet; they are on their way. Still needed: the target less done and registered, never below 0.
  A total adds up its groups' still needed: extra people in one group do not fill another, and
  people without the detail fill none.
- Conversations: the target less the approved ones and the open tasks (not started, in progress,
  waiting for QC or approval).
- Capacity: whether the registered people can give the conversations still to make under the
  pairing rules (D-143): each conversation takes two different people, each at most the
  conversations-per-speaker limit (less the conversations they have, rejected and cancelled ones
  aside), and with "each pair only once" a pair of people at most one. How many more people
  that needs, when they cannot.

The download (owner's request, `GET /projects/{id}/progress/export`): the same answer as tables,
`summary_tables`, one sheet each in the Excel workbook and one long table in the CSV
(`summary_csv_rows`), so a file always says what the tab says.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
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
OPEN = NOT_STARTED + IN_PROGRESS + WAITING_QC
MAX_DISTRICT_ROWS = 30  # districts shown when the project lists none
OTHER, NOT_GIVEN, ALL = "OTHER", "NOT_GIVEN", "ALL"
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


class Need(BaseModel):
    """Speakers wanted in one group, and how far the group is (D-153)."""

    target: int | None  # None: no target for this group
    done: int  # with an approved conversation
    registered: int  # registered in the project, no approved conversation yet
    still_needed: int | None  # target - done - registered, at least 0; None without a target


class AgeGenderNeed(BaseModel):
    """One row of the age band x gender matrix: an age band (or "Other ages", "Not given", or
    "All ages" when the project has no age bands), by gender and in all."""

    key: str
    label: str
    male: Need
    female: Need
    total: Need  # people without a gender too


class SpeakersNeeded(BaseModel):
    target: int | None
    by_age: bool  # the project has age bands
    by_gender: bool  # the project has a gender target
    rows: list[AgeGenderNeed]
    total: AgeGenderNeed


class DistrictNeed(Need):
    key: str
    label: str


class DistrictsNeeded(BaseModel):
    has_target: bool  # the project lists districts; otherwise no rows
    rows: list[DistrictNeed]
    total: DistrictNeed | None


class ConversationNeed(BaseModel):
    key: str  # ALL, then FACE_TO_FACE and TELEPHONY for a project that records both
    label: str
    target: int | None
    approved: int
    in_pipeline: int  # open tasks: not started, in progress, waiting for QC or approval
    still_to_make: int | None  # target - approved - in_pipeline, at least 0


class Capacity(BaseModel):
    """Whether the registered people can give the conversations still to make under the pairing
    rules (D-143): each conversation takes two different people, each person at most `limit`
    conversations, and with `unique_pairs` each pair of people at most one."""

    limit: int | None  # conversations per speaker; None = no limit
    unique_pairs: bool  # each pair of speakers only once
    registered: int
    # Conversations the registered people may still take part in, added up (each conversation
    # takes two of these places); None without a limit.
    places_left: int | None
    conversations_to_make: int | None
    # The fewest more people with whom the registered ones could give the conversations still to
    # make: as many as their places allow (two a conversation; k more people bring k x limit) and,
    # with unique pairs, as many as the pairs not used yet (k more people bring k x registered +
    # k(k-1)/2); 0 when the registered people can. None without a conversations target.
    more_speakers_needed: int | None


class StillNeeded(BaseModel):
    speakers: SpeakersNeeded
    districts: DistrictsNeeded
    conversations: list[ConversationNeed]
    capacity: Capacity


class Progress(BaseModel):
    project_id: uuid.UUID
    pause_limit_seconds: int
    # The project's one recording type (D-153); None for a project made before it that allows both.
    recording_mode: str | None
    completed: Completed
    conversations: Conversations
    speakers: Speakers
    age_bands: Share
    gender: Share
    modes: Share | None  # None for a project that records one type: the split means nothing
    districts: Share
    still_needed: StillNeeded


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


def _age_key(age: int | None, bands: list[dict[str, int]]) -> str:
    """A person's age band as a row key: the band's index, OTHER outside them, NOT_GIVEN."""
    if age is None:
        return NOT_GIVEN
    index = targets.band_of(age, bands)
    return OTHER if index is None else str(index)


def _gender_key(gender: str | None) -> str:
    return gender if gender in GENDER_WORDS else NOT_GIVEN


def _district_key(person: Any, wanted: list[dict[str, str]]) -> str:
    """A person's listed district as a row key: its index, OTHER for another one, NOT_GIVEN."""
    if not person.district:
        return NOT_GIVEN
    index = targets.district_of(person.native_state, person.district, wanted)
    return OTHER if index is None else str(index)


def _age_share(people: list[Any], bands: list[dict[str, int]], total: int) -> Share:
    counts: dict[str, int] = {}
    for p in people:
        key = _age_key(p.age, bands)
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
        key = _gender_key(p.gender)
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


def _district_label(d: dict[str, str]) -> str:
    return f"{d['district']} ({d['state']})"


def _district_share(people: list[Any], wanted: list[dict[str, str]], total: int) -> Share:
    counts: dict[str, int] = {}
    if wanted:
        for p in people:
            key = _district_key(p, wanted)
            counts[key] = counts.get(key, 0) + int(p.n)
        each = 100 / len(wanted)
        rows = [
            _row(
                f"{d['state']}|{d['district']}",
                _district_label(d),
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


# ---------------------------------------------------------------------- still needed (D-153)


def _need(target: int | None, done: int, registered: int) -> Need:
    still = None if target is None else max(0, target - done - registered)
    return Need(target=target, done=done, registered=registered, still_needed=still)


def _sum_targets(values: Iterable[int | None]) -> int | None:
    found = [v for v in values if v is not None]
    return sum(found) if found else None


def _added(needs: Sequence[Need]) -> Need:
    """Groups added up: their targets, done and registered, and their still needed (extra people in
    one group do not fill another)."""
    return Need(
        target=_sum_targets(n.target for n in needs),
        done=sum(n.done for n in needs),
        registered=sum(n.registered for n in needs),
        still_needed=_sum_targets(n.still_needed for n in needs),
    )


def _tally(rows: Iterable[Any], key: Any) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for r in rows:
        k = key(r)
        counts[k] = counts.get(k, 0) + int(r.n)
    return counts


def _speakers_needed(project: Project, done: list[Any], waiting: list[Any]) -> SpeakersNeeded:
    """The age band x gender matrix: each cell's target (the speakers target shared out by band
    percent times gender percent, adding up to the target), done, registered and still needed."""
    bands = list(project.target_age_bands)
    wanted = dict(project.target_gender)
    target = project.target_speakers
    genders = list(GENDER_WORDS)

    def cell(r: Any) -> tuple[str, str]:
        return (_age_key(r.age, bands) if bands else ALL, _gender_key(r.gender))

    done_n, waiting_n = _tally(done, cell), _tally(waiting, cell)

    def counted(row: str, genders_in: Sequence[str]) -> tuple[int, int]:
        return (
            sum(done_n.get((row, g), 0) for g in genders_in),
            sum(waiting_n.get((row, g), 0) for g in genders_in),
        )

    every = [*genders, NOT_GIVEN]
    keys = [str(i) for i in range(len(bands))] or [ALL]
    labels = [_band_label(b) for b in bands] or ["All ages"]
    band_weights = [int(b["percent"]) for b in bands] or [1]
    gender_weights = [int(wanted[g]) for g in genders] if wanted else [1]
    shares: list[int | None] = (
        list(targets.split(target, [a * g for a in band_weights for g in gender_weights]))
        if target is not None
        else [None] * (len(band_weights) * len(gender_weights))
    )
    rows: list[AgeGenderNeed] = []
    width = len(gender_weights)
    for i, (key, label) in enumerate(zip(keys, labels, strict=True)):
        own = shares[i * width : (i + 1) * width]
        by_gender = {
            g: _need(own[j] if wanted else None, *counted(key, [g])) for j, g in enumerate(genders)
        }
        row_target = _sum_targets(own)
        everyone = _need(row_target, *counted(key, every))
        if wanted and row_target is not None:
            # Still needed adds up the genders: people without a gender fill neither.
            everyone.still_needed = _sum_targets(n.still_needed for n in by_gender.values())
        rows.append(
            AgeGenderNeed(
                key=_band_label(bands[i]) if bands else ALL,
                label=label,
                male=by_gender["MALE"],
                female=by_gender["FEMALE"],
                total=everyone,
            )
        )
    for key, label in ((OTHER, "Other ages"), (NOT_GIVEN, "Not given")):
        if bands and (counted(key, every) != (0, 0)):
            rows.append(
                AgeGenderNeed(
                    key=key,
                    label=label,
                    male=_need(None, *counted(key, ["MALE"])),
                    female=_need(None, *counted(key, ["FEMALE"])),
                    total=_need(None, *counted(key, every)),
                )
            )
    total = AgeGenderNeed(
        key="TOTAL",
        label="Total",
        male=_added([r.male for r in rows]),
        female=_added([r.female for r in rows]),
        total=_added([r.total for r in rows]),
    )
    return SpeakersNeeded(
        target=target, by_age=bool(bands), by_gender=bool(wanted), rows=rows, total=total
    )


def _districts_needed(project: Project, done: list[Any], waiting: list[Any]) -> DistrictsNeeded:
    """Each listed district's equal share of the speakers target (adding up to it), done,
    registered and still needed; people from other districts or without one after them."""
    wanted = list(project.target_districts)
    if not wanted:
        return DistrictsNeeded(has_target=False, rows=[], total=None)
    target = project.target_speakers
    shares: list[int | None] = (
        list(targets.split(target, [1] * len(wanted)))
        if target is not None
        else [None] * len(wanted)
    )
    done_n = _tally(done, lambda r: _district_key(r, wanted))
    waiting_n = _tally(waiting, lambda r: _district_key(r, wanted))

    def row(key: str, label: str, index: str, share: int | None) -> DistrictNeed:
        need = _need(share, done_n.get(index, 0), waiting_n.get(index, 0))
        return DistrictNeed(key=key, label=label, **need.model_dump())

    rows = [
        row(f"{d['state']}|{d['district']}", _district_label(d), str(i), shares[i])
        for i, d in enumerate(wanted)
    ]
    for key, label in ((OTHER, "Other districts"), (NOT_GIVEN, "Not given")):
        if done_n.get(key) or waiting_n.get(key):
            rows.append(row(key, label, key, None))
    total = DistrictNeed(key="TOTAL", label="Total", **_added(rows).model_dump())
    return DistrictsNeeded(has_target=True, rows=rows, total=total)


def _conversation_need(
    key: str, label: str, target: int | None, approved: int, pipeline: int
) -> ConversationNeed:
    still = None if target is None else max(0, target - approved - pipeline)
    return ConversationNeed(
        key=key,
        label=label,
        target=target,
        approved=approved,
        in_pipeline=pipeline,
        still_to_make=still,
    )


def _capacity(
    limit: int | None,
    unique_pairs: bool,
    registered: int,
    used: int,
    pairs_used: int,
    to_make: int | None,
) -> Capacity:
    """What the registered people can still give, and how many more people the conversations
    still to make need (the Capacity model): `used` is the registered people's counted
    conversations (each up to the limit), `pairs_used` the pairs among them that already share a
    counted conversation."""
    places = None if limit is None else max(0, registered * limit - used)

    def can_give(more: int) -> float:
        """Conversations the registered people and `more` new ones could give at most."""
        people = registered + more
        if people < 2:
            return 0
        most = math.inf
        if limit is not None and places is not None:
            most = min(most, (places + more * limit) // 2)
        if unique_pairs:
            most = min(most, people * (people - 1) // 2 - pairs_used)
        return most

    needed = None
    if to_make is not None:
        # The fewest: can_give only grows with more people, and 2 x to_make + 2 always suffice.
        low, high = 0, 2 * to_make + 2
        while low < high:
            middle = (low + high) // 2
            if can_give(middle) >= to_make:
                high = middle
            else:
                low = middle + 1
        needed = low
    return Capacity(
        limit=limit,
        unique_pairs=unique_pairs,
        registered=registered,
        places_left=places,
        conversations_to_make=to_make,
        more_speakers_needed=needed,
    )


def progress(db: Session, principal: Principal, project_id: uuid.UUID) -> Progress:
    """The Progress tab: completed minutes, conversations and speakers against the project's
    targets, the shares by age band, gender, recording type and district, and what is still
    needed (module docstring)."""
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

    def open_tasks(mode: str | None = None) -> int:
        return sum(
            int(row.tasks)
            for row in rows
            if row.status in OPEN and (mode is None or row.mode == mode)
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

    # 2. The people of the project grouped by the details the shares and the matrix need: the
    # speakers of approved conversations (each once, whether or not still registered) and the
    # people registered in the project (not removed) without one yet.
    is_approved = (in_project, Task.status == "APPROVED")
    sides = union(
        select(Task.participant_a_id.label("pid")).where(*is_approved),
        select(Task.participant_b_id.label("pid")).where(*is_approved),
    ).subquery()
    everyone = union(
        select(sides.c.pid),
        select(ParticipantProjectLink.participant_id.label("pid")).where(
            ParticipantProjectLink.project_id == project.id
        ),
    ).subquery()
    approved_flag = sides.c.pid.is_not(None)
    grouped = list(
        db.execute(
            select(
                Participant.age,
                Participant.gender,
                Participant.native_state,
                Participant.district,
                approved_flag.label("approved"),
                func.count().label("n"),
            )
            .select_from(everyone)
            .join(Participant, Participant.id == everyone.c.pid)
            .outerjoin(sides, sides.c.pid == everyone.c.pid)
            .where(approved_flag | Participant.deleted_at.is_(None))
            .group_by(
                Participant.age,
                Participant.gender,
                Participant.native_state,
                Participant.district,
                approved_flag,
            )
        )
    )
    people = [p for p in grouped if p.approved]
    waiting = [p for p in grouped if not p.approved]
    with_approved = sum(int(p.n) for p in people)

    # 3. The people registered in the project, those of them who reached the conversations-per-
    # speaker limit (D-143: cancelled and rejected tasks do not count), the conversations they
    # have under the limit and, with unique pairs, the pairs among them already used, in one
    # round trip.
    registered_ids = (
        select(ParticipantProjectLink.participant_id)
        .join(Participant, Participant.id == ParticipantProjectLink.participant_id)
        .where(ParticipantProjectLink.project_id == project.id, Participant.deleted_at.is_(None))
    )
    registered = select(func.count()).select_from(registered_ids.subquery()).scalar_subquery()
    limit = project.max_conversations_per_speaker
    counted = (in_project, Task.status.not_in(NOT_COUNTED))
    at_limit_q: Any = null()
    used_q: Any = null()
    pairs_q: Any = null()
    if limit is not None:
        each = union_all(
            select(Task.participant_a_id.label("pid")).where(*counted),
            select(Task.participant_b_id.label("pid")).where(*counted),
        ).subquery()
        per = select(each.c.pid, func.count().label("used")).group_by(each.c.pid).subquery()
        mine = per.c.pid.in_(registered_ids)  # people erased since no longer count (PROJ-10)
        at_limit_q = (
            select(func.count()).select_from(per).where(per.c.used >= limit, mine)
        ).scalar_subquery()
        used_q = (
            select(func.coalesce(func.sum(func.least(per.c.used, limit)), 0))
            .where(mine)
            .scalar_subquery()
        )
    if project.unique_pairs:
        a, b = Task.participant_a_id, Task.participant_b_id
        pairs = (
            select(func.least(a, b).label("x"), func.greatest(a, b).label("y"))
            .where(*counted, a.in_(registered_ids), b.in_(registered_ids))
            .distinct()
            .subquery()
        )
        pairs_q = select(func.count()).select_from(pairs).scalar_subquery()
    registered_n, at_limit, used, pairs_used = db.execute(
        select(registered, at_limit_q, used_q, pairs_q)
    ).one()
    registered_n = int(registered_n or 0)

    one_mode = project.only_mode
    modes = None
    if one_mode is None:
        modes = Share(
            basis="conversations",
            total=completed.approved_conversations,
            has_target=bool(project.target_modes),
            rows=[
                _row(
                    mode,
                    words,
                    total("n", is_approved=True, mode=mode),
                    completed.approved_conversations,
                    _target(project.target_modes, mode),
                )
                for mode, words in MODE_WORDS.items()
            ],
        )

    # Still needed (D-153).
    talks_target = project.target_conversations
    talks = [
        _conversation_need(ALL, "All conversations", talks_target, approved_count, open_tasks())
    ]
    if one_mode is None:
        wanted_modes = dict(project.target_modes)
        per_mode: list[int | None] = (
            list(targets.split(talks_target, [int(wanted_modes[m]) for m in MODE_WORDS]))
            if talks_target is not None and wanted_modes
            else [None] * len(MODE_WORDS)
        )
        talks += [
            _conversation_need(
                mode,
                words,
                per_mode[i],
                total("tasks", is_approved=True, mode=mode),
                open_tasks(mode),
            )
            for i, (mode, words) in enumerate(MODE_WORDS.items())
        ]
    still_needed = StillNeeded(
        speakers=_speakers_needed(project, people, waiting),
        districts=_districts_needed(project, people, waiting),
        conversations=talks,
        capacity=_capacity(
            limit,
            project.unique_pairs,
            registered_n,
            int(used or 0),
            int(pairs_used or 0),
            talks[0].still_to_make,
        ),
    )

    return Progress(
        project_id=project.id,
        pause_limit_seconds=project.pause_limit_seconds,
        recording_mode=one_mode,
        completed=completed,
        conversations=conversations,
        speakers=Speakers(
            with_approved=with_approved,
            target=project.target_speakers,
            percent_of_target=_of_target(with_approved, project.target_speakers),
            registered=registered_n,
            limit=limit,
            at_limit=None if at_limit is None else int(at_limit),
        ),
        age_bands=_age_share(people, list(project.target_age_bands), with_approved),
        gender=_gender_share(people, dict(project.target_gender), with_approved),
        modes=modes,
        districts=_district_share(people, list(project.target_districts), with_approved),
        still_needed=still_needed,
    )


# ---------------------------------------------------------------------- the download

Cell = str | int | float | None
# The CSV: every table of the download in one long table, a row per row of a sheet.
SUMMARY_COLUMNS = (
    "section",
    "group",
    "label",
    "target",
    "done",
    "registered",
    "still_needed",
    "count",
    "percent",
    "target_percent",
    "variance",
)
COUNTS_WORDS = {"EFFECTIVE": "Effective speech", "FULL": "Full length"}
# The task statuses by stage, in the tab's order (frontend components/charts/stages.ts).
STAGES = (
    ("Approved", ("APPROVED",)),
    ("Waiting for QC or approval", WAITING_QC),
    ("In progress", IN_PROGRESS),
    ("Not started", NOT_STARTED),
    ("Rejected", ("REJECTED",)),
    ("Cancelled", ("CANCELLED",)),
)
STATUS_WORDS = {
    "APPROVED": "Approved",
    "AUDIO_QC": "Audio QC",
    "ADMIN_REVIEW": "Admin review",
    "IN_PROGRESS": "In progress",
    "RECORDED": "Recorded",
    "ON_HOLD": "On hold",
    "CONSENT_FIX": "Consent form to fix",
    "DRAFT": "Draft",
    "ASSIGNED": "Assigned",
    "REJECTED": "Rejected",
    "CANCELLED": "Cancelled",
}


@dataclass(frozen=True)
class SummaryTable:
    """One table of the download: a sheet of the workbook, named by its title, and a section of
    the CSV. `columns`: each column's key among SUMMARY_COLUMNS and its heading on the sheet, in
    the sheet's order; `rows` by those keys (a key left out is an empty cell)."""

    title: str
    columns: tuple[tuple[str, str], ...]
    rows: list[dict[str, Cell]]

    @property
    def header(self) -> list[str]:
        return [heading for _, heading in self.columns]

    def cells(self) -> list[list[Cell]]:
        return [[row.get(key) for key, _ in self.columns] for row in self.rows]


def stamp(now: datetime) -> str:
    """When a download was made, in the report's time zone: "2026-11-22 15:04 (UTC+05:30,
    Asia/Kolkata)"."""
    offset = now.strftime("%z")
    zone = getattr(now.tzinfo, "key", None) or now.strftime("%Z")
    return f"{now:%Y-%m-%d %H:%M} (UTC{offset[:3]}:{offset[3:]}, {zone})"


def _hours(ms: int) -> float:
    return round(ms / 3_600_000, 2)


def _many(n: int, one: str) -> str:
    return f"{n} {one}{'' if n == 1 else 's'}"


def _need_cells(need: Need) -> dict[str, Cell]:
    return {
        "target": need.target,
        "done": need.done,
        "registered": need.registered,
        "still_needed": need.still_needed,
    }


_NEED_COLUMNS = (
    ("target", "Target"),
    ("done", "Done"),
    ("registered", "Registered"),
    ("still_needed", "Still needed"),
)


def _about(p: Progress, project: Project, generated: str) -> SummaryTable:
    capacity = p.still_needed.capacity
    items: list[tuple[str, Cell]] = [
        ("Project code", project.code),
        ("Project name", project.name),
        ("Recording type", MODE_WORDS.get(p.recording_mode or "", "Face-to-face and phone call")),
        ("Generated", generated),
        ("Completed counts", COUNTS_WORDS.get(p.completed.counts, p.completed.counts)),
        ("Conversations per speaker", "No limit" if capacity.limit is None else capacity.limit),
        ("Each pair of speakers only once", "Yes" if capacity.unique_pairs else "No"),
    ]
    return SummaryTable(
        "About",
        (("group", "Item"), ("label", "Value")),
        [{"group": item, "label": value} for item, value in items],
    )


def _key_figures(p: Progress) -> SummaryTable:
    done, talks, people = p.completed, p.conversations, p.speakers
    counted = COUNTS_WORDS.get(done.counts, done.counts).lower()
    rows: list[dict[str, Cell]] = [
        {
            "label": f"Completed hours ({counted})",
            "count": _hours(done.completed_ms),
            "target": done.target_hours,
            "percent": done.percent_of_target,
        },
        {
            "label": "Approved conversations",
            "count": talks.approved,
            "target": talks.target,
            "percent": talks.percent_of_target,
        },
        {
            "label": "Speakers with an approved conversation",
            "count": people.with_approved,
            "target": people.target,
            "percent": people.percent_of_target,
        },
        {"label": "Registered speakers", "count": people.registered},
    ]
    if people.limit is not None:
        limit = _many(people.limit, "conversation")
        rows.append(
            {"label": f"Registered speakers at the limit of {limit}", "count": people.at_limit}
        )
    rows += [
        {"label": "Approved conversations not measured yet", "count": done.not_measured},
        {"label": "Effective speech (% of the recorded audio)", "count": done.effective_share_pct},
    ]
    return SummaryTable(
        "Key figures",
        (("label", "Figure"), ("count", "Value"), ("target", "Target"), ("percent", "% of target")),
        rows,
    )


def _speakers_by_age(p: Progress) -> SummaryTable:
    speakers = p.still_needed.speakers
    groups = [*speakers.rows, *([speakers.total] if len(speakers.rows) > 1 else [])]
    return SummaryTable(
        "Speakers by age and gender",
        (("group", "Age band"), ("label", "Gender"), *_NEED_COLUMNS),
        [
            {"group": row.label, "label": gender, **_need_cells(need)}
            for row in groups
            for gender, need in (("Male", row.male), ("Female", row.female), ("Total", row.total))
        ],
    )


def _speakers_by_district(p: Progress) -> SummaryTable:
    districts = p.still_needed.districts
    rows = [*districts.rows, *([districts.total] if districts.total else [])]
    return SummaryTable(
        "Speakers by district",
        (("label", "Native district"), *_NEED_COLUMNS),
        [{"label": row.label, **_need_cells(row)} for row in rows],
    )


def _conversations_to_make(p: Progress) -> SummaryTable:
    return SummaryTable(
        "Conversations to make",
        (
            ("label", "Conversations"),
            ("target", "Target"),
            ("done", "Approved"),
            ("count", "Open tasks"),
            ("still_needed", "Still to make"),
        ),
        [
            {
                "label": c.label,
                "target": c.target,
                "done": c.approved,
                "count": c.in_pipeline,
                "still_needed": c.still_to_make,
            }
            for c in p.still_needed.conversations
        ],
    )


def _capacity_table(p: Progress) -> SummaryTable:
    capacity = p.still_needed.capacity
    items: list[tuple[str, Cell]] = [
        ("Registered speakers", capacity.registered),
        ("Places left (two per conversation; none without a limit)", capacity.places_left),
        ("Conversations still to make", capacity.conversations_to_make),
        ("More speakers needed", capacity.more_speakers_needed),
    ]
    return SummaryTable(
        "Capacity",
        (("label", "Item"), ("count", "Value")),
        [{"label": item, "count": value} for item, value in items],
    )


def _balance(p: Progress) -> SummaryTable:
    groups = [
        ("Age bands", p.age_bands),
        ("Gender", p.gender),
        *([("Face-to-face and phone", p.modes)] if p.modes else []),
        ("Districts", p.districts),
    ]
    return SummaryTable(
        "Balance",
        (
            ("group", "Group"),
            ("label", "Row"),
            ("count", "Count"),
            ("percent", "Share (%)"),
            ("target_percent", "Target share (%)"),
            ("variance", "Variance (points)"),
        ),
        [
            {
                "group": name,
                "label": row.label,
                "count": row.count,
                "percent": row.percent,
                "target_percent": row.target_percent,
                "variance": row.variance,
            }
            # Shares of nobody yet are left out, as on the tab: their variance would mean nothing.
            for name, share in groups
            if share.total
            for row in share.rows
        ],
    )


def _by_status(p: Progress) -> SummaryTable:
    by = p.conversations.by_status
    total = sum(by.values())
    known = {status for _, statuses in STAGES for status in statuses}
    listed = [(stage, status) for stage, statuses in STAGES for status in statuses]
    listed += [("Other", status) for status in sorted(set(by) - known)]
    rows: list[dict[str, Cell]] = [
        {
            "group": stage,
            "label": STATUS_WORDS.get(status, status),
            "count": by.get(status, 0),
            "percent": _pct(by.get(status, 0), total),
        }
        for stage, status in listed
    ]
    rows.append(
        {"group": "Total", "label": "All tasks", "count": total, "percent": _pct(total, total)}
    )
    return SummaryTable(
        "Conversations by status",
        (("group", "Stage"), ("label", "Status"), ("count", "Tasks"), ("percent", "Share (%)")),
        rows,
    )


def _completed(p: Progress) -> SummaryTable:
    done = p.completed
    kinds = (
        ("Approved", done.approved_conversations, done.approved_ms, done.approved_effective_ms),
        (
            "Recorded, not yet approved",
            done.recorded_conversations,
            done.recorded_ms,
            done.recorded_effective_ms,
        ),
    )
    rows: list[dict[str, Cell]] = []
    for kind, n, full, speech in kinds:
        rows += [
            {"group": kind, "label": "Number", "count": n},
            {"group": kind, "label": "Full length (h)", "count": _hours(full)},
            {"group": kind, "label": "Effective speech (h)", "count": _hours(speech)},
        ]
    return SummaryTable(
        "Completed", (("group", "Conversations"), ("label", "Measure"), ("count", "Value")), rows
    )


def summary_tables(p: Progress, project: Project, generated: str) -> list[SummaryTable]:
    """The Progress tab as tables, in its order: about the file, the key figures, what is still
    needed (speakers by age band and gender and by district, conversations, capacity), the
    balance against the targets (every row, all the districts too), the conversations by status
    and the completed time. `generated`: when, as `stamp` writes it."""
    return [
        _about(p, project, generated),
        _key_figures(p),
        _speakers_by_age(p),
        _speakers_by_district(p),
        _conversations_to_make(p),
        _capacity_table(p),
        _balance(p),
        _by_status(p),
        _completed(p),
    ]


def summary_csv_rows(tables: Sequence[SummaryTable]) -> list[list[Cell]]:
    """The tables as one long table under SUMMARY_COLUMNS, each row named by its table's title."""
    return [
        [table.title, *(row.get(key) for key in SUMMARY_COLUMNS[1:])]
        for table in tables
        for row in table.rows
    ]
