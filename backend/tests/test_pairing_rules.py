"""Task rules per project (D-143): both speakers need complete speaker details, at most N
conversations per speaker, each pair of speakers only once; for one task and for a file of tasks.
The project options that set them, and what the participant list tells the task form.

Requirements: TASK-001, PROJ-001, PROJ-011, PART-001, PART-016
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select

from app.modules.tasks.models import Task
from tests.conftest import (
    SPEAKER_DETAILS,
    Api,
    make_participant,
    make_project,
    make_user,
    set_status,
)

pytestmark = pytest.mark.db


@pytest.fixture
def world(db: Any, new_api: Any) -> dict[str, Any]:
    project = make_project(db, "PAIRS", max_conversations_per_speaker=3, unique_pairs=True)
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    pa: Api = new_api()
    assert pa.login("pa@example.org").status_code == 200
    root: Api = new_api()
    assert root.login("root@example.org").status_code == 200
    people = {name: make_participant(pa, project.id, name) for name in "ABCDEF"}
    return {"db": db, "pa": pa, "root": root, "project": project, **people}


def _task(world: dict[str, Any], a: str, b: str) -> Any:
    return world["pa"].post(
        "/api/v1/tasks",
        json={
            "project_id": str(world["project"].id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": world[a]["id"],
            "participant_b_id": world[b]["id"],
        },
    )


def _code(world: dict[str, Any], name: str) -> str:
    code: str = world[name]["participant_code"]
    return code


def _error(response: Any) -> tuple[int, str, str]:
    error = response.json()["error"]
    return response.status_code, error["code"], error["message"]


def test_both_speakers_need_complete_details(world: dict[str, Any], db: Any) -> None:
    pid = world["project"].id
    world["X"] = make_participant(world["pa"], pid, "X", speaker={})
    world["Y"] = make_participant(world["pa"], pid, "Y", speaker={"age": 30})
    x, y = _code(world, "X"), _code(world, "Y")
    assert _error(_task(world, "A", "X")) == (
        422,
        "SPEAKER_DETAILS_MISSING",
        f"Participant {x} has no complete speaker details yet: add them with Edit.",
    )
    both = _task(world, "X", "Y")
    assert _error(both)[2] == (
        f"Participants {x} and {y} have no complete speaker details yet: add them with Edit."
    )
    assert both.json()["error"]["details"] == [{"participants": [x, y]}]
    assert db.scalar(select(func.count()).select_from(Task)) == 0
    # Added with Edit: now the task can be made.
    fixed = world["pa"].patch(
        f"/api/v1/projects/{pid}/participants/{world['X']['id']}",
        json={
            "display_label": "X",
            "language_code": "hi",
            **SPEAKER_DETAILS,
        },
    )
    assert fixed.json()["speaker_details_complete"] is True
    assert _task(world, "A", "X").status_code == 201


def test_at_most_n_conversations_per_speaker(world: dict[str, Any], db: Any) -> None:
    made = [_task(world, "A", other) for other in "BCD"]
    assert [r.status_code for r in made] == [201, 201, 201]
    a = _code(world, "A")
    assert _error(_task(world, "E", "A")) == (
        409,
        "SPEAKER_LIMIT_REACHED",
        f"Participant {a} already has 3 conversations in this project, the most for one speaker.",
    )
    # A cancelled, rejected or deleted task frees its place; any other status counts.
    set_status(db, made[0].json()["id"], "CANCELLED")
    assert _task(world, "A", "E").status_code == 201
    assert _task(world, "A", "F").json()["error"]["code"] == "SPEAKER_LIMIT_REACHED"
    set_status(db, made[1].json()["id"], "REJECTED")
    assert _task(world, "A", "F").status_code == 201
    set_status(db, made[2].json()["id"], "APPROVED")
    assert _task(world, "B", "A").json()["error"]["code"] == "SPEAKER_LIMIT_REACHED"
    last = _task(world, "C", "D")  # C and D are free (C's task was rejected)
    assert last.status_code == 201
    pa = world["pa"]
    deleted = pa.post(f"/api/v1/tasks/{last.json()['id']}/delete", json={"reason": "By mistake"})
    assert deleted.status_code == 204, deleted.text

    # The limit is the project's: 1, or none at all.
    set_rules(world, max_conversations_per_speaker=1)
    b, c = _code(world, "B"), _code(world, "C")
    one = _task(world, "B", "C")
    assert one.status_code == 201
    assert _error(_task(world, "B", "C"))[1:] == (
        "SPEAKER_LIMIT_REACHED",
        f"Participants {b} and {c} already have 1 conversation in this project, the most for "
        "one speaker.",
    )
    set_rules(world, max_conversations_per_speaker=None, unique_pairs=False)
    assert all(_task(world, "A", "B").status_code == 201 for _ in range(3))


def test_each_pair_of_speakers_only_once(world: dict[str, Any], db: Any) -> None:
    first = _task(world, "A", "B")
    task_code = first.json()["task_code"]
    a, b = _code(world, "A"), _code(world, "B")
    again = _task(world, "B", "A")  # either way round
    assert _error(again) == (
        409,
        "PAIR_ALREADY_USED",
        f"{b} and {a} already have a conversation together in this project ({task_code}): "
        "each pair of speakers only once.",
    )
    assert again.json()["error"]["details"] == [{"participants": [b, a], "task": task_code}]
    set_status(db, first.json()["id"], "CANCELLED")
    assert _task(world, "B", "A").status_code == 201
    set_rules(world, unique_pairs=False)
    assert _task(world, "A", "B").status_code == 201


def set_rules(world: dict[str, Any], **rules: Any) -> Any:
    project = world["root"].get(f"/api/v1/projects/{world['project'].id}").json()
    body = {
        key: project[key]
        for key in (
            "name",
            "description",
            "allows_telephony",
            "allows_face_to_face",
            "phone_visibility_policy",
            "consent_policy_version",
            "consent_text",
            "qc_final_approval",
            "max_conversations_per_speaker",
            "unique_pairs",
        )
    }
    saved = world["root"].patch(f"/api/v1/projects/{world['project'].id}", json={**body, **rules})
    assert saved.status_code == 200, saved.text
    return saved.json()


def test_the_project_options(world: dict[str, Any], db: Any) -> None:
    """New projects start with 3 conversations per speaker and each pair once; the options are
    saved, audited with the project, and an empty limit means no limit."""
    from app.modules.audit.models import AuditLog

    root = world["root"]
    new = root.post(
        "/api/v1/projects",
        json={"name": "New", "allows_telephony": False, "allows_face_to_face": True},
    ).json()
    assert (new["max_conversations_per_speaker"], new["unique_pairs"]) == (3, True)
    saved = set_rules(world, max_conversations_per_speaker=5, unique_pairs=False)
    assert (saved["max_conversations_per_speaker"], saved["unique_pairs"]) == (5, False)
    assert (
        set_rules(world, max_conversations_per_speaker=None)["max_conversations_per_speaker"]
        is None
    )
    pid = world["project"].id
    for wrong in (0, -1, "many"):
        refused = root.patch(
            f"/api/v1/projects/{pid}",
            json={
                "name": "x",
                "allows_telephony": True,
                "allows_face_to_face": True,
                "max_conversations_per_speaker": wrong,
            },
        )
        assert refused.status_code == 422, wrong
    entry = db.scalars(
        select(AuditLog)
        .where(AuditLog.action == "project.updated")
        .order_by(AuditLog.created_at.desc())
    ).first()
    assert '"max_conversations_per_speaker": null' in (entry.after_summary or "")


def test_a_file_of_tasks_follows_the_same_rules(world: dict[str, Any], db: Any) -> None:
    """Each row is checked against the project's tasks and the rows above it, then made through
    the same create_task."""
    pid = world["project"].id
    world["X"] = make_participant(world["pa"], pid, "X", speaker={})
    assert _task(world, "A", "B").status_code == 201
    a, b, c, d, e, x = (_code(world, n) for n in "ABCDEX")
    csv = (
        "participant_a,participant_b\n"
        f"{b},{a}\n"  # 2: the pair has a task already
        f"{a},{c}\n"  # 3: A's second
        f"{c},{a}\n"  # 4: the same pair as line 3
        f"{a},{d}\n"  # 5: A's third
        f"{a},{e}\n"  # 6: a fourth for A
        f"{x},{e}\n"  # 7: X has no speaker details
        f"{d},{e}\n"  # 8: fine
    )
    body = {"project_id": str(pid), "csv": csv}
    check = world["pa"].post("/api/v1/tasks/import", json=body).json()
    rows = [(r["ok"], r["message"]) for r in check["rows"]]
    first = db.scalar(select(Task.task_code))
    assert rows == [
        (
            False,
            f"{b} and {a} already have a conversation together in this project ({first}): "
            "each pair of speakers only once.",
        ),
        (True, "Ready to add"),
        (
            False,
            f"{c} and {a} already have a conversation together in this project (line 3 of this "
            "file): each pair of speakers only once.",
        ),
        (True, "Ready to add"),
        (
            False,
            f"Participant {a} already has 3 conversations in this project, the most for one "
            "speaker.",
        ),
        (False, f"Participant {x} has no complete speaker details yet: add them with Edit."),
        (True, "Ready to add"),
    ]
    added = world["pa"].post("/api/v1/tasks/import", json={**body, "confirm": True}).json()
    assert added["created"] == 3
    assert [r["ok"] for r in added["rows"]] == [r[0] for r in rows]
    assert db.scalar(select(func.count()).select_from(Task)) == 4


def test_the_list_tells_the_task_form_who_can_be_paired(world: dict[str, Any]) -> None:
    pid = world["project"].id
    world["X"] = make_participant(world["pa"], pid, "X", speaker={})
    _task(world, "A", "B")
    _task(world, "A", "C")
    cancelled = _task(world, "D", "E").json()["id"]
    set_status(world["db"], cancelled, "CANCELLED")
    listed = {
        p["display_label"]: p
        for p in world["pa"].get(f"/api/v1/projects/{pid}/participants").json()["items"]
    }
    assert listed["A"]["pairing"] == {
        "conversations": 2,
        "paired_with": sorted([world["B"]["id"], world["C"]["id"]]),
    }
    assert listed["B"]["pairing"] == {"conversations": 1, "paired_with": [world["A"]["id"]]}
    assert listed["D"]["pairing"] == {"conversations": 0, "paired_with": []}
    assert (listed["X"]["speaker_details_complete"], listed["A"]["speaker_details_complete"]) == (
        False,
        True,
    )
    # Only in the list: one participant's own answer has no pairing.
    one = world["pa"].get(f"/api/v1/projects/{pid}/participants/{world['A']['id']}").json()
    assert one["pairing"] is None
