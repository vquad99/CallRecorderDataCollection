"""One recording type per project (D-153): a project records face-to-face conversations or phone
calls, never both; a project made before that allows both keeps working until it is edited; a new
task takes the project's type.

Requirements: PROJ-001, PROJ-002, PROJ-011, TASK-001
"""

from __future__ import annotations

from itertools import count
from typing import Any

import pytest
from sqlalchemy import select

from app.modules.tasks.models import Task
from tests.conftest import Api, make_participant, make_project, make_user

pytestmark = pytest.mark.db

ONE_TYPE = (
    "Choose one recording type: face-to-face or phone call. Make another project for the other."
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
)
FACE = {"allows_telephony": False, "allows_face_to_face": True}
PHONE = {"allows_telephony": True, "allows_face_to_face": False}
BOTH = {"allows_telephony": True, "allows_face_to_face": True}


@pytest.fixture
def world(db: Any, new_api: Any) -> dict[str, Any]:
    """A project made before D-153 that allows both types, and a Super Admin."""
    legacy = make_project(db, "OLD")
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    root: Api = new_api()
    assert root.login("root@example.org").status_code == 200
    return {"db": db, "root": root, "legacy": legacy}


def _save(api: Api, project_id: Any, **changes: Any) -> Any:
    """The project as the Overview or the Rules tab saves it: as it is, with these changes."""
    current = api.get(f"/api/v1/projects/{project_id}").json()
    return api.patch(
        f"/api/v1/projects/{project_id}", json={**{k: current[k] for k in BODY_KEYS}, **changes}
    )


def _refused(answer: Any) -> None:
    assert answer.status_code == 422, answer.text
    assert answer.json()["error"]["code"] == "ONE_RECORDING_TYPE"
    assert answer.json()["error"]["message"] == ONE_TYPE
    assert answer.json()["error"]["details"] == [{"field": "recording_mode"}]


def test_a_new_project_records_one_type(world: dict[str, Any]) -> None:
    root = world["root"]
    for modes in (BOTH, {"allows_telephony": False, "allows_face_to_face": False}):
        _refused(root.post("/api/v1/projects", json={"name": "Konkani", **modes}))
    for modes, mode in ((FACE, "FACE_TO_FACE"), (PHONE, "TELEPHONY")):
        made = root.post("/api/v1/projects", json={"name": f"Konkani {mode}", **modes})
        assert made.status_code == 201, made.text
        assert [r["mode"] for r in made.json()["audio_rules"]] == [mode]


def test_a_project_changes_from_one_type_to_the_other_but_never_to_both(
    world: dict[str, Any],
) -> None:
    root = world["root"]
    pid = root.post("/api/v1/projects", json={"name": "Konkani", **FACE}).json()["id"]
    _refused(_save(root, pid, **BOTH))
    _refused(_save(root, pid, allows_face_to_face=False))
    moved = _save(root, pid, **PHONE)
    assert moved.status_code == 200, moved.text
    assert (moved.json()["allows_telephony"], moved.json()["allows_face_to_face"]) == (True, False)
    # The face-to-face audio rule stays for the tasks made before; the tab may send it back.
    assert {r["mode"] for r in moved.json()["audio_rules"]} == {"FACE_TO_FACE", "TELEPHONY"}
    rules = moved.json()["audio_rules"]
    kept = root.put(f"/api/v1/projects/{pid}/audio-rules", json={"rules": rules})
    assert kept.status_code == 200, kept.text
    without_own = [r for r in rules if r["mode"] == "FACE_TO_FACE"]
    answer = root.put(f"/api/v1/projects/{pid}/audio-rules", json={"rules": without_own})
    assert answer.json()["error"]["code"] == "MODE_NOT_ALLOWED"


def test_a_project_that_allows_both_keeps_them_until_it_chooses_one(
    world: dict[str, Any],
) -> None:
    """Nothing changes by itself: saved as it is (the Rules tab), it still allows both; the
    Overview chooses one, and then it stays one type."""
    root, pid = world["root"], world["legacy"].id
    kept = _save(root, pid, description="Saved from the Rules tab")
    assert kept.status_code == 200, kept.text
    assert (kept.json()["allows_telephony"], kept.json()["allows_face_to_face"]) == (True, True)
    _refused(_save(root, pid, allows_telephony=False, allows_face_to_face=False))
    chosen = _save(root, pid, allows_telephony=False, target_telephony_hours_per_day="0")
    assert chosen.status_code == 200, chosen.text
    assert (chosen.json()["allows_telephony"], chosen.json()["allows_face_to_face"]) == (
        False,
        True,
    )
    _refused(_save(root, pid, **BOTH))


_PHONES = count(10)


def _people(api: Api, project_id: Any, tag: str, n: int = 2) -> list[str]:
    """People who agreed, with complete details and a phone number each."""
    return [
        make_participant(api, project_id, f"{tag}{i}", phone=f"+9198765432{next(_PHONES):02d}")[
            "id"
        ]
        for i in range(n)
    ]


def test_a_task_takes_the_projects_type(world: dict[str, Any]) -> None:
    db, root = world["db"], world["root"]
    made = root.post("/api/v1/projects", json={"name": "Phone only", **PHONE}).json()
    pid = made["id"]
    assert root.post(f"/api/v1/projects/{pid}/status", json={"status": "ACTIVE"}).status_code == 200
    a, b = _people(root, pid, "Phone")

    def task(**extra: Any) -> Any:
        return root.post(
            "/api/v1/tasks",
            json={"project_id": pid, "participant_a_id": a, "participant_b_id": b, **extra},
        )

    wrong = task(recording_mode="FACE_TO_FACE")
    assert wrong.status_code == 422, wrong.text
    assert wrong.json()["error"]["code"] == "MODE_NOT_ALLOWED"
    assert wrong.json()["error"]["message"] == "This project records phone calls only"
    made_task = task()
    assert made_task.status_code == 201, made_task.text
    assert made_task.json()["recording_mode"] == "TELEPHONY"
    # Many at once: an empty mode is the project's type; another type is refused on its row.
    c, d, e, f = _people(root, pid, "More", 4)
    codes = {
        p["id"]: p["participant_code"]
        for p in root.get(f"/api/v1/projects/{pid}/participants").json()["items"]
    }
    csv = (
        "participant_a,participant_b,mode\n"
        f"{codes[c]},{codes[d]},\n"
        f"{codes[e]},{codes[f]},face_to_face\n"
    )
    rows = root.post(
        "/api/v1/tasks/import", json={"project_id": pid, "csv": csv, "confirm": True}
    ).json()["rows"]
    assert [(r["ok"], r["message"]) for r in rows] == [
        (True, "Added"),
        (False, "This project records phone calls only"),
    ]
    modes = db.scalars(select(Task.recording_mode).where(Task.project_id == made["id"])).all()
    assert sorted(modes) == ["TELEPHONY", "TELEPHONY"]


def test_a_project_that_allows_both_still_needs_the_type_of_a_task(world: dict[str, Any]) -> None:
    root, pid = world["root"], str(world["legacy"].id)
    a, b = _people(root, pid, "Old")
    body = {"project_id": pid, "participant_a_id": a, "participant_b_id": b}
    missing = root.post("/api/v1/tasks", json=body)
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"]["code"] == "MODE_REQUIRED"
    either = root.post("/api/v1/tasks", json={**body, "recording_mode": "TELEPHONY"})
    assert either.status_code == 201, either.text
    assert either.json()["recording_mode"] == "TELEPHONY"
