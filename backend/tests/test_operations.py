"""Storage and processing efficiency, integrity audits and clean-up (owner's list, O3, O4, O12).

Requirements: STOR-006, STOR-009, STOR-010, AUDIO-019, OPS-004
"""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app import cli
from app.modules.recordings import media, service
from app.modules.recordings.models import AudioAsset
from tests import audio_fixtures as fx
from tests import test_recordings
from tests.test_recordings import BUCKET, START, put

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world


def _recorded(world: dict[str, Any]) -> str:
    rid: str = (
        world["mod"]
        .post(f"/api/v1/tasks/{world['task']['id']}/recordings", json=START)
        .json()["id"]
    )
    for seq in range(2):
        put(world["mod"], rid, seq, fx.tone(1.0).tobytes())
    world["mod"].post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": 2})
    assert world["mod"].get(f"/api/v1/recordings/{rid}").json()["state"] == "READY"
    return rid


def test_a_wav_is_converted_in_place_exactly_like_its_raw_samples(tmp_path: Path) -> None:
    raw = fx.write_raw(tmp_path / "s.f32", fx.interleave(fx.tone(2.0), fx.noise(2.0)))
    media.write_float_wav(raw, tmp_path / "o.wav", fx.RATE, 2)
    info = media.inspect_wav(tmp_path / "o.wav")
    media.resample_to_pcm16(raw, fx.RATE, tmp_path / "a.wav", 2)
    media.resample_to_pcm16(
        tmp_path / "o.wav",
        fx.RATE,
        tmp_path / "b.wav",
        2,
        offset=info.data_offset,
        length=info.data_bytes,
    )
    assert media.sha256_file(tmp_path / "a.wav") == media.sha256_file(tmp_path / "b.wav")


def test_processing_leaves_no_scratch_files(world: dict[str, Any]) -> None:
    _recorded(world)
    work = Path(world["app"].state.settings.media_work_dir)
    assert list(work.iterdir()) == []


def test_the_integrity_audit_finds_every_kind_of_damage(
    world: dict[str, Any],
    s3: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _recorded(world)
    db, storage = world["db"], world["app"].state.storage
    checked, problems = service.verify_assets(db, storage, deep=10)
    assert (checked, problems) == (2, [])
    original, derived = sorted(db.scalars(select_assets()).all(), key=lambda a: a.kind)
    body = s3.get_object(Bucket=BUCKET, Key=original.storage_key)["Body"].read()
    # Same size and label, different content: only a deep check can see it.
    altered = body[:-4] + b"\x00\x00\x80\x3f"
    s3.put_object(
        Bucket=BUCKET, Key=original.storage_key, Body=altered, Metadata={"sha256": original.sha256}
    )
    s3.delete_object(Bucket=BUCKET, Key=derived.storage_key)
    checked, problems = service.verify_assets(db, storage, deep=10)
    assert sorted(p.problem for p in problems) == [
        "content does not match its checksum",
        "missing from storage",
    ]
    settings = world["app"].state.settings
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    assert cli.main(["verify-assets", "--deep", "5"]) == 1
    assert "2 problem(s)" in capsys.readouterr().out


def select_assets() -> Any:
    from sqlalchemy import select

    return select(AudioAsset).where(AudioAsset.deleted_at.is_(None))


def test_orphan_files_are_found_and_removed_but_records_and_backups_are_kept(
    world: dict[str, Any],
    s3: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _recorded(world)
    storage, db = world["app"].state.storage, world["db"]
    storage.put_bytes(
        "VOICE/stray/left-behind.bin",
        b"x" * 10,
        content_type="application/octet-stream",
        sha256="0",
    )
    storage.put_bytes(
        "backups/db/ccp-1.dump", b"y", content_type="application/octet-stream", sha256="0"
    )
    assert service.storage_orphans(db, storage, timedelta(hours=1)) == [], "too new to touch"
    found = service.storage_orphans(db, storage, timedelta(0))
    assert [o.key for o in found] == ["VOICE/stray/left-behind.bin"]
    monkeypatch.setattr(cli, "load_settings", lambda: world["app"].state.settings)
    assert cli.main(["storage-orphans", "--older-than-hours", "0", "--delete"]) == 0
    assert "1 file(s), 10 bytes, deleted" in capsys.readouterr().out
    assert storage.head("VOICE/stray/left-behind.bin") is None
    assert storage.head("backups/db/ccp-1.dump") is not None
    checked, problems = service.verify_assets(db, storage)
    assert (checked, problems) == (2, []), "every recorded file is still there"


def test_scratch_folders_left_by_a_stopped_process_are_removed(world: dict[str, Any]) -> None:
    settings = world["app"].state.settings
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    old, fresh = work / "tmp-crashed", work / "tmp-busy"
    for d in (old, fresh):
        d.mkdir()
        (d / "original.wav").write_bytes(b"0" * 100)
    hours_ago = time.time() - 3 * 3600
    os.utime(old, (hours_ago, hours_ago))
    assert service.clean_work_dir(settings) == 1
    assert not old.exists()
    assert fresh.exists(), "a folder that may still be in use is left alone"
