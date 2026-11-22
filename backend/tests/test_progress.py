"""The project's audio and progress settings, its targets, the Progress tab and completed hours on
the dashboard (D-148), and the Progress tab's download as Excel or CSV (owner's request).

Every number of the Progress tab is worked out here by hand from a small set of tasks with known
lengths, effective speech and speakers; the download is checked against the tab's own answer.

Requirements: DASH-001, DASH-003, PROJ-001, PROJ-011, EXP-002, EXP-007, SEC-001
"""

from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.modules.audit.models import AuditLog
from app.modules.participants.models import Participant
from app.modules.projects import progress, targets
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task
from tests.conftest import Api, make_participant, make_project, make_user

pytestmark = pytest.mark.db

FRONTEND_TARGETS = Path(__file__).resolve().parents[2] / "frontend/src/features/projects/targets.ts"
MINUTE = 60_000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _person(api: Api, pid: Any, label: str, **details: Any) -> uuid.UUID:
    from tests.conftest import SPEAKER_DETAILS

    made = make_participant(api, pid, label, speaker={**SPEAKER_DETAILS, **details})
    return uuid.UUID(made["id"])


def _task(
    db: Any,
    project: Any,
    code: int,
    a: uuid.UUID,
    b: uuid.UUID,
    mode: str,
    status: str,
    by: uuid.UUID,
    ms: int | None = None,
    effective_ms: int | None = None,
) -> uuid.UUID:
    """A task in a status; with `ms` a finished recording whose delivery file is that long."""
    task = Task(
        task_code=f"T{code:06d}",
        project_id=project.id,
        recording_mode=mode,
        status=status,
        participant_a_id=a,
        participant_b_id=b,
    )
    db.add(task)
    db.flush()
    if ms is not None:
        rec = Recording(
            task_id=task.id,
            mode=mode,
            state="READY",
            created_by=by,
            native_sample_rate=16000,
            channel_count=1,
            channel_handling="mono",
            started_at=datetime.now(UTC),
        )
        db.add(rec)
        db.flush()
        db.add(
            AudioAsset(
                recording_id=rec.id,
                project_id=project.id,
                kind="FTF_DERIVED_PCM" if mode == "FACE_TO_FACE" else "TELEPHONY_DERIVED_PCM",
                version=1,
                storage_key=f"{project.code}/{task.id}.wav",
                file_extension="wav",
                container="wav",
                codec="pcm_s16le",
                sample_format="int",
                sample_rate=16000,
                bit_depth=16,
                channels=1,
                duration_ms=ms,
                size_bytes=ms * 32,
                sha256=f"{code:064d}",
                clip_count=0,
                clip_pct=0.0,
                silence_pct=0.0,
                effective_ms=effective_ms,
                longest_pause_ms=None if effective_ms is None else 0,
                pauses_ms=None if effective_ms is None else [],
            )
        )
    db.commit()
    return task.id


@pytest.fixture
def world(db: Any, new_api: Any) -> dict[str, Any]:
    """Six speakers and seven tasks:

    T1 A+B face-to-face APPROVED 10 min (7 min effective); T2 C+D phone APPROVED 5 min (4);
    T3 A+E face-to-face APPROVED 2 min (not measured yet); T4 B+F face-to-face AUDIO_QC 1 min
    (0.5); T5 C+F phone IN_PROGRESS; T6 D+E face-to-face REJECTED 1 min (1); T7 A+F CANCELLED.
    A 25 F North Goa, B 35 M South Goa, C 45 M Udupi (Karnataka), D 22 F Pune (Maharashtra),
    E 55 "north goa" (Goa) with no gender, F 30 M North Goa (no approved conversation).
    """
    project = make_project(db, "PROG", max_conversations_per_speaker=2)
    other = make_project(db, "OTHER")
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project, other])
    make_user(db, "pa2@example.org", ["PROJECT_ADMIN"], projects=[other])
    mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[project])
    make_user(db, "client@example.org", ["CLIENT_VIEWER"], projects=[project])
    apis: dict[str, Api] = {}
    for name in ("root", "pa", "pa2", "mod", "qc", "client"):
        apis[name] = new_api()
        assert apis[name].login(f"{name}@example.org").status_code == 200
    pa = apis["pa"]
    pid = project.id
    a = _person(pa, pid, "Asha", age=25, gender="FEMALE", native_state="Goa", district="North Goa")
    b = _person(pa, pid, "Bina", age=35, gender="MALE", native_state="Goa", district="South Goa")
    c = _person(pa, pid, "Chet", age=45, gender="MALE", native_state="Karnataka", district="Udupi")
    d = _person(
        pa, pid, "Devi", age=22, gender="FEMALE", native_state="Maharashtra", district="Pune"
    )
    e = _person(pa, pid, "Esha", age=55, gender="FEMALE", native_state="Goa", district="north goa ")
    f = _person(pa, pid, "Farh", age=30, gender="MALE", native_state="Goa", district="North Goa")
    by = mod.id
    _task(db, project, 1, a, b, "FACE_TO_FACE", "APPROVED", by, 10 * MINUTE, 7 * MINUTE)
    _task(db, project, 2, c, d, "TELEPHONY", "APPROVED", by, 5 * MINUTE, 4 * MINUTE)
    _task(db, project, 3, a, e, "FACE_TO_FACE", "APPROVED", by, 2 * MINUTE, None)
    _task(db, project, 4, b, f, "FACE_TO_FACE", "AUDIO_QC", by, MINUTE, MINUTE // 2)
    _task(db, project, 5, c, f, "TELEPHONY", "IN_PROGRESS", by)
    _task(db, project, 6, d, e, "FACE_TO_FACE", "REJECTED", by, MINUTE, MINUTE)
    _task(db, project, 7, a, f, "FACE_TO_FACE", "CANCELLED", by)
    # E's gender is missing (saved before D-143, say).
    db.execute(update(Participant).where(Participant.id == e).values(gender=None))
    db.commit()
    people = {"A": a, "B": b, "C": c, "D": d, "E": e, "F": f}
    return {"db": db, "project": project, "other": other, "mod_user": mod, "people": people, **apis}


def _progress(api: Api, project: Any) -> Any:
    return api.get(f"/api/v1/projects/{project.id}/progress")


def _rows(share: dict[str, Any]) -> dict[str, tuple[int, float, float | None, float | None]]:
    return {
        r["label"]: (r["count"], r["percent"], r["target_percent"], r["variance"])
        for r in share["rows"]
    }


def _set(world: dict[str, Any], project: Any, **values: Any) -> None:
    db = world["db"]
    db.execute(update(Project).where(Project.id == project.id).values(**values))
    db.commit()


# ------------------------------------------------------------------------ the Progress tab


def test_the_progress_tab_adds_up(world: dict[str, Any]) -> None:
    _set(
        world,
        world["project"],
        target_hours=1,
        target_districts=list(targets.CLIENT_DISTRICTS),
    )
    answer = _progress(world["pa"], world["project"])
    assert answer.status_code == 200, answer.text
    body = answer.json()

    done = body["completed"]
    assert done == {
        "counts": "EFFECTIVE",
        "completed_ms": 11 * MINUTE,  # 7 + 4; T3 not measured yet counts as none
        "target_hours": 1.0,
        "percent_of_target": 18.3,  # 11 of 60 minutes
        "approved_conversations": 3,
        "approved_ms": 17 * MINUTE,
        "approved_effective_ms": 11 * MINUTE,
        "not_measured": 1,
        "recorded_conversations": 1,  # T4; the rejected T6 does not count
        "recorded_ms": MINUTE,
        "recorded_effective_ms": MINUTE // 2,
        # Measured files only: (7 + 4 + 0.5) of (10 + 5 + 1) minutes.
        "effective_share_pct": 71.9,
    }
    talks = body["conversations"]
    assert (talks["approved"], talks["target"], talks["percent_of_target"]) == (3, 600, 0.5)
    assert (talks["in_progress"], talks["waiting_qc"], talks["not_started"]) == (1, 1, 0)
    assert (talks["rejected"], talks["cancelled"]) == (1, 1)

    people = body["speakers"]
    assert people == {
        "with_approved": 5,  # A, B, C, D, E
        "target": 500,
        "percent_of_target": 1.0,
        "registered": 6,
        "limit": 2,
        "at_limit": 4,  # A (T1, T3), B (T1, T4), C (T2, T5), F (T4, T5); rejected and cancelled
    }

    # Shares of the 5 speakers: label -> (count, percent, target percent, variance).
    assert _rows(body["age_bands"]) == {
        "20-30": (2, 40.0, 40.0, 0.0),  # A 25, D 22
        "30-40": (1, 20.0, 30.0, -10.0),  # B 35
        "40-50": (1, 20.0, 20.0, 0.0),  # C 45
        "50-60": (1, 20.0, 10.0, 10.0),  # E 55
    }
    assert _rows(body["gender"]) == {
        "Male": (2, 40.0, 50.0, -10.0),
        "Female": (2, 40.0, 50.0, -10.0),
        "Not given": (1, 20.0, None, None),
    }
    assert body["gender"]["basis"] == "speakers"
    districts = _rows(body["districts"])
    assert districts["North Goa (Goa)"] == (2, 40.0, 12.5, 27.5), "A, and E's 'north goa '"
    assert districts["South Goa (Goa)"] == (1, 20.0, 12.5, 7.5)
    assert districts["Udupi (Karnataka)"] == (1, 20.0, 12.5, 7.5)
    assert districts["Raigad (Maharashtra)"] == (0, 0.0, 12.5, -12.5)
    assert districts["Other districts"] == (1, 20.0, None, None), "D from Pune"
    assert len(districts) == 9
    # Shares of the 3 approved conversations.
    assert body["modes"]["basis"] == "conversations"
    assert _rows(body["modes"]) == {
        "Face-to-face": (2, 66.7, 50.0, 16.7),
        "Phone call": (1, 33.3, 50.0, -16.7),
    }


def test_full_length_counts_when_the_project_says_so(world: dict[str, Any]) -> None:
    _set(world, world["project"], progress_counts="FULL", target_hours=None)
    done = _progress(world["pa"], world["project"]).json()["completed"]
    assert (done["counts"], done["completed_ms"]) == ("FULL", 17 * MINUTE)
    assert (done["target_hours"], done["percent_of_target"]) == (None, None)
    # An hours target of 0, saved before PROJ-12 refused it, is no target either.
    _set(world, world["project"], target_hours=0)
    done = _progress(world["pa"], world["project"]).json()["completed"]
    assert (done["target_hours"], done["percent_of_target"]) == (None, None)


def test_without_targets_the_tab_still_shows_what_there_is(world: dict[str, Any]) -> None:
    _set(
        world,
        world["project"],
        target_speakers=None,
        target_conversations=None,
        target_age_bands=[],
        target_gender={},
        target_modes={},
        target_districts=[],
        max_conversations_per_speaker=None,
    )
    body = _progress(world["pa"], world["project"]).json()
    assert (body["speakers"]["target"], body["speakers"]["percent_of_target"]) == (None, None)
    assert (body["speakers"]["limit"], body["speakers"]["at_limit"]) == (None, None)
    assert body["conversations"]["target"] is None
    assert body["age_bands"] == {"basis": "speakers", "total": 5, "has_target": False, "rows": []}
    assert _rows(body["gender"])["Male"] == (2, 40.0, None, None)
    assert body["modes"]["has_target"] is False
    # The speakers' own districts, the most common first, spaces and capitals aside.
    assert _rows(body["districts"]) == {
        "North Goa": (2, 40.0, None, None),
        "Pune": (1, 20.0, None, None),
        "South Goa": (1, 20.0, None, None),
        "Udupi": (1, 20.0, None, None),
    }


def test_an_empty_project_shows_zeros(world: dict[str, Any]) -> None:
    body = _progress(world["pa"], world["other"]).json()
    assert body["completed"]["completed_ms"] == 0
    assert body["completed"]["effective_share_pct"] is None
    assert body["conversations"]["approved"] == 0
    assert body["speakers"]["with_approved"] == 0
    assert [r["count"] for r in body["age_bands"]["rows"]] == [0, 0, 0, 0]
    assert [r["percent"] for r in body["gender"]["rows"]] == [0.0, 0.0]


def test_only_the_people_who_manage_the_project_see_it(world: dict[str, Any]) -> None:
    for who in ("mod", "qc", "client"):
        assert _progress(world[who], world["project"]).status_code == 403, who
    assert _progress(world["pa2"], world["project"]).status_code == 404, "not their project"
    assert _progress(world["root"], world["project"]).status_code == 200


# ------------------------------------------------------------------------ still needed (D-153)


def _need(cell: dict[str, Any]) -> tuple[int | None, int, int, int | None]:
    return (cell["target"], cell["done"], cell["registered"], cell["still_needed"])


def _matrix(speakers: dict[str, Any]) -> dict[str, tuple[Any, Any, Any]]:
    """label -> (male, female, total), each (target, done, registered, still needed)."""
    return {
        r["label"]: (_need(r["male"]), _need(r["female"]), _need(r["total"]))
        for r in [*speakers["rows"], speakers["total"]]
    }


def test_still_needed_shares_the_targets_out_and_counts_who_is_on_the_way(
    world: dict[str, Any],
) -> None:
    """500 speakers by age band (40/30/20/10) and gender (50/50); F (30, male) is registered
    with no approved conversation yet; E (55) has no gender and so fills neither cell."""
    _set(world, world["project"], target_districts=list(targets.CLIENT_DISTRICTS))
    body = _progress(world["pa"], world["project"]).json()
    assert body["recording_mode"] is None, "made before D-153: both types"
    needed = body["still_needed"]
    speakers = needed["speakers"]
    assert (speakers["target"], speakers["by_age"], speakers["by_gender"]) == (500, True, True)
    assert _matrix(speakers) == {
        "20-30": ((100, 0, 0, 100), (100, 2, 0, 98), (200, 2, 0, 198)),  # A 25 F, D 22 F
        "30-40": ((75, 1, 1, 73), (75, 0, 0, 75), (150, 1, 1, 148)),  # B 35 M; F 30 M waiting
        "40-50": ((50, 1, 0, 49), (50, 0, 0, 50), (100, 1, 0, 99)),  # C 45 M
        "50-60": ((25, 0, 0, 25), (25, 0, 0, 25), (50, 1, 0, 50)),  # E 55, no gender
        "Total": ((250, 2, 1, 247), (250, 2, 0, 248), (500, 5, 1, 495)),
    }
    # Each listed district an equal share of 500: 62.5 each, the first four get the 4 left over.
    districts = {
        r["label"]: _need(r) for r in [*needed["districts"]["rows"], needed["districts"]["total"]]
    }
    assert needed["districts"]["has_target"] is True
    assert districts == {
        "North Goa (Goa)": (63, 2, 1, 60),  # A, E's "north goa "; F waiting
        "South Goa (Goa)": (63, 1, 0, 62),
        "Uttara Kannada (Karnataka)": (63, 0, 0, 63),
        "Udupi (Karnataka)": (63, 1, 0, 62),
        "Dakshina Kannada (Karnataka)": (62, 0, 0, 62),
        "Sindhudurg (Maharashtra)": (62, 0, 0, 62),
        "Ratnagiri (Maharashtra)": (62, 0, 0, 62),
        "Raigad (Maharashtra)": (62, 0, 0, 62),
        "Other districts": (None, 1, 0, None),  # D from Pune
        "Total": (500, 5, 1, 495),
    }
    # 600 conversations: 3 approved, T4 and T5 open; a project that records both also by type.
    assert [
        (c["key"], c["target"], c["approved"], c["in_pipeline"], c["still_to_make"])
        for c in needed["conversations"]
    ] == [
        ("ALL", 600, 3, 2, 595),
        ("FACE_TO_FACE", 300, 2, 1, 297),
        ("TELEPHONY", 300, 1, 1, 298),
    ]
    # At most 2 conversations each: A, B, C and F have 2, D and E 1 (rejected and cancelled
    # aside), so the 6 registered people have 2 places left; 595 conversations need 1190.
    assert needed["capacity"] == {
        "limit": 2,
        "unique_pairs": False,
        "registered": 6,
        "places_left": 2,
        "conversations_to_make": 595,
        "more_speakers_needed": 594,
    }


def test_the_targets_are_shared_out_in_whole_people_that_add_up() -> None:
    """The largest remainder: whole parts first, the ones left to the largest fractions, the
    first in order on a tie."""
    cells = [a * g for a in (40, 30, 20, 10) for g in (50, 50)]
    assert targets.split(7, cells) == [2, 1, 1, 1, 1, 1, 0, 0]
    assert sum(targets.split(7, cells)) == 7
    assert targets.split(500, [1] * 8) == [63, 63, 63, 63, 62, 62, 62, 62]
    assert targets.split(601, [50, 50]) == [301, 300]
    assert targets.split(0, [1, 1]) == [0, 0]
    assert targets.split(5, []) == []
    for total in range(0, 120):
        assert sum(targets.split(total, cells)) == total


def test_still_needed_without_targets_shows_who_there_is(world: dict[str, Any]) -> None:
    _set(
        world,
        world["project"],
        target_speakers=None,
        target_conversations=None,
        target_age_bands=[],
        target_gender={},
        target_districts=[],
        max_conversations_per_speaker=None,
    )
    needed = _progress(world["pa"], world["project"]).json()["still_needed"]
    assert (needed["speakers"]["by_age"], needed["speakers"]["by_gender"]) == (False, False)
    assert _matrix(needed["speakers"]) == {
        "All ages": ((None, 2, 1, None), (None, 2, 0, None), (None, 5, 1, None)),
        "Total": ((None, 2, 1, None), (None, 2, 0, None), (None, 5, 1, None)),
    }
    assert needed["districts"] == {"has_target": False, "rows": [], "total": None}
    assert needed["conversations"][0] == {
        "key": "ALL",
        "label": "All conversations",
        "target": None,
        "approved": 3,
        "in_pipeline": 2,
        "still_to_make": None,
    }
    assert needed["capacity"] == {
        "limit": None,
        "unique_pairs": False,
        "registered": 6,
        "places_left": None,
        "conversations_to_make": None,
        "more_speakers_needed": None,
    }


def test_a_project_of_one_type_has_no_split_by_type(world: dict[str, Any]) -> None:
    """D-153: the face-to-face and phone split means nothing in a project that records one."""
    _set(world, world["project"], allows_telephony=False, target_telephony_hours_per_day=0)
    body = _progress(world["pa"], world["project"]).json()
    assert body["recording_mode"] == "FACE_TO_FACE"
    assert body["modes"] is None
    assert [c["key"] for c in body["still_needed"]["conversations"]] == ["ALL"]


def test_an_empty_project_still_needs_everything(world: dict[str, Any]) -> None:
    needed = _progress(world["pa"], world["other"]).json()["still_needed"]
    assert [r["label"] for r in needed["speakers"]["rows"]] == ["20-30", "30-40", "40-50", "50-60"]
    assert _need(needed["speakers"]["total"]["total"]) == (500, 0, 0, 500)
    assert needed["capacity"]["registered"] == 0


def test_capacity_needs_two_people_a_conversation_and_each_pair_once(
    world: dict[str, Any],
) -> None:
    """PROJ-09: what the registered people can give is bounded by their places (each at most the
    limit, two a conversation) and, with each pair only once, by the pairs they have left; more
    speakers needed is the fewest more people that are enough, with or without a limit."""
    db, pa, other = world["db"], world["pa"], world["other"]
    # 600 conversations to make (the project's target, nothing made yet), no limit per speaker.
    _set(world, other, max_conversations_per_speaker=None, unique_pairs=True)
    gita = _person(pa, other.id, "Gita")

    def capacity() -> dict[str, Any]:
        found: dict[str, Any] = _progress(pa, other).json()["still_needed"]["capacity"]
        return found

    # One person: each pair talks once, and 36 people make 630 pairs (35 only 595).
    assert capacity() == {
        "limit": None,
        "unique_pairs": True,
        "registered": 1,
        "places_left": None,
        "conversations_to_make": 600,
        "more_speakers_needed": 35,
    }
    _set(world, other, unique_pairs=False)
    assert capacity()["more_speakers_needed"] == 1, "without the pairs rule, a second person"

    # Three people, at most 3 conversations each, each pair once, 4 to make: their 9 places
    # would give 4, but three people make only 3 pairs; a fourth makes 6.
    hari = _person(pa, other.id, "Hari")
    isha = _person(pa, other.id, "Isha")
    _set(world, other, max_conversations_per_speaker=3, unique_pairs=True, target_conversations=4)
    assert capacity() == {
        "limit": 3,
        "unique_pairs": True,
        "registered": 3,
        "places_left": 9,
        "conversations_to_make": 4,
        "more_speakers_needed": 1,
    }

    # Gita and Hari talked (approved): their pair is used, and a place each. 3 still to make,
    # 7 places would give 3, but only 2 pairs are left. A rejected conversation uses nothing.
    by = world["mod_user"].id
    _task(db, other, 21, gita, hari, "FACE_TO_FACE", "APPROVED", by)
    _task(db, other, 22, hari, isha, "FACE_TO_FACE", "REJECTED", by)
    found = capacity()
    assert (found["places_left"], found["conversations_to_make"]) == (7, 3)
    assert found["more_speakers_needed"] == 1
    # Without the pairs rule the places are enough.
    _set(world, other, unique_pairs=False)
    assert capacity()["more_speakers_needed"] == 0


def test_at_the_limit_counts_only_the_people_still_registered(world: dict[str, Any]) -> None:
    """PROJ-10: a person erased since (data erasure) is no longer registered, nor at the limit;
    their approved conversations still count as done."""
    db = world["db"]
    db.execute(
        update(Participant)
        .where(Participant.id == world["people"]["A"])
        .values(deleted_at=datetime.now(UTC))
    )
    db.commit()
    body = _progress(world["pa"], world["project"]).json()
    people = body["speakers"]
    # Limit 2: B (T1, T4), C (T2, T5) and F (T4, T5); A (T1, T3) is erased.
    assert (people["registered"], people["at_limit"], people["with_approved"]) == (5, 3, 5)
    assert body["still_needed"]["capacity"]["places_left"] == 2  # D and E, one each


# ------------------------------------------------------------------------ the download


def _export(api: Api, project: Any, table_format: str | None = None) -> Any:
    params = {"format": table_format} if table_format else None
    return api.get(f"/api/v1/projects/{project.id}/progress/export", params=params)


def _value(text: str | None) -> int | float:
    number = float(text or "nan")
    return int(number) if (text or "").lstrip("-").isdigit() else number


def _column(ref: str) -> int:
    """A cell's column, counted from 0, from its reference ("C7" is 2)."""
    letters = re.match(r"[A-Z]+", ref)
    assert letters is not None, ref
    index = 0
    for letter in letters.group():
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def _workbook(data: bytes) -> dict[str, list[list[Any]]]:
    """An .xlsx file's sheets by name, each as rows of values (None for an empty cell); no cell
    may be a formula."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.testzip() is None
    book = ElementTree.fromstring(archive.read("xl/workbook.xml"))  # noqa: S314 - our own file
    sheets: dict[str, list[list[Any]]] = {}
    for number, sheet in enumerate(book.iterfind(".//m:sheet", SHEET_NS), start=1):
        part = archive.read(f"xl/worksheets/sheet{number}.xml")
        rows = []
        for row in ElementTree.fromstring(part).iterfind(".//m:row", SHEET_NS):  # noqa: S314
            values: list[Any] = []
            for cell in row.iterfind("m:c", SHEET_NS):
                assert cell.find("m:f", SHEET_NS) is None, "never a formula"
                values += [None] * (_column(cell.get("r") or "") - len(values))
                if cell.get("t") == "inlineStr":
                    values.append("".join(t.text or "" for t in cell.iterfind(".//m:t", SHEET_NS)))
                else:
                    values.append(_value(cell.findtext("m:v", namespaces=SHEET_NS)))
            rows.append(values)
        sheets[str(sheet.get("name"))] = rows
    return sheets


def _padded(rows: list[list[Any]]) -> list[list[Any]]:
    """Rows as wide as the heading (a sheet leaves out empty cells at a row's end)."""
    width = len(rows[0])
    return [row + [None] * (width - len(row)) for row in rows]


def test_the_progress_tab_downloads_as_excel_with_its_own_numbers(world: dict[str, Any]) -> None:
    """Owner's request: the tab as a workbook, one sheet per table, every number the tab's."""
    project = world["project"]
    _set(world, project, target_hours=1, target_districts=list(targets.CLIENT_DISTRICTS))
    tab = _progress(world["pa"], project).json()
    answer = _export(world["pa"], project)  # Excel unless asked otherwise
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"] == XLSX
    day = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d")
    assert answer.headers["content-disposition"] == (
        f'attachment; filename="progress_summary_PROG_{day}.xlsx"'
    )
    book = {name: _padded(rows) for name, rows in _workbook(answer.content).items()}
    assert list(book) == [
        "About",
        "Key figures",
        "Speakers by age and gender",
        "Speakers by district",
        "Conversations to make",
        "Capacity",
        "Balance",
        "Conversations by status",
        "Completed",
    ]
    about = dict(book["About"][1:])
    assert about["Project code"] == "PROG"
    assert about["Project name"] == "Project PROG"
    assert about["Recording type"] == "Face-to-face and phone call"
    assert re.fullmatch(
        r"\d{4}-\d\d-\d\d \d\d:\d\d \(UTC\+05:30, Asia/Kolkata\)", about["Generated"]
    )
    assert about["Completed counts"] == "Effective speech"
    assert (about["Conversations per speaker"], about["Each pair of speakers only once"]) == (
        2,
        "No",
    )

    figures = {row[0]: row[1:] for row in book["Key figures"][1:]}
    assert book["Key figures"][0] == ["Figure", "Value", "Target", "% of target"]
    assert figures["Completed hours (effective speech)"] == [0.18, 1, 18.3]  # 11 of 60 minutes
    assert figures["Approved conversations"] == [3, 600, 0.5]
    assert figures["Speakers with an approved conversation"] == [5, 500, 1]
    assert figures["Registered speakers"] == [6, None, None]
    assert figures["Registered speakers at the limit of 2 conversations"] == [4, None, None]
    assert figures["Approved conversations not measured yet"] == [1, None, None]
    assert figures["Effective speech (% of the recorded audio)"] == [71.9, None, None]

    needed = tab["still_needed"]
    matrix = book["Speakers by age and gender"]
    assert matrix[0] == ["Age band", "Gender", "Target", "Done", "Registered", "Still needed"]
    expected = [
        [row["label"], gender, *_need(row[key])]
        for row in [*needed["speakers"]["rows"], needed["speakers"]["total"]]
        for gender, key in (("Male", "male"), ("Female", "female"), ("Total", "total"))
    ]
    assert matrix[1:] == expected
    assert matrix[-1] == ["Total", "Total", 500, 5, 1, 495]
    districts = book["Speakers by district"]
    assert districts[1:] == [
        [row["label"], *_need(row)]
        for row in [*needed["districts"]["rows"], needed["districts"]["total"]]
    ]
    assert districts[-2:] == [["Other districts", None, 1, 0, None], ["Total", 500, 5, 1, 495]]
    assert book["Conversations to make"][1:] == [
        [c["label"], c["target"], c["approved"], c["in_pipeline"], c["still_to_make"]]
        for c in needed["conversations"]
    ]
    assert book["Capacity"][1:] == [
        ["Registered speakers", 6],
        ["Places left (two per conversation; none without a limit)", 2],
        ["Conversations still to make", 595],
        ["More speakers needed", 594],
    ]

    balance = book["Balance"]
    assert balance[0][-1] == "Variance (points)"
    shares = [("Age bands", "age_bands"), ("Gender", "gender")]
    shares += [("Face-to-face and phone", "modes"), ("Districts", "districts")]
    assert balance[1:] == [
        [group, r["label"], r["count"], r["percent"], r["target_percent"], r["variance"]]
        for group, key in shares
        for r in tab[key]["rows"]
    ]
    assert ["Gender", "Male", 2, 40, 50, -10] in balance  # a number below the target
    assert ["Districts", "Raigad (Maharashtra)", 0, 0, 12.5, -12.5] in balance

    statuses = {row[1]: row[2:] for row in book["Conversations by status"][1:]}
    assert statuses["Approved"] == [3, 42.9]
    assert statuses["Audio QC"] == [1, 14.3]
    assert statuses["Draft"] == [0, 0]
    assert statuses["All tasks"] == [7, 100]
    assert len(statuses) == 12, "every status, and the total"
    assert book["Completed"][1:] == [
        ["Approved", "Number", 3],
        ["Approved", "Full length (h)", 0.28],  # 17 minutes
        ["Approved", "Effective speech (h)", 0.18],  # 11 minutes
        ["Recorded, not yet approved", "Number", 1],
        ["Recorded, not yet approved", "Full length (h)", 0.02],
        ["Recorded, not yet approved", "Effective speech (h)", 0.01],
    ]


def test_the_csv_is_one_long_table_with_the_same_numbers(world: dict[str, Any]) -> None:
    project = world["project"]
    _set(world, project, target_districts=list(targets.CLIENT_DISTRICTS))
    answer = _export(world["pa"], project, "csv")
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"] == "text/csv; charset=utf-8"
    day = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d")
    assert answer.headers["content-disposition"] == (
        f'attachment; filename="progress_summary_PROG_{day}.csv"'
    )
    text = answer.content.decode("utf-8")
    assert text.startswith("\ufeff"), "spreadsheets read UTF-8 with the BOM"
    rows = list(csv.reader(io.StringIO(text.removeprefix("\ufeff"))))
    assert tuple(rows[0]) == progress.SUMMARY_COLUMNS
    found = {(r[0], r[1], r[2]): dict(zip(rows[0], r, strict=True)) for r in rows[1:]}
    # The same tables as the workbook, one row each.
    book = _workbook(_export(world["pa"], project, "xlsx").content)
    assert len(rows) - 1 == sum(len(sheet) - 1 for sheet in book.values())
    assert found[("About", "Project code", "PROG")]["section"] == "About"
    key = found[("Key figures", "", "Approved conversations")]
    assert (key["count"], key["target"], key["percent"]) == ("3", "600", "0.5")
    cell = found[("Speakers by age and gender", "30-40", "Male")]
    assert [cell[k] for k in ("target", "done", "registered", "still_needed")] == [
        "75",
        "1",
        "1",
        "73",
    ]
    talks = found[("Conversations to make", "", "All conversations")]
    assert [talks[k] for k in ("target", "done", "count", "still_needed")] == [
        "600",
        "3",
        "2",
        "595",
    ]
    # A variance below the target is written as a number (no quote in front), and so is every
    # other figure.
    male = found[("Balance", "Gender", "Male")]
    assert (male["count"], male["percent"], male["target_percent"], male["variance"]) == (
        "2",
        "40.0",
        "50.0",
        "-10.0",
    )
    assert found[("Balance", "Districts", "Raigad (Maharashtra)")]["variance"] == "-12.5"
    assert found[("Conversations by status", "Total", "All tasks")]["count"] == "7"


def test_a_district_typed_as_a_formula_stays_text_in_the_download(world: dict[str, Any]) -> None:
    """With no districts listed, the balance's rows are the speakers' own native districts, free
    text: one written as a formula must not run in a spreadsheet."""
    formula = '=HYPERLINK("http://evil.example","Click")'
    db = world["db"]
    db.execute(
        update(Participant).where(Participant.id == world["people"]["E"]).values(district=formula)
    )
    db.commit()
    project = world["project"]
    text = _export(world["pa"], project, "csv").content.decode("utf-8").removeprefix("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    districts = [r[2] for r in rows if r[0] == "Balance" and r[1] == "Districts"]
    assert "'" + formula in districts, "a quote in front: the spreadsheet shows it as text"
    assert not any(cell.startswith(("=", "+", "@")) for r in rows for cell in r)
    sheet = _workbook(_export(world["pa"], project).content)["Balance"]
    assert ["Districts", formula] in [row[:2] for row in sheet], "plain text, never a formula"


def test_only_the_people_who_manage_the_project_download_it(world: dict[str, Any]) -> None:
    """Like the tab: projects.manage (others 403, another project's admin 404); every download
    is audited, a refused one is not; only Excel and CSV."""
    db, project = world["db"], world["project"]
    for who in ("mod", "qc", "client"):
        assert _export(world[who], project).status_code == 403, who
    assert _export(world["pa2"], project, "csv").status_code == 404, "not their project"
    assert _export(world["root"], project, "csv").status_code == 200
    assert _export(world["pa"], project, "xlsx").status_code == 200
    wrong = _export(world["pa"], project, "pdf")
    assert wrong.status_code == 422, wrong.text
    assert wrong.json()["error"]["code"] == "VALIDATION_ERROR"
    db.expire_all()
    entries = db.scalars(
        select(AuditLog)
        .where(AuditLog.action == "project.exported")
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    assert sorted(e.after_summary or "" for e in entries) == [
        '{"content": "progress_summary", "format": "csv"}',
        '{"content": "progress_summary", "format": "xlsx"}',
    ]
    assert {e.project_id for e in entries} == {project.id}


# ------------------------------------------------------------------------ the dashboard


def test_the_dashboard_counts_completed_hours_as_each_project_says(world: dict[str, Any]) -> None:
    db, pa = world["db"], world["pa"]
    other = world["other"]
    a = _person(pa, other.id, "Gita")
    b = _person(pa, other.id, "Hari")
    _task(
        db,
        other,
        11,
        a,
        b,
        "FACE_TO_FACE",
        "APPROVED",
        world["mod_user"].id,
        6 * MINUTE,
        3 * MINUTE,
    )
    _set(world, other, progress_counts="FULL")

    def board(project: Any | None) -> dict[str, Any]:
        params = {"project_id": str(project.id)} if project else {}
        answer = pa.get("/api/v1/dashboard", params=params)
        assert answer.status_code == 200, answer.text
        result: dict[str, Any] = answer.json()
        return result

    def hours(face_minutes: float, phone_minutes: float) -> float:
        """A total as the dashboard adds it: hours per mode, two places, then added."""
        return round(
            sum(round(m * MINUTE / 3_600_000, 2) for m in (face_minutes, phone_minutes)), 2
        )

    one = board(world["project"])
    # Every finished recording of the project: T1, T3, T4 and the rejected T6 face-to-face, T2
    # by phone.
    assert one["recorded_hours"] == hours(10 + 2 + 1 + 1, 5)
    assert one["effective_hours"] == hours(7 + 0.5 + 1, 4), "T3 not measured yet"
    assert one["approved_hours"] == hours(10 + 2, 5)
    assert one["approved_effective_hours"] == hours(7, 4)
    assert one["completed_hours"] == hours(7, 4), "EFFECTIVE: the approved effective speech"
    assert one["effective_pending"] == 1  # T3
    face = next(m for m in one["by_mode"] if m["mode"] == "FACE_TO_FACE")
    assert face["completed_hours"] == hours(7, 0)
    assert face["effective_hours"] == hours(8.5, 0)
    # The other project counts the full length: 6 minutes, not its 3 of speech.
    assert board(other)["completed_hours"] == hours(6, 0)
    assert board(other)["approved_effective_hours"] == hours(3, 0)
    # Together, each project adds its own completed hours.
    assert board(None)["completed_hours"] == hours(7 + 6, 4)


# ------------------------------------------------------------------------ the settings


SETTINGS = (
    "pause_limit_seconds",
    "long_pauses_need_review",
    "progress_counts",
    "target_hours",
    "target_speakers",
    "target_conversations",
    "target_age_bands",
    "target_gender",
    "target_modes",
    "target_districts",
)
BODY_KEYS = (
    "name",
    "description",
    "allows_telephony",
    "allows_face_to_face",
    "target_telephony_hours_per_day",
    "target_face_to_face_hours_per_day",
    "phone_visibility_policy",
    "consent_policy_version",
    "consent_text",
    "pause_limit_seconds",
    "long_pauses_need_review",
    "progress_counts",
    "target_hours",
    "target_speakers",
    "target_conversations",
)


def _save(api: Api, project: Any, **changes: Any) -> Any:
    """The project as the Rules tab saves it: everything as it is, with these changes (the JSON
    settings only when given)."""
    current = api.get(f"/api/v1/projects/{project.id}").json()
    return api.patch(
        f"/api/v1/projects/{project.id}",
        json={**{k: current[k] for k in BODY_KEYS}, **changes},
    )


def test_a_new_project_starts_with_the_clients_targets(world: dict[str, Any]) -> None:
    made = world["root"].post(
        "/api/v1/projects",
        json={"name": "Konkani", "allows_telephony": False, "allows_face_to_face": True},
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert {k: body[k] for k in SETTINGS} == {
        "pause_limit_seconds": 3,
        "long_pauses_need_review": False,
        "progress_counts": "EFFECTIVE",
        "target_hours": None,
        "target_speakers": 500,
        "target_conversations": 600,
        "target_age_bands": [
            {"from": 20, "to": 30, "percent": 40},
            {"from": 30, "to": 40, "percent": 30},
            {"from": 40, "to": 50, "percent": 20},
            {"from": 50, "to": 60, "percent": 10},
        ],
        "target_gender": {"MALE": 50, "FEMALE": 50},
        "target_modes": {"FACE_TO_FACE": 50, "TELEPHONY": 50},
        "target_districts": [],
    }


def test_the_settings_save_with_the_project_and_are_audited(world: dict[str, Any]) -> None:
    db, pa, project = world["db"], world["pa"], world["project"]
    saved = _save(
        pa,
        project,
        pause_limit_seconds=5,
        long_pauses_need_review=True,
        progress_counts="FULL",
        target_hours="250.5",
        target_speakers=None,
        target_conversations=650,
        target_age_bands=[
            {"from": 40, "to": 61, "percent": 50},
            {"from": 18, "to": 40, "percent": 50},
        ],
        target_gender={"MALE": 40, "FEMALE": 60},
        target_modes={},
        target_districts=[{"state": " goa ", "district": " North   Goa "}],
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert {k: body[k] for k in SETTINGS} == {
        "pause_limit_seconds": 5,
        "long_pauses_need_review": True,
        "progress_counts": "FULL",
        "target_hours": "250.50",
        "target_speakers": None,
        "target_conversations": 650,
        # In age order.
        "target_age_bands": [
            {"from": 18, "to": 40, "percent": 50},
            {"from": 40, "to": 61, "percent": 50},
        ],
        "target_gender": {"MALE": 40, "FEMALE": 60},
        "target_modes": {},
        "target_districts": [{"state": "Goa", "district": "North Goa"}],
    }
    db.expire_all()
    [entry] = db.scalars(select(AuditLog).where(AuditLog.action == "project.updated")).all()
    assert '"pause_limit_seconds": 5' in (entry.after_summary or "")
    assert "North Goa" in (entry.after_summary or "")
    # The shares left out keep the project's own (D-146's rule); the others are saved as sent.
    kept = _save(pa, project, description="Konkani talk")
    assert kept.status_code == 200, kept.text
    assert kept.json()["target_gender"] == {"MALE": 40, "FEMALE": 60}
    assert kept.json()["target_districts"] == [{"state": "Goa", "district": "North Goa"}]
    assert kept.json()["pause_limit_seconds"] == 5


@pytest.mark.parametrize(
    ("changes", "code", "says"),
    [
        ({"pause_limit_seconds": 0}, "VALIDATION_ERROR", None),
        ({"pause_limit_seconds": 31}, "VALIDATION_ERROR", None),
        ({"progress_counts": "SOME"}, "VALIDATION_ERROR", None),
        ({"target_speakers": 0}, "VALIDATION_ERROR", None),
        ({"target_hours": 0}, "VALIDATION_ERROR", None),  # PROJ-12: no target is null
        (
            {"target_age_bands": [{"from": 20, "to": 30, "percent": 60}]},
            "INVALID_TARGETS",
            "Age bands: the percents add up to 60, not 100",
        ),
        (
            {
                "target_age_bands": [
                    {"from": 20, "to": 35, "percent": 50},
                    {"from": 30, "to": 40, "percent": 50},
                ]
            },
            "INVALID_TARGETS",
            "Age bands 20-35 and 30-40 overlap",
        ),
        (
            {"target_age_bands": [{"from": 30, "to": 30, "percent": 100}]},
            "INVALID_TARGETS",
            "Age band 1: the first age must be below the last",
        ),
        (
            {"target_gender": {"MALE": 100}},
            "INVALID_TARGETS",
            "Gender: give a percent for each of MALE, FEMALE",
        ),
        (
            {"target_modes": {"FACE_TO_FACE": 70, "TELEPHONY": 20}},
            "INVALID_TARGETS",
            "Face-to-face and phone: the percents add up to 90, not 100",
        ),
        (
            {"target_districts": [{"state": "Atlantis", "district": "North"}]},
            "INVALID_TARGETS",
            "District 1: the state must be a state or union territory of India",
        ),
        (
            {
                "target_districts": [
                    {"state": "Goa", "district": "North Goa"},
                    {"state": "Goa", "district": "north goa"},
                ]
            },
            "INVALID_TARGETS",
            "District 2: north goa is listed twice",
        ),
    ],
)
def test_wrong_settings_are_refused_in_words(
    world: dict[str, Any], changes: dict[str, Any], code: str, says: str | None
) -> None:
    answer = _save(world["pa"], world["project"], **changes)
    assert answer.status_code == 422, answer.text
    assert answer.json()["error"]["code"] == code
    if says:
        assert says in answer.json()["error"]["message"]


def test_age_bands_take_their_first_age_and_the_last_band_its_last() -> None:
    bands = list(targets.DEFAULT_TARGET_AGE_BANDS)
    assert [targets.band_of(age, bands) for age in (19, 20, 29, 30, 59, 60, 61, None)] == [
        None,
        0,
        0,
        1,
        3,
        3,
        None,
        None,
    ]


def test_the_frontend_copy_of_the_clients_districts_matches() -> None:
    """ "Use the client's Konkani districts" on the Rules tab fills in the same list."""
    source = FRONTEND_TARGETS.read_text(encoding="utf-8")
    block = source.split("CLIENT_DISTRICTS", 1)[1].split("];", 1)[0]
    pairs = re.findall(r'state: "([^"]+)", district: "([^"]+)"', block)
    assert [{"state": s, "district": d} for s, d in pairs] == list(targets.CLIENT_DISTRICTS)
