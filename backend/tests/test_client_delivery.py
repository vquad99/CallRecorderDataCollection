"""The client's delivery format for exports (D-149): the project settings that name the files, the
exact folders, names and values of a bundle and of one task's ZIP, MISSING.csv, and who may make
one (the format holds speaker details).

The fixture: a phone call (T000001, CON001) and a face-to-face recording (T000002, CON002) of the
same two speakers in an Upload project. Speaker 001 (P000001, native PIN 570001) has an uploaded
signed consent form (PDF) and address proof (JPEG); speaker 002 (P000002, native PIN 576101)
agreed online only and has no address proof. The phone call has device details for both and a QC
decision (002's breath sounds unanswered); the face-to-face one has 001's device details only and
no QC decision yet.

Requirements: EXP-001, EXP-002, EXP-003, EXP-004, EXP-005, EXP-006, EXP-008, PROJ-011
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from sqlalchemy import select, update

from app.core.errors import AppError
from app.modules.audio_qc import checklist
from app.modules.audio_qc.models import AudioQcResult
from app.modules.audit.models import AuditLog
from app.modules.exports import bundle, client
from app.modules.participants.models import Participant
from app.modules.projects import delivery
from app.modules.projects.models import Project
from app.modules.tasks.models import TaskDeviceDetail
from tests import test_telephony
from tests.conftest import Api, make_user, set_status
from tests.test_export_jobs import ask, layout, opened, recorded, rows_of
from tests.test_telephony import A_PHONE, B_PHONE

audio = test_telephony.audio
world = test_telephony.world

FRONTEND_DELIVERY = (
    Path(__file__).resolve().parents[2] / "frontend/src/features/projects/delivery.ts"
)
CONSENT_PDF = b"%PDF-1.4 signed consent form of speaker 001"
PROOF_JPEG = b"\xff\xd8\xff\xe0 address proof of speaker 001"
KONKANI = "कोंकणी"

# Speaker-level files and the tables every bundle in the client's format has.
COMMON = [
    "MISSING.csv",
    "README.txt",
    "SHA256SUMS",
    "manifest.csv",
    "manifest.json",
    "participants.csv",
    "recordings.csv",
    "recordings.json",
    "schema/manifest.schema.json",
    "schema/recordings.schema.json",
    "schema/speaker-conversation-metadata.schema.json",
    "schema/speaker-metadata.schema.json",
]
AUDIO = [
    "face_to_face/audio/001_002_570001_576101_CON002.wav",
    "telephonic/audio/001_002_570001_576101_CON001.wav",
]
METADATA = [
    "SPEAKER_METADATA_README.json",
    "face_to_face/metadata/001_CON002_570001_METADATA.json",
    "face_to_face/metadata/002_CON002_576101_METADATA.json",
    "speakers/001_570001_METADATA.json",
    "speakers/001_consent.pdf",
    "speakers/001_speaker_proof.jpg",
    "speakers/002_576101_METADATA.json",
    "speakers/002_consent.html",
    "telephonic/metadata/001_CON001_570001_METADATA.json",
    "telephonic/metadata/002_CON001_576101_METADATA.json",
]
MISSING = [
    ["002", "P000002", "", "", "consent", "No signed consent form uploaded: "
     "the online consent record is given instead"],
    ["002", "P000002", "", "", "speaker_proof", "No address proof uploaded"],
    ["002", "P000002", "CON001", "T000001", "speaker_breath_sounds", "Not answered"],
    ["001", "P000001", "CON002", "T000002", "qc_answers",
     "No QC decision with checklist answers yet"],
    ["002", "P000002", "CON002", "T000002", "device_details", "Not filled"],
    ["002", "P000002", "CON002", "T000002", "qc_answers",
     "No QC decision with checklist answers yet"],
]  # fmt: skip
SPEAKER_QC_KEYS = [i["key"] for i in checklist.DEFAULT_QC_CHECKLIST if i["scope"] == "speaker"]


# ------------------------------------------------------------------- names (no database)


def test_speaker_and_conversation_ids_follow_the_chosen_style() -> None:
    assert delivery.speaker_id("P000123", "NUMBER") == "123"
    assert delivery.speaker_id("P000007", "NUMBER") == "007"
    assert delivery.speaker_id("P1234567", "NUMBER") == "1234567"
    assert delivery.speaker_id("P000123", "CODE") == "P000123"
    assert delivery.conversation_id("T000045", "CON_NUMBER") == "CON045"
    assert delivery.conversation_id("T001234", "CON_NUMBER") == "CON1234"
    assert delivery.conversation_id("T000045", "CODE") == "T000045"
    values = {
        "a": "001",
        "b": "002",
        "a_pin": "570001",
        "b_pin": "576101",
        "conversation": "CON001",
    }
    assert delivery.audio_name(delivery.DEFAULT_AUDIO_NAME_PATTERN, values) == (
        "001_002_570001_576101_CON001"
    )
    assert delivery.audio_name("{conversation}-{b}", values) == "CON001-002"


@pytest.mark.parametrize(
    ("pattern", "says"),
    [
        ("", "Write the audio file name"),
        ("   ", "Write the audio file name"),
        ("{a}_{b}_{a_pin}_{b_pin}", "needs {conversation}"),
        ("{speaker}_{conversation}", "{speaker} is not a token"),
        ("{A}_{conversation}", "{A} is not a token"),
        ("{a} {conversation}", "only letters, digits, _ and -"),
        ("{a}.{conversation}", "only letters, digits, _ and -"),
        ("../{conversation}", "only letters, digits, _ and -"),
        ("{{conversation}}", "only letters, digits, _ and -"),
        ("x" * 90 + "_{conversation}", "at most 100 characters"),
    ],
)
def test_a_wrong_audio_name_is_refused_in_words(pattern: str, says: str) -> None:
    with pytest.raises(AppError) as refused:
        delivery.clean_audio_name_pattern(pattern)
    assert refused.value.code == "INVALID_AUDIO_NAME_PATTERN"
    assert refused.value.status_code == 422
    assert says in refused.value.message


def test_a_good_audio_name_is_kept_without_its_spaces() -> None:
    assert delivery.clean_audio_name_pattern(" {conversation}-{a}_{b} ") == "{conversation}-{a}_{b}"
    assert delivery.clean_audio_name_pattern("NLTM_{a_pin}_{conversation}") == (
        "NLTM_{a_pin}_{conversation}"
    )


def test_the_frontend_copy_of_the_clients_audio_name_matches() -> None:
    """The Rules tab's preview and its Reset button use the same name as the server."""
    source = FRONTEND_DELIVERY.read_text(encoding="utf-8")
    found = re.search(r'CLIENT_AUDIO_NAME = "([^"]+)"', source)
    assert found is not None
    assert found.group(1) == delivery.DEFAULT_AUDIO_NAME_PATTERN


# ------------------------------------------------------------------- the project settings

BODY_KEYS = (
    "name",
    "description",
    "allows_telephony",
    "allows_face_to_face",
    "target_telephony_hours_per_day",
    "target_face_to_face_hours_per_day",
    "phone_visibility_policy",
    "consent_policy_version",
    "consent_text",
)
SETTINGS = ("export_layout", "speaker_id_style", "conversation_id_style", "audio_name_pattern")


def _save(api: Api, project_id: str, **changes: Any) -> Any:
    current = api.get(f"/api/v1/projects/{project_id}").json()
    return api.patch(
        f"/api/v1/projects/{project_id}", json={**{k: current[k] for k in BODY_KEYS}, **changes}
    )


@pytest.mark.db
def test_the_export_settings_start_as_the_clients_and_save_with_the_project(
    world: dict[str, Any],
) -> None:
    made = world["sa"].post(
        "/api/v1/projects",
        json={"name": "Konkani", "allows_telephony": False, "allows_face_to_face": True},
    )
    assert made.status_code == 201, made.text
    assert {k: made.json()[k] for k in SETTINGS} == {
        "export_layout": "CLIENT",
        "speaker_id_style": "NUMBER",
        "conversation_id_style": "CON_NUMBER",
        "audio_name_pattern": "{a}_{b}_{a_pin}_{b_pin}_{conversation}",
    }
    pa, pid = world["pa"], world["project_id"]
    saved = _save(
        pa,
        pid,
        export_layout="PLATFORM",
        speaker_id_style="CODE",
        conversation_id_style="CODE",
        audio_name_pattern="  {conversation}-{a}-{b} ",
    )
    assert saved.status_code == 200, saved.text
    assert {k: saved.json()[k] for k in SETTINGS} == {
        "export_layout": "PLATFORM",
        "speaker_id_style": "CODE",
        "conversation_id_style": "CODE",
        "audio_name_pattern": "{conversation}-{a}-{b}",
    }
    entry = world["db"].scalar(
        select(AuditLog)
        .where(AuditLog.action == "project.updated")
        .order_by(AuditLog.created_at.desc())
    )
    assert entry is not None
    assert '"export_layout": "PLATFORM"' in (entry.after_summary or "")
    assert '"export_layout": "CLIENT"' in (entry.before_summary or "")
    # Left out, they keep the project's own (an Overview save does not reset them).
    kept = _save(pa, pid, description="Konkani talk")
    assert kept.status_code == 200, kept.text
    assert kept.json()["audio_name_pattern"] == "{conversation}-{a}-{b}"
    assert kept.json()["export_layout"] == "PLATFORM"
    # Wrong ones are refused.
    wrong = _save(pa, pid, audio_name_pattern="{a}_{b}")
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (422, "INVALID_AUDIO_NAME_PATTERN")
    assert "needs {conversation}" in wrong.json()["error"]["message"]
    assert wrong.json()["error"]["details"] == [{"field": "audio_name_pattern"}]
    for bad in ({"export_layout": "ZIP"}, {"speaker_id_style": "NAME"}):
        refused = _save(pa, pid, **bad)
        assert (refused.status_code, refused.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    # Only the people who manage the project change them.
    assert _save(world["mod"], pid, export_layout="CLIENT").status_code == 403


# ------------------------------------------------------------------- the bundle


@pytest.fixture
def cw(world: dict[str, Any]) -> dict[str, Any]:
    """The two recordings described at the top, in the client's format."""
    layout(world, "CLIENT")
    w = recorded(world)
    db = w["db"]
    a, b = w["a"], w["b"]
    assert (a["participant_code"], b["participant_code"]) == ("P000001", "P000002")
    db.execute(update(Participant).where(Participant.id == a["id"]).values(native_pincode="570001"))
    db.execute(
        update(Participant)
        .where(Participant.id == b["id"])
        .values(native_pincode="576101", native_language=KONKANI)
    )
    db.execute(update(Project).where(Project.id == w["project_id"]).values(consent_mode="UPLOAD"))
    db.commit()
    people = f"{w['base']}/participants/{a['id']}/documents"
    for kind, body, kind_type in (
        ("consent-form", CONSENT_PDF, "application/pdf"),
        ("address-proof", PROOF_JPEG, "image/jpeg"),
    ):
        sent = w["pa"].post(
            f"{people}/{kind}",
            content=body,
            headers={"Content-Type": kind_type, "X-File-Name": "Asha%20scan"},
        )
        assert sent.status_code == 201, sent.text

    project = db.get_one(Project, uuid.UUID(w["project_id"]))
    entries = {
        e.mode: e
        for e in bundle.select_entries(
            db, project, bundle.Selection(scope="finished"), "Asia/Kolkata"
        )
    }
    phone, face = entries["TELEPHONY"], entries["FACE_TO_FACE"]
    assert (phone.task_code, face.task_code) == ("T000001", "T000002")
    now = datetime.now(UTC)
    for task_id, pid, values in (
        (phone.task_id, a["id"], ("Samsung", "Galaxy M31", False, True, False)),
        (phone.task_id, b["id"], ("Nokia", "105", False, False, True)),
        (face.task_id, a["id"], ("Apple", "iPhone 13", True, False, False)),
    ):
        make, model, bluetooth, wired, loudspeaker = values
        db.add(
            TaskDeviceDetail(
                task_id=task_id,
                participant_id=uuid.UUID(pid),
                device_make=make,
                device_model=model,
                bluetooth_earphones=bluetooth,
                wired_earphones=wired,
                loudspeaker_on=loudspeaker,
                filled_at=now,
            )
        )
    # Two QC decisions on the phone call: the newest one's answers are delivered.
    items = checklist.items_of(project.qc_checklist)
    sides = [
        {"side": "A", "participant_id": a["id"], "participant_code": "P000001"},
        {"side": "B", "participant_id": b["id"], "participant_code": "P000002"},
    ]
    for when, intelligible in ((now - timedelta(hours=1), "no"), (now, "yes")):
        answers = checklist.Answers(
            speakers={
                "A": {k: "no" for k in SPEAKER_QC_KEYS} | {"speech_intelligible": intelligible},
                "B": {k: "yes" for k in SPEAKER_QC_KEYS if k != "speaker_breath_sounds"},
            }
        )
        db.add(
            AudioQcResult(
                recording_id=phone.recording_id,
                task_id=phone.task_id,
                project_id=project.id,
                automated=False,
                outcome="FAIL" if intelligible == "no" else "PASS",
                checklist=checklist.snapshot(items, answers, sides, consent_check=False),
                created_at=when,
            )
        )
    db.commit()
    w["phone"], w["face"] = phone, face
    return w


def _json(archive: zipfile.ZipFile, name: str) -> Any:
    return json.loads(archive.read(name).decode("utf-8"))


def _missing(archive: zipfile.ZipFile) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(archive.read("MISSING.csv").decode("utf-8-sig"))))
    assert rows[0] == client.MISSING_COLUMNS
    return rows[1:]


@pytest.mark.db
def test_a_bundle_in_the_clients_format_has_its_folders_names_and_values(
    cw: dict[str, Any],
) -> None:
    pa, base = cw["pa"], cw["base"]
    summary = pa.get(f"{base}/export/summary", params={"scope": "finished"}).json()
    assert (summary["layout"], summary["missing"], summary["recordings"]) == ("CLIENT", 6, 2)
    job = ask(cw, content="both")
    assert job["state"] == "READY", job
    assert (job["missing"], job["filters"]["layout"]) == (6, "CLIENT")
    archive = opened(cw, job)
    names = sorted(archive.namelist())
    assert names == sorted(COMMON + AUDIO + METADATA)
    assert archive.testzip() is None
    assert job["files"] == len(names)

    # Audio and uploaded documents go in as they are; JSON files and tables are deflated.
    methods = {i.filename: i.compress_type for i in archive.infolist()}
    stored = {*AUDIO, "speakers/001_consent.pdf", "speakers/001_speaker_proof.jpg"}
    assert {n for n, m in methods.items() if m == zipfile.ZIP_STORED} == stored
    for name in AUDIO:
        assert archive.read(name)[:4] == b"RIFF"
    assert archive.read("speakers/001_consent.pdf") == CONSENT_PDF
    assert archive.read("speakers/001_speaker_proof.jpg") == PROOF_JPEG

    # A speaker's details: text, lowercase keys in the client's order, UTF-8 as it is.
    first = _json(archive, "speakers/001_570001_METADATA.json")
    assert list(first) == list(client.SPEAKER_KEYS)
    assert first == {
        "speaker_id": "001",
        "age": "34",
        "gender": "female",
        "current_residing_district": "North Goa",
        "current_residing_state": "Goa",
        "current_residing_pincode": "403001",
        "native_state": "Goa",
        "native_district": "North Goa",
        "native_language": "Konkani",
        "native_pincode": "570001",
        "educational_background": "Bachelor's Degree",
        "medium_of_education": "English",
        "speaker_state_during_recording": "Goa",
        "speaker_district_during_recording": "North Goa",
        "speaker_pincode_during_recording": "403001",
    }
    second = archive.read("speakers/002_576101_METADATA.json")
    assert KONKANI.encode("utf-8") in second
    assert json.loads(second)["native_pincode"] == "576101"

    # One speaker in one conversation: device, call type, then the newest QC answers by key.
    phone_a = _json(archive, "telephonic/metadata/001_CON001_570001_METADATA.json")
    assert list(phone_a) == [*client.CONVERSATION_KEYS, *SPEAKER_QC_KEYS]
    assert {k: phone_a[k] for k in client.CONVERSATION_KEYS} == {
        "speaker_id": "001",
        "device_make": "Samsung",
        "device_model": "Galaxy M31",
        "call_type": "Telephonic",
        "is_bluetooth_earphones_used": "No",
        "if_wired_earphones_used": "Yes",
        "is_loudspeaker_switched_on": "No",
    }
    assert phone_a["speech_intelligible"] == "Yes"  # the newer decision's answer
    assert phone_a["echo_in_audio"] == "No"
    phone_b = _json(archive, "telephonic/metadata/002_CON001_576101_METADATA.json")
    assert (phone_b["is_loudspeaker_switched_on"], phone_b["speaker_breath_sounds"]) == ("Yes", "")
    face_b = _json(archive, "face_to_face/metadata/002_CON002_576101_METADATA.json")
    assert face_b == {
        "speaker_id": "002",
        "device_make": "",
        "device_model": "",
        "call_type": "Face-to-face",
        "is_bluetooth_earphones_used": "",
        "if_wired_earphones_used": "",
        "is_loudspeaker_switched_on": "",
        **dict.fromkeys(SPEAKER_QC_KEYS, ""),
    }
    assert (
        _json(archive, "face_to_face/metadata/001_CON002_570001_METADATA.json")[
            "is_bluetooth_earphones_used"
        ]
        == "Yes"
    )

    # What each key means, the QC answers by their question.
    meanings = _json(archive, "SPEAKER_METADATA_README.json")
    assert list(meanings) == [
        *client.SPEAKER_KEYS,
        *[k for k in client.CONVERSATION_KEYS if k != "speaker_id"],
        *SPEAKER_QC_KEYS,
    ]
    assert meanings["speech_intelligible"] == "QC answer, Yes or No: Is speech intelligible?"

    # What is not on file, by speaker and conversation.
    assert _missing(archive) == MISSING

    # The online consent record of the speaker without a signed form: by ID and code only.
    record = archive.read("speakers/002_consent.html").decode()
    assert "Consent record of speaker 002" in record
    assert "P000002" in record
    assert "Consent given" in record

    # The tables carry the new names.
    rows = {r["conversation_id"]: r for r in rows_of(archive, "recordings.csv")}
    assert list(rows) == ["CON001", "CON002"]
    assert "metadata_file" not in rows["CON001"]
    assert {k: rows["CON001"][k] for k in ("task_code", "speaker_a_id", "speaker_b_id")} == {
        "task_code": "T000001",
        "speaker_a_id": "001",
        "speaker_b_id": "002",
    }
    assert rows["CON001"]["audio_file"] == "telephonic/audio/001_002_570001_576101_CON001.wav"
    assert rows["CON002"]["speaker_b_metadata_file"] == (
        "face_to_face/metadata/002_CON002_576101_METADATA.json"
    )
    assert rows_of(archive, "participants.csv") == [
        {
            "participant_code": "P000001",
            "speaker_id": "001",
            "language": "hi",
            "dialect": "",
            "recordings_in_export": "2",
            "metadata_file": "speakers/001_570001_METADATA.json",
            "consent_file": "speakers/001_consent.pdf",
            "proof_file": "speakers/001_speaker_proof.jpg",
        },
        {
            "participant_code": "P000002",
            "speaker_id": "002",
            "language": "hi",
            "dialect": "",
            "recordings_in_export": "2",
            "metadata_file": "speakers/002_576101_METADATA.json",
            "consent_file": "speakers/002_consent.html",
            "proof_file": "",
        },
    ]

    # Every JSON file matches the schema that travels with it.
    schemas = {n: _json(archive, n) for n in names if n.startswith("schema/")}
    for schema in schemas.values():
        jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_json(archive, "recordings.json"), schemas["schema/recordings.schema.json"])
    manifest = _json(archive, "manifest.json")
    jsonschema.validate(manifest, schemas["schema/manifest.schema.json"])
    for name in names:
        if name.startswith("speakers/") and name.endswith("_METADATA.json"):
            jsonschema.validate(
                _json(archive, name), schemas["schema/speaker-metadata.schema.json"]
            )
        elif name.endswith("_METADATA.json"):
            jsonschema.validate(
                _json(archive, name), schemas["schema/speaker-conversation-metadata.schema.json"]
            )

    # Every file is in the manifest with its checksum, and SHA256SUMS says the same.
    assert manifest["counts"]["missing"] == 6
    assert manifest["selection"]["layout"] == "CLIENT"
    listed = {f["path"]: f for f in manifest["files"]}
    assert set(listed) == set(names) - {"manifest.json", "manifest.csv", "SHA256SUMS"}
    assert listed["speakers/001_speaker_proof.jpg"]["kind"] == "proof"
    assert listed["speakers/001_570001_METADATA.json"]["kind"] == "speaker"
    for line in archive.read("SHA256SUMS").decode().splitlines():
        digest, path = line.split("  ", 1)
        assert hashlib.sha256(archive.read(path)).hexdigest() == digest, path
    readme = archive.read("README.txt").decode()
    assert "the client's delivery format" in readme
    assert "for example 001_002_570001_576101_CON001.wav" in readme
    assert "6 items missing" in readme

    # No name, phone number or email address anywhere (D-094, EXP-004).
    for name in names:
        if name.endswith(".wav"):
            continue
        body = archive.read(name)
        for secret in (b"Asha", b"Bina", A_PHONE[-10:].encode(), B_PHONE[-10:].encode()):
            assert secret not in body, (name, secret)
        assert b"@example.org" not in body, name

    entry = cw["db"].scalar(select(AuditLog).where(AuditLog.action == "export.requested"))
    assert entry is not None
    assert json.loads(entry.after_summary)["missing"] == 6


@pytest.mark.db
def test_audio_only_and_metadata_only_hold_their_part(cw: dict[str, Any]) -> None:
    sound = ask(cw, content="audio")
    archive = opened(cw, sound)
    assert sorted(archive.namelist()) == sorted(COMMON + AUDIO)
    assert _missing(archive) == []
    assert sound["missing"] == 0
    assert [r["speaker_a_metadata_file"] for r in rows_of(archive, "recordings.csv")] == ["", ""]

    details = ask(cw, content="metadata")
    archive = opened(cw, details)
    assert sorted(archive.namelist()) == sorted(COMMON + METADATA)
    assert _missing(archive) == MISSING
    assert [r["audio_file"] for r in rows_of(archive, "recordings.csv")] == ["", ""]


@pytest.mark.db
def test_a_missing_pin_code_is_000000_in_names_and_listed(cw: dict[str, Any]) -> None:
    db = cw["db"]
    db.execute(
        update(Participant).where(Participant.id == cw["a"]["id"]).values(native_pincode=None)
    )
    db.commit()
    pin_row = ["001", "P000001", "", "", "native_pincode", "Not given: 000000 in file names"]
    sound = ask(cw, content="audio")
    archive = opened(cw, sound)
    assert sorted(n for n in archive.namelist() if n.endswith(".wav")) == [
        "face_to_face/audio/001_002_000000_576101_CON002.wav",
        "telephonic/audio/001_002_000000_576101_CON001.wav",
    ]
    assert _missing(archive) == [pin_row]
    assert sound["missing"] == 1

    archive = opened(cw, ask(cw, content="metadata"))
    assert "speakers/001_000000_METADATA.json" in archive.namelist()
    assert "telephonic/metadata/001_CON001_000000_METADATA.json" in archive.namelist()
    assert _json(archive, "speakers/001_000000_METADATA.json")["native_pincode"] == ""
    assert _missing(archive) == [pin_row, *MISSING]


@pytest.mark.db
def test_the_ids_and_the_audio_name_follow_the_project_settings(cw: dict[str, Any]) -> None:
    db = cw["db"]
    db.execute(
        update(Project)
        .where(Project.id == cw["project_id"])
        .values(
            speaker_id_style="CODE",
            conversation_id_style="CODE",
            audio_name_pattern="NLTM-{conversation}-{b}-{a}",
        )
    )
    db.commit()
    archive = opened(cw, ask(cw, content="both"))
    names = archive.namelist()
    assert "telephonic/audio/NLTM-T000001-P000002-P000001.wav" in names
    assert "face_to_face/metadata/P000001_T000002_570001_METADATA.json" in names
    assert "speakers/P000002_576101_METADATA.json" in names
    assert "speakers/P000001_consent.pdf" in names
    assert _json(archive, "speakers/P000001_570001_METADATA.json")["speaker_id"] == "P000001"
    assert "for example NLTM-T000001-P000002-P000001.wav" in archive.read("README.txt").decode()


@pytest.mark.db
def test_an_online_project_delivers_the_online_consent_records(cw: dict[str, Any]) -> None:
    """The uploaded scan counts only in an Upload project (D-144); online, each speaker's own
    answers are the consent delivered."""
    db = cw["db"]
    db.execute(update(Project).where(Project.id == cw["project_id"]).values(consent_mode="ONLINE"))
    db.commit()
    archive = opened(cw, ask(cw, content="metadata"))
    consent = sorted(n for n in archive.namelist() if "_consent." in n)
    assert consent == ["speakers/001_consent.html", "speakers/002_consent.html"]
    assert _missing(archive) == MISSING[1:]


@pytest.mark.db
def test_one_tasks_zip_has_the_same_layout(cw: dict[str, Any]) -> None:
    """D-136's download from the task page, in the client's format."""
    face = cw["face"]
    set_status(cw["db"], face.task_id, "APPROVED")
    answer = cw["pa"].get(f"/api/v1/tasks/{face.task_id}/export")
    assert answer.status_code == 200, answer.text
    archive = zipfile.ZipFile(io.BytesIO(answer.content))
    assert sorted(archive.namelist()) == sorted(
        [n for n in COMMON + AUDIO + METADATA if "CON001" not in n]
    )
    assert _missing(archive) == [m for m in MISSING if m[2] != "CON001"]
    entry = cw["db"].scalar(
        select(AuditLog).where(
            AuditLog.action == "task.exported", AuditLog.entity_id == str(face.task_id)
        )
    )
    assert entry is not None
    assert json.loads(entry.after_summary)["missing"] == 5


@pytest.mark.db
def test_only_people_who_see_speaker_details_get_the_clients_format(cw: dict[str, Any]) -> None:
    """A Client Viewer may export (exports.create) but sees no speaker details (D-143): the
    client's format, which holds them, is refused to them, asked for or downloaded (D-149)."""
    base, db = cw["base"], cw["db"]
    project = db.get_one(Project, uuid.UUID(cw["project_id"]))
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[project])
    cv: Api = cw["api"]("cv@example.org")
    for refused in (
        cv.get(f"{base}/export/summary"),
        cv.post(f"{base}/exports", json={"content": "audio", "scope": "finished"}),
    ):
        assert refused.status_code == 403, refused.text
        assert "client's delivery format" in refused.json()["error"]["message"]
    made = ask(cw, content="audio")
    assert cv.get(f"{base}/exports").status_code == 200
    link = f"{base}/exports/{made['id']}/download-link"
    assert cw["pa"].post(link).status_code == 200
    assert cv.post(link).status_code == 403
    # The moderator may not export at all.
    assert cw["mod"].get(f"{base}/export/summary").status_code == 403
    # In the platform's layout the Client Viewer exports as before.
    layout(cw, "PLATFORM")
    assert cv.get(f"{base}/export/summary", params={"scope": "finished"}).json()["recordings"] == 2
    # A bundle keeps the layout it was made in: the one in the client's format stays theirs.
    assert cv.post(link).status_code == 403
