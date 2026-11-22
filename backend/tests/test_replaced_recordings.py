"""A recording the moderator replaced with Record again is marked as such, and only the current
recording reaches QC Executives: the list, its files and its details (D-135).

Requirements: ROLE-006, ROLE-012, STOR-005, AQC-008
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.modules.audio_qc.models import AudioQcResult
from app.modules.recordings import worker_dispatch
from tests import test_audio_qc, test_recordings
from tests.conftest import Api

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world
audio_rule = test_audio_qc.audio_rule


def test_a_replaced_recording_is_marked_and_kept_from_qc(world: dict[str, Any]) -> None:
    tid = world["task"]["id"]
    mod: Api = world["mod"]
    pa: Api = world["pa"]
    first = test_audio_qc._record(world, 4, send=False)
    # The moderator listens and records again (D-092): the newer recording replaces the first.
    again = mod.post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    assert again.status_code == 200, again.text
    second = test_audio_qc._record(world, 6)
    qc = test_audio_qc._assign_qc(world)

    # The project admin and the moderator see both, the replaced one marked.
    for api in (pa, mod):
        listed = api.get(f"/api/v1/tasks/{tid}/recordings").json()
        assert [(r["id"], r["current"]) for r in listed] == [(second, True), (first, False)]
    # The QC Executive sees the current recording only, and it is the one checked.
    seen = qc.get(f"/api/v1/tasks/{tid}/recordings").json()
    assert [(r["id"], r["current"]) for r in seen] == [(second, True)]
    checked = qc.get(f"/api/v1/tasks/{tid}/audio-qc").json()["results"][0]
    assert checked["recording_id"] == second

    def delivery(rid: str) -> str:
        files = pa.get(f"/api/v1/recordings/{rid}").json()["assets"]
        return str(next(a["id"] for a in files if a["kind"] == "FTF_DERIVED_PCM"))

    old, new = delivery(first), delivery(second)
    assert qc.post(f"/api/v1/assets/{new}/url", json={"purpose": "play"}).status_code == 200
    assert qc.get(f"/api/v1/recordings/{second}").json()["current"] is True
    # The replaced recording answers the QC Executive like one that does not exist.
    refused = qc.post(f"/api/v1/assets/{old}/url", json={"purpose": "play"})
    assert (refused.status_code, refused.json()["error"]["message"]) == (404, "File not found")
    assert qc.get(f"/api/v1/recordings/{first}").status_code == 404
    # The people who run the project, and the moderator, still reach it.
    assert pa.get(f"/api/v1/recordings/{first}").json()["current"] is False
    assert pa.post(f"/api/v1/assets/{old}/url", json={"purpose": "download"}).status_code == 200
    assert mod.post(f"/api/v1/assets/{old}/url", json={"purpose": "play"}).status_code == 200
    assert pa.get(f"/api/v1/recordings/{first}/metadata").status_code == 200
    assert pa.get(f"/api/v1/recordings/{first}/consent-form").status_code == 200


def test_qc_checks_and_decides_the_current_recording_only(world: dict[str, Any]) -> None:
    """TASK-06: the first recording missed its automatic check and was replaced. The sweep never
    checks the replaced one; a check of it made anyway is not what QC reads, and the decision is
    stored on the current recording, so the client delivery finds it."""
    tid = world["task"]["id"]
    mod: Api = world["mod"]
    db = world["db"]
    first = test_audio_qc._record(world, 4, send=False)

    def automatic(rid: str) -> list[AudioQcResult]:
        db.expire_all()
        return list(
            db.scalars(
                select(AudioQcResult).where(
                    AudioQcResult.recording_id == uuid.UUID(rid), AudioQcResult.automated.is_(True)
                )
            )
        )

    for result in automatic(first):  # the process stopped before the check
        db.delete(result)
    db.commit()
    again = mod.post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
    assert again.status_code == 200, again.text
    second = test_audio_qc._record(world, 6, send=False)
    assert worker_dispatch.check_pending_audio(world["app"]) == 0, "the replaced one is left"
    assert automatic(first) == []
    [checked] = automatic(second)
    # A check of the replaced recording made later (as the sweep did before) is not used.
    db.add(
        AudioQcResult(
            id=uuid.uuid4(),
            recording_id=uuid.UUID(first),
            task_id=checked.task_id,
            project_id=checked.project_id,
            automated=True,
            outcome="FAIL",
            reason_code="MISSING_AUDIO",
            comment="",
            created_at=datetime.now(UTC) + timedelta(minutes=1),
        )
    )
    db.commit()
    sent = mod.post(f"/api/v1/tasks/{tid}/transition", json={"to": "AUDIO_QC"})
    assert sent.status_code == 200, sent.text
    qc = test_audio_qc._assign_qc(world)
    shown = qc.get(f"/api/v1/tasks/{tid}/audio-qc").json()["results"]
    assert [(r["recording_id"], r["automated"]) for r in shown] == [(second, True)]
    decided = qc.post(
        f"/api/v1/tasks/{tid}/audio-qc/decision",
        json=test_audio_qc.passing(qc, tid, comment="Clear speech"),
    )
    assert decided.status_code == 200, decided.text
    db.expire_all()
    decision = db.scalar(select(AudioQcResult).where(AudioQcResult.automated.is_(False)))
    assert str(decision.recording_id) == second
