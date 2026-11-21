"""Effective speech and long pauses (D-148): measured on generated files with known content, the
automatic check PAUSES, the recording's line on the task page, the details file, and the backfill
of files made before (recovery sweep and CLI).

Requirements: AQC-003, AQC-010, AUDIO-018
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile
from sqlalchemy import select, update

from app import cli
from app.modules.audio_qc import rules as qc
from app.modules.audio_qc import speech as backfill
from app.modules.projects.models import Project, ProjectAudioRule
from app.modules.recordings import media, worker_dispatch
from app.modules.recordings.models import AudioAsset
from tests import test_recordings
from tests.conftest import Api
from tests.test_recordings import BUCKET, START, put

RATE = 16_000
WINDOW = 20  # ms, media.FRAME_SECONDS


def _tone(seconds: float, freq: float = 440.0, amp: float = 0.5) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    return amp * np.sin(2 * np.pi * freq * t)


def _quiet(seconds: float) -> np.ndarray:
    return np.zeros(round(seconds * RATE))


def _wav(tmp: Path, name: str, data: np.ndarray) -> Path:
    path = tmp / name
    soundfile.write(path, data, RATE, subtype="PCM_16", format="WAV")
    return path


def _flags(*parts: tuple[bool, int]) -> np.ndarray:
    """Windows of speech (True) and silence (False), each part a number of milliseconds."""
    return np.concatenate([np.full(ms // WINDOW, on) for on, ms in parts])


# ------------------------------------------------------------------ the measurement, pure


def test_short_gaps_are_speech_and_silence_at_the_ends_is_not_a_pause() -> None:
    speech = media.speech_of(
        _flags(
            (False, 1000),  # before the first word: not a pause
            (True, 500),
            (False, 280),  # a gap between words, under 300 ms: part of the speech
            (True, 500),
            (False, 3500),
            (True, 400),
            (False, 2000),  # after the last word: not a pause
        ),
        WINDOW,
    )
    assert speech == media.Speech(effective_ms=1680, longest_pause_ms=3500, pauses_ms=(3500,))
    assert speech.long_pauses(3000) == 1
    assert speech.long_pauses(4000) == 0


def test_a_click_alone_in_a_pause_does_not_split_it() -> None:
    """A sound shorter than 100 ms on its own is a click, not speech."""
    speech = media.speech_of(
        _flags((True, 1000), (False, 2000), (True, 60), (False, 2000), (True, 1000)), WINDOW
    )
    assert speech == media.Speech(effective_ms=2000, longest_pause_ms=4060, pauses_ms=(4060,))


def test_pauses_under_a_second_are_not_kept_but_the_longest_is_told() -> None:
    speech = media.speech_of(_flags((True, 600), (False, 800), (True, 600)), WINDOW)
    assert speech == media.Speech(effective_ms=1200, longest_pause_ms=800, pauses_ms=())
    nothing = media.speech_of(_flags((False, 2000)), WINDOW)
    assert nothing == media.Speech(effective_ms=0, longest_pause_ms=0, pauses_ms=())


def test_a_mono_file_with_tone_bursts_gives_the_numbers(tmp_path: Path) -> None:
    """1 s quiet, 2 s talk, 0.2 s gap, 2 s talk, 4 s pause, 1.5 s talk, 1.5 s pause, 1 s talk,
    2 s quiet: 6.7 s of speech, pauses of 4 s and 1.5 s."""
    audio = np.concatenate(
        [
            _quiet(1),
            _tone(2),
            _quiet(0.2),
            _tone(2),
            _quiet(4),
            _tone(1.5),
            _quiet(1.5),
            _tone(1),
            _quiet(2),
        ]
    )
    levels = media.measure(_wav(tmp_path, "talk.wav", audio))
    assert levels.speech == media.Speech(
        effective_ms=6700, longest_pause_ms=4000, pauses_ms=(4000, 1500)
    )


def test_a_phone_call_counts_speech_on_either_channel_once(tmp_path: Path) -> None:
    """One speaker per channel (D-101): left talks 0-2 s and 5-6 s, right 2.5-4.5 s and
    5.5-6.5 s; together 5.5 s of speech, the overlap counted once, two pauses of 0.5 s."""
    left, right = _quiet(8), _quiet(8)
    left[: 2 * RATE] = _tone(2)
    left[5 * RATE : 6 * RATE] = _tone(1)
    right[int(2.5 * RATE) : int(4.5 * RATE)] = _tone(2, 1000, 0.25)
    right[int(5.5 * RATE) : int(6.5 * RATE)] = _tone(1, 1000, 0.25)
    levels = media.measure(_wav(tmp_path, "call.wav", np.stack([left, right], axis=1)))
    assert levels.speech == media.Speech(effective_ms=5500, longest_pause_ms=500, pauses_ms=())


def test_effective_speech_is_measured_the_same_on_a_float_original(tmp_path: Path) -> None:
    audio = np.concatenate([_tone(1), _quiet(3.2), _tone(1)])
    path = tmp_path / "original.wav"
    soundfile.write(path, audio, RATE, subtype="FLOAT", format="WAV")
    assert media.measure(path).speech == media.Speech(2000, 3200, (3200,))


# ------------------------------------------------------------------ the automatic check, pure


RULE = qc.Limits(
    sample_rate=RATE,
    bit_depth=16,
    channels=1,
    max_silence_pct=90.0,
    max_clipping_pct=None,
    min_duration_seconds=0,
    max_duration_seconds=None,
)
TALK = np.concatenate([_tone(2), _quiet(4), _tone(2), _quiet(3.5), _tone(2)])


def _pauses_check(path: Path, pauses: qc.Pauses | None) -> tuple[str, qc.Check]:
    measured, error = qc.analyze_file(path)
    checks = qc.evaluate(measured, RULE, decode_error=error, pauses=pauses)
    outcome, _ = qc.outcome_of(checks)
    return outcome, next(c for c in checks if c.code == "PAUSES")


def test_long_pauses_are_shown_by_default(tmp_path: Path) -> None:
    outcome, check = _pauses_check(_wav(tmp_path, "talk.wav", TALK), None)
    assert outcome == "PASS", "shown, not judged: the outcome does not change"
    assert (check.state, check.measured, check.expected) == (
        "INFO",
        "2 over 3 s, longest 4.0 s",
        "Shown, not judged",
    )
    assert check.message == "Effective speech 6 s of 14 s"


def test_long_pauses_ask_for_a_listen_where_the_project_says_so(tmp_path: Path) -> None:
    path = _wav(tmp_path, "talk.wav", TALK)
    outcome, check = _pauses_check(path, qc.Pauses(limit_seconds=3, needs_review=True))
    assert (outcome, check.state, check.reason) == ("NEEDS_REVIEW", "REVIEW", "LONG_PAUSES")
    assert check.expected == "No pause over 3 s"
    assert check.message.endswith("listen to the long pauses")
    # A higher limit: none over it, the check passes.
    outcome, check = _pauses_check(path, qc.Pauses(limit_seconds=5, needs_review=True))
    assert (outcome, check.state, check.measured) == (
        "PASS",
        "PASS",
        "None over 5 s (longest 4.0 s)",
    )
    # Exactly the limit is not over it.
    _, check = _pauses_check(path, qc.Pauses(limit_seconds=4, needs_review=True))
    assert check.measured == "None over 4 s (longest 4.0 s)"


def test_a_file_made_before_the_measurement_says_so() -> None:
    m = qc.Measured(
        container="wav",
        codec="pcm_s16le",
        sample_rate=RATE,
        bit_depth=16,
        channels=1,
        duration_ms=1000,
        size_bytes=32_044,
        sha256="0" * 64,
        peak_dbfs=-6.0,
        rms_dbfs=-9.0,
        clip_pct=0.0,
        silence_pct=0.0,
        dynamic_range_db=1.0,
        content_fingerprint=None,
        speech=None,
    )
    check = next(c for c in qc.evaluate(m, RULE) if c.code == "PAUSES")
    assert (check.state, check.measured) == ("INFO", "Not measured yet")


def test_every_check_has_words_on_the_task_page(tmp_path: Path) -> None:
    """The task page names each check (frontend/src/api/audioQc.ts CHECK_LABELS), PAUSES too."""
    source = (Path(__file__).resolve().parents[2] / "frontend/src/api/audioQc.ts").read_text(
        encoding="utf-8"
    )
    block = source.split("CHECK_LABELS", 1)[1].split("};", 1)[0]
    labels = set(re.findall(r"^\s+([A-Z_]+):", block, re.M))
    measured, _ = qc.analyze_file(_wav(tmp_path, "talk.wav", TALK))
    codes = {c.code for c in qc.evaluate(measured, RULE)}
    assert "PAUSES" in codes
    assert codes <= labels, codes - labels


def test_lengths_read_as_minutes_and_seconds() -> None:
    assert qc.spoken(372_000) == "6 min 12 s"
    assert qc.spoken(45_400) == "45 s"
    assert qc.spoken(0) == "0 s"


# ------------------------------------------------------------------ end to end

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world


@pytest.fixture(autouse=True)
def audio_rule(world: dict[str, Any]) -> None:
    """A face-to-face rule that allows the silence of a conversation with pauses."""
    db = world["db"]
    db.add(
        ProjectAudioRule(
            project_id=world["project"].id,
            mode="FACE_TO_FACE",
            sample_rate=RATE,
            bit_depth=16,
            channels=1,
            max_silence_pct=90,
            max_clipping_pct=None,
            min_duration_seconds=0,
            max_duration_seconds=None,
        )
    )
    db.commit()


def _record_talk(world: dict[str, Any]) -> str:
    """2 s talk, 4 s pause, 2 s talk, 3.5 s pause, 2 s talk (whole seconds per part sent)."""
    mod: Api = world["mod"]
    rid: str = mod.post(f"/api/v1/tasks/{world['task']['id']}/recordings", json=START).json()["id"]
    audio = np.concatenate([TALK, _quiet(0.5)]).astype("<f4")
    parts = [audio[i : i + RATE].tobytes() for i in range(0, len(audio), RATE)]
    for seq, data in enumerate(parts):
        assert put(mod, rid, seq, data).status_code == 200
    done = mod.post(f"/api/v1/recordings/{rid}/complete", json={"chunk_count": len(parts)})
    assert done.status_code == 200, done.text
    return rid


def _delivery(world: dict[str, Any], rid: str) -> AudioAsset:
    db = world["db"]
    db.expire_all()
    asset = db.scalar(
        select(AudioAsset).where(
            AudioAsset.recording_id == uuid.UUID(rid), AudioAsset.kind == "FTF_DERIVED_PCM"
        )
    )
    assert asset is not None
    return asset


def _set_project(world: dict[str, Any], **values: Any) -> None:
    db = world["db"]
    db.execute(update(Project).where(Project.id == world["project"].id).values(**values))
    db.commit()


def test_a_new_recording_is_measured_and_shown_with_its_pauses(world: dict[str, Any]) -> None:
    rid = _record_talk(world)
    asset = _delivery(world, rid)
    assert (asset.effective_ms, asset.longest_pause_ms, asset.pauses_ms) == (
        6000,
        4000,
        [4000, 3500],
    )
    tid = world["task"]["id"]
    listed = world["mod"].get(f"/api/v1/tasks/{tid}/recordings").json()
    file = next(a for a in listed[0]["assets"] if a["kind"] == "FTF_DERIVED_PCM")
    assert (file["effective_ms"], file["longest_pause_ms"]) == (6000, 4000)
    assert (file["long_pauses"], file["pause_limit_seconds"]) == (2, 3)
    one = world["mod"].get(f"/api/v1/recordings/{rid}").json()
    assert next(a for a in one["assets"] if a["kind"] == "FTF_DERIVED_PCM")["long_pauses"] == 2
    # The project's limit changes the count without measuring the file again.
    _set_project(world, pause_limit_seconds=4)
    listed = world["mod"].get(f"/api/v1/tasks/{tid}/recordings").json()
    file = next(a for a in listed[0]["assets"] if a["kind"] == "FTF_DERIVED_PCM")
    assert (file["long_pauses"], file["pause_limit_seconds"]) == (0, 4)
    # The automatic check shows them (INFO: the outcome does not change).
    qc_view = world["pa"].get(f"/api/v1/tasks/{tid}/audio-qc").json()
    automatic = qc_view["results"][0]
    pauses = next(c for c in automatic["checks"] if c["code"] == "PAUSES")
    assert pauses["state"] == "INFO"
    assert pauses["measured"] == "2 over 3 s, longest 4.0 s", "checked with the limit of then"
    assert automatic["outcome"] == "PASS"
    # The details file carries the effective speech of each file.
    body = json.loads(world["pa"].get(f"/api/v1/recordings/{rid}/metadata").text)
    derived = next(f for f in body["files"] if f["kind"] == "FTF_DERIVED_PCM")
    assert (derived["effective_ms"], derived["longest_pause_ms"]) == (6000, 4000)


def test_long_pauses_need_a_listen_in_a_project_that_asks_for_it(world: dict[str, Any]) -> None:
    _set_project(world, long_pauses_need_review=True)
    _record_talk(world)
    tid = world["task"]["id"]
    automatic = world["pa"].get(f"/api/v1/tasks/{tid}/audio-qc").json()["results"][0]
    assert (automatic["outcome"], automatic["reason_code"]) == ("NEEDS_REVIEW", "LONG_PAUSES")
    assert automatic["comment"] == "Listen and decide: pauses"
    # A re-check from the stored file measures it again and says the same.
    world["pa"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "AUDIO_QC"})
    again = world["pa"].post(f"/api/v1/tasks/{tid}/audio-qc/recheck")
    assert again.status_code == 200, again.text
    pauses = next(c for c in again.json()["results"][0]["checks"] if c["code"] == "PAUSES")
    assert (pauses["state"], pauses["measured"]) == ("REVIEW", "2 over 3 s, longest 4.0 s")


def _forget(world: dict[str, Any], asset: AudioAsset) -> None:
    """The file as one made before D-148: no effective speech."""
    db = world["db"]
    db.execute(
        update(AudioAsset)
        .where(AudioAsset.id == asset.id)
        .values(effective_ms=None, longest_pause_ms=None, pauses_ms=None, speech_error=None)
    )
    db.commit()


def test_the_recovery_sweep_measures_files_made_before(world: dict[str, Any], s3: Any) -> None:
    rid = _record_talk(world)
    asset = _delivery(world, rid)
    _forget(world, asset)
    tid = world["task"]["id"]
    listed = world["mod"].get(f"/api/v1/tasks/{tid}/recordings").json()
    file = next(a for a in listed[0]["assets"] if a["kind"] == "FTF_DERIVED_PCM")
    assert (file["effective_ms"], file["long_pauses"]) == (None, None)
    assert worker_dispatch.fill_effective_speech(world["app"]) == 1
    asset = _delivery(world, rid)
    assert (asset.effective_ms, asset.longest_pause_ms, asset.pauses_ms) == (
        6000,
        4000,
        [4000, 3500],
    )
    assert worker_dispatch.fill_effective_speech(world["app"]) == 0, "nothing left to measure"
    # A file gone from storage is noted, not tried again and again.
    _forget(world, asset)
    s3.delete_object(Bucket=BUCKET, Key=asset.storage_key)
    assert worker_dispatch.fill_effective_speech(world["app"]) == 1
    asset = _delivery(world, rid)
    assert (asset.effective_ms, asset.speech_error) == (None, "The file is not in storage")
    assert worker_dispatch.fill_effective_speech(world["app"]) == 0


def test_a_changed_file_is_not_measured(world: dict[str, Any], s3: Any) -> None:
    rid = _record_talk(world)
    asset = _delivery(world, rid)
    _forget(world, asset)
    s3.put_object(Bucket=BUCKET, Key=asset.storage_key, Body=b"overwritten by mistake")
    with world["app"].state.session_factory() as db:
        done = backfill.backfill(db, world["app"].state.storage, world["app"].state.settings, None)
    assert (done.measured, done.failed) == (0, 1)
    assert _delivery(world, rid).speech_error == "The stored file does not match its SHA-256"


def test_the_cli_measures_every_file_left(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    rid = _record_talk(world)
    _forget(world, _delivery(world, rid))
    assert cli.run_backfill_effective_speech(world["app"].state.settings, None) == 0
    out = capsys.readouterr().out
    assert "1 file(s) measured, 0 could not be measured (reason kept on the file), 0 left" in out
    assert _delivery(world, rid).effective_ms == 6000
