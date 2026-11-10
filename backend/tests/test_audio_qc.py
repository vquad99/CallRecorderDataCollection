"""Audio QC end to end: the automatic check after recording, the QC Executive's decision, duplicate
detection across a project, a re-check from storage, recovery, and the details file (D-079).

Requirements: AQC-001, AQC-002, AQC-006, AQC-007, AQC-008, AQC-009, TASK-002, TASK-004, PROJ-007
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select, update

from app.modules.audio_qc import service as audio_qc
from app.modules.audio_qc.models import AudioQcResult
from app.modules.audit.models import AuditLog
from app.modules.projects.models import ProjectAudioRule
from app.modules.recordings import worker_dispatch
from app.modules.recordings.models import AudioAsset
from tests import test_recordings
from tests.conftest import Api, make_user
from tests.test_recordings import BUCKET, chunks

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world


@pytest.fixture(autouse=True)
def audio_rule(world: dict[str, Any]) -> None:
    """The project's face-to-face rule, as a project made through the API gets it (PROJ-007)."""
    db = world["db"]
    db.add(
        ProjectAudioRule(
            project_id=world["project"].id,
            mode="FACE_TO_FACE",
            sample_rate=16000,
            bit_depth=16,
            channels=1,
            max_silence_pct=25,
            max_clipping_pct=None,
            min_duration_seconds=0,
            max_duration_seconds=None,
        )
    )
    db.commit()


def _record(world: dict[str, Any], seconds: int = 6, task_id: str | None = None) -> str:
    mod: Api = world["mod"]
    tid = task_id or world["task"]["id"]
    rid: str = mod.post(f"/api/v1/tasks/{tid}/recordings", json=test_recordings.START).json()["id"]
    parts = chunks(seconds, 0)
    for seq, data in enumerate(parts):
        assert test_recordings.put(mod, rid, seq, data).status_code == 200
    done = mod.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": len(parts)})
    assert done.status_code == 200, done.text
    return rid


def _second_task(world: dict[str, Any], moderator_email: str = "mod@example.org") -> str:
    pa: Api = world["pa"]
    first = pa.get(f"/api/v1/tasks/{world['task']['id']}").json()
    task = pa.post(
        "/api/v1/tasks",
        json={
            "project_id": str(world["project"].id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": first["participant_a"]["id"],
            "participant_b_id": first["participant_b"]["id"],
        },
    ).json()
    user_id = world["api"](moderator_email).get("/api/v1/auth/me").json()["id"]
    assert (
        pa.post(f"/api/v1/tasks/{task['id']}/assign", json={"user_id": user_id}).status_code == 200
    )
    return str(task["id"])


def _qc(world: dict[str, Any]) -> tuple[Api, str]:
    qc = world["api"]("qc@example.org")
    return qc, qc.get("/api/v1/auth/me").json()["id"]


def _assign_qc(world: dict[str, Any]) -> Api:
    qc, qc_id = _qc(world)
    tid = world["task"]["id"]
    assigned = world["pa"].post(f"/api/v1/tasks/{tid}/assign-qc", json={"user_id": qc_id})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["qc_name"] == "qc"
    return qc


def test_a_finished_recording_is_checked_and_waits_for_a_decision(world: dict[str, Any]) -> None:
    _record(world)
    tid = world["task"]["id"]
    pa: Api = world["pa"]
    assert pa.get(f"/api/v1/tasks/{tid}").json()["status"] == "AUDIO_QC"
    view = pa.get(f"/api/v1/tasks/{tid}/audio-qc").json()
    assert view["can_assign"] is True
    assert view["can_decide"] is False, "a Project Admin reads QC but does not decide (matrix O(R))"
    [auto] = view["results"]
    assert (auto["automated"], auto["outcome"], auto["reason_code"]) == (True, "PASS", None)
    codes = [c["code"] for c in auto["checks"]]
    for code in (
        "DECODES",
        "CHECKSUM",
        "FORMAT",
        "FILE_SIZE",
        "SAMPLE_RATE",
        "BIT_DEPTH",
        "CHANNELS",
        "DURATION",
        "SILENCE",
        "CLIPPING",
        "LEVELS",
        "DYNAMIC_RANGE",
        "SNR",
        "CHANNEL_LEAKAGE",
        "DUPLICATE",
    ):
        assert code in codes
    assert auto["duration_ms"] == 6000
    assert auto["dynamic_range_db"] is not None
    assert view["reasons"]["FAIL"] == [
        "AUDIO_QUALITY",
        "CONSENT_PROBLEM",
        "OTHER",
        "WRONG_SPEAKERS",
    ]
    body = pa.get("/api/v1/dashboard").json()
    assert (body["qc"]["auto_pass"], body["qc"]["auto_review"], body["qc"]["auto_fail"]) == (
        1,
        0,
        0,
    )


def test_the_assigned_qc_executive_passes_it_and_the_task_is_approved(
    world: dict[str, Any],
) -> None:
    _record(world)
    tid = world["task"]["id"]
    qc = _assign_qc(world)
    view = qc.get(f"/api/v1/tasks/{tid}/audio-qc").json()
    assert view["can_decide"] is True
    decided = qc.post(f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"})
    assert decided.status_code == 200, decided.text
    latest = decided.json()["results"][0]
    assert (latest["automated"], latest["outcome"], latest["reviewer_name"]) == (
        False,
        "PASS",
        "qc",
    )
    assert world["pa"].get(f"/api/v1/tasks/{tid}").json()["status"] == "APPROVED"
    db = world["db"]
    stored = db.scalar(select(AudioQcResult).where(AudioQcResult.automated.is_(False)))
    assert stored.reviewer_id is not None
    assert stored.created_at is not None
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "audio_qc.decision"))
    again = qc.post(f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"})
    assert again.json()["error"]["code"] == "TASK_NOT_IN_QC"


def test_only_the_assigned_qc_executive_decides(world: dict[str, Any]) -> None:
    db = world["db"]
    make_user(db, "qc2@example.org", ["QC_EXECUTIVE"], projects=[world["project"]])
    db.commit()
    _record(world)
    tid = world["task"]["id"]
    qc, _ = _qc(world)
    before = qc.post(f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"})
    assert before.status_code in (403, 404), "not assigned yet: not theirs"
    _assign_qc(world)
    other = world["api"]("qc2@example.org")
    assert other.post(
        f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"}
    ).status_code in (403, 404)
    assert (
        world["pa"]
        .post(f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"})
        .status_code
        == 403
    )
    assert (
        world["mod"]
        .post(f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"})
        .status_code
        == 403
    )


def test_failing_needs_a_reason_from_the_list(world: dict[str, Any]) -> None:
    _record(world)
    tid = world["task"]["id"]
    qc = _assign_qc(world)
    url = f"/api/v1/tasks/{tid}/audio-qc/decision"
    assert qc.post(url, json={"outcome": "FAIL"}).json()["error"]["code"] == "REASON_REQUIRED"
    other = qc.post(url, json={"outcome": "FAIL", "reason_code": "OTHER"})
    assert other.json()["error"]["code"] == "COMMENT_REQUIRED"
    failed = qc.post(
        url, json={"outcome": "FAIL", "reason_code": "AUDIO_QUALITY", "comment": "Hum"}
    )
    assert failed.status_code == 200, failed.text
    task = world["pa"].get(f"/api/v1/tasks/{tid}").json()
    assert (task["status"], task["reason_code"]) == ("REJECTED", "AUDIO_QUALITY")


def test_returning_asks_for_a_new_recording(world: dict[str, Any]) -> None:
    _record(world)
    tid = world["task"]["id"]
    qc = _assign_qc(world)
    returned = qc.post(
        f"/api/v1/tasks/{tid}/audio-qc/decision",
        json={"outcome": "RETURN", "reason_code": "RE_RECORD", "comment": "Too much traffic"},
    )
    assert returned.status_code == 200, returned.text
    assert world["pa"].get(f"/api/v1/tasks/{tid}").json()["status"] == "RETURNED"


def test_passing_a_failed_automatic_check_needs_a_comment(world: dict[str, Any]) -> None:
    db = world["db"]
    db.execute(
        update(ProjectAudioRule)
        .where(ProjectAudioRule.project_id == world["project"].id)
        .values(min_duration_seconds=10)
    )
    db.commit()
    _record(world, seconds=3)
    tid = world["task"]["id"]
    qc = _assign_qc(world)
    auto = qc.get(f"/api/v1/tasks/{tid}/audio-qc").json()["results"][0]
    assert (auto["outcome"], auto["reason_code"]) == ("FAIL", "TOO_SHORT")
    url = f"/api/v1/tasks/{tid}/audio-qc/decision"
    assert qc.post(url, json={"outcome": "PASS"}).json()["error"]["code"] == "COMMENT_REQUIRED"
    ok = qc.post(url, json={"outcome": "PASS", "comment": "Client accepts short greetings"})
    assert ok.status_code == 200, ok.text


def test_the_same_recording_twice_in_a_project_is_caught(world: dict[str, Any]) -> None:
    first = _record(world)
    second_task = _second_task(world)
    mod: Api = world["mod"]
    assert (
        mod.post(f"/api/v1/tasks/{second_task}/transition", json={"to": "IN_PROGRESS"}).status_code
        == 200
    )
    _record(world, task_id=second_task)
    auto = world["pa"].get(f"/api/v1/tasks/{second_task}/audio-qc").json()["results"][0]
    assert (auto["outcome"], auto["reason_code"]) == ("FAIL", "DUPLICATE")
    assert auto["duplicate_of_recording_id"] == first


def test_assigning_qc_checks_the_person(world: dict[str, Any]) -> None:
    db = world["db"]
    make_user(db, "outsider.qc@example.org", ["QC_EXECUTIVE"])
    make_user(db, "both@example.org", ["MODERATOR", "QC_EXECUTIVE"], projects=[world["project"]])
    make_user(db, "qc2@example.org", ["QC_EXECUTIVE"], projects=[world["project"]])
    db.commit()
    pa: Api = world["pa"]
    tid = world["task"]["id"]
    url = f"/api/v1/tasks/{tid}/assign-qc"

    def user_id(email: str) -> str:
        return str(world["api"](email).get("/api/v1/auth/me").json()["id"])

    assert pa.post(url, json={"user_id": user_id("mod@example.org")}).json()["error"]["code"] == (
        "NOT_A_QC_EXECUTIVE"
    )
    assert (
        pa.post(url, json={"user_id": user_id("outsider.qc@example.org")}).json()["error"]["code"]
        == "NOT_PROJECT_MEMBER"
    )
    _assign_qc(world)
    swap = pa.post(url, json={"user_id": user_id("qc2@example.org")})
    assert swap.json()["error"]["code"] == "REASON_REQUIRED"
    assert (
        pa.post(url, json={"user_id": user_id("qc2@example.org"), "reason": "Leave"}).status_code
        == 200
    )
    # The person who records a session never checks it.
    own = _second_task(world, "both@example.org")
    same = pa.post(f"/api/v1/tasks/{own}/assign-qc", json={"user_id": user_id("both@example.org")})
    assert same.json()["error"]["code"] == "SAME_PERSON"
    assert world["mod"].post(url, json={"user_id": user_id("qc@example.org")}).status_code == 403


def test_a_recheck_reads_the_stored_file_and_catches_damage(world: dict[str, Any], s3: Any) -> None:
    rid = _record(world)
    tid = world["task"]["id"]
    qc = _assign_qc(world)
    url = f"/api/v1/tasks/{tid}/audio-qc/recheck"
    fresh = qc.post(url)
    assert fresh.status_code == 200, fresh.text
    latest = fresh.json()["results"][0]
    assert (latest["automated"], latest["outcome"], latest["reviewer_name"]) == (True, "PASS", "qc")
    db = world["db"]
    key = db.scalar(
        select(AudioAsset.storage_key).where(
            AudioAsset.recording_id == rid, AudioAsset.kind == "FTF_DERIVED_PCM"
        )
    )
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"overwritten by mistake")
    damaged = qc.post(url).json()["results"][0]
    assert (damaged["outcome"], damaged["reason_code"]) == ("FAIL", "DECODE_ERROR")
    s3.delete_object(Bucket=BUCKET, Key=key)
    gone = qc.post(url).json()["results"][0]
    assert (gone["outcome"], gone["reason_code"]) == ("FAIL", "MISSING_AUDIO")
    assert world["mod"].post(url).status_code == 403


def test_a_check_that_did_not_run_is_run_by_the_recovery_sweep(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("stopped")

    monkeypatch.setattr(audio_qc, "run_automatic", broken)
    _record(world)
    tid = world["task"]["id"]
    assert world["pa"].get(f"/api/v1/tasks/{tid}").json()["status"] == "RECORDED"
    monkeypatch.undo()
    assert worker_dispatch.check_pending_audio(world["app"]) == 1
    assert world["pa"].get(f"/api/v1/tasks/{tid}").json()["status"] == "AUDIO_QC"
    assert worker_dispatch.check_pending_audio(world["app"]) == 0


def test_the_details_file_goes_with_the_recording(world: dict[str, Any]) -> None:
    rid = _record(world)
    pa: Api = world["pa"]
    response = pa.get(f"/api/v1/recordings/{rid}/metadata")
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith('attachment; filename="metadata_')
    assert "Asha" not in response.text, "codes only, no names"
    assert "Bina" not in response.text
    body = json.loads(response.text)
    assert body["format"] == "ccp.recording-metadata/1"
    assert [p["slot"] for p in body["participants"]] == ["A", "B"]
    assert body["recording"]["device_label"] == "Test mic"
    kinds = {f["kind"]: f for f in body["files"]}
    assert set(kinds) == {"BROWSER_ORIGINAL", "FTF_DERIVED_PCM"}
    derived = kinds["FTF_DERIVED_PCM"]
    assert (derived["sample_rate"], derived["bit_depth"], derived["channels"]) == (16000, 16, 1)
    assert len(derived["sha256"]) == 64
    assert derived["processing"][0]["tool"] == "python-soxr"
    assert body["audio_qc"]["automatic"]["outcome"] == "PASS"
    assert body["audio_qc"]["decision"] is None
    qc = _assign_qc(world)
    assert qc.get(f"/api/v1/recordings/{rid}/metadata").status_code == 403, "QC cannot download"
    assert world["mod"].get(f"/api/v1/recordings/{rid}/metadata").status_code == 403
