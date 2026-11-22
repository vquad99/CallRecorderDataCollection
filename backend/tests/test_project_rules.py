"""The project's rules (D-145): the speaker ages a project takes and the speaker details a person
needs before a task are project settings with the first client's numbers only as defaults; the
rules moved to the Rules tab (pairing, consent, approval) still save through the project PATCH;
a new project may have no limit and no targets (PROJ-08).

Requirements: PROJ-001, PROJ-011, PART-001, PART-012, PART-016, TASK-001
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditLog
from app.modules.participants import speakers
from tests.conftest import Api, email_for, make_participant, make_project, make_user

pytestmark = pytest.mark.db

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
    "qc_final_approval",
    "max_conversations_per_speaker",
    "unique_pairs",
    "consent_mode",
    "speaker_min_age",
    "speaker_max_age",
    "required_speaker_details",
)


@pytest.fixture
def world(db: Any, new_api: Any) -> dict[str, Any]:
    rules = make_project(db, "RULES")
    wide = make_project(db, "WIDE")
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[rules, wide])
    apis = {}
    for name in ("root", "pa"):
        apis[name] = new_api()
        assert apis[name].login(f"{name}@example.org").status_code == 200
    return {
        "db": db,
        "rules": rules,
        "wide": wide,
        "base": f"/api/v1/projects/{rules.id}/participants",
        "wide_base": f"/api/v1/projects/{wide.id}/participants",
        **apis,
    }


def save(api: Api, project_id: Any, **changes: Any) -> Any:
    """The project as the Rules tab saves it: everything as it is, with these changes."""
    current = api.get(f"/api/v1/projects/{project_id}").json()
    body = {key: current[key] for key in BODY_KEYS}
    return api.patch(f"/api/v1/projects/{project_id}", json={**body, **changes})


def saved(api: Api, project_id: Any, **changes: Any) -> dict[str, Any]:
    response = save(api, project_id, **changes)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def _error(response: Any) -> tuple[int, str, str]:
    error = response.json()["error"]
    return response.status_code, error["code"], error["message"]


def _new(world: dict[str, Any], base: str = "", **details: Any) -> Any:
    """A new person (each with an address of their own: the same name and address twice is the
    same person, PART-05)."""
    body = {"display_label": "Sneha", "language_code": "hi", "email": email_for("Sneha")}
    return world["pa"].post(base or world["base"], json={**body, **details})


def test_a_new_project_starts_with_the_usual_rules_and_keeps_its_own(
    world: dict[str, Any], db: Any
) -> None:
    root = world["root"]
    new = root.post(
        "/api/v1/projects",
        json={"name": "New", "allows_telephony": False, "allows_face_to_face": True},
    ).json()
    assert (new["speaker_min_age"], new["speaker_max_age"]) == (20, 60)
    assert new["required_speaker_details"] == list(speakers.FIELDS)
    assert (new["qc_final_approval"], new["consent_mode"]) == (False, "ONLINE")
    assert (new["max_conversations_per_speaker"], new["unique_pairs"]) == (3, True)

    pid = world["rules"].id
    changed = saved(
        root,
        pid,
        speaker_min_age=18,
        speaker_max_age=75,
        required_speaker_details=["gender", "age", "age", "recording_pincode"],
        qc_final_approval=True,
        consent_mode="UPLOAD",
        max_conversations_per_speaker=2,
        unique_pairs=True,
    )
    assert (changed["speaker_min_age"], changed["speaker_max_age"]) == (18, 75)
    assert changed["required_speaker_details"] == ["age", "gender", "recording_pincode"]
    # The rules moved to the Rules tab still save through the project PATCH.
    assert (changed["qc_final_approval"], changed["consent_mode"]) == (True, "UPLOAD")
    assert (changed["max_conversations_per_speaker"], changed["unique_pairs"]) == (2, True)
    again = root.get(f"/api/v1/projects/{pid}").json()
    assert {k: again[k] for k in BODY_KEYS} == {k: changed[k] for k in BODY_KEYS}
    assert saved(root, pid, required_speaker_details=[])["required_speaker_details"] == []

    entries = db.scalars(
        select(AuditLog)
        .where(AuditLog.action == "project.updated", AuditLog.project_id == pid)
        .order_by(AuditLog.created_at)
    ).all()
    first = entries[0]
    assert '"speaker_min_age": 20' in (first.before_summary or "")
    assert '"speaker_min_age": 18' in (first.after_summary or "")
    assert '"required_speaker_details": ["age", "gender", "recording_pincode"]' in (
        first.after_summary or ""
    )
    assert '"required_speaker_details": []' in (entries[-1].after_summary or "")


def test_a_new_project_may_have_no_limit_and_no_targets(world: dict[str, Any], db: Any) -> None:
    """PROJ-08: null on POST is "no limit" and "no target", stored as null (not the column's
    default) and audited as stored; left out, the usual numbers."""
    root = world["root"]
    one_type = {"allows_telephony": False, "allows_face_to_face": True}
    nulls = {
        "max_conversations_per_speaker": None,
        "target_speakers": None,
        "target_conversations": None,
    }
    made = root.post("/api/v1/projects", json={"name": "Open", **one_type, **nulls})
    assert made.status_code == 201, made.text
    assert {k: made.json()[k] for k in nulls} == nulls
    again = root.get(f"/api/v1/projects/{made.json()['id']}").json()
    assert {k: again[k] for k in nulls} == nulls
    [entry] = db.scalars(
        select(AuditLog).where(
            AuditLog.action == "project.created", AuditLog.entity_id == made.json()["id"]
        )
    ).all()
    after = json.loads(entry.after_summary or "")
    assert {k: after[k] for k in nulls} == nulls
    usual = root.post("/api/v1/projects", json={"name": "Usual", **one_type}).json()
    assert [usual[k] for k in nulls] == [3, 500, 600]


@pytest.mark.parametrize(
    ("changes", "status", "code", "words"),
    [
        (
            {"speaker_min_age": 61, "speaker_max_age": 60},
            422,
            "INVALID_AGE_RANGE",
            "The youngest speaker age (61) is above the oldest (60)",
        ),
        ({"speaker_min_age": 0}, 422, "VALIDATION_ERROR", ""),
        ({"speaker_max_age": 121}, 422, "VALIDATION_ERROR", ""),
        ({"speaker_min_age": "young"}, 422, "VALIDATION_ERROR", ""),
        (
            {"required_speaker_details": ["age", "shoe_size"]},
            422,
            "UNKNOWN_SPEAKER_DETAIL",
            "shoe_size is not a speaker detail. Choose from: age, gender, current_state",
        ),
        ({"required_speaker_details": "age"}, 422, "VALIDATION_ERROR", ""),
    ],
)
def test_a_wrong_rule_is_refused_in_words(
    world: dict[str, Any], changes: dict[str, Any], status: int, code: str, words: str
) -> None:
    pid = world["rules"].id
    refused = save(world["root"], pid, **changes)
    got = _error(refused)
    assert got[:2] == (status, code)
    assert got[2].startswith(words), got[2]
    kept = world["root"].get(f"/api/v1/projects/{pid}").json()
    assert (kept["speaker_min_age"], kept["speaker_max_age"]) == (20, 60), "nothing saved"
    assert kept["required_speaker_details"] == list(speakers.FIELDS)


def test_a_participant_is_held_to_the_project_ages(world: dict[str, Any]) -> None:
    """Adding and correcting in a project hold the age to the project's range; any person's age
    is 1 to 120. An age kept as it was is not checked again."""
    for age in (19, 61):
        refused = _new(world, age=age)
        assert _error(refused) == (
            422,
            "SPEAKER_AGE_OUT_OF_RANGE",
            "Age must be from 20 to 60 in this project (its speaker ages)",
        )
        assert refused.json()["error"]["details"] == [
            {"field": "age", "min_age": 20, "max_age": 60}
        ]
    assert _error(_new(world, age=121))[1] == "INVALID_SPEAKER_DETAILS"
    assert world["pa"].get(world["base"]).json()["total"] == 0, "nobody is added"

    pid = world["rules"].id
    saved(world["pa"], pid, speaker_min_age=18, speaker_max_age=75)
    young = _new(world, age=19)
    assert young.status_code == 201, young.text
    old = _new(world, age=70)
    assert old.status_code == 201, old.text

    saved(world["pa"], pid, speaker_min_age=20, speaker_max_age=60)
    url = f"{world['base']}/{old.json()['id']}"
    plain = {"display_label": "Old", "language_code": "hi"}
    assert world["pa"].patch(url, json={**plain, "notes": "x"}).status_code == 200
    assert world["pa"].patch(url, json={**plain, "age": 70}).status_code == 200, "unchanged"
    moved = world["pa"].patch(url, json={**plain, "age": 72})
    assert _error(moved)[1] == "SPEAKER_AGE_OUT_OF_RANGE"
    assert world["pa"].get(url).json()["age"] == 70, "nothing saved"
    assert world["pa"].patch(url, json={**plain, "age": 45}).json()["age"] == 45


def test_joining_a_project_follows_its_ages(world: dict[str, Any]) -> None:
    """Adding an existing person, one or many at once, checks the project's ages."""
    pa = world["pa"]
    saved(pa, world["wide"].id, speaker_min_age=1, speaker_max_age=120)
    elder = make_participant(pa, world["wide"].id, "Elder", speaker={"age": 80})
    adult = make_participant(pa, world["wide"].id, "Adult", speaker={"age": 30})
    code = elder["participant_code"]
    offered = pa.get(f"{world['base']}/link-candidates").json()
    assert [c["participant_code"] for c in offered] == [adult["participant_code"]]
    linked = pa.post(f"{world['base']}/link", json={"participant_code": code})
    assert _error(linked) == (
        422,
        "SPEAKER_AGE_OUT_OF_RANGE",
        f"Participant {code} is outside this project's speaker ages (20 to 60).",
    )
    assert linked.json()["error"]["details"] == [
        {"participants": [code], "min_age": 20, "max_age": 60}
    ]
    bulk = pa.post(
        f"{world['wide_base']}/bulk",
        json={
            "action": "assign",
            "participant_ids": [elder["id"], adult["id"]],
            "target_project_id": str(world["rules"].id),
        },
    ).json()
    assert [(r["participant_code"], r["ok"]) for r in bulk["results"]] == [
        (code, False),
        (adult["participant_code"], True),
    ]
    assert bulk["results"][0]["message"].startswith(f"Participant {code} is outside")


def test_the_file_checks_the_project_ages_and_needed_details(world: dict[str, Any]) -> None:
    pa, base = world["pa"], world["base"]
    saved(pa, world["rules"].id, required_speaker_details=["age", "gender"])
    csv = (
        "name,phone,email,language,dialect,district,age,gender\n"
        "Asha,,asha@example.org,hi,,,34,female\n"
        "Gita,,gita@example.org,hi,,,65,female\n"
        "Hema,,hema@example.org,hi,,,34,\n"
    )
    preview = pa.post(f"{base}/import", json={"csv": csv}).json()
    assert [(r["ok"], r["message"]) for r in preview["rows"]] == [
        (True, "Ready to add"),
        (False, "Age must be from 20 to 60 in this project (its speaker ages)"),
        (
            True,
            "Ready to add (speaker details missing: add them with Edit before making tasks)",
        ),
    ]
    done = pa.post(f"{base}/import", json={"csv": csv, "confirm": True}).json()
    assert done["created"] == 2
    listed = {p["display_label"]: p for p in pa.get(base).json()["items"]}
    assert (
        listed["Asha"]["speaker_details_complete"],
        listed["Hema"]["speaker_details_complete"],
    ) == (
        True,
        False,
    )


def test_tasks_follow_the_project_ages_and_needed_details(world: dict[str, Any]) -> None:
    pa, pid = world["pa"], world["rules"].id
    saved(pa, pid, required_speaker_details=["age", "gender"])
    a = make_participant(pa, pid, "A", speaker={"age": 30, "gender": "male"})
    b = make_participant(pa, pid, "B", speaker={"age": 35, "gender": "female"})
    c = make_participant(pa, pid, "C", speaker={"age": 30})
    assert (a["speaker_details_complete"], c["speaker_details_complete"]) == (True, False)

    def task(x: dict[str, Any], y: dict[str, Any]) -> Any:
        return pa.post(
            "/api/v1/tasks",
            json={
                "project_id": str(pid),
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": x["id"],
                "participant_b_id": y["id"],
            },
        )

    assert task(a, b).status_code == 201, "the details this project needs are enough"
    assert _error(task(a, c))[1] == "SPEAKER_DETAILS_MISSING"

    saved(pa, pid, speaker_min_age=40, speaker_max_age=60)
    codes = [a["participant_code"], b["participant_code"]]
    refused = task(a, b)
    assert _error(refused) == (
        422,
        "SPEAKER_AGE_OUT_OF_RANGE",
        f"Participants {codes[0]} and {codes[1]} are outside this project's speaker ages "
        "(40 to 60).",
    )
    assert refused.json()["error"]["details"] == [
        {"participants": codes, "min_age": 40, "max_age": 60}
    ]
    assert _error(task(c, a))[1] == "SPEAKER_DETAILS_MISSING", "details are checked first"
    rows = pa.post(
        "/api/v1/tasks/import",
        json={
            "project_id": str(pid),
            "csv": f"participant_a,participant_b\n{codes[0]},{codes[1]}\n",
        },
    ).json()["rows"]
    assert (rows[0]["ok"], rows[0]["message"]) == (False, refused.json()["error"]["message"])

    # The flag follows the project's list: the same people lack details once all are needed.
    saved(pa, pid, required_speaker_details=list(speakers.FIELDS), speaker_min_age=20)
    listed = {p["display_label"]: p for p in pa.get(world["base"]).json()["items"]}
    assert [listed[n]["speaker_details_complete"] for n in "ABC"] == [False, False, False]
    assert _error(task(a, b))[1] == "SPEAKER_DETAILS_MISSING"
