"""Phone calls end to end with a stand-in provider and a fake S3 (test-only): the moderator starts
the call, closes it after consent, the platform finds the provider's recording, stores it and moves
the task to Recorded; unclear matches wait for a person; failures are visible and recoverable.

Requirements: TEL-002, TEL-010, TEL-011, TEL-018, TEL-027, TEL-037, GEN-004
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import pytest
import soundfile
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select, update

from app.adapters.telephony import DialResult, ProviderError, ProviderSession
from app.main import create_app
from app.modules.audio_qc.models import AudioQcResult
from app.modules.auth.models import User
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.recordings.worker_dispatch import fetch_call_recordings
from app.modules.telephony.models import Call
from tests.conftest import Api, build_settings, make_participant, make_project, make_user

pytestmark = pytest.mark.db
BUCKET = "ccp-telephony"
A_PHONE = "+919876543210"
B_PHONE = "+919812345678"
SEAT = "70001"


class StandIn:
    """Plays TxContact: records dial requests, lists the calls it is given, serves a WAV file."""

    name = "TXCONTACT"

    def __init__(self, audio: Path) -> None:
        self.audio = audio
        self.dials: list[tuple[str, str]] = []
        self.accept = True
        self.listed: list[ProviderSession] = []
        self.download_error: str | None = None
        self.searches = 0

    def dial(self, phone_e164: str, agent_id: str) -> DialResult:
        self.dials.append((phone_e164, agent_id))
        if self.accept:
            return DialResult(True, 200, "Contact queued")
        return DialResult(False, 200, "error: agent not logged in")

    def sessions(self, agent_id: str, day: date) -> list[ProviderSession]:
        self.searches += 1
        return [s for s in self.listed if s.agent_id == agent_id]

    def download(self, session: ProviderSession, dest: Path, max_bytes: int) -> int:
        if self.download_error:
            raise ProviderError(self.download_error)
        data = self.audio.read_bytes()
        dest.write_bytes(data)
        return len(data)


def session(sid: str, start: datetime, from_number: str = "9876543210") -> ProviderSession:
    return ProviderSession(
        session_id=sid,
        trans_id=f"T{sid}",
        from_number=from_number,
        to_number=SEAT,
        agent_id=SEAT,
        start=start,
        end=start + timedelta(minutes=5),
        duration="300",
        rec_filename=f"rec_{sid}",
        rec_ext="wav",
        rec_status="C",
    )


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    """Three seconds of an 8 kHz phone-quality tone, 16-bit mono, then one second of silence."""
    rate = 8000
    t = np.arange(3 * rate) / rate
    samples = np.concatenate([0.4 * np.sin(2 * np.pi * 300 * t), np.zeros(rate)])
    path = tmp_path / "provider.wav"
    soundfile.write(str(path), samples, rate, subtype="PCM_16")
    return path


@pytest.fixture
def world(migrated_db: str, tmp_path: Path, audio: Path) -> Iterator[dict[str, Any]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        app = create_app(
            build_settings(
                database_url=migrated_db,
                storage_bucket=BUCKET,
                storage_access_key_id="test-key",
                storage_secret_access_key="test-secret",
                media_work_dir=str(tmp_path / "media"),
                txcontact_dialer_username="dsc_user",
                txcontact_dialer_password="dial-pass",
                txcontact_record_user="rec_user",
                txcontact_record_password="rec-pass",
            )
        )
        provider = StandIn(audio)
        app.state.telephony = provider
        clients: list[TestClient] = []

        def api(email: str) -> Api:
            client = TestClient(app)
            clients.append(client)
            a = Api(client)
            assert a.login(email).status_code == 200
            return a

        with app.state.session_factory() as db:
            project = make_project(db, "PHONE")
            mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
            make_user(db, "mod2@example.org", ["MODERATOR"], projects=[project])
            make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
            make_user(db, "sa@example.org", ["SUPER_ADMIN"])
            pa, moderator, sa = api("pa@example.org"), api("mod@example.org"), api("sa@example.org")
            a = make_participant(pa, project.id, "Asha", phone=A_PHONE)
            b = make_participant(pa, project.id, "Bina", phone=B_PHONE)

            def new_task() -> str:
                task = pa.post(
                    "/api/v1/tasks",
                    json={
                        "project_id": str(project.id),
                        "recording_mode": "TELEPHONY",
                        "participant_a_id": a["id"],
                        "participant_b_id": b["id"],
                    },
                )
                assert task.status_code == 201, task.text
                tid: str = task.json()["id"]
                assigned = pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": str(mod.id)})
                assert assigned.status_code == 200, assigned.text
                moved = moderator.post(
                    f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"}
                )
                assert moved.status_code == 200, moved.text
                return tid

            yield {
                "app": app,
                "db": db,
                "provider": provider,
                "pa": pa,
                "mod": moderator,
                "sa": sa,
                "api": api,
                "mod_id": str(mod.id),
                "a": a,
                "b": b,
                "new_task": new_task,
            }
        for c in clients:
            c.close()


def give_seat(w: dict[str, Any]) -> None:
    r = w["sa"].put(f"/api/v1/users/{w['mod_id']}/telephony-agent", json={"agent_id": SEAT})
    assert r.status_code == 200, r.text
    assert r.json()["telephony_agent_id"] == SEAT


def consent(w: dict[str, Any], tid: str) -> None:
    for p in (w["a"], w["b"]):
        r = w["mod"].post(
            f"/api/v1/tasks/{tid}/consent",
            json={"participant_id": p["id"], "status": "GIVEN", "method": "VERBAL_NOTED"},
        )
        assert r.status_code == 201, r.text


def due_now(w: dict[str, Any], call_id: str) -> None:
    db = w["db"]
    db.execute(
        update(Call)
        .where(Call.id == call_id)
        .values(next_fetch_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()


def sweep(w: dict[str, Any]) -> None:
    fetch_call_recordings(w["app"])
    w["db"].expire_all()


def started_and_closed(w: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    give_seat(w)
    tid = w["new_task"]()
    started = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert started.status_code == 201, started.text
    consent(w, tid)
    closed = w["mod"].post(f"/api/v1/calls/{started.json()['id']}/close", json={"note": ""})
    assert closed.status_code == 200, closed.text
    return tid, closed.json()


def test_not_configured_is_reported_truthfully(db_app: Any, new_api: Any, db: Any) -> None:
    make_user(db, "mod@example.org", ["MODERATOR"])
    api: Api = new_api()
    api.login("mod@example.org")
    status = api.get("/api/v1/telephony/status")
    assert status.json() == {"configured": False, "provider": "TXCONTACT"}
    r = api.post("/api/v1/tasks/00000000-0000-0000-0000-000000000001/calls")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "NOT_CONFIGURED"


def test_full_call_flow(world: dict[str, Any]) -> None:
    w = world
    assert w["mod"].get("/api/v1/telephony/status").json()["configured"] is True
    tid = w["new_task"]()

    # Without an agent seat the moderator is told what to do; nothing is dialled.
    no_seat = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert no_seat.status_code == 409
    assert no_seat.json()["error"]["code"] == "NO_AGENT_SEAT"
    assert w["provider"].dials == []

    give_seat(w)
    started = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert started.status_code == 201, started.text
    call = started.json()
    assert call["state"] == "DIALLING"
    assert call["agent_id"] == SEAT
    assert call["phone_hint"] == "10"
    assert [e["kind"] for e in call["events"]] == ["DIAL_REQUESTED", "DIAL_ACCEPTED"]
    assert "Contact queued" in call["events"][1]["text"]  # the provider's own answer (TEL-037)
    assert A_PHONE not in json.dumps(call)
    assert w["provider"].dials == [(A_PHONE, SEAT)]

    again = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CALL_OPEN"

    # Closing needs both consents.
    early = w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "CONSENT_MISSING"
    consent(w, tid)
    closed = w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={"note": "good call"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["state"] == "WAITING_FOR_RECORDING"

    # Not due yet: the sweep leaves it alone.
    sweep(w)
    assert w["provider"].searches == 0

    now = datetime.now(UTC)
    w["provider"].listed = [
        session("OLD", now - timedelta(hours=3)),  # an earlier call on the same seat
        session("OTHER", now, from_number="9000000000"),  # another person, same time
        session("S1", now),
    ]
    due_now(w, call["id"])
    sweep(w)

    db = w["db"]
    row = db.get(Call, call["id"])
    assert row.state == "RECORDED", (row.failure_code, row.failure_detail)
    assert row.provider_session_id == "S1"
    rec = db.get(Recording, row.recording_id)
    assert (rec.mode, rec.state, rec.native_sample_rate, rec.channel_count) == (
        "TELEPHONY",
        "READY",
        8000,
        1,
    )
    assets = {
        a.kind: a for a in db.scalars(select(AudioAsset).where(AudioAsset.recording_id == rec.id))
    }
    original, final = assets["PROVIDER_ORIGINAL_MIXED"], assets["TELEPHONY_DERIVED_PCM"]
    assert (original.sample_rate, original.channels, original.file_extension) == (8000, 1, "wav")
    assert original.storage_key.startswith("PHONE/telephony/")
    assert "/provider-original/" in original.storage_key
    assert (final.codec, final.sample_rate, final.channels, final.bit_depth) == (
        "pcm_s16le",
        16000,
        1,
        16,
    )
    assert final.parent_asset_id == original.id
    assert abs(final.duration_ms - 4000) <= 5

    task = w["mod"].get(f"/api/v1/tasks/{tid}").json()
    assert task["status"] == "RECORDED"
    assert db.scalar(select(AudioQcResult).where(AudioQcResult.recording_id == rec.id))

    listed = w["pa"].get(f"/api/v1/tasks/{tid}/calls").json()
    kinds = [e["kind"] for e in listed[0]["events"]]
    assert kinds[-4:] == ["SEARCHING", "MATCHED", "DOWNLOADED", "RECORDED"]
    recordings = w["mod"].get(f"/api/v1/tasks/{tid}/recordings").json()
    assert recordings[0]["state"] == "READY"


def test_several_fitting_calls_wait_for_a_person_to_choose(world: dict[str, Any]) -> None:
    w = world
    tid, call = started_and_closed(w)
    now = datetime.now(UTC)
    w["provider"].listed = [session("X1", now), session("X2", now + timedelta(seconds=30))]
    due_now(w, call["id"])
    sweep(w)
    seen = w["mod"].get(f"/api/v1/tasks/{tid}/calls").json()[0]
    assert seen["state"] == "NEEDS_MATCH"
    assert seen["failure_code"] == "SEVERAL_CALLS"
    assert sorted(c["session_id"] for c in seen["candidates"]) == ["X1", "X2"]
    assert all(c["from_hint"] == "10" for c in seen["candidates"])
    assert "9876543210" not in json.dumps(seen)

    wrong = w["mod"].post(f"/api/v1/calls/{call['id']}/match", json={"session_id": "NOPE"})
    assert wrong.status_code == 422
    chosen = w["mod"].post(f"/api/v1/calls/{call['id']}/match", json={"session_id": "X2"})
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["state"] == "WAITING_FOR_RECORDING"
    sweep(w)
    row = w["db"].get(Call, call["id"])
    assert row.state == "RECORDED"
    assert row.provider_session_id == "X2"


def test_no_recording_keeps_looking_then_asks_a_person(world: dict[str, Any]) -> None:
    w = world
    tid, call = started_and_closed(w)
    for _ in range(3):
        due_now(w, call["id"])
        sweep(w)
    row = w["db"].get(Call, call["id"])
    assert row.state == "WAITING_FOR_RECORDING"
    assert row.fetch_attempts == 3

    # The search window has passed: a person is asked.
    w["db"].execute(
        update(Call)
        .where(Call.id == call["id"])
        .values(closed_at=datetime.now(UTC) - timedelta(hours=2))
    )
    w["db"].commit()
    due_now(w, call["id"])
    sweep(w)
    seen = w["mod"].get(f"/api/v1/tasks/{tid}/calls").json()[0]
    assert seen["state"] == "NEEDS_MATCH"
    assert seen["failure_code"] == "RECORDING_NOT_FOUND"

    retried = w["mod"].post(f"/api/v1/calls/{call['id']}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["state"] == "WAITING_FOR_RECORDING"
    assert [e["kind"] for e in retried.json()["events"]][-1] == "RETRY_REQUESTED"


def test_download_failures_are_retried_then_shown(world: dict[str, Any]) -> None:
    w = world
    tid, call = started_and_closed(w)
    w["provider"].listed = [session("D1", datetime.now(UTC))]
    w["provider"].download_error = "TxContact answered 500 to the recording download"
    for _ in range(5):
        due_now(w, call["id"])
        sweep(w)
    row = w["db"].get(Call, call["id"])
    assert row.state == "FETCH_FAILED"
    assert row.provider_session_id == "D1"  # the match is kept
    assert "500" in (row.failure_detail or "")
    assert w["mod"].get(f"/api/v1/tasks/{tid}").json()["status"] == "IN_PROGRESS"

    w["provider"].download_error = None
    assert w["mod"].post(f"/api/v1/calls/{call['id']}/retry").status_code == 200
    sweep(w)
    assert w["db"].get(Call, call["id"]).state == "RECORDED"


def test_a_refused_dial_is_shown_and_the_task_can_call_again(world: dict[str, Any]) -> None:
    w = world
    give_seat(w)
    tid = w["new_task"]()
    w["provider"].accept = False
    refused = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert refused.status_code == 201
    assert refused.json()["state"] == "DIAL_FAILED"
    assert refused.json()["failure_code"] == "PROVIDER_REFUSED"
    assert "agent not logged in" in refused.json()["failure_detail"]
    w["provider"].accept = True
    assert w["mod"].post(f"/api/v1/tasks/{tid}/calls").status_code == 201


def test_cancel_needs_a_reason_and_only_the_caller_or_a_manager_changes_a_call(
    world: dict[str, Any],
) -> None:
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = w["mod"].post(f"/api/v1/tasks/{tid}/calls").json()
    other = w["api"]("mod2@example.org")
    assert (
        other.post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "NO_ANSWER"}).status_code
        == 404
    )
    bad = w["mod"].post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "OTHER"})
    assert bad.status_code == 422
    ok = w["pa"].post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "NO_ANSWER"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"] == "CANCELLED"
    assert ok.json()["events"][-1]["actor"] == "pa"
    # Cancelled: a new call can be made.
    assert w["mod"].post(f"/api/v1/tasks/{tid}/calls").status_code == 201


def test_an_agent_seat_belongs_to_one_user(world: dict[str, Any]) -> None:
    w = world
    give_seat(w)
    mod2 = w["db"].scalar(select(User).where(User.email == "mod2@example.org"))
    taken = w["sa"].put(f"/api/v1/users/{mod2.id}/telephony-agent", json={"agent_id": SEAT})
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "AGENT_SEAT_TAKEN"
    cleared = w["sa"].put(f"/api/v1/users/{w['mod_id']}/telephony-agent", json={"agent_id": ""})
    assert cleared.json()["telephony_agent_id"] is None
    assert (
        w["pa"].put(f"/api/v1/users/{mod2.id}/telephony-agent", json={"agent_id": "1"}).status_code
        == 403
    )
