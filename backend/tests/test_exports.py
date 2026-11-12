"""Project exports (D-094): audio, metadata, both or a progress report, for the project as a whole.

Requirements: EXP-001, EXP-002, EXP-004, EXP-005, EXP-008
"""

from __future__ import annotations

import csv
import io
import zipfile
from typing import Any

import pytest

from tests import test_audio_qc, test_recordings
from tests.conftest import Api, make_user

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world
audio_rule = test_audio_qc.audio_rule


@pytest.mark.db
def test_a_project_exports_audio_metadata_both_or_progress(world: dict[str, Any]) -> None:
    tid = world["task"]["id"]
    test_audio_qc._record(world)
    qc = test_audio_qc._assign_qc(world)
    assert (
        qc.post(f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"}).status_code
        == 200
    )
    pa: Api = world["pa"]
    assert pa.post(f"/api/v1/tasks/{tid}/transition", json={"to": "APPROVED"}).status_code == 200
    base = f"/api/v1/projects/{world['project'].id}/export"

    summary = pa.get(f"{base}/summary", params={"content": "audio"}).json()
    assert summary["recordings"] == 1
    assert summary["audio_bytes"] > 0
    assert summary["file_name"].startswith("audio_VOICE_")

    def archive(content: str) -> zipfile.ZipFile:
        got = pa.get(base, params={"content": content})
        assert got.status_code == 200, got.text
        assert got.headers["content-type"] == "application/zip"
        return zipfile.ZipFile(io.BytesIO(got.content))

    audio = archive("audio").namelist()
    assert [n.split("/")[0] for n in audio] == ["audio", "manifest.csv"]
    meta = archive("metadata").namelist()
    assert sorted(n.split("/")[0] for n in meta) == ["consent", "manifest.csv", "metadata"]
    both = archive("both")
    assert sorted(n.split("/")[0] for n in both.namelist()) == [
        "audio",
        "consent",
        "manifest.csv",
        "metadata",
    ]
    meta_name = next(n for n in both.namelist() if n.startswith("metadata/"))
    assert b'"format": "ccp.recording-metadata/1"' in both.read(meta_name)

    progress = pa.get(base, params={"content": "progress"})
    assert progress.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(progress.text)))
    assert rows[0]["task_code"] == world["task"]["task_code"]
    assert rows[0]["status"] == "APPROVED"
    assert rows[0]["approved_at"]

    # Who may export: the project's admin and client viewer; not its moderator; no other project.
    assert world["mod"].get(f"{base}/summary").status_code == 403
    make_user(world["db"], "cv@example.org", ["CLIENT_VIEWER"], projects=[world["project"]])
    client = world["api"]("cv@example.org")
    assert client.get(f"{base}/summary").json()["recordings"] == 1
    make_user(world["db"], "pa.other@example.org", ["PROJECT_ADMIN"])
    outsider = world["api"]("pa.other@example.org")
    assert outsider.get(f"{base}/summary").status_code == 404


@pytest.mark.db
def test_each_participant_is_credited_with_half_of_an_approved_conversation(
    world: dict[str, Any],
) -> None:
    """D-095: payment follows approved audio, split equally between the two participants."""
    tid = world["task"]["id"]
    pa: Api = world["pa"]
    pid = world["project"].id
    test_audio_qc._record(world)

    def people() -> dict[str, dict[str, Any]]:
        items = pa.get(f"/api/v1/projects/{pid}/participants").json()["items"]
        return {p["display_label"]: p["minutes"] for p in items}

    before = people()
    assert before["Asha"]["conversations"] == 1
    assert before["Asha"]["recorded_minutes"] > 0
    assert before["Asha"]["approved_minutes"] == 0
    assert before["Asha"]["payable_minutes"] == 0

    qc = test_audio_qc._assign_qc(world)
    assert (
        qc.post(f"/api/v1/tasks/{tid}/audio-qc/decision", json={"outcome": "PASS"}).status_code
        == 200
    )
    assert pa.post(f"/api/v1/tasks/{tid}/transition", json={"to": "APPROVED"}).status_code == 200

    after = people()
    for name in ("Asha", "Bina"):
        m = after[name]
        assert m["approved_conversations"] == 1
        assert m["approved_minutes"] == m["recorded_minutes"]
        assert m["payable_minutes"] == pytest.approx(m["approved_minutes"] / 2, abs=0.01)

    got = pa.get(f"/api/v1/projects/{pid}/export", params={"content": "participants"})
    assert got.status_code == 200, got.text
    assert got.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(got.text)))
    assert len(rows) == 2
    for row in rows:
        assert float(row["payable_minutes"]) == pytest.approx(
            float(row["approved_minutes"]) / 2, abs=0.01
        )
    summary = pa.get(
        f"/api/v1/projects/{pid}/export/summary", params={"content": "participants"}
    ).json()
    assert summary["file_name"].startswith("participants_VOICE_")

    # A moderator sees the people, not the payment minutes.
    assert all(
        p["minutes"] is None
        for p in world["mod"].get(f"/api/v1/projects/{pid}/participants").json()["items"]
    )


def test_payable_minutes_are_half_of_approved() -> None:
    from app.modules.exports.minutes import Minutes, as_minutes

    five_minutes = Minutes(conversations=1, recorded_ms=300_000, approved_ms=300_000)
    assert as_minutes(five_minutes.payable_ms) == 2.5
