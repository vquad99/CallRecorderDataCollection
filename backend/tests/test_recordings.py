"""Face-to-face recording end to end against a fake S3 (test-only): start, chunk upload with retry
and checksums, completion, processing into original + derived files, links, retention, usage.

Requirements: FTF-005, FTF-007, FTF-009, FTF-010, FTF-011, FTF-012, FTF-013, FTF-014, STOR-002, STOR-003, STOR-004, STOR-005, STOR-006, STOR-007, STOR-008, STOR-009, STOR-010, STOR-011, STOR-012, AUDIO-015, AUDIO-017, AUDIO-019, GEN-004
"""

import hashlib
import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import pytest
import soundfile
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select, update

from app.main import create_app
from app.modules.recordings import service
from app.modules.recordings.models import AssetProcessingStep, AudioAsset, Recording
from tests.conftest import Api, build_settings, make_participant, make_project, make_user

pytestmark = pytest.mark.db
BUCKET = "ccp-test"
RATE = 48000


@pytest.fixture
def s3() -> Iterator[Any]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture
def app(migrated_db: str, s3: Any, tmp_path: Path) -> Any:
    return create_app(
        build_settings(
            database_url=migrated_db,
            storage_bucket=BUCKET,
            storage_access_key_id="test-key",
            storage_secret_access_key="test-secret",
            media_work_dir=str(tmp_path / "media"),
        )
    )


@pytest.fixture
def world(app: Any) -> Iterator[dict[str, Any]]:
    clients: list[TestClient] = []

    def api(email: str) -> Api:
        client = TestClient(app)
        clients.append(client)
        a = Api(client)
        assert a.login(email).status_code == 200
        return a

    with app.state.session_factory() as db:
        project = make_project(db, "VOICE")
        mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
        make_user(db, "mod2@example.org", ["MODERATOR"], projects=[project])
        make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[project])
        make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[project])
        pa, moderator = api("pa@example.org"), api("mod@example.org")
        a = make_participant(pa, project.id, "Asha")
        b = make_participant(pa, project.id, "Bina")
        task = pa.post(
            "/api/v1/tasks",
            json={
                "project_id": str(project.id),
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": a["id"],
                "participant_b_id": b["id"],
            },
        ).json()
        pa.post(f"/api/v1/tasks/{task['id']}/assign", json={"user_id": str(mod.id)})
        assert (
            moderator.post(
                f"/api/v1/tasks/{task['id']}/transition", json={"to": "IN_PROGRESS"}
            ).status_code
            == 200
        )
        yield {
            "app": app,
            "project": project,
            "task": task,
            "pa": pa,
            "mod": moderator,
            "api": api,
            "db": db,
        }
    for c in clients:
        c.close()


def chunks(seconds_tone: int = 3, seconds_silence: int = 1) -> list[bytes]:
    t = np.arange(seconds_tone * RATE) / RATE
    audio = np.concatenate(
        [
            (0.5 * np.sin(2 * np.pi * 440 * t)).astype("<f4"),
            np.zeros(seconds_silence * RATE, dtype="<f4"),
        ]
    )
    return [audio[i : i + RATE].tobytes() for i in range(0, len(audio), RATE)]


def stereo_chunks(seconds: int = 2) -> tuple[list[bytes], np.ndarray]:
    """Two different tones: 440 Hz on channel 1, 1000 Hz on channel 2, interleaved per frame."""
    t = np.arange(seconds * RATE) / RATE
    frames = np.stack(
        [0.5 * np.sin(2 * np.pi * 440 * t), 0.25 * np.sin(2 * np.pi * 1000 * t)], axis=1
    ).astype("<f4")
    flat = frames.reshape(-1)
    return [flat[i : i + 2 * RATE].tobytes() for i in range(0, len(flat), 2 * RATE)], frames


START = {
    "native_sample_rate": RATE,
    "channel_count": 1,
    "device_channel_count": 1,
    "echo_cancellation": False,
    "noise_suppression": False,
    "auto_gain_control": False,
    "device_label": "Test mic",
    "user_agent": "pytest",
}


def put(api: Api, rid: str, seq: int, data: bytes, sha: str | None = None) -> Any:
    return api.put(
        f"/api/v1/recordings/{rid}/chunks/{seq}",
        content=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Content-SHA256": sha or hashlib.sha256(data).hexdigest(),
        },
    )


def test_storage_not_configured_is_reported_truthfully(db_app: Any, db: Any, new_api: Any) -> None:
    project = make_project(db, "NOSTORE")
    make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    api: Api = new_api()
    api.login("mod@example.org")
    response = api.post("/api/v1/tasks/00000000-0000-0000-0000-000000000001/recordings", json=START)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NOT_CONFIGURED"


def test_full_recording_flow(world: dict[str, Any], s3: Any) -> None:
    mod: Api = world["mod"]
    tid = world["task"]["id"]
    rec = mod.post(f"/api/v1/tasks/{tid}/recordings", json=START)
    assert rec.status_code == 201, rec.text
    rid = rec.json()["id"]
    assert rec.json()["echo_cancellation"] is False
    assert rec.json()["channel_handling"] == "mono"
    parts = chunks()
    for seq, data in enumerate(parts):
        assert put(mod, rid, seq, data).status_code == 200
    assert put(mod, rid, 1, parts[1]).status_code == 200, "retrying the same chunk is harmless"
    assert put(mod, rid, 1, parts[0]).json()["error"]["code"] == "CHUNK_CONFLICT"
    assert put(mod, rid, 9, parts[0], sha="0" * 64).json()["error"]["code"] == "CHECKSUM_MISMATCH"
    done = mod.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": len(parts)})
    assert done.status_code == 200, done.text

    detail = mod.get(f"/api/v1/recordings/{rid}").json()
    assert detail["state"] == "READY", detail
    assets = {a["kind"]: a for a in detail["assets"]}
    original, derived = assets["BROWSER_ORIGINAL"], assets["FTF_DERIVED_PCM"]
    assert (
        original["codec"],
        original["sample_rate"],
        original["bit_depth"],
        original["channels"],
        original["duration_ms"],
    ) == ("pcm_f32le", RATE, 32, 1, 4000)
    assert (
        derived["codec"],
        derived["sample_rate"],
        derived["bit_depth"],
        derived["channels"],
        derived["duration_ms"],
    ) == ("pcm_s16le", 16000, 16, 1, 4000)
    assert derived["parent_asset_id"] == original["id"]
    assert derived["silence_pct"] == pytest.approx(25.0, abs=1.0)
    assert derived["peak_dbfs"] == pytest.approx(-6.0, abs=0.3)

    db = world["db"]
    db.expire_all()
    keys = {a.kind: a.storage_key for a in db.scalars(select(AudioAsset)).all()}
    # Files are filed under the day the recording started (not "today": a test may cross midnight).
    day = f"{db.get(Recording, uuid.UUID(rid)).started_at:%Y/%m/%d}"
    assert keys["FTF_DERIVED_PCM"].startswith(f"VOICE/face-to-face/{day}/{tid}/derived/")
    stored = s3.get_object(Bucket=BUCKET, Key=keys["FTF_DERIVED_PCM"])
    body = stored["Body"].read()
    assert hashlib.sha256(body).hexdigest() == derived["sha256"] == stored["Metadata"]["sha256"]
    info = soundfile.info(io.BytesIO(body))
    assert (info.samplerate, info.channels, info.subtype) == (16000, 1, "PCM_16")
    original_body = s3.get_object(Bucket=BUCKET, Key=keys["BROWSER_ORIGINAL"])["Body"].read()
    assert original_body.endswith(b"".join(parts)), "original keeps the browser samples unchanged"
    remaining = s3.list_objects_v2(
        Bucket=BUCKET,
        Prefix=f"VOICE/face-to-face/{day}/{tid}/original/chunks/",
    ).get("KeyCount", 0)
    assert remaining == 0, "chunks are removed once the original is stored"
    steps = db.scalars(select(AssetProcessingStep.tool)).all()
    assert set(steps) == {"ccp chunk assembly", "python-soxr"}
    # D-092: the task waits for its moderator to listen and send it to QC.
    assert mod.get(f"/api/v1/tasks/{tid}").json()["status"] == "RECORDED"


def _record(world: dict[str, Any], parts: list[bytes], complete: bool = True) -> str:
    mod: Api = world["mod"]
    rid: str = mod.post(f"/api/v1/tasks/{world['task']['id']}/recordings", json=START).json()["id"]
    for seq, data in enumerate(parts):
        put(mod, rid, seq, data)
    if complete:
        mod.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": len(parts)})
    return rid


def test_two_channel_capture_keeps_both_channels_and_derives_from_the_first(
    world: dict[str, Any], s3: Any
) -> None:
    """Microphone channels, captured channels and the delivered mono file are recorded separately,
    and each claim is checked against the actual files (D-048)."""
    mod: Api = world["mod"]
    tid = world["task"]["id"]
    parts, frames = stereo_chunks(2)
    rec = mod.post(
        f"/api/v1/tasks/{tid}/recordings",
        json={**START, "channel_count": 2, "device_channel_count": 2},
    ).json()
    assert (rec["channel_count"], rec["device_channel_count"], rec["channel_handling"]) == (
        2,
        2,
        "first channel of 2",
    )
    rid = rec["id"]
    assert put(mod, rid, 0, parts[0][:12]).json()["error"]["code"] == "INVALID_CHUNK", "half frame"
    assert put(mod, rid, 0, b"").json()["error"]["code"] == "INVALID_CHUNK", "empty"
    for seq, data in enumerate(parts):
        assert put(mod, rid, seq, data).status_code == 200
    assert mod.get(f"/api/v1/recordings/{rid}").json()["saved_seconds"] == 2.0
    mod.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": len(parts)})

    detail = mod.get(f"/api/v1/recordings/{rid}").json()
    assert detail["state"] == "READY", detail
    assets = {a["kind"]: a for a in detail["assets"]}
    original, derived = assets["BROWSER_ORIGINAL"], assets["FTF_DERIVED_PCM"]
    assert (original["codec"], original["channels"], original["duration_ms"]) == (
        "pcm_f32le",
        2,
        2000,
    )
    assert (derived["codec"], derived["sample_rate"], derived["channels"]) == (
        "pcm_s16le",
        16000,
        1,
    )
    assert original["sha256"] != derived["sha256"]

    db = world["db"]
    db.expire_all()
    keys = {a.kind: a.storage_key for a in db.scalars(select(AudioAsset)).all()}
    original_body = s3.get_object(Bucket=BUCKET, Key=keys["BROWSER_ORIGINAL"])["Body"].read()
    assert hashlib.sha256(original_body).hexdigest() == original["sha256"]
    assert original_body.endswith(b"".join(parts)), "both channels kept byte for byte"
    as_read, rate = soundfile.read(io.BytesIO(original_body), dtype="float32")
    assert rate == RATE
    assert as_read.shape == (2 * RATE, 2)
    assert np.array_equal(as_read, frames), "an independent reader sees the same two channels"

    delivered, rate = soundfile.read(
        io.BytesIO(s3.get_object(Bucket=BUCKET, Key=keys["FTF_DERIVED_PCM"])["Body"].read())
    )
    assert rate == 16000
    assert delivered.ndim == 1
    spectrum = np.abs(np.fft.rfft(delivered))
    freqs = np.fft.rfftfreq(len(delivered), 1 / 16000)
    at = {f: spectrum[np.argmin(np.abs(freqs - f))] for f in (440, 1000)}
    assert at[440] > 1000 * at[1000], "channel 1 only; channel 2 is not mixed in"
    params = db.scalars(
        select(AssetProcessingStep.parameters).where(AssetProcessingStep.tool == "python-soxr")
    ).one()
    assert params.startswith("channel 1 of 2 kept")


def test_reprocessing_creates_a_new_identical_version(world: dict[str, Any]) -> None:
    rid = _record(world, chunks(2, 0))
    db = world["db"]
    original_before = db.scalars(
        select(AudioAsset).where(AudioAsset.kind == "BROWSER_ORIGINAL")
    ).one()
    sha_before = original_before.sha256
    service.process(
        db, world["app"].state.settings, world["app"].state.storage, __import__("uuid").UUID(rid)
    )
    derived = db.scalars(
        select(AudioAsset).where(AudioAsset.kind == "FTF_DERIVED_PCM").order_by(AudioAsset.version)
    ).all()
    assert [d.version for d in derived] == [1, 2]
    assert derived[0].sha256 == derived[1].sha256
    originals = db.scalars(select(AudioAsset).where(AudioAsset.kind == "BROWSER_ORIGINAL")).all()
    assert [o.sha256 for o in originals] == [sha_before], "the original is never rewritten"


def test_reprocessing_refuses_a_damaged_stored_original(world: dict[str, Any], s3: Any) -> None:
    rid = _record(world, chunks(1, 0))
    db = world["db"]
    original = db.scalars(select(AudioAsset).where(AudioAsset.kind == "BROWSER_ORIGINAL")).one()
    body = bytearray(s3.get_object(Bucket=BUCKET, Key=original.storage_key)["Body"].read())
    body[-1] ^= 0xFF
    s3.put_object(Bucket=BUCKET, Key=original.storage_key, Body=bytes(body))
    with pytest.raises(RuntimeError, match="no longer matches its checksum"):
        service.process(
            db,
            world["app"].state.settings,
            world["app"].state.storage,
            __import__("uuid").UUID(rid),
        )
    assert world["mod"].get(f"/api/v1/recordings/{rid}").json()["state"] == "FAILED"


def test_missing_chunks_block_completion(world: dict[str, Any]) -> None:
    parts = chunks(3, 0)
    rid = _record(world, [], complete=False)
    put(world["mod"], rid, 0, parts[0])
    put(world["mod"], rid, 2, parts[2])
    response = world["mod"].post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 3})
    assert response.json()["error"]["code"] == "MISSING_CHUNKS"
    assert response.json()["error"]["details"] == [{"missing": [1]}]


def test_interrupted_recording_keeps_saved_audio(world: dict[str, Any]) -> None:
    parts = chunks(3, 0)
    rid = _record(world, parts[:2], complete=False)
    mod: Api = world["mod"]
    stopped = mod.post(
        f"/api/v1/recordings/{rid}/interrupted", json={"reason": "tab closed"}
    ).json()
    assert (stopped["state"], stopped["saved_seconds"]) == ("INTERRUPTED", 2.0)
    assert put(mod, rid, 2, parts[2]).json()["error"]["code"] == "RECORDING_CLOSED"
    assert (
        mod.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 99}).status_code == 200
    )
    detail = mod.get(f"/api/v1/recordings/{rid}").json()
    assert detail["interrupted"] is True
    assert {a["kind"]: a["duration_ms"] for a in detail["assets"]}["FTF_DERIVED_PCM"] == 2000


def test_discard_removes_uploaded_chunks(world: dict[str, Any], s3: Any) -> None:
    rid = _record(world, chunks(2, 0), complete=False)
    assert (
        world["mod"]
        .post(f"/api/v1/recordings/{rid}/discard", json={"reason": "wrong people"})
        .json()["state"]
        == "DISCARDED"
    )
    assert s3.list_objects_v2(Bucket=BUCKET).get("KeyCount", 0) == 0


def test_who_may_record(world: dict[str, Any]) -> None:
    tid = world["task"]["id"]
    assert world["pa"].post(f"/api/v1/tasks/{tid}/recordings", json=START).status_code == 403
    other = world["api"]("mod2@example.org")
    assert other.post(f"/api/v1/tasks/{tid}/recordings", json=START).status_code == 404
    rid = world["mod"].post(f"/api/v1/tasks/{tid}/recordings", json=START).json()["id"]
    second = world["mod"].post(f"/api/v1/tasks/{tid}/recordings", json=START)
    assert second.json()["error"]["code"] == "RECORDING_OPEN"
    assert second.json()["error"]["details"] == [{"recording_id": rid}]


def test_links_are_signed_short_lived_and_permission_checked(world: dict[str, Any]) -> None:
    rid = _record(world, chunks(1, 0))
    detail = world["mod"].get(f"/api/v1/recordings/{rid}").json()
    derived = next(a for a in detail["assets"] if a["kind"] == "FTF_DERIVED_PCM")
    play = world["mod"].post(f"/api/v1/assets/{derived['id']}/url", json={"purpose": "play"}).json()
    assert "X-Amz-Expires=300" in play["url"]
    assert "X-Amz-Signature=" in play["url"]
    assert (
        world["mod"]
        .post(f"/api/v1/assets/{derived['id']}/url", json={"purpose": "download"})
        .status_code
        == 403
    )
    download = (
        world["pa"].post(f"/api/v1/assets/{derived['id']}/url", json={"purpose": "download"}).json()
    )
    assert "response-content-disposition=attachment" in download["url"]
    qc_unassigned = world["api"]("qc@example.org")
    assert (
        qc_unassigned.post(
            f"/api/v1/assets/{derived['id']}/url", json={"purpose": "play"}
        ).status_code
        == 404
    )


def test_retention_deletes_expired_files_and_usage_counts_live_ones(
    world: dict[str, Any], s3: Any
) -> None:
    rid = _record(world, chunks(1, 0))
    db = world["db"]
    from app.modules.projects.models import ProjectRetentionRule

    db.add(
        ProjectRetentionRule(
            project_id=world["project"].id, asset_kind="BROWSER_ORIGINAL", retain_days=1
        )
    )
    db.execute(
        update(AudioAsset)
        .where(AudioAsset.kind == "BROWSER_ORIGINAL")
        .values(created_at=datetime.now(UTC) - timedelta(days=2))
    )
    db.commit()
    before = {r["kind"]: r["files"] for r in world["pa"].get("/api/v1/storage/usage").json()}
    assert before == {"BROWSER_ORIGINAL": 1, "FTF_DERIVED_PCM": 1}
    assert service.apply_retention(db, world["app"].state.storage) == 1
    original = db.scalars(select(AudioAsset).where(AudioAsset.kind == "BROWSER_ORIGINAL")).one()
    assert original.deleted_at is not None
    assert world["app"].state.storage.head(original.storage_key) is None
    after = {r["kind"]: r["files"] for r in world["pa"].get("/api/v1/storage/usage").json()}
    assert after == {"FTF_DERIVED_PCM": 1}
    assert (
        db.scalar(select(Recording.state).where(Recording.id == __import__("uuid").UUID(rid)))
        == "READY"
    )


def test_the_task_list_carries_each_recordings_files(world: dict[str, Any]) -> None:
    """The task page offers Listen and the download from this list (D-092): every recording comes
    with its files, and a second processing shows its newer version too."""
    rid = _record(world, chunks())
    listed = world["mod"].get(f"/api/v1/tasks/{world['task']['id']}/recordings")
    assert listed.status_code == 200, listed.text
    (rec,) = listed.json()
    assert rec["id"] == rid
    assert sorted(a["kind"] for a in rec["assets"]) == ["BROWSER_ORIGINAL", "FTF_DERIVED_PCM"]
    delivery = next(a for a in rec["assets"] if a["kind"] == "FTF_DERIVED_PCM")
    assert (delivery["sample_rate"], delivery["channels"]) == (16000, 1)
    # A file removed by retention is not offered.
    db = world["db"]
    db.execute(
        update(AudioAsset)
        .where(AudioAsset.id == delivery["id"])
        .values(deleted_at=datetime.now(UTC))
    )
    db.commit()
    again = world["mod"].get(f"/api/v1/tasks/{world['task']['id']}/recordings").json()
    assert [a["kind"] for a in again[0]["assets"]] == ["BROWSER_ORIGINAL"]
