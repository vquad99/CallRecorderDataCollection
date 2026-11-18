"""A recording the moderator replaced with Record again is marked as such, and only the current
recording reaches QC Executives: the list, its files and its details (D-135).

Requirements: ROLE-006, ROLE-012, STOR-005, AQC-008
"""

from __future__ import annotations

from typing import Any

import pytest

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
