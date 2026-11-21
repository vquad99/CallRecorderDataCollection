"""Phone calls end to end with a stand-in provider and a fake S3 (test-only): the moderator starts
the call, ticks the checklist, closes it after consent, the platform finds the provider's
recording, stores it and moves the task to Recorded; unclear matches wait for a person; every
failure is visible, recoverable and cancellable; figures, the list and the CSV count what happened.
The real TxContact adapter runs against tests/fake_txcontact.py where its clock matters (D-131); a
seat's password is kept encrypted and shown only to whom it belongs (D-130).

Requirements: TEL-002, TEL-010, TEL-011, TEL-015, TEL-018, TEL-027, TEL-036, TEL-037, TEL-038, GEN-004, PART-008, PART-016
"""

from __future__ import annotations

import csv
import io
import json
import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import boto3
import numpy as np
import pytest
import soundfile
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select, update

from app import cli
from app.adapters.telephony import DialResult, ProviderError, ProviderSession
from app.main import create_app
from app.modules.audio_qc.models import AudioQcResult
from app.modules.audit.models import AuditLog
from app.modules.auth.models import User
from app.modules.auth.security import FieldCipher
from app.modules.participants.models import ConsentRecord, Participant
from app.modules.projects.models import ProjectAudioRule
from app.modules.projects.service import DEFAULT_AUDIO, DEFAULT_MAX_SILENCE_PCT
from app.modules.recordings.models import AssetProcessingStep, AudioAsset, Recording
from app.modules.recordings.worker_dispatch import fetch_call_recordings
from app.modules.telephony import fetch
from app.modules.telephony.models import Call, CallEvent
from tests import fake_txcontact
from tests.conftest import (
    TEST_FERNET_KEY,
    Api,
    agree,
    build_settings,
    make_participant,
    make_project,
    make_user,
)

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
        self.attaches: list[tuple[str, str]] = []
        self.accept = True
        self.attach_answer: DialResult | Exception = DialResult(
            True, 200, "Contact queued", "B-REF"
        )
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

    def attach(self, phone_e164: str, agent_id: str) -> DialResult:
        self.attaches.append((phone_e164, agent_id))
        if isinstance(self.attach_answer, Exception):
            raise self.attach_answer
        return self.attach_answer

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


def provider_wav(path: Path, rate: int, channels: int) -> Path:
    """Three seconds of tones, then one second of silence, 16-bit: one tone per channel, each at
    its own pitch and level, as two speakers on their own channels."""
    t = np.arange(3 * rate) / rate
    tones = [(0.4 - 0.15 * c) * np.sin(2 * np.pi * (300 + 150 * c) * t) for c in range(channels)]
    samples = np.concatenate([np.stack(tones, axis=1), np.zeros((rate, channels))])
    soundfile.write(str(path), samples, rate, subtype="PCM_16")
    return path


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    """A call as TxContact records it (D-134): WAV, 16 kHz, 16-bit, stereo."""
    return provider_wav(tmp_path / "provider.wav", 16000, 2)


@pytest.fixture
def stand_in_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """tests/fake_txcontact.py on a free local port, listing no calls yet."""
    monkeypatch.setattr(fake_txcontact, "CALLS", [])
    server = ThreadingHTTPServer(("127.0.0.1", 0), fake_txcontact.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def world(
    request: pytest.FixtureRequest, migrated_db: str, tmp_path: Path, audio: Path
) -> Iterator[dict[str, Any]]:
    # Parametrized (indirect) with minutes: the real TxContact adapter against the stand-in, both
    # clocks that far ahead of the real time (D-131). Otherwise StandIn plays the provider.
    ahead: int | None = getattr(request, "param", None)
    txcontact: dict[str, Any] = {
        "txcontact_dialer_username": "dsc_user",
        "txcontact_dialer_password": "dial-pass",
        "txcontact_record_user": "rec_user",
        "txcontact_record_password": "rec-pass",
    }
    if ahead is not None:
        request.getfixturevalue("monkeypatch").setattr(
            fake_txcontact, "CLOCK_AHEAD", timedelta(minutes=ahead)
        )
        txcontact = {
            "txcontact_base_url": request.getfixturevalue("stand_in_url"),
            "txcontact_dialer_username": fake_txcontact.DIALER_USER,
            "txcontact_dialer_password": fake_txcontact.DIALER_PASSWORD,
            "txcontact_record_user": fake_txcontact.RECORD_USER,
            "txcontact_record_password": fake_txcontact.RECORD_PASSWORD,
            "txcontact_clock_ahead_minutes": ahead,
        }
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
                **txcontact,
            )
        )
        if ahead is None:
            app.state.telephony = StandIn(audio)
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
                "provider": app.state.telephony,
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


def withdrawn_before_d129(w: dict[str, Any], *people: dict[str, Any]) -> None:
    """These people's consent no longer counts: they withdrew it on their page before D-129
    (nobody can since). Written straight into the database."""
    for p in people:
        w["db"].add(
            ConsentRecord(
                participant_id=uuid.UUID(p["id"]),
                project_id=uuid.UUID(w["project_id"]),
                task_id=None,
                status="WITHDRAWN",
                method="DIGITAL",
                policy_version="1",
                captured_by=None,
            )
        )
    w["db"].commit()


def joined(w: dict[str, Any], call_id: str, tid: str) -> None:
    """The moderator confirms that A and B are on the call, then starts the recording (D-113).
    Both agreed to the consent form when they were added (D-119, D-129)."""
    for item in ("A_JOINED", "B_JOINED"):
        r = w["mod"].post(f"/api/v1/calls/{call_id}/checklist", json={"item": item})
        assert r.status_code == 200, r.text
    r = w["mod"].post(f"/api/v1/calls/{call_id}/recording/start")
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
    joined(w, call["id"], tid)
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
    assert status.json() == {"configured": False, "provider": "TXCONTACT", "seat_login": None}
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
    # D-127: nobody is rung before both participants have agreed (here: consent from before
    # D-129 that no longer counts).
    withdrawn_before_d129(w, w["a"], w["b"])
    early_call = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert (early_call.status_code, early_call.json()["error"]["code"]) == (409, "CONSENT_MISSING")
    assert w["provider"].dials == []
    for p in (w["a"], w["b"]):
        agree(w["pa"], w["project_id"], p["id"])
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

    # Closing needs both people on the call.
    early = w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "CHECKLIST_INCOMPLETE"
    joined(w, call["id"], tid)
    ticked = w["mod"].post(f"/api/v1/calls/{call['id']}/checklist", json={"item": "QUALITY_OK"})
    assert sorted(ticked.json()["checklist"]) == ["A_JOINED", "B_JOINED", "QUALITY_OK"]
    undone = w["mod"].post(
        f"/api/v1/calls/{call['id']}/checklist", json={"item": "QUALITY_OK", "done": False}
    )
    assert sorted(undone.json()["checklist"]) == ["A_JOINED", "B_JOINED"]
    closed = w["mod"].post(f"/api/v1/calls/{call['id']}/close", json={"note": "good call"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["state"] == "WAITING_FOR_RECORDING"

    # Not due yet: the sweep leaves it alone.
    sweep(w)
    assert w["provider"].searches == 0

    # The provider's file starts after the marks: the whole 4 s file is kept, whatever the
    # clock's resolution (cutting to the marks has its own test).
    now = datetime.now(UTC) + timedelta(seconds=5)
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
        16000,
        2,
    )
    assert rec.channel_handling == "all 2 channels kept, not mixed"
    assets = {
        a.kind: a for a in db.scalars(select(AudioAsset).where(AudioAsset.recording_id == rec.id))
    }
    original, final = assets["PROVIDER_ORIGINAL_MIXED"], assets["TELEPHONY_DERIVED_PCM"]
    assert (original.sample_rate, original.channels, original.file_extension) == (16000, 2, "wav")
    assert original.storage_key.startswith("PHONE/telephony/")
    assert "/provider-original/" in original.storage_key
    assert (final.codec, final.sample_rate, final.channels, final.bit_depth) == (
        "pcm_s16le",
        16000,
        2,
        16,
    )
    assert final.parent_asset_id == original.id
    assert abs(final.duration_ms - 4000) <= 5
    # Already 16 kHz: both channels are delivered sample for sample, not resampled (D-134).
    delivered = w["s3"].get_object(Bucket=BUCKET, Key=final.storage_key)["Body"].read()
    samples, _ = soundfile.read(io.BytesIO(delivered), dtype="int16")
    provided, _ = soundfile.read(str(w["provider"].audio), dtype="int16")
    assert np.array_equal(samples, provided)
    step = db.scalar(select(AssetProcessingStep).where(AssetProcessingStep.asset_id == final.id))
    assert step is not None
    assert "soxr" not in step.tool
    assert "16000 Hz as delivered, no resampling" in step.parameters

    task = w["mod"].get(f"/api/v1/tasks/{tid}").json()
    assert task["status"] == "RECORDED"
    # Stereo is what the project expects of a phone call (D-134): the check does not fail.
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


def test_a_mono_phone_recording_fails_the_check_with_a_track_missing(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """D-134: should the provider send one mixed channel at 8 kHz again (as seen 2026-11-15), the
    recording is still stored, resampled to 16 kHz, and the automatic check fails it with "A
    track is missing": the change is caught, not delivered as stereo."""
    w = world
    w["provider"].audio = provider_wav(tmp_path / "mono.wav", 8000, 1)
    _, call = started_and_closed(w)
    w["provider"].listed = [session("MONO", datetime.now(UTC) + timedelta(seconds=5))]
    due_now(w, call["id"])
    sweep(w)
    db = w["db"]
    row = db.get(Call, call["id"])
    assert row.state == "RECORDED", row.failure_detail
    final = db.scalar(
        select(AudioAsset).where(
            AudioAsset.recording_id == row.recording_id,
            AudioAsset.kind == "TELEPHONY_DERIVED_PCM",
        )
    )
    assert final is not None
    assert (final.sample_rate, final.channels) == (16000, 1)
    step = db.scalar(select(AssetProcessingStep).where(AssetProcessingStep.asset_id == final.id))
    assert step is not None
    assert "libsoxr quality=VHQ, 8000 Hz -> 16000 Hz" in step.parameters
    check = db.scalar(select(AudioQcResult).where(AudioQcResult.recording_id == row.recording_id))
    assert check is not None
    assert (check.outcome, check.reason_code) == ("FAIL", "MISSING_TRACK")
    channels = next(c for c in check.checks if c.code == "CHANNELS")
    assert (channels.measured, channels.expected, channels.message) == (
        "1",
        "2",
        "A track is missing",
    )


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
    joined(w, call["id"], tid)
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
    # The provider's file starts after the marks: the whole 4 s file is kept, whatever the
    # clock's resolution (D-113 cutting is tested on its own).
    w["provider"].listed = [session("S9", datetime.now(UTC) + timedelta(seconds=5))]
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

    for who in ("pa", "sa"):
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
    assert w["pa"].get("/api/v1/telephony/analytics").json()["target_minutes_per_day"] is not None
    # Figures and the spreadsheet are for the people who run the project (D-104): a moderator
    # has neither, only the list of their own calls.
    assert w["mod"].get("/api/v1/telephony/analytics").status_code == 403
    assert w["mod"].get("/api/v1/calls/export").status_code == 403
    mine = w["mod"].get("/api/v1/calls").json()
    assert mine["total"] == 3

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
    assert mod2.get("/api/v1/calls").json()["total"] == 0
    assert mod2.get("/api/v1/telephony/analytics").status_code == 403


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


def test_participant_details_tell_everything_about_the_person_to_those_who_manage_them(
    world: dict[str, Any],
) -> None:
    """The Participants page's View shows the whole person, not only the consent form (D-104):
    profile, who added them, their sessions with recording, minutes, phone calls."""
    w = world
    tid, call = started_and_closed(w)
    # The provider's file starts after the marks: the whole 4 s file is kept, whatever the
    # clock's resolution (D-113 cutting is tested on its own).
    w["provider"].listed = [session("PD1", datetime.now(UTC) + timedelta(seconds=5))]
    due_now(w, call["id"])
    sweep(w)
    w["new_task"]()  # a second session, not called yet
    base = f"/api/v1/projects/{w['project_id']}/participants"

    got = w["pa"].get(f"{base}/{w['a']['id']}/details")
    assert got.status_code == 200, got.text
    d = got.json()
    person = d["participant"]
    assert (person["participant_code"], person["display_label"], person["language_code"]) == (
        w["a"]["participant_code"],
        "Asha",
        "hi",
    )
    assert person["phone"] == A_PHONE  # a project admin may see contact details
    assert d["added_by"] == "pa"
    assert [p["code"] for p in d["projects"]] == ["PHONE"]
    assert d["removed"] is None
    assert d["link"] is None  # no personal link was made
    assert d["sessions_total"] == 2
    newest, first = d["sessions"]
    assert (first["task_id"], first["slot"], first["mode"], first["status"]) == (
        tid,
        "A",
        "TELEPHONY",
        "RECORDED",
    )
    assert first["other_participant_code"] == w["b"]["participant_code"]
    assert first["moderator"] == "mod"
    assert "consent_status" not in first, "consent is the form's answer, shown once (D-129)"
    assert (first["recordings"], first["recording_seconds"], first["phone_calls"]) == (1, 4.0, 1)
    assert (newest["status"], newest["recordings"]) == ("IN_PROGRESS", 0)
    assert d["minutes"]["conversations"] == 1
    assert d["calls"] == {
        "total": 1,
        "recorded": 1,
        "last_at": d["calls"]["last_at"],
        "last_state": "RECORDED",
    }
    # They agreed on their page before the task was made (D-129).
    assert (d["consent_form"]["answered"], d["consent_form"]["current"]["status"]) == (
        True,
        "GIVEN",
    )

    # Participant B is in the same sessions as B; phone calls ring A only.
    b = w["pa"].get(f"{base}/{w['b']['id']}/details").json()
    assert [s["slot"] for s in b["sessions"]] == ["B", "B"]
    assert b["calls"] is None

    # Only those who manage participants: not the moderator of the session, not another one.
    assert w["mod"].get(f"{base}/{w['a']['id']}/details").status_code == 403
    assert w["api"]("mod2@example.org").get(f"{base}/{w['a']['id']}/details").status_code == 403
    # A removed participant says so, with who and why.
    extra = w["pa"].post(
        base,
        json={"display_label": "Chitra", "language_code": "hi", "email": "chitra@example.org"},
    )
    assert extra.status_code == 201, extra.text
    cid = extra.json()["id"]
    fresh = w["pa"].get(f"{base}/{cid}/details").json()
    assert (fresh["sessions"], fresh["sessions_total"], fresh["calls"]) == ([], 0, None)
    gone = w["pa"].post(f"{base}/{cid}/delete", json={"reason": "Asked to be removed"})
    assert gone.status_code == 200, gone.text
    after = w["sa"].get(f"{base}/{cid}/details")
    assert after.status_code == 200, after.text
    removed = after.json()["removed"]
    assert (removed["by"], removed["reason"]) == ("pa", "Asked to be removed")
    assert after.json()["participant"]["deleted"] is True


def test_provider_traffic_is_passed_on_for_managers_only(world: dict[str, Any]) -> None:
    w = world
    t = w["pa"].get("/api/v1/telephony/provider-traffic?days=7")
    assert t.status_code == 200
    assert t.json()["available"] is True
    assert t.json()["data"] == {"10": 3, "11": 5}
    assert w["mod"].get("/api/v1/telephony/provider-traffic").status_code == 403


def test_the_moderator_rings_participant_b_into_the_call_once_a_is_on(
    world: dict[str, Any],
) -> None:
    """D-111: after A is confirmed on the line, the moderator rings B through the attach
    campaign; it is on record, limited, and only the task's moderator can do it."""
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    ring = f"/api/v1/calls/{call['id']}/call-b"

    # Not before A is confirmed on the call.
    early = w["mod"].post(ring)
    assert (early.status_code, early.json()["error"]["code"]) == (409, "A_NOT_JOINED")
    assert w["provider"].attaches == []

    joined_a = w["mod"].post(f"/api/v1/calls/{call['id']}/checklist", json={"item": "A_JOINED"})
    assert joined_a.status_code == 200
    # Not by a project admin, not by another moderator.
    assert w["pa"].post(ring).status_code == 403
    assert w["api"]("mod2@example.org").post(ring).status_code in (403, 404)

    rung = w["mod"].post(ring)
    assert rung.status_code == 200, rung.text
    body = rung.json()
    assert (body["b_dial_attempts"], body["b_dial_status"], body["b_phone_hint"]) == (
        1,
        "ACCEPTED",
        B_PHONE[-2:],
    )
    assert body["state"] == "DIALLING"
    # B's number, on the moderator's seat; A was rung once, by the other campaign.
    assert w["provider"].attaches == [(B_PHONE, SEAT)]
    assert w["provider"].dials == [(A_PHONE, SEAT)]
    kinds = [e["kind"] for e in body["events"]]
    assert kinds[-2:] == ["B_DIAL_REQUESTED", "B_DIAL_ACCEPTED"]
    text = " ".join(e["text"] for e in body["events"])
    assert B_PHONE not in text
    assert B_PHONE[3:] not in text

    # Refused by TxContact, then not reachable: said so, and B can be rung again.
    w["provider"].attach_answer = DialResult(False, 200, "")
    refused = w["mod"].post(ring).json()
    assert (refused["b_dial_status"], refused["events"][-1]["kind"]) == ("REFUSED", "B_DIAL_FAILED")
    w["provider"].attach_answer = ProviderError("TxContact did not answer in time (attach)")
    lost = w["mod"].post(ring).json()
    assert lost["b_dial_status"] == "UNREACHABLE"
    assert "may still ring" in lost["events"][-1]["text"]
    # Three rings in one call at most.
    w["provider"].attach_answer = DialResult(True, 200, "ok", "B2")
    many = w["mod"].post(ring)
    assert (many.status_code, many.json()["error"]["code"]) == (429, "TOO_MANY_CALLS")
    assert len(w["provider"].attaches) == 3

    # Once the call is closed or cancelled, B is not rung.
    cancelled = w["mod"].post(
        f"/api/v1/calls/{call['id']}/cancel", json={"reason": "OTHER", "note": "test"}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert w["mod"].post(ring).json()["error"]["code"] == "CALL_STATE"


def test_the_recording_mark_waits_for_consent_that_counts(world: dict[str, Any]) -> None:
    """D-119: on a call, Start recording is refused while someone's consent does not count (here
    one withdrawn before D-129), and allowed once they agree again."""
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    for item in ("A_JOINED", "B_JOINED"):
        w["mod"].post(f"/api/v1/calls/{call['id']}/checklist", json={"item": item})
    withdrawn_before_d129(w, w["b"])
    no = w["mod"].post(f"/api/v1/calls/{call['id']}/recording/start")
    assert (no.status_code, no.json()["error"]["code"]) == (409, "CONSENT_MISSING")
    assert "Participant B " in no.json()["error"]["message"]
    agree(w["pa"], w["project_id"], w["b"]["id"])
    assert w["mod"].post(f"/api/v1/calls/{call['id']}/recording/start").status_code == 200


def test_the_moderator_marks_the_conversation_once_both_are_on_the_line(
    world: dict[str, Any],
) -> None:
    """D-113: Start recording needs A and B on the call; Stop needs a start; the call cannot be
    closed without a start, and a call closed without Stop ends the recording there."""
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    base = f"/api/v1/calls/{call['id']}"
    early = w["mod"].post(f"{base}/recording/start")
    assert (early.status_code, early.json()["error"]["code"]) == (409, "CHECKLIST_INCOMPLETE")
    stop_first = w["mod"].post(f"{base}/recording/stop")
    assert (stop_first.status_code, stop_first.json()["error"]["code"]) == (
        409,
        "RECORDING_NOT_STARTED",
    )
    for item in ("A_JOINED", "B_JOINED"):
        w["mod"].post(f"{base}/checklist", json={"item": item})
    unmarked = w["mod"].post(f"{base}/close", json={})
    assert (unmarked.status_code, unmarked.json()["error"]["code"]) == (
        409,
        "RECORDING_NOT_STARTED",
    )
    # Only the task's moderator marks it.
    assert w["pa"].post(f"{base}/recording/start").status_code == 403
    started = w["mod"].post(f"{base}/recording/start").json()
    assert started["record_started_at"]
    assert started["record_stopped_at"] is None
    assert started["events"][-1]["kind"] == "RECORDING_STARTED"
    # Starting again replaces the start.
    again = w["mod"].post(f"{base}/recording/start").json()
    assert datetime.fromisoformat(again["record_started_at"]) >= datetime.fromisoformat(
        started["record_started_at"]
    )
    assert "replaced" in again["events"][-1]["text"]
    stopped = w["mod"].post(f"{base}/recording/stop").json()
    assert datetime.fromisoformat(stopped["record_stopped_at"]) >= datetime.fromisoformat(
        stopped["record_started_at"]
    )
    assert stopped["events"][-1]["kind"] == "RECORDING_STOPPED"
    # A second Stop changes nothing.
    assert datetime.fromisoformat(
        w["mod"].post(f"{base}/recording/stop").json()["record_stopped_at"]
    ) == datetime.fromisoformat(stopped["record_stopped_at"])
    closed = w["mod"].post(f"{base}/close", json={}).json()
    assert datetime.fromisoformat(closed["record_stopped_at"]) == datetime.fromisoformat(
        stopped["record_stopped_at"]
    )

    # Not stopped by hand: the recording ends when the call is closed.
    tid2 = w["new_task"]()
    call2 = start(w, tid2)
    joined(w, call2["id"], tid2)
    closed2 = w["mod"].post(f"/api/v1/calls/{call2['id']}/close", json={}).json()
    at = datetime.fromisoformat
    assert at(closed2["record_stopped_at"]) == at(closed2["closed_at"])


def test_the_delivery_file_is_cut_to_the_marks_and_the_original_kept_whole(
    world: dict[str, Any],
) -> None:
    """D-113: the provider's 4-second file starts 1 s before Start recording; Stop comes 1.5 s
    after it. With the 1-second margin the delivery file holds 0 s to 3.5 s."""
    w = world
    _, call = started_and_closed(w)
    db = w["db"]
    row = db.get(Call, call["id"])
    begin = row.record_started_at
    row.record_stopped_at = begin + timedelta(seconds=1.5)
    db.commit()
    w["provider"].listed = [session("CUT1", begin - timedelta(seconds=1))]
    due_now(w, call["id"])
    sweep(w)
    db.expire_all()
    row = db.get(Call, call["id"])
    assert row.state == "RECORDED", row.failure_detail
    assets = {
        a.kind: a
        for a in db.scalars(select(AudioAsset).where(AudioAsset.recording_id == row.recording_id))
    }
    assert assets["PROVIDER_ORIGINAL_MIXED"].duration_ms == 4000  # kept whole
    assert abs(assets["TELEPHONY_DERIVED_PCM"].duration_ms - 3500) <= 5
    texts = [e.detail for e in db.scalars(select(CallEvent).where(CallEvent.call_id == row.id))]
    assert any("cut to the moderator's recording marks: 0.0 s to 3.5 s" in t for t in texts)


def test_effective_speech_is_measured_on_the_cut_file(world: dict[str, Any]) -> None:
    """D-148: the delivered file is the one measured. The provider's file talks for 3 s; Stop
    comes 0.5 s after Start, so with the 1-second margins the delivery file holds 0 s to 2.5 s:
    2.5 s of speech, where the provider's whole file has 3 s."""
    w = world
    _, call = started_and_closed(w)
    db = w["db"]
    row = db.get(Call, call["id"])
    begin = row.record_started_at
    row.record_stopped_at = begin + timedelta(seconds=0.5)
    db.commit()
    w["provider"].listed = [session("CUT2", begin - timedelta(seconds=1))]
    due_now(w, call["id"])
    sweep(w)
    db.expire_all()
    row = db.get(Call, call["id"])
    assert row.state == "RECORDED", row.failure_detail
    assets = {
        a.kind: a
        for a in db.scalars(select(AudioAsset).where(AudioAsset.recording_id == row.recording_id))
    }
    assert assets["PROVIDER_ORIGINAL_MIXED"].effective_ms == 3000
    delivered = assets["TELEPHONY_DERIVED_PCM"]
    assert abs(delivered.duration_ms - 2500) <= 5
    assert delivered.effective_ms == 2500
    assert (delivered.longest_pause_ms, delivered.pauses_ms) == (0, [])


def test_the_window_is_found_or_the_whole_call_kept_with_the_reason() -> None:
    begin = datetime(2026, 11, 16, 10, 0, 0, tzinfo=UTC)

    def window(
        start_s: float, stop_s: float, file_start: datetime | None, frames: int = 80_000
    ) -> fetch.Window:
        c = Call(
            record_started_at=begin + timedelta(seconds=start_s),
            record_stopped_at=begin + timedelta(seconds=stop_s),
        )
        s = session("W", begin)
        s = ProviderSession(**{**s.__dict__, "start": file_start})
        return fetch.recording_window(c, s, frames, 8000, 1.0)

    inside = window(3, 7, begin)
    assert (inside.first_frame, inside.last_frame, inside.cut) == (16_000, 64_000, True)
    assert not window(0.5, 9.5, begin).cut  # margins reach both ends: whole file
    late = window(20, 30, begin)  # marks after the file ends
    assert (late.cut, late.last_frame) == (False, 80_000)
    assert "fall outside" in late.description
    unknown = window(3, 7, None)
    assert (unknown.cut, unknown.description) == (
        False,
        "whole call kept: the provider gave no start time",
    )


def test_only_the_answer_on_the_consent_form_lets_a_participant_be_called(
    world: dict[str, Any],
) -> None:
    """Calling follows the participant's own answer on the consent form (D-129): with consent
    that no longer counts (withdrawn before D-129) they are not called, a consent noted by the
    moderator for the session (as before D-129) changes nothing, agreeing again does."""
    w = world
    give_seat(w)
    tid = w["new_task"]()
    withdrawn_before_d129(w, w["a"])
    w["db"].add(
        ConsentRecord(
            participant_id=uuid.UUID(w["a"]["id"]),
            project_id=uuid.UUID(w["project_id"]),
            task_id=uuid.UUID(tid),
            status="GIVEN",
            method="VERBAL_NOTED",
            policy_version="1",
            captured_by=uuid.UUID(w["mod_id"]),
        )
    )
    w["db"].commit()
    no = w["mod"].post(f"/api/v1/tasks/{tid}/calls")
    assert (no.status_code, no.json()["error"]["code"]) == (409, "CONSENT_MISSING")
    assert "Participant A " in no.json()["error"]["message"]
    assert w["provider"].dials == []
    agree(w["pa"], w["project_id"], w["a"]["id"])
    assert w["mod"].post(f"/api/v1/tasks/{tid}/calls").status_code == 201


def test_participant_b_without_a_phone_number_is_named_as_b(world: dict[str, Any]) -> None:
    w = world
    give_seat(w)
    tid = w["new_task"]()
    call = start(w, tid)
    w["mod"].post(f"/api/v1/calls/{call['id']}/checklist", json={"item": "A_JOINED"})
    w["db"].execute(
        update(Participant)
        .where(Participant.id == uuid.UUID(w["b"]["id"]))
        .values(phone_e164_enc=None, phone_hash=None, phone_hint=None)
    )
    w["db"].commit()
    answer = w["mod"].post(f"/api/v1/calls/{call['id']}/call-b")
    assert (answer.status_code, answer.json()["error"]["code"]) == (409, "PHONE_MISSING")
    assert answer.json()["error"]["message"] == "Participant B has no phone number"


def test_a_seat_password_is_kept_encrypted_and_shown_only_to_a_super_admin_or_its_owner(
    world: dict[str, Any],
) -> None:
    """D-130: the seat's password (the moderator's Chirp sign-in) is stored encrypted and is in no
    answer and no audit entry; a Super Admin or the moderator can show it, and each showing is
    audited. Left out it is kept, empty it is removed, and removing the seat removes it too."""
    w = world
    db = w["db"]
    seat = f"/api/v1/users/{w['mod_id']}/telephony-agent"
    secret = "chirp-test-pass-71"
    saved = w["sa"].put(seat, json={"agent_id": SEAT, "password": secret})
    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        "user_id": w["mod_id"],
        "telephony_agent_id": SEAT,
        "has_password": True,
    }
    db.expire_all()
    stored = db.get(User, uuid.UUID(w["mod_id"])).telephony_password_enc
    assert stored is not None
    assert secret not in stored, "encrypted at rest"
    assert w["app"].state.cipher.decrypt(stored) == secret
    # The user page and the moderator's own account say that a password is saved, nothing more.
    user_page = w["sa"].get(f"/api/v1/users/{w['mod_id']}")
    assert user_page.json()["telephony_has_password"] is True
    me = w["mod"].get("/api/v1/auth/me")
    assert (me.json()["telephony_agent_id"], me.json()["telephony_has_password"]) == (SEAT, True)
    assert all(secret not in r.text for r in (saved, user_page, me))

    # Shown to a Super Admin and to the moderator, each time on record without the password.
    assert w["sa"].get(f"{seat}/password").json() == {"password": secret}
    assert w["mod"].get("/api/v1/auth/phone-seat/password").json() == {"password": secret}
    shown = db.scalars(
        select(AuditLog)
        .where(AuditLog.action == "user.seat_password_shown")
        .order_by(AuditLog.created_at)
    ).all()
    sa_id = db.scalar(select(User.id).where(User.email == "sa@example.org"))
    assert [(a.actor_id, a.entity_id) for a in shown] == [
        (sa_id, w["mod_id"]),
        (uuid.UUID(w["mod_id"]), w["mod_id"]),
    ]

    # Nobody else: not a project admin, not another moderator (whose own seat has none).
    assert w["pa"].get(f"{seat}/password").status_code == 403
    mod2 = w["api"]("mod2@example.org")
    assert mod2.get(f"{seat}/password").status_code == 403
    assert mod2.get("/api/v1/auth/phone-seat/password").status_code == 404

    # Left out: kept, also when the seat number changes. Empty: removed.
    assert w["sa"].put(seat, json={"agent_id": "70002"}).json()["has_password"] is True
    assert w["sa"].get(f"{seat}/password").json() == {"password": secret}
    cleared = w["sa"].put(seat, json={"agent_id": "70002", "password": ""})
    assert cleared.json()["has_password"] is False
    assert w["sa"].get(f"{seat}/password").status_code == 404
    # A seat removed takes its password with it; a password needs a seat.
    assert w["sa"].put(seat, json={"agent_id": "70002", "password": "next-pass"}).status_code == 200
    gone = w["sa"].put(seat, json={"agent_id": ""})
    assert gone.json() == {
        "user_id": w["mod_id"],
        "telephony_agent_id": None,
        "has_password": False,
    }
    lonely = w["sa"].put(seat, json={"agent_id": "", "password": "next-pass"})
    assert (lonely.status_code, lonely.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    changes = db.scalars(select(AuditLog).where(AuditLog.action == "user.agent_seat")).all()
    assert len(changes) == 5
    every_entry = " ".join(
        f"{a.before_summary} {a.after_summary}" for a in db.scalars(select(AuditLog))
    )
    assert secret not in every_entry
    assert "next-pass" not in every_entry

    # Rotating the encryption key (D-088) takes the seat password along.
    w["sa"].put(seat, json={"agent_id": SEAT, "password": secret})
    new_key = Fernet.generate_key().decode()
    url = w["app"].state.settings.database_url.get_secret_value()
    counts = cli.rotate_keys(
        build_settings(database_url=url, data_encryption_key=f"{new_key},{TEST_FERNET_KEY}")
    )
    assert counts["phone seat password"] == 1
    db.expire_all()
    rotated = db.get(User, uuid.UUID(w["mod_id"])).telephony_password_enc
    assert FieldCipher(new_key).decrypt(rotated) == secret


def test_the_status_tells_the_moderators_page_how_to_sign_the_seat_in(
    world: dict[str, Any],
) -> None:
    """D-133: the moderator's page signs their own seat in to TxContact's agent manager. The
    status gives the address (by default TxContact's own over WebSocket), the tenant, the caller's
    seat and the extension it signs in on, and whether a password is saved. The page takes the
    password itself from the own-seat request, on record as a sign-in rather than a showing."""
    w = world
    status = "/api/v1/telephony/status"
    line = {
        "url": "wss://amber.txcontact.com/txagentmanager/",
        "tenant_id": "desicrew",
        "agent_id": None,
        "extension": None,
        "has_password": False,
    }
    assert w["mod"].get(status).json()["seat_login"] == line
    seat = f"/api/v1/users/{w['mod_id']}/telephony-agent"
    assert w["sa"].put(seat, json={"agent_id": SEAT, "password": "line-pass-71"}).status_code == 200
    line |= {"agent_id": SEAT, "extension": SEAT, "has_password": True}
    assert w["mod"].get(status).json()["seat_login"] == line
    # Another person's status carries their own seat, never this one.
    assert w["pa"].get(status).json()["seat_login"]["agent_id"] is None

    taken = w["mod"].get("/api/v1/auth/phone-seat/password?purpose=line")
    assert taken.json() == {"password": "line-pass-71"}
    db = w["db"]
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_id == w["mod_id"])).all()
    assert "user.phone_line_signed_in" in actions
    assert "user.seat_password_shown" not in actions
    assert w["mod"].get("/api/v1/auth/phone-seat/password?purpose=other").status_code == 422

    # The settings: an extension rule with {seat}, another address and tenant, or switched off
    # (the seat is then made Ready in the Chirp app, as before).
    app = w["app"]
    app.state.settings = app.state.settings.model_copy(
        update={
            "txcontact_extension": "9{seat}",
            "txcontact_agent_url": "wss://agents.example.org/txagentmanager/",
            "txcontact_tenant_id": "other",
        }
    )
    assert w["mod"].get(status).json()["seat_login"] == line | {
        "url": "wss://agents.example.org/txagentmanager/",
        "tenant_id": "other",
        "extension": f"9{SEAT}",
    }
    app.state.settings = app.state.settings.model_copy(update={"txcontact_seat_login": False})
    assert w["mod"].get(status).json() == {
        "configured": True,
        "provider": "TXCONTACT",
        "seat_login": None,
    }


AHEAD = pytest.mark.parametrize("world", [0, 330], ids=["on-time", "330-min-ahead"], indirect=True)


@AHEAD
def test_txcontact_times_running_ahead_are_corrected_and_the_call_cut_to_its_marks(
    world: dict[str, Any],
) -> None:
    """D-131: TxContact listed a call placed at 14:52 IST as starting at 20:22 IST, 5 h 30 min
    ahead. With TXCONTACT_CLOCK_AHEAD_MINUTES at 330 the call is still found and the delivery
    file cut to the moderator's marks; at 0 (a provider on time) all is as before."""
    w = world
    ahead = timedelta(minutes=w["app"].state.settings.txcontact_clock_ahead_minutes)
    _, call = started_and_closed(w)
    (listed,) = fake_txcontact.CALLS
    shown = datetime.fromisoformat(listed["sl_start_time"]).replace(tzinfo=fake_txcontact.IST)
    real = shown - ahead  # when TxContact's file really starts
    db = w["db"]
    row = db.get(Call, call["id"])
    assert abs(real - row.dialled_at) < timedelta(seconds=5)
    # Start recording 3 s into the provider's 12 s file and stop 3 s later: with the 1 s margin
    # the delivery file holds 2 s to 7 s.
    row.record_started_at = real + timedelta(seconds=3)
    row.record_stopped_at = real + timedelta(seconds=6)
    db.commit()
    due_now(w, call["id"])
    sweep(w)
    row = db.get(Call, call["id"])
    assert (row.state, row.provider_session_id) == ("RECORDED", listed["sl_session_id"]), (
        row.failure_detail
    )
    assets = {
        a.kind: a
        for a in db.scalars(select(AudioAsset).where(AudioAsset.recording_id == row.recording_id))
    }
    assert assets["PROVIDER_ORIGINAL_MIXED"].duration_ms == 12000  # kept whole
    assert abs(assets["TELEPHONY_DERIVED_PCM"].duration_ms - 5000) <= 5
    texts = [e.detail for e in db.scalars(select(CallEvent).where(CallEvent.call_id == row.id))]
    assert any("cut to the moderator's recording marks: 2.0 s to 7.0 s" in t for t in texts)
    assert db.get(Recording, row.recording_id).started_at == real + timedelta(seconds=2)


@AHEAD
def test_an_evening_call_is_found_under_the_date_txcontact_files_it(
    world: dict[str, Any],
) -> None:
    """D-131: 5 h 30 min ahead, TxContact files a call made at 18:40 IST under the next date; the
    platform searches the date TxContact uses (at 0, the same date, as before)."""
    w = world
    ahead = w["app"].state.settings.txcontact_clock_ahead_minutes
    _, call = started_and_closed(w)
    real = datetime(2026, 11, 17, 18, 40, tzinfo=fake_txcontact.IST)
    fake_txcontact.CALLS[:] = [fake_txcontact.row("EVENING", "9876543210", SEAT, real)]
    assert fake_txcontact.CALLS[0]["sl_start_date"] == ("2026-11-18" if ahead else "2026-11-17")
    w["db"].execute(
        update(Call)
        .where(Call.id == call["id"])
        .values(
            dialled_at=real - timedelta(seconds=20),
            record_started_at=real + timedelta(seconds=3),
            record_stopped_at=real + timedelta(seconds=6),
            closed_at=real + timedelta(minutes=1),
        )
    )
    w["db"].commit()
    due_now(w, call["id"])
    sweep(w)
    row = w["db"].get(Call, call["id"])
    assert (row.state, row.provider_session_id) == ("RECORDED", "EVENING"), row.failure_detail


def test_the_dates_searched_are_the_dates_txcontact_files_calls_under() -> None:
    """D-131: TxContact files a call under the date on its own clock: 5 h 30 min ahead, a call at
    18:40 IST is under the next date, and one across its midnight under both."""
    ist = ZoneInfo("Asia/Kolkata")

    def days(ahead: int, dialled: datetime, minutes: int) -> list[date]:
        c = Call(dialled_at=dialled, closed_at=dialled + timedelta(minutes=minutes))
        return fetch.provider_days(build_settings(txcontact_clock_ahead_minutes=ahead), c)

    evening = datetime(2026, 11, 17, 18, 40, tzinfo=ist)
    assert days(0, evening, 10) == [date(2026, 11, 17)]
    assert days(330, evening, 10) == [date(2026, 11, 18)]
    # 18:25 to 18:35 IST is 23:55 to 00:05 on TxContact's clock: both dates are searched.
    across = datetime(2026, 11, 17, 18, 25, tzinfo=ist)
    assert days(330, across, 10) == [date(2026, 11, 17), date(2026, 11, 18)]
    # As before at 0: a call just after midnight is looked for under the day before as well.
    after_midnight = datetime(2026, 11, 18, 0, 1, tzinfo=ist)
    assert days(0, after_midnight, 5) == [date(2026, 11, 17), date(2026, 11, 18)]
