"""Recovery (owner's test list, Option H): what happens when something stops part-way.

A server restart mid-recording, processing that never started or was abandoned, two processes
picking the same recording, storage failing during an upload, the worker hand-off failing, and the
sweep that repairs all of these at start-up and on demand.

Requirements: FTF-009, FTF-010, STOR-004, STOR-009, AUDIO-019, GEN-004, OPS-007
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from botocore.exceptions import EndpointConnectionError
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import cli
from app.main import create_app
from app.modules.recordings import service, worker_dispatch
from app.modules.recordings.models import AudioAsset, Recording
from tests import audio_fixtures as fx
from tests import test_recordings
from tests.conftest import Api
from tests.test_recordings import START, put

pytestmark = pytest.mark.db

# Fixtures shared with the recording tests (a real app on a fake S3 and a moderator's task).
app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world

CHUNK = fx.tone(1.0).tobytes()  # START declares 48 kHz mono


def _complete_without_processing(
    world: dict[str, Any], rid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'Complete' succeeds, then the process stops before processing runs."""
    with monkeypatch.context() as m:
        m.setattr(worker_dispatch, "run_inline", lambda *_: None)
        done = world["mod"].post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 1})
        assert done.status_code == 200


def _start(world: dict[str, Any]) -> str:
    rid: str = (
        world["mod"]
        .post(f"/api/v1/tasks/{world['task']['id']}/recordings", json=START)
        .json()["id"]
    )
    return rid


def _age(db: Any, rid: str, state: str, minutes: float) -> None:
    db.execute(
        update(Recording)
        .where(Recording.id == uuid.UUID(rid))
        .values(state=state, updated_at=datetime.now(UTC) - timedelta(minutes=minutes))
    )
    db.commit()


def _state(db: Any, rid: str) -> str:
    db.expire_all()
    return str(db.get(Recording, uuid.UUID(rid)).state)


def test_a_server_restart_mid_recording_loses_nothing(world: dict[str, Any]) -> None:
    rid = _start(world)
    mod: Api = world["mod"]
    for seq in (0, 1):
        assert put(mod, rid, seq, CHUNK).status_code == 200
    # A new server process on the same database and storage; the browser keeps its cookie.
    restarted = create_app(world["app"].state.settings)
    restarted.state.storage = world["app"].state.storage
    client = TestClient(restarted)
    client.cookies.update(mod.client.cookies)
    after = Api(client)
    assert after.get("/api/v1/auth/me").status_code == 200, "a restart signs nobody out"
    assert put(after, rid, 1, CHUNK).status_code == 200, "a part re-sent after the restart is fine"
    assert put(after, rid, 2, CHUNK).status_code == 200
    assert (
        after.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 3}).status_code == 200
    )
    detail = after.get(f"/api/v1/recordings/{rid}").json()
    assert detail["state"] == "READY", detail
    assert detail["saved_seconds"] == 3.0
    client.close()


def test_processing_that_never_started_is_picked_up_by_the_sweep(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = _start(world)
    put(world["mod"], rid, 0, CHUNK)
    _complete_without_processing(world, rid, monkeypatch)
    db = world["db"]
    assert _state(db, rid) == "UPLOADED"
    assert worker_dispatch.recover(world["app"]) == 0, "too recent: may still be on its way"
    _age(db, rid, "UPLOADED", minutes=2)
    assert worker_dispatch.recover(world["app"]) == 1
    assert _state(db, rid) == "READY"
    assert world["mod"].get(f"/api/v1/tasks/{world['task']['id']}").json()["status"] == "AUDIO_QC"


def test_processing_abandoned_mid_way_is_finished_but_live_work_is_left_alone(
    world: dict[str, Any],
) -> None:
    rid = _start(world)
    put(world["mod"], rid, 0, CHUNK)
    world["mod"].post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 1})
    db, a = world["db"], world["app"]
    _age(db, rid, "PROCESSING", minutes=1)  # another process is working on it right now
    assert worker_dispatch.recover(a) == 0
    service.process(db, a.state.settings, a.state.storage, uuid.UUID(rid))  # e.g. a re-delivery
    assert _state(db, rid) == "PROCESSING", "live work is never taken over"
    _age(db, rid, "PROCESSING", minutes=a.state.settings.processing_stale_minutes + 1)
    assert worker_dispatch.recover(a) == 1, "the stopped process's work is finished"
    assert _state(db, rid) == "READY"


def test_two_processes_on_one_recording_produce_one_result(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = _start(world)
    put(world["mod"], rid, 0, CHUNK)
    a = world["app"]
    _complete_without_processing(world, rid, monkeypatch)

    def run() -> None:
        with a.state.session_factory() as db:
            service.process(db, a.state.settings, a.state.storage, uuid.UUID(rid))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: run(), range(4)))
    db = world["db"]
    assert _state(db, rid) == "READY"
    derived = db.scalars(
        select(AudioAsset).where(
            AudioAsset.recording_id == uuid.UUID(rid), AudioAsset.kind == "FTF_DERIVED_PCM"
        )
    ).all()
    assert len(derived) == 1, "processed exactly once"


def test_storage_failing_during_an_upload_asks_the_browser_to_retry(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = _start(world)
    storage = world["app"].state.storage
    real = storage.put_bytes

    def down(*_: Any, **__: Any) -> None:
        raise EndpointConnectionError(endpoint_url="https://storage.example")

    monkeypatch.setattr(storage, "put_bytes", down)
    response = put(world["mod"], rid, 0, CHUNK)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert response.headers["retry-after"] == "5"
    assert world["mod"].get(f"/api/v1/recordings/{rid}").json()["chunks_received"] == 0
    monkeypatch.setattr(storage, "put_bytes", real)
    assert put(world["mod"], rid, 0, CHUNK).status_code == 200, "the retry is stored"
    assert world["mod"].get(f"/api/v1/recordings/{rid}").json()["chunks_received"] == 1


def test_a_failed_hand_off_to_the_worker_is_recovered(world: dict[str, Any]) -> None:
    rid = _start(world)
    put(world["mod"], rid, 0, CHUNK)

    class BrokenQueue:
        def send_task(self, *_: Any, **__: Any) -> None:
            raise ConnectionError("Redis is unreachable")

    a = world["app"]
    a.state.celery = BrokenQueue()
    done = world["mod"].post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 1})
    assert done.status_code == 200, "the moderator's upload is safe; processing follows later"
    assert _state(world["db"], rid) == "UPLOADED"
    a.state.celery = None  # the queue is back (here: in-process processing)
    _age(world["db"], rid, "UPLOADED", minutes=2)
    assert worker_dispatch.recover(a) == 1
    assert _state(world["db"], rid) == "READY"


def test_the_sweep_runs_by_itself_when_the_server_starts(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = _start(world)
    put(world["mod"], rid, 0, CHUNK)
    _complete_without_processing(world, rid, monkeypatch)
    _age(world["db"], rid, "UPLOADED", minutes=5)
    started = create_app(world["app"].state.settings)
    started.state.storage = world["app"].state.storage
    with TestClient(started):  # runs start-up, which starts the sweep
        deadline = time.monotonic() + 30
        while _state(world["db"], rid) != "READY" and time.monotonic() < deadline:
            time.sleep(0.2)
    assert _state(world["db"], rid) == "READY"


def test_recovery_and_retention_commands_do_their_work(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rid = _start(world)
    put(world["mod"], rid, 0, CHUNK)
    _complete_without_processing(world, rid, monkeypatch)
    _age(world["db"], rid, "UPLOADED", minutes=5)
    settings = world["app"].state.settings
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    assert cli.main(["recover-recordings"]) == 0
    assert "1 recording(s) handed to processing" in capsys.readouterr().out
    assert _state(world["db"], rid) == "READY"
    assert cli.main(["retention"]) == 0
    assert "retention: 0 file(s) deleted" in capsys.readouterr().out


def test_a_database_outage_is_answered_as_temporary_not_as_a_crash() -> None:
    from tests.conftest import build_settings

    down = TestClient(create_app(build_settings()))  # points at a closed port
    down.cookies.set("ccp_session", "some-session-token")
    response = down.get("/api/v1/auth/me")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert response.headers["retry-after"] == "5"
    assert down.get("/health/ready").status_code == 503
