"""Speaker details on each participant (D-143): what is kept, how each value is checked, who sees
them, the "complete" flag, the file import's columns, and the list of states the form offers.

Requirements: PART-005, PART-008, PART-009, PART-010, PART-012, PART-016
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditLog
from app.modules.participants import speakers
from app.modules.participants.models import EDUCATION_CODES, EDUCATION_MEDIUM_CODES, GENDER_CODES
from tests.conftest import SPEAKER_DETAILS, Api, make_participant, make_project, make_user

pytestmark = pytest.mark.db

FRONTEND_LIST = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "speakers.ts"


@pytest.fixture
def world(db: Any, new_api: Any) -> dict[str, Any]:
    project = make_project(db, "KONKANI")
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
    mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[project])
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[project])
    apis = {}
    for name in ("pa", "mod", "qc", "cv"):
        apis[name] = new_api()
        assert apis[name].login(f"{name}@example.org").status_code == 200
    base = f"/api/v1/projects/{project.id}/participants"
    return {"db": db, "project": project, "mod_user": mod, "base": base, **apis}


def _new(world: dict[str, Any], **details: Any) -> Any:
    body = {"display_label": "Sneha", "language_code": "hi", "email": "sneha@example.org"}
    return world["pa"].post(world["base"], json={**body, **details})


def test_details_are_kept_and_make_the_participant_complete(world: dict[str, Any]) -> None:
    made = _new(world, **SPEAKER_DETAILS)
    assert made.status_code == 201, made.text
    body = made.json()
    assert {name: body[name] for name in SPEAKER_DETAILS} == SPEAKER_DETAILS
    assert body["speaker_details_complete"] is True
    listed = world["pa"].get(world["base"]).json()["items"]
    assert [p["speaker_details_complete"] for p in listed] == [True]


@pytest.mark.parametrize(
    ("field", "value", "words"),
    [
        ("age", 19, "Age must be a whole number from 20 to 60"),
        ("age", 61, "Age must be a whole number from 20 to 60"),
        ("gender", "OTHER", "Gender must be one of: MALE, FEMALE"),
        ("current_state", "Goa State", "Current state must be a state or union territory"),
        ("native_state", "Ceylon", "Native state must be a state or union territory"),
        ("current_pincode", "012345", "Current PIN code must be 6 digits and cannot start with 0"),
        ("native_pincode", "40300", "Native PIN code must be 6 digits"),
        ("recording_pincode", "4030011", "Recording PIN code must be 6 digits"),
        ("recording_pincode", "40300A", "Recording PIN code must be 6 digits"),
        ("education", "SCHOOL", "Education must be one of: PRIMARY, SECONDARY"),
        ("education_medium", "HINDI", "Medium of education must be one of: ENGLISH, NON_ENGLISH"),
    ],
)
def test_a_wrong_value_is_refused_in_words(
    world: dict[str, Any], field: str, value: Any, words: str
) -> None:
    refused = _new(world, **{**SPEAKER_DETAILS, field: value})
    assert refused.status_code == 422
    error = refused.json()["error"]
    assert error["code"] == "INVALID_SPEAKER_DETAILS"
    assert error["message"].startswith(words), error["message"]
    assert error["details"] == [{"field": field}]
    assert world["pa"].get(world["base"]).json()["total"] == 0, "nobody is added"


def test_values_are_kept_in_one_form(world: dict[str, Any]) -> None:
    """The bounds are allowed; states, codes and PIN codes are kept as the list writes them."""
    made = _new(
        world,
        **{
            **SPEAKER_DETAILS,
            "age": 20,
            "gender": "male",
            "current_state": "  tamil   nadu ",
            "native_state": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
            "current_pincode": "600 001",
            "education": "higher secondary",
            "education_medium": "non-english",
            "native_language": " Konkani ",
            "district": " Bardez ",
        },
    ).json()
    assert (made["age"], made["gender"]) == (20, "MALE")
    assert made["current_state"] == "Tamil Nadu"
    assert made["native_state"] == "Dadra and Nagar Haveli and Daman and Diu"
    assert made["current_pincode"] == "600001"
    assert (made["education"], made["education_medium"]) == ("HIGHER_SECONDARY", "NON_ENGLISH")
    assert (made["native_language"], made["district"]) == ("Konkani", "Bardez")
    older = world["pa"].post(
        world["base"],
        json={
            "display_label": "Old",
            "language_code": "hi",
            "email": "old@example.org",
            **{**SPEAKER_DETAILS, "age": 60},
        },
    )
    assert older.json()["age"] == 60
    long = _new(world, **{**SPEAKER_DETAILS, "native_language": "k" * 51})
    assert long.json()["error"]["code"] == "VALIDATION_ERROR"


def test_someone_saved_before_has_none_and_a_correction_keeps_what_it_leaves_out(
    world: dict[str, Any],
) -> None:
    pa, base = world["pa"], world["base"]
    old = make_participant(pa, world["project"].id, "Old", speaker={})
    assert old["speaker_details_complete"] is False
    assert (old["age"], old["district"], old["native_state"]) == (None, "", None)
    url = f"{base}/{old['id']}"
    plain = {"display_label": "Old", "language_code": "hi"}
    assert pa.patch(url, json=plain).json()["speaker_details_complete"] is False
    some = pa.patch(url, json={**plain, "age": 45, "native_state": "goa"}).json()
    assert (some["age"], some["native_state"], some["speaker_details_complete"]) == (
        45,
        "Goa",
        False,
    )
    kept = pa.patch(url, json={**plain, "notes": "Called back"}).json()
    assert (kept["age"], kept["native_state"]) == (45, "Goa"), "left out = kept"
    full = pa.patch(url, json={**plain, **SPEAKER_DETAILS}).json()
    assert full["speaker_details_complete"] is True
    cleared = pa.patch(url, json={**plain, "age": None, "district": ""}).json()
    assert (cleared["age"], cleared["district"], cleared["speaker_details_complete"]) == (
        None,
        "",
        False,
    )
    entry = (
        world["db"]
        .scalars(
            select(AuditLog)
            .where(AuditLog.action == "participant.corrected")
            .order_by(AuditLog.created_at.desc())
        )
        .first()
    )
    assert '"speaker_details_changed": ["age", "district"]' in (entry.after_summary or "")
    assert "North Goa" not in (entry.after_summary or ""), "names of fields, not values"


def test_speaker_details_are_seen_like_the_name(world: dict[str, Any]) -> None:
    """Managers and the moderator of an open task with the person see them; QC, client viewers
    and other moderators see that they are complete, and the native district, as before."""
    pid = world["project"].id
    a = make_participant(world["pa"], pid, "Asha")
    b = make_participant(world["pa"], pid, "Bina")

    def seen(api: Api) -> dict[str, Any]:
        response = api.get(f"{world['base']}/{a['id']}")
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    for name in ("qc", "cv", "mod"):
        view = seen(world[name])
        assert all(view[f] is None for f in speakers.FIELDS if f != "district"), name
        assert (view["speaker_details_complete"], view["district"]) == (True, "North Goa")
    assert seen(world["pa"])["native_pincode"] == "403601"
    task = world["pa"].post(
        "/api/v1/tasks",
        json={
            "project_id": str(pid),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": a["id"],
            "participant_b_id": b["id"],
            "moderator_id": str(world["mod_user"].id),
        },
    )
    assert task.status_code == 201, task.text
    assigned = seen(world["mod"])
    assert (assigned["age"], assigned["recording_district"]) == (34, "North Goa")


def test_removing_a_participant_removes_the_details(world: dict[str, Any]) -> None:
    person = make_participant(world["pa"], world["project"].id, "Gone")
    removed = world["pa"].post(
        f"{world['base']}/{person['id']}/delete", json={"reason": "Asked to be removed"}
    )
    assert removed.status_code == 200, removed.text
    gone = removed.json()
    assert all(gone[f] in (None, "") for f in speakers.FIELDS)
    assert gone["speaker_details_complete"] is False


def test_the_file_takes_the_details_and_checks_them_as_the_form(world: dict[str, Any]) -> None:
    pa, base = world["pa"], world["base"]
    columns = ",".join(f for f in speakers.FIELDS if f != "district")
    full = ",".join(str(SPEAKER_DETAILS[f]) for f in speakers.FIELDS if f != "district")
    bad = full.replace("403601", "003601")
    csv = (
        f"name,phone,email,language,dialect,district,{columns}\n"
        f"Kavya,,kavya@example.org,hi,,Salcete,{full}\n"
        f"Lata,,lata@example.org,hi,,Salcete,{bad}\n"
        f"Meera,,meera@example.org,hi,,,{',' * (len(speakers.FIELDS) - 2)}\n"
    )
    preview = pa.post(f"{base}/import", json={"csv": csv}).json()
    rows = [(r["ok"], r["message"]) for r in preview["rows"]]
    assert rows == [
        (True, "Ready to add"),
        (False, "Native PIN code must be 6 digits and cannot start with 0"),
        (
            True,
            "Ready to add (speaker details missing: add them with Edit before making tasks)",
        ),
    ]
    done = pa.post(f"{base}/import", json={"csv": csv, "confirm": True}).json()
    assert done["created"] == 2
    listed = {p["display_label"]: p for p in pa.get(base).json()["items"]}
    kavya = listed["Kavya"]
    assert kavya["speaker_details_complete"] is True
    assert (kavya["district"], kavya["native_pincode"], kavya["age"]) == ("Salcete", "403601", 34)
    assert listed["Meera"]["speaker_details_complete"] is False
    # The old six columns still work: the details are simply missing.
    short = "name,phone,email,language,dialect,district\nNila,,nila@example.org,hi,,Pune\n"
    assert pa.post(f"{base}/import", json={"csv": short}).json()["rows"][0]["ok"] is True
    header = pa.post(f"{base}/import", json={"csv": "label\nx\n"}).json()["error"]["message"]
    assert header.endswith(f"name,phone,email,language,dialect,district,{columns}")


def test_the_form_offers_the_same_lists_the_server_checks() -> None:
    """frontend/src/lib/speakers.ts writes the states and codes once for the form; they must be
    the ones the server accepts."""
    source = FRONTEND_LIST.read_text(encoding="utf-8")

    def listed(name: str) -> list[str]:
        block = re.search(rf"export const {name}\b[^=]*= \[(.*?)\]", source, re.S)
        assert block, f"{name} not found in {FRONTEND_LIST.name}"
        return re.findall(r'"([^"]+)"', block.group(1))

    def labelled(name: str) -> list[str]:
        block = re.search(rf"export const {name}\b[^=]*= \{{(.*?)\}}", source, re.S)
        assert block, f"{name} not found in {FRONTEND_LIST.name}"
        return re.findall(r"^\s*([A-Z_]+):", block.group(1), re.M)

    assert listed("INDIAN_STATES") == list(speakers.INDIAN_STATES)
    assert len(speakers.INDIAN_STATES) == 36
    assert labelled("GENDER_LABELS") == list(GENDER_CODES)
    assert labelled("EDUCATION_LABELS") == list(EDUCATION_CODES)
    assert labelled("EDUCATION_MEDIUM_LABELS") == list(EDUCATION_MEDIUM_CODES)
