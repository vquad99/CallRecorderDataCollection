"""Device details per speaker and the moderator's reminders (D-147): which details a project asks
and its reminders as project settings with the first client's as defaults, the moderator filling
both people's details (and "Same as last time"), Send to QC waiting for the asked ones, read only
from QC on, who may read and change them, and the reminders served with the task.

Requirements: TASK-002, TASK-004, TASK-005, PROJ-001, PROJ-011, FTF-006, FTF-014, TEL-036
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text

from app.modules.audit.models import AuditLog
from app.modules.projects import moderation
from tests import test_audio_qc, test_recordings
from tests.conftest import Api, make_participant, make_user, set_status

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world
audio_rule = test_audio_qc.audio_rule

FRONTEND_REMINDERS = (
    Path(__file__).resolve().parents[2] / "frontend/src/features/projects/reminders.ts"
)
ALL = list(moderation.DEVICE_FIELDS)
PHONE = {
    "device_make": "Samsung",
    "device_model": "Galaxy A14",
    "bluetooth_earphones": False,
    "wired_earphones": True,
    "loudspeaker_on": False,
}


def _ask(world: dict[str, Any], fields: list[str]) -> None:
    world["project"].device_fields = fields
    world["db"].commit()


def _body(a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"participants": [{"side": "A", **(a or {})}, {"side": "B", **(b or {})}]}


def _put(api: Api, tid: str, body: dict[str, Any]) -> Any:
    return api.put(f"/api/v1/tasks/{tid}/device-details", json=body)


def _get(api: Api, tid: str) -> dict[str, Any]:
    response = api.get(f"/api/v1/tasks/{tid}/device-details")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _error(response: Any) -> str:
    code: str = response.json()["error"]["code"]
    return code


def _audits(db: Any, action: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


def _send(api: Api, tid: str) -> Any:
    return api.post(f"/api/v1/tasks/{tid}/transition", json={"to": "AUDIO_QC"})


def _patch(api: Api, pid: Any, **changes: Any) -> Any:
    """The project's PATCH with its Overview and speaker fields as they are, and `changes`; the
    D-146/D-147 settings left out unless given."""
    current = api.get(f"/api/v1/projects/{pid}").json()
    kept = {
        k: v
        for k, v in current.items()
        if k
        in {
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
        }
    }
    return api.patch(f"/api/v1/projects/{pid}", json={**kept, **changes})


# ------------------------------------------------------------------------ the project settings


def test_a_project_starts_with_the_clients_device_details_and_reminders(
    world: dict[str, Any],
) -> None:
    db = world["db"]
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    root = world["api"]("root@example.org")
    made = root.post(
        "/api/v1/projects",
        json={"name": "Konkani", "allows_telephony": True, "allows_face_to_face": True},
    )
    assert made.status_code == 201, made.text
    project = made.json()
    assert project["device_fields"] == ALL
    assert project["recording_reminders"] == moderation.DEFAULT_RECORDING_REMINDERS
    reminders = project["recording_reminders"]
    assert "agriculture" in reminders["topics"]
    assert "politics" in reminders["avoid"]
    assert any("2.5 feet" in line for line in reminders["face_to_face"])
    assert any("loudspeaker off" in line for line in reminders["telephony"])

    pid = project["id"]
    mine = {
        "speaker_id": False,
        "topics": ["  cricket  ", "", "monsoon   farming"],
        "avoid": ["politics"],
        "face_to_face": [],
        "telephony": ["Use a headset"],
    }
    saved = _patch(
        root, pid, device_fields=["loudspeaker_on", "device_make"], recording_reminders=mine
    )
    assert saved.status_code == 200, saved.text
    # The form's order, each once; spaces tidied and empty lines dropped.
    assert saved.json()["device_fields"] == ["device_make", "loudspeaker_on"]
    assert saved.json()["recording_reminders"] == {
        "speaker_id": False,
        "topics": ["cricket", "monsoon farming"],
        "avoid": ["politics"],
        "face_to_face": [],
        "telephony": ["Use a headset"],
    }
    [entry] = [e for e in _audits(db, "project.updated") if e.entity_id == pid]
    assert "monsoon farming" in (entry.after_summary or "")
    assert "loudspeaker_on" in (entry.after_summary or "")

    # Left out, both stay as they are; a change of something else does not repeat the reminders.
    kept = _patch(root, pid, description="Konkani talk")
    assert kept.json()["device_fields"] == ["device_make", "loudspeaker_on"]
    assert kept.json()["recording_reminders"]["topics"] == ["cricket", "monsoon farming"]
    last = [e for e in _audits(db, "project.updated") if e.entity_id == pid][-1]
    assert "recording_reminders" not in (last.after_summary or "")
    assert "device_fields" in (last.after_summary or "")
    # None asked: allowed (the project asks no device details).
    assert _patch(root, pid, device_fields=[]).json()["device_fields"] == []


def test_the_settings_are_checked_when_saved(world: dict[str, Any]) -> None:
    pa, pid = world["pa"], world["project"].id
    unknown = _patch(pa, pid, device_fields=["device_make", "battery_level"])
    assert unknown.status_code == 422
    assert _error(unknown) == "UNKNOWN_DEVICE_FIELD"
    assert "battery_level" in unknown.json()["error"]["message"]
    too_many = _patch(pa, pid, recording_reminders={"topics": [f"topic {i}" for i in range(21)]})
    assert too_many.status_code == 422
    assert _error(too_many) == "INVALID_REMINDERS"
    assert "Talk about: at most 20 lines" in too_many.json()["error"]["message"]
    too_long = _patch(pa, pid, recording_reminders={"avoid": ["ok", "x" * 201]})
    assert _error(too_long) == "INVALID_REMINDERS"
    assert too_long.json()["error"]["message"] == "Avoid, line 2: at most 200 characters"
    assert too_long.json()["error"]["details"] == [
        {"field": "recording_reminders", "list": "avoid", "line": 2}
    ]
    # Nothing was saved.
    assert pa.get(f"/api/v1/projects/{pid}").json()["recording_reminders"]["avoid"] == list(
        moderation.DEFAULT_RECORDING_REMINDERS["avoid"]
    )


def test_the_frontend_copy_of_the_clients_reminders_matches() -> None:
    """ "Reset to the client's text" on the Rules tab puts back the same lines as the server."""
    source = FRONTEND_REMINDERS.read_text(encoding="utf-8")
    block = source.split("CLIENT_REMINDERS", 1)[1]
    for name in moderation.REMINDER_LISTS:
        found = re.search(rf"\b{name}: \[(.*?)\]", block, re.S)
        assert found, name
        lines = re.findall(r'"((?:[^"\\]|\\.)*)"', found.group(1))
        assert lines == moderation.DEFAULT_RECORDING_REMINDERS[name], name
    assert re.search(r"speaker_id: true", block)


# ------------------------------------------------------------------------ filling them


def test_the_moderator_fills_both_people_and_send_to_qc_waits_for_them(
    world: dict[str, Any],
) -> None:
    _ask(world, ALL)
    db, mod, pa = world["db"], world["mod"], world["pa"]
    tid = world["task"]["id"]
    task = mod.get(f"/api/v1/tasks/{tid}").json()
    a, b = task["participant_a"]["participant_code"], task["participant_b"]["participant_code"]
    # The task says what is asked and who still needs it.
    assert task["device_fields"] == ALL
    assert task["device_details_missing"] == [a, b]
    view = _get(mod, tid)
    assert view["editable"] is True
    assert view["call_type"] == "Face-to-face"
    assert view["complete"] is False
    assert [p["side"] for p in view["participants"]] == ["A", "B"]
    assert view["participants"][0]["missing"] == ALL
    assert view["participants"][0]["last_time"] is None

    test_audio_qc._record(world, send=False)
    blocked = _send(mod, tid)
    assert blocked.status_code == 422
    assert _error(blocked) == "DEVICE_DETAILS_MISSING"
    assert blocked.json()["error"]["message"] == (
        "Fill in the device details before sending the task to QC. Missing: "
        f"{a} (Device make, Device model, Bluetooth earphones used, Wired earphones used, "
        f"Loudspeaker on); {b} (Device make, Device model, Bluetooth earphones used, "
        "Wired earphones used, Loudspeaker on)."
    )

    # A first; spaces tidied; B half done.
    saved = _put(
        mod, tid, _body({**PHONE, "device_make": "  Samsung   "}, {"device_make": "Nokia"})
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["participants"][0]["details"] == PHONE
    assert body["participants"][0]["missing"] == []
    assert body["participants"][0]["filled_by"] == "mod"
    assert body["participants"][1]["missing"] == ALL[1:]
    assert mod.get(f"/api/v1/tasks/{tid}").json()["device_details_missing"] == [b]
    still = _send(mod, tid)
    assert _error(still) == "DEVICE_DETAILS_MISSING"
    assert still.json()["error"]["details"] == [{"participants": {b: ALL[1:]}}]

    # The project admin may fill too; an empty text is no answer.
    done = _put(pa, tid, _body(PHONE, {**PHONE, "device_model": "  "}))
    assert done.json()["participants"][1]["missing"] == ["device_model"]
    done = _put(pa, tid, _body(PHONE, {**PHONE, "loudspeaker_on": True}))
    assert done.json()["complete"] is True
    assert done.json()["participants"][1]["filled_by"] == "pa"
    changes = _audits(db, "task.device_details_changed")
    assert len(changes) == 3
    assert '"Galaxy A14"' in (changes[0].after_summary or "")
    assert "loudspeaker_on" in (changes[-1].before_summary or "")
    # Saving the same again changes nothing and is not audited.
    assert _put(pa, tid, _body(PHONE, {**PHONE, "loudspeaker_on": True})).status_code == 200
    assert len(_audits(db, "task.device_details_changed")) == 3

    sent = _send(mod, tid)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "AUDIO_QC"
    assert sent.json()["device_details_missing"] == []

    # From QC on: read only, for the moderator and the admin too.
    after = _get(mod, tid)
    assert after["editable"] is False
    assert after["participants"][1]["details"]["loudspeaker_on"] is True
    locked = _put(mod, tid, _body(PHONE, PHONE))
    assert locked.status_code == 409
    assert _error(locked) == "DEVICE_DETAILS_LOCKED"
    assert _error(_put(pa, tid, _body(PHONE, PHONE))) == "DEVICE_DETAILS_LOCKED"
    # The QC Executive given the task reads them.
    qc = world["api"]("qc@example.org")
    seen = _get(qc, tid)
    assert seen["participants"][0]["details"] == PHONE
    assert seen["editable"] is False
    assert _put(qc, tid, _body(PHONE, PHONE)).status_code == 403


def test_only_the_asked_details_are_needed(world: dict[str, Any]) -> None:
    _ask(world, ["device_make", "loudspeaker_on"])
    mod, tid = world["mod"], world["task"]["id"]
    set_status(world["db"], tid, "RECORDED")
    half = {"device_make": "Apple", "loudspeaker_on": False}
    assert _get(mod, tid)["fields"] == ["device_make", "loudspeaker_on"]
    assert _put(mod, tid, _body(half, {"device_make": "Apple"})).status_code == 200
    blocked = _send(mod, tid)
    assert blocked.json()["error"]["details"] == [
        {
            "participants": {
                _get(mod, tid)["participants"][1]["participant_code"]: ["loudspeaker_on"]
            }
        }
    ]
    assert _put(mod, tid, _body(half, half)).json()["complete"] is True
    # Past the device details: the next check is the automatic sound check (no recording here).
    assert _error(_send(mod, tid)) == "CHECK_PENDING"
    # A project that asks none never holds a task for them.
    _ask(world, [])
    assert mod.get(f"/api/v1/tasks/{tid}").json()["device_details_missing"] == []
    assert _error(_send(mod, tid)) == "CHECK_PENDING"


def test_the_details_are_checked(world: dict[str, Any]) -> None:
    _ask(world, ALL)
    mod, tid = world["mod"], world["task"]["id"]
    too_long = _put(mod, tid, _body({"device_make": "x" * 61}))
    assert too_long.status_code == 422
    assert _put(mod, tid, _body({"device_make": "x" * 60})).status_code == 200
    one_side = _put(mod, tid, {"participants": [{"side": "A", **PHONE}]})
    assert one_side.status_code == 422
    assert _error(one_side) == "INVALID_DEVICE_DETAILS"
    twice = _put(mod, tid, {"participants": [{"side": "A"}, {"side": "A"}]})
    assert _error(twice) == "INVALID_DEVICE_DETAILS"
    assert _put(mod, tid, _body({"loudspeaker_on": "maybe"})).status_code == 422
    assert _put(mod, tid, {"participants": [{"side": "C"}, {"side": "A"}]}).status_code == 422


def test_who_may_read_and_fill_the_details(world: dict[str, Any]) -> None:
    _ask(world, ALL)
    db, project, tid = world["db"], world["project"], world["task"]["id"]
    make_user(db, "client@example.org", ["CLIENT_VIEWER"], projects=[project])
    other = world["api"]("mod2@example.org")
    qc = world["api"]("qc@example.org")
    client = world["api"]("client@example.org")
    # Another moderator, and a QC Executive not given the task, do not see it at all.
    for outsider in (other, qc):
        assert outsider.get(f"/api/v1/tasks/{tid}/device-details").status_code == 404
        assert _put(outsider, tid, _body(PHONE, PHONE)).status_code == 404
    # A client viewer does not see tasks.
    assert client.get(f"/api/v1/tasks/{tid}/device-details").status_code == 403
    assert _put(client, tid, _body(PHONE, PHONE)).status_code == 403
    # Before the session starts the details wait.
    set_status(db, tid, "ASSIGNED")
    assert _get(world["mod"], tid)["editable"] is False
    assert _error(_put(world["mod"], tid, _body(PHONE, PHONE))) == "DEVICE_DETAILS_LOCKED"
    set_status(db, tid, "IN_PROGRESS")
    assert _get(world["pa"], tid)["editable"] is True
    assert _put(world["mod"], tid, _body(PHONE, PHONE)).status_code == 200


def test_same_as_last_time_is_offered_never_filled_in(world: dict[str, Any]) -> None:
    _ask(world, ALL)
    db, pa, mod = world["db"], world["pa"], world["mod"]
    first = world["task"]["id"]
    assert _put(mod, first, _body(PHONE, {**PHONE, "device_make": "Nokia"})).status_code == 200
    old = pa.get(f"/api/v1/tasks/{first}").json()
    a = old["participant_a"]["id"]
    c = make_participant(pa, world["project"].id, "Chitra")
    second = pa.post(
        "/api/v1/tasks",
        json={
            "project_id": str(world["project"].id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": c["id"],
            "participant_b_id": a,
        },
    ).json()
    mod_id = mod.get("/api/v1/auth/me").json()["id"]
    pa.post(f"/api/v1/tasks/{second['id']}/assign", json={"user_id": mod_id})
    mod.post(f"/api/v1/tasks/{second['id']}/transition", json={"to": "IN_PROGRESS"})
    view = _get(mod, second["id"])
    new_person, known = view["participants"]
    assert new_person["last_time"] is None
    assert known["details"]["device_make"] is None, "nothing filled in by itself"
    assert known["missing"] == ALL
    last = known["last_time"]
    assert last["task_code"] == old["task_code"]
    assert {k: last[k] for k in PHONE} == PHONE
    assert last["filled_at"]
    # The newest wins.
    _put(mod, first, _body({**PHONE, "device_model": "Galaxy S24"}, PHONE))
    assert _get(mod, second["id"])["participants"][1]["last_time"]["device_model"] == "Galaxy S24"
    # Offered only to whoever may fill them.
    set_status(db, second["id"], "AUDIO_QC")
    assert _get(mod, second["id"])["participants"][1]["last_time"] is None


# ------------------------------------------------------------------------ the reminders


def test_the_task_carries_the_reminders_for_its_mode(world: dict[str, Any]) -> None:
    pa, mod, pid, tid = world["pa"], world["mod"], world["project"].id, world["task"]["id"]
    task = mod.get(f"/api/v1/tasks/{tid}").json()
    default = moderation.DEFAULT_RECORDING_REMINDERS
    assert task["reminders"] == {
        "speaker_id": True,
        "topics": default["topics"],
        "avoid": default["avoid"],
        "tips": default["face_to_face"],
    }
    mine = {"speaker_id": False, "topics": ["cricket"], "avoid": [], "telephony": ["Headset"]}
    assert _patch(pa, pid, recording_reminders=mine).status_code == 200
    again = mod.get(f"/api/v1/tasks/{tid}").json()["reminders"]
    assert again == {"speaker_id": False, "topics": ["cricket"], "avoid": [], "tips": []}
    set_status(world["db"], tid, "IN_PROGRESS")
    world["db"].execute(
        text("UPDATE tasks SET recording_mode = 'TELEPHONY' WHERE id = :t"), {"t": tid}
    )
    world["db"].commit()
    assert mod.get(f"/api/v1/tasks/{tid}").json()["reminders"]["tips"] == ["Headset"]
