"""Phone calls end to end with a stand-in provider and a fake S3 (test-only): the moderator starts
the call, ticks the checklist, closes it after consent, the platform finds the provider's
recording, stores it and moves the task to Recorded; unclear matches wait for a person; every
failure is visible, recoverable and cancellable; figures, the list and the CSV count what happened.

Requirements: TEL-002, TEL-010, TEL-011, TEL-015, TEL-018, TEL-027, TEL-036, TEL-037, TEL-038, GEN-004
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
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
from app.modules.projects.models import ProjectAudioRule
from app.modules.projects.service import DEFAULT_AUDIO, DEFAULT_MAX_SILENCE_PCT
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.recordings.worker_dispatch import fetch_call_recordings
from app.modules.telephony.models import Call
from tests.conftest import Api, build_settings, make_participant, make_project, make_user

pytestmark = pytest.mark.db
BUCKET = "ccp-telephony"
A_PHONE = "+919876543210"
B_PHONE = "+919812345678"
SEAT = "70001"
REFERENCE = "fec72ece-df50-11f1-96b6-bc24110b2437"


class StandIn:
    """Plays TxContact: records dial requests, lists the calls it is given, serves a WAV file."""

    name = "TXCONTACT"

    def __init__(self, audio: Path) -> None:
        self.audio = audio
        self.dials: list[tuple[str, str]] = []
        self.accept = True
        self.listed: list[ProviderSession] = []
        self.search_error: str | None = None
        self.download_error: str | None = None
        self.before_download: Callable[[], None] | None = None
        self.searches = 0

    def dial(self, phone_e164: str, agent_id: str) -> DialResult:
        self.dials.append((phone_e164, agent_id))
        if self.accept:
            return DialResult(True, 200, "Contact queued", REFERENCE)
        return DialResult(False, 200, "error: agent not logged in")

    def sessions(self, agent_id: str, day: date) -> list[ProviderSession]:
        self.searches += 1
        if self.search_error:
            raise ProviderError(self.search_error)
        return [s for s in self.listed if s.agent_id == agent_id]

    def traffic(self, first: Any, last: Any) -> Any:
        return {"10": 3, "11": 5}

    def download(self, session: ProviderSession, dest: Path, max_bytes: int) -> int:
        if self.before_download:
            self.before_download()
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
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
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
            # The audio rule a project created through the application gets for phone calls.
            db.add(
                ProjectAudioRule(
                    project_id=project.id,
                    mode="TELEPHONY",
                    **DEFAULT_AUDIO["TELEPHONY"],
                    max_silence_pct=DEFAULT_MAX_SILENCE_PCT,
                    max_clipping_pct=None,
                    min_duration_seconds=0,
                    max_duration_seconds=None,
                )
            )
            db.commit()
            mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
            mod2 = make_user(db, "mod2@example.org", ["MODERATOR"], projects=[project])
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
                "s3": s3,
                "provider": provider,
                "project_id": str(project.id),
                "pa": pa,
                "mod": moderator,
                "sa": sa,
                "api": api,
                "mod_id": str(mod.id),
                "mod2_id": str(mod2.id),
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


def consent(w: dict[str, Any], tid: str, status: str = "GIVEN") -> None:
    for p in (w["a"], w["b"]):
        r = w["mod"].post(
            f"/api/v1/tasks/{tid}/consent",
            json={"participant_id": p["id"], "status": status, "method": "VERBAL_NOTED"},
        )
        assert r.status_code == 201, r.text


def joined(w: dict[str, Any], call_id: str) -> None:
    """The moderator confirms that A and B are on the call."""
    for item in ("A_JOINED", "B_JOINED"):
        r = w["mod"].post(f"/api/v1/calls/{call_id}/checklist", json={"item": item})
        assert r.status_code == 200, r.text


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


def start(w: dict[str, Any], tid: str) -> dict[str, Any]:
    started = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert started.status_code == 201, started.text
    body: dict[str, Any] = started.json()
    return body


def started_and_closed(w: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    joined(w, call["id"])
    consent(w, tid)
    closed = w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={"note": ""})
    assert closed.status_code == 200, closed.text
    return tid, closed.json()


def seen(w: dict[str, Any], tid: str) -> dict[str, Any]:
    """The task's newest call as the moderator's page gets it."""
    calls: list[dict[str, Any]] = w["mod"].get(f"/api/v1/tasks/{tid}/calls").json()
    return calls[0]


def stored_keys(w: dict[str, Any]) -> list[str]:
    listed = w["s3"].list_objects_v2(Bucket=BUCKET)
    return [o["Key"] for o in listed.get("Contents", [])]


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
    call = start(w, tid)
    assert call["state"] == "DIALLING"
    assert call["agent_id"] == SEAT
    assert call["phone_hint"] == "10"
    assert call["provider_reference"] == REFERENCE
    assert call["checklist"] == {}
    assert [e["kind"] for e in call["events"]] == ["DIAL_REQUESTED", "DIAL_ACCEPTED"]
    assert "Contact queued" in call["events"][1]["text"]  # the provider's own answer (TEL-037)
    assert A_PHONE not in json.dumps(call)
    assert w["provider"].dials == [(A_PHONE, SEAT)]

    again = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CALL_OPEN"

    # Closing needs both people on the call, then both consents.
    early = w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "CHECKLIST_INCOMPLETE"
    joined(w, call["id"])
    ticked = w["mod"].post(f"/api/v1/calls/{call['id']}/checklist", json={"item": "QUALITY_OK"})
    assert sorted(ticked.json()["checklist"]) == ["A_JOINED", "B_JOINED", "QUALITY_OK"]
    undone = w["mod"].post(
        f"/api/v1/calls/{call['id']}/checklist", json={"item": "QUALITY_OK", "done": False}
    )
    assert sorted(undone.json()["checklist"]) == ["A_JOINED", "B_JOINED"]
    no_consent = w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={})
    assert no_consent.status_code == 409
    assert no_consent.json()["error"]["code"] == "CONSENT_MISSING"
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
    # One channel is what the project expects of a phone call (D-103): the check does not fail.
    check = db.scalar(select(AudioQcResult).where(AudioQcResult.recording_id == rec.id))
    assert check is not None
    assert check.outcome != "FAIL", check.comment
    assert {c.code: c.state for c in check.checks}["CHANNELS"] == "PASS"

    listed = w["pa"].get(f"/api/v1/tasks/{tid}/calls").json()
    kinds = [e["kind"] for e in listed[0]["events"]]
    assert kinds[-4:] == ["SEARCHING", "MATCHED", "DOWNLOADED", "RECORDED"]
    assert kinds.count("CHECKLIST") == 4

    # The moderator's page gets the files with the recording: it can offer Listen (D-092).
    recordings = w["mod"].get(f"/api/v1/tasks/{tid}/recordings").json()
    assert recordings[0]["state"] == "READY"
    assert sorted(a["kind"] for a in recordings[0]["assets"]) == [
        "PROVIDER_ORIGINAL_MIXED",
        "TELEPHONY_DERIVED_PCM",
    ]

    # The details file tells the call's story (D-103), without the number.
    details = w["pa"].get(f"/api/v1/recordings/{rec.id}/metadata")
    assert details.status_code == 200, details.text
    told = details.json()["call"]
    assert (told["provider"], told["agent_seat"], told["provider_reference"]) == (
        "TXCONTACT",
        SEAT,
        REFERENCE,
    )
    assert told["number_ends_in"] == "10"
    assert told["note"] == "good call"
    assert told["checklist"]["A_JOINED"]
    assert told["checklist"]["B_JOINED"]
    assert told["checklist"]["QUALITY_OK"] is None
    assert [h["kind"] for h in told["history"]][-1] == "RECORDED"
    assert "9876543210" not in details.text


def test_boxes_ticked_at_the_same_moment_are_all_kept(world: dict[str, Any]) -> None:
    """A moderator ticks the checklist quickly: four requests arrive together and none may
    overwrite another (found in the browser run: only the last tick survived)."""
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    items = ["A_JOINED", "B_JOINED", "MODERATOR_MUTED", "QUALITY_OK"]
    clients = [w["api"]("mod@example.org") for _ in items]

    def tick(pair: tuple[Api, str]) -> int:
        client, item = pair
        status: int = client.post(
            f"/api/v1/calls/{call['id']}/checklist", json={"item": item}
        ).status_code
        return status

    for _ in range(3):  # a few rounds: untick everything, then tick all at once again
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(tick, zip(clients, items, strict=True))) == [200] * 4
        assert sorted(seen(w, tid)["checklist"]) == sorted(items)
        for item in items:
            w["mod"].post(
                f"/api/v1/calls/{call['id']}/checklist", json={"item": item, "done": False}
            )
        assert seen(w, tid)["checklist"] == {}


def test_several_fitting_calls_wait_for_a_person_to_choose(world: dict[str, Any]) -> None:
    w = world
    tid, call = started_and_closed(w)
    now = datetime.now(UTC)
    # A provider that puts the caller's number in its ids and file names: shown masked only.
    w["provider"].listed = [
        session("919876543210-X1", now),
        session("919876543210-X2", now + timedelta(seconds=30)),
    ]
    due_now(w, call["id"])
    sweep(w)
    got = seen(w, tid)
    assert got["state"] == "NEEDS_MATCH"
    assert got["failure_code"] == "SEVERAL_CALLS"
    assert sorted(c["session_id"] for c in got["candidates"]) == ["…10-X1", "…10-X2"]
    assert all(c["from_hint"] == "10" for c in got["candidates"])
    assert "9876543210" not in json.dumps(got)

    wrong = w["mod"].post(f"/api/v1/calls/{call['id']}/match", json={"key": "nope"})
    assert wrong.status_code == 422
    key = next(c["key"] for c in got["candidates"] if c["session_id"].endswith("X2"))
    chosen = w["mod"].post(f"/api/v1/calls/{call['id']}/match", json={"key": key})
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["state"] == "WAITING_FOR_RECORDING"
    sweep(w)
    row = w["db"].get(Call, call["id"])
    assert row.state == "RECORDED"
    assert row.provider_session_id == "919876543210-X2"  # the real id is kept for the download
    after = seen(w, tid)
    assert after["provider_session_id"] == "…10-X2"
    assert "9876543210" not in json.dumps(after)
    steps = w["pa"].get(f"/api/v1/recordings/{row.recording_id}/metadata").text
    assert "9876543210" not in steps


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
    got = seen(w, tid)
    assert got["state"] == "NEEDS_MATCH"
    assert got["failure_code"] == "RECORDING_NOT_FOUND"

    retried = w["mod"].post(f"/api/v1/calls/{call['id']}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["state"] == "WAITING_FOR_RECORDING"
    assert [e["kind"] for e in retried.json()["events"]][-1] == "RETRY_REQUESTED"


def test_a_provider_that_cannot_be_searched_ends_with_a_person_and_can_be_cancelled(
    world: dict[str, Any],
) -> None:
    """A wrong recording login (the state of the account on 2026-11-13) must not leave closed
    calls retrying for ever with the task blocked."""
    w = world
    tid, call = started_and_closed(w)
    w["provider"].search_error = "TxContact refused the recording sign-in"
    due_now(w, call["id"])
    sweep(w)
    waiting = seen(w, tid)
    assert waiting["state"] == "WAITING_FOR_RECORDING"
    assert waiting["events"][-1]["kind"] == "SEARCH_ERROR"

    # While it waits the call can be cancelled, and the task can then be called again.
    other_tid, other = started_and_closed(w)
    stopped = w["mod"].post(f"/api/v1/calls/{other['id']}/cancel", json={"reason": "POOR_QUALITY"})
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["state"] == "CANCELLED"
    assert w["mod"].post(f"/api/v1/tasks/{other_tid}/calls").status_code == 201

    # After the window a person is told why.
    w["db"].execute(
        update(Call)
        .where(Call.id == call["id"])
        .values(closed_at=datetime.now(UTC) - timedelta(hours=2), fetch_attempts=5)
    )
    w["db"].commit()
    due_now(w, call["id"])
    sweep(w)
    got = seen(w, tid)
    assert got["state"] == "NEEDS_MATCH"
    assert got["failure_code"] == "SEARCH_FAILED"
    assert "refused the recording sign-in" in got["failure_detail"]
    assert got["candidates"] == []


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
    assert row.failure_code == "DOWNLOAD_FAILED"
    assert row.provider_session_id == "D1"  # the match is kept
    assert "500" in (row.failure_detail or "")
    assert w["mod"].get(f"/api/v1/tasks/{tid}").json()["status"] == "IN_PROGRESS"
    assert stored_keys(w) == []  # nothing of the failed tries is left in storage

    w["provider"].download_error = None
    assert w["mod"].post(f"/api/v1/calls/{call['id']}/retry").status_code == 200
    sweep(w)
    assert w["db"].get(Call, call["id"]).state == "RECORDED"


def test_a_file_that_is_not_audio_is_shown_at_once_without_server_paths(
    world: dict[str, Any], tmp_path: Path
) -> None:
    w = world
    tid, call = started_and_closed(w)
    w["provider"].audio = tmp_path / "not-audio.mp4"
    w["provider"].audio.write_bytes(b"\x00\x00\x00\x18ftypmp42 this is not something we can read")
    w["provider"].listed = [session("M1", datetime.now(UTC))]
    due_now(w, call["id"])
    sweep(w)
    got = seen(w, tid)
    assert got["state"] == "FETCH_FAILED"  # at the first try: trying again would not help
    assert got["failure_code"] == "UNREADABLE_AUDIO"
    assert "not audio this platform can read" in got["failure_detail"]
    assert str(tmp_path) not in json.dumps(got)
    assert stored_keys(w) == []


def test_a_call_cancelled_while_its_file_comes_down_stores_nothing(world: dict[str, Any]) -> None:
    w = world
    tid, call = started_and_closed(w)
    w["provider"].listed = [session("C1", datetime.now(UTC))]

    def cancel_now() -> None:
        r = w["pa"].post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "CONSENT_REFUSED"})
        assert r.status_code == 200, r.text

    w["provider"].before_download = cancel_now
    due_now(w, call["id"])
    sweep(w)
    row = w["db"].get(Call, call["id"])
    assert row.state == "CANCELLED"
    assert row.recording_id is None
    assert w["db"].scalar(select(Recording.id)) is None
    assert stored_keys(w) == []
    assert w["mod"].get(f"/api/v1/tasks/{tid}").json()["status"] == "IN_PROGRESS"


def test_a_redial_does_not_take_the_dropped_calls_recording(world: dict[str, Any]) -> None:
    w = world
    give_seat(w)
    tid = w["new_task"]()
    dropped = start(w, tid)
    cancelled = w["mod"].post(
        f"/api/v1/calls/{dropped['id']}/cancel", json={"reason": "CALL_DROPPED"}
    )
    assert cancelled.status_code == 200, cancelled.text
    now = datetime.now(UTC)
    # The first attempt went out a minute ago and its 40 seconds were recorded by the provider.
    w["db"].execute(
        update(Call).where(Call.id == dropped["id"]).values(dialled_at=now - timedelta(seconds=60))
    )
    w["db"].commit()
    call = start(w, tid)
    joined(w, call["id"])
    consent(w, tid)
    assert w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={}).status_code == 200
    w["provider"].listed = [
        session("DROPPED", now - timedelta(seconds=55)),
        session("REAL", now + timedelta(seconds=1)),
    ]
    due_now(w, call["id"])
    sweep(w)
    row = w["db"].get(Call, call["id"])
    assert (row.state, row.provider_session_id) == ("RECORDED", "REAL")


def test_a_call_waits_with_a_task_on_hold_and_ends_with_a_task_that_is_over(
    world: dict[str, Any],
) -> None:
    w = world
    tid, call = started_and_closed(w)
    w["provider"].listed = [session("H1", datetime.now(UTC))]
    held = w["pa"].post(
        f"/api/v1/tasks/{tid}/transition",
        json={"to": "ON_HOLD", "reason_code": "TECHNICAL_PROBLEM"},
    )
    assert held.status_code == 200, held.text
    due_now(w, call["id"])
    sweep(w)
    row = w["db"].get(Call, call["id"])
    assert (row.state, row.fetch_attempts, row.recording_id) == ("WAITING_FOR_RECORDING", 0, None)
    resumed = w["pa"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    assert resumed.status_code == 200, resumed.text
    due_now(w, call["id"])
    sweep(w)
    assert w["db"].get(Call, call["id"]).state == "RECORDED"
    assert w["mod"].get(f"/api/v1/tasks/{tid}").json()["status"] == "RECORDED"

    # A task cancelled before the recording arrives: the call ends with it, nothing is fetched.
    tid2, call2 = started_and_closed(w)
    w["provider"].listed = [session("H2", datetime.now(UTC))]
    over = w["pa"].post(
        f"/api/v1/tasks/{tid2}/transition",
        json={"to": "CANCELLED", "reason_code": "CLIENT_REQUEST"},
    )
    assert over.status_code == 200, over.text
    due_now(w, call2["id"])
    sweep(w)
    ended = w["db"].get(Call, call2["id"])
    assert (ended.state, ended.cancel_reason, ended.recording_id) == ("CANCELLED", "OTHER", None)
    assert "cancelled" in ended.note


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


def test_a_participant_is_not_rung_over_and_over(world: dict[str, Any]) -> None:
    w = world
    give_seat(w)
    tid = w["new_task"]()
    w["provider"].accept = False
    for _ in range(6):  # TELEPHONY_MAX_CALLS_PER_TASK_PER_HOUR
        assert w["mod"].post(f"/api/v1/tasks/{tid}/calls").status_code == 201
    w["provider"].accept = True
    seventh = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert seventh.status_code == 429
    assert seventh.json()["error"]["code"] == "TOO_MANY_CALLS"
    assert len(w["provider"].dials) == 6

    # Someone who refused consent for the session is not called again.
    other = w["new_task"]()
    consent(w, other, "REFUSED")
    no = w["mod"].post(f"/api/v1/tasks/{other}/calls")
    assert no.status_code == 409
    assert no.json()["error"]["code"] == "CONSENT_REFUSED"
    assert len(w["provider"].dials) == 6


def test_cancel_needs_a_reason_and_only_the_tasks_people_change_a_call(
    world: dict[str, Any],
) -> None:
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    other = w["api"]("mod2@example.org")
    refused = other.post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "NO_ANSWER"})
    assert refused.status_code == 404
    bad = w["mod"].post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "OTHER"})
    assert bad.status_code == 422

    # After a reassignment the new moderator takes the open call over.
    assert (
        w["pa"]
        .post(
            f"/api/v1/tasks/{tid}/transition",
            json={"to": "ON_HOLD", "reason_code": "TECHNICAL_PROBLEM"},
        )
        .status_code
        == 200
    )
    moved = w["pa"].post(
        f"/api/v1/tasks/{tid}/assign", json={"user_id": w["mod2_id"], "reason": "Shift ended"}
    )
    assert moved.status_code == 200, moved.text
    ok = other.post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "NO_ANSWER"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"] == "CANCELLED"
    assert ok.json()["events"][-1]["actor"] == "mod2"


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


def test_analytics_count_what_happened_and_respect_who_may_see_it(world: dict[str, Any]) -> None:
    w = world
    tid, call = started_and_closed(w)
    w["provider"].listed = [session("S9", datetime.now(UTC))]
    due_now(w, call["id"])
    sweep(w)
    other = w["new_task"]()
    w["provider"].accept = False
    w["mod"].post(f"/api/v1/tasks/{other}/calls")  # refused by the provider
    w["provider"].accept = True
    cancelled = start(w, other)
    w["mod"].post(f"/api/v1/calls/{cancelled['id']}/cancel", json={"reason": "NO_ANSWER"})
    w["new_task"]()  # a task nobody has called yet
    sent = w["mod"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "AUDIO_QC"})
    assert sent.status_code == 200, sent.text

    for who in ("pa", "mod"):
        a = w[who].get("/api/v1/telephony/analytics?days=7")
        assert a.status_code == 200, a.text
        body = a.json()
        assert (body["calls"], body["recorded"], body["dial_failed"], body["cancelled"]) == (
            3,
            1,
            1,
            1,
        )
        assert body["success_pct"] == 33.3
        assert body["cancel_reasons"] == {"NO_ANSWER": 1}
        assert body["problems"] == {"PROVIDER_REFUSED": 1}
        assert body["recorded_minutes"] == round(4000 / 60000, 1)
        assert body["today_recorded_minutes"] == body["recorded_minutes"]
        assert len(body["by_day"]) == 7
        assert sum(d["calls"] for d in body["by_day"]) == 3
        assert sum(body["by_hour"]) == 3
        assert body["by_moderator"][0]["calls"] == 3
        assert body["funnel"] == {
            "dialled": 3,
            "accepted": 2,
            "closed": 1,
            "recorded": 1,
            "sent_to_qc": 1,
            "approved": 0,
        }
        assert (body["tasks_called"], body["tasks_called_again"], body["calls_per_task"]) == (
            2,
            1,
            1.5,
        )
        assert body["tasks_by_status"] == {"IN_PROGRESS": 2, "AUDIO_QC": 1}
        assert body["tasks_not_called"] == 1
        assert sum(body["automatic_checks"].values()) == 1
        assert body["checklist"]["A_JOINED"] == body["checklist"]["closed_calls"] == 1
        assert [p["code"] for p in body["by_project"]] == ["PHONE"]
    # A project's target belongs to those who manage it.
    assert w["pa"].get("/api/v1/telephony/analytics").json()["target_minutes_per_day"] is not None
    assert w["mod"].get("/api/v1/telephony/analytics").json()["target_minutes_per_day"] is None

    page = w["pa"].get("/api/v1/calls?page_size=2").json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["items"][0]["task_code"].startswith("T")
    recorded = w["pa"].get("/api/v1/calls?state=RECORDED").json()
    assert [i["state"] for i in recorded["items"]] == ["RECORDED"]
    assert recorded["items"][0]["recording_seconds"] == 4.0

    # The spreadsheet of calls: one row a call, no phone numbers.
    sheet = w["pa"].get(f"/api/v1/calls/export?project_id={w['project_id']}&days=7")
    assert sheet.status_code == 200, sheet.text
    assert sheet.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(sheet.text)))
    assert len(rows) == 3
    done = next(r for r in rows if r["state"] == "RECORDED")
    assert (done["a_joined"], done["b_joined"], done["quality_ok"]) == ("yes", "yes", "no")
    assert (done["agent_seat"], done["number_ends_in"], done["provider_reference"]) == (
        SEAT,
        "10",
        REFERENCE,
    )
    assert done["recording_seconds"] == "4.0"
    assert "9876543210" not in sheet.text

    # Another moderator in the same project sees none of these calls.
    mod2 = w["api"]("mod2@example.org")
    assert mod2.get("/api/v1/telephony/analytics").json()["calls"] == 0
    assert mod2.get("/api/v1/calls").json()["total"] == 0
    assert len(list(csv.DictReader(io.StringIO(mod2.get("/api/v1/calls/export").text)))) == 0


def test_a_call_left_open_is_counted_as_needing_a_person(world: dict[str, Any]) -> None:
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    w["db"].execute(
        update(Call)
        .where(Call.id == call["id"])
        .values(dialled_at=datetime.now(UTC) - timedelta(hours=5))
    )
    w["db"].commit()
    body = w["pa"].get("/api/v1/telephony/analytics?days=7").json()
    assert (body["in_call"], body["stale_calls"], body["needs_person"]) == (0, 1, 1)
    needing = w["pa"].get("/api/v1/calls?state=NEEDS_PERSON").json()
    assert [(i["state"], i["stale"]) for i in needing["items"]] == [("DIALLING", True)]
    # A project admin ends it.
    ended = w["pa"].post(f"/api/v1/calls/{call['id']}/cancel", json={"reason": "CALL_DROPPED"})
    assert ended.status_code == 200, ended.text


def test_the_progress_report_lists_each_tasks_calls(world: dict[str, Any]) -> None:
    w = world
    _, call = started_and_closed(w)
    w["provider"].listed = [session("P1", datetime.now(UTC))]
    due_now(w, call["id"])
    sweep(w)
    report = w["pa"].get(f"/api/v1/projects/{w['project_id']}/export?content=progress")
    assert report.status_code == 200, report.text
    (row,) = list(csv.DictReader(io.StringIO(report.text)))
    assert (row["mode"], row["phone_calls"], row["last_call_state"]) == (
        "TELEPHONY",
        "1",
        "RECORDED",
    )


def test_provider_traffic_is_passed_on_for_managers_only(world: dict[str, Any]) -> None:
    w = world
    t = w["pa"].get("/api/v1/telephony/provider-traffic?days=7")
    assert t.status_code == 200
    assert t.json()["available"] is True
    assert t.json()["data"] == {"10": 3, "11": 5}
    assert w["mod"].get("/api/v1/telephony/provider-traffic").status_code == 403
