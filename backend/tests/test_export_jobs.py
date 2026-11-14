"""Export bundles (D-105): made in the background, every file listed with its checksum, phone and
face-to-face recordings in their own folders, filters, a short-lived link, an end date.

Requirements: EXP-001, EXP-002, EXP-003, EXP-004, EXP-005, EXP-006, EXP-008, EXP-009, EXP-010
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import jsonschema
import pytest
from sqlalchemy import select, text, update

from app.modules.audit.models import AuditLog
from app.modules.exports import bundle, jobs
from app.modules.exports.models import ExportJob
from app.modules.projects.models import Project
from app.modules.recordings.models import AudioAsset
from app.modules.recordings.worker_dispatch import run_export_inline, sweep_exports
from tests import test_audio_qc, test_telephony
from tests.conftest import Api, make_user
from tests.test_telephony import A_PHONE, BUCKET, due_now, session, started_and_closed, sweep

pytestmark = pytest.mark.db

audio = test_telephony.audio
world = test_telephony.world


@pytest.fixture
def w(world: dict[str, Any]) -> dict[str, Any]:
    """One phone recording and one face-to-face recording in the same project, both finished."""
    tid, call = started_and_closed(world)
    world["provider"].listed = [session("EX1", datetime.now(UTC))]
    due_now(world, call["id"])
    sweep(world)
    pa: Api = world["pa"]
    made = pa.post(
        "/api/v1/tasks",
        json={
            "project_id": world["project_id"],
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": world["a"]["id"],
            "participant_b_id": world["b"]["id"],
        },
    )
    assert made.status_code == 201, made.text
    ftf = made.json()["id"]
    assert (
        pa.post(f"/api/v1/tasks/{ftf}/assign", json={"user_id": world["mod_id"]}).status_code == 200
    )
    assert (
        world["mod"].post(f"/api/v1/tasks/{ftf}/transition", json={"to": "IN_PROGRESS"}).status_code
        == 200
    )
    test_audio_qc._record(world, 3, ftf, send=False)
    world["phone_task"], world["ftf_task"] = tid, ftf
    world["base"] = f"/api/v1/projects/{world['project_id']}"
    return world


def ask(w: dict[str, Any], who: str = "pa", **choice: Any) -> dict[str, Any]:
    """Ask for a bundle and wait for it (without a worker it is made right after the answer)."""
    asked = w[who].post(f"{w['base']}/exports", json={"scope": "finished", **choice})
    assert asked.status_code == 202, asked.text
    assert asked.json()["state"] == "QUEUED"
    job: dict[str, Any] = w[who].get(f"{w['base']}/exports/{asked.json()['id']}").json()
    return job


def stored(w: dict[str, Any], job_id: str) -> bytes | None:
    key = w["db"].scalar(select(ExportJob.storage_key).where(ExportJob.id == job_id))
    w["db"].expire_all()
    if key is None:
        return None
    found = w["s3"].list_objects_v2(Bucket=BUCKET).get("Contents", [])
    name = next((o["Key"] for o in found if o["Key"].endswith(key)), None)
    if name is None:
        return None
    body: bytes = w["s3"].get_object(Bucket=BUCKET, Key=name)["Body"].read()
    return body


def opened(w: dict[str, Any], job: dict[str, Any]) -> zipfile.ZipFile:
    data = stored(w, job["id"])
    assert data is not None, job
    return zipfile.ZipFile(io.BytesIO(data))


def rows_of(archive: zipfile.ZipFile, name: str, delimiter: str = ",") -> list[dict[str, str]]:
    return list(
        csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig")), delimiter=delimiter)
    )


def test_a_bundle_is_made_in_the_background_with_every_file_listed_and_checked(
    w: dict[str, Any],
) -> None:
    job = ask(w, content="both")
    assert job["state"] == "READY", job
    assert (job["recordings"], job["requested_by"], job["error"]) == (2, "pa", None)
    data = stored(w, job["id"])
    assert data is not None
    # The stored state says what the bundle is: size, checksum, and when it goes.
    assert job["size_bytes"] == len(data)
    assert job["sha256"] == hashlib.sha256(data).hexdigest()
    left = datetime.fromisoformat(job["expires_at"]) - datetime.now(UTC)
    assert timedelta(hours=23) < left <= timedelta(hours=24)

    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()
    assert archive.testzip() is None
    assert job["files"] == len(names)
    # Phone and face-to-face recordings each in their own folder (EXP-006).
    folders = sorted({n.rsplit("/", 1)[0] for n in names if "/" in n})
    assert folders == [
        "face_to_face/audio",
        "face_to_face/consent",
        "face_to_face/metadata",
        "schema",
        "telephony/audio",
        "telephony/consent",
        "telephony/metadata",
    ]
    assert sorted(n for n in names if "/" not in n) == [
        "README.txt",
        "SHA256SUMS",
        "manifest.csv",
        "manifest.json",
        "participants.csv",
        "recordings.csv",
        "recordings.json",
    ]
    for name in names:
        if name.endswith(".wav"):
            assert archive.read(name)[:4] == b"RIFF", name

    # Everything in the bundle is in the manifest, with a size and checksum that recalculate
    # (EXP-005); SHA256SUMS says the same and covers the manifests too.
    manifest = json.loads(archive.read("manifest.json"))
    listed = {f["path"]: f for f in manifest["files"]}
    assert set(listed) == set(names) - {"manifest.json", "manifest.csv", "SHA256SUMS"}
    for path, entry in listed.items():
        body = archive.read(path)
        assert (entry["bytes"], entry["sha256"]) == (len(body), hashlib.sha256(body).hexdigest())
    sums: dict[str, str] = {}
    for line in archive.read("SHA256SUMS").decode().splitlines():
        digest, path = line.split("  ", 1)
        sums[path] = digest
    assert set(sums) == set(names) - {"SHA256SUMS"}
    for path, expected in sums.items():
        assert hashlib.sha256(archive.read(path)).hexdigest() == expected, path
    assert [r["path"] for r in rows_of(archive, "manifest.csv")] == list(listed)
    assert manifest["counts"] == {
        "recordings": 2,
        "face_to_face": 1,
        "telephony": 1,
        "files": len(listed),
        "bytes": sum(f["bytes"] for f in listed.values()),
    }
    assert manifest["selection"]["scope"] == "finished"
    assert manifest["requested_by"] == "pa"

    # The tables: one row per recording, the same in CSV and JSON (EXP-002, EXP-005).
    table = rows_of(archive, "recordings.csv")
    as_json = json.loads(archive.read("recordings.json"))
    assert len(table) == len(as_json) == 2
    assert [r["task_code"] for r in table] == [r["task_code"] for r in as_json]
    by_mode = {r["mode"]: r for r in as_json}
    assert set(by_mode) == {"FACE_TO_FACE", "TELEPHONY"}
    phone = by_mode["TELEPHONY"]
    assert phone["audio_file"].startswith("telephony/audio/")
    assert phone["audio_sha256"] == listed[phone["audio_file"]]["sha256"]
    assert phone["audio_bytes"] == listed[phone["audio_file"]]["bytes"]
    assert (phone["sample_rate"], phone["bit_depth"]) == (16000, 16)
    assert phone["participant_a"] == w["a"]["participant_code"]
    assert (phone["participant_a_language"], phone["participant_a_consent"]) == ("hi", "GIVEN")
    assert phone["moderator"] == "mod"
    assert phone["original_files"] == []
    assert by_mode["FACE_TO_FACE"]["metadata_file"].startswith("face_to_face/metadata/")

    # Every JSON file matches the schema that travels with it (EXP-003).
    schemas = {n: json.loads(archive.read(n)) for n in names if n.startswith("schema/")}
    for schema in schemas.values():
        jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(as_json, schemas["schema/recordings.schema.json"])
    jsonschema.validate(manifest, schemas["schema/manifest.schema.json"])
    details = [n for n in names if "/metadata/" in n]
    assert len(details) == 2
    for name in details:
        body = json.loads(archive.read(name))
        jsonschema.validate(body, schemas["schema/recording-metadata.schema.json"])
        # What the requirement lists (EXP-001): people by code, consent, checks, provenance.
        assert {p["participant_code"] for p in body["participants"]} == {
            w["a"]["participant_code"],
            w["b"]["participant_code"],
        }
        assert body["files"]
        assert all("processing" in f for f in body["files"])
    # A file that breaks the schema is seen as such.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            [{**as_json[0], "mode": "RADIO"}], schemas["schema/recordings.schema.json"]
        )

    # No phone number, name or email address anywhere, unless asked for (EXP-004).
    people = rows_of(archive, "participants.csv")
    assert list(people[0]) == ["participant_code", "language", "dialect", "recordings_in_export"]
    assert [p["recordings_in_export"] for p in people] == ["2", "2"]
    digits = A_PHONE[-10:]
    for name in names:
        if not name.endswith(".wav"):
            assert digits.encode() not in archive.read(name), name
    readme = archive.read("README.txt").decode()
    assert "Names, phone numbers and email addresses are not included." in readme
    assert "Transcripts: Not included" in readme

    # Asking for it is in the audit log, with what was chosen.
    entry = w["db"].scalar(select(AuditLog).where(AuditLog.action == "export.requested"))
    assert entry is not None
    assert entry.entity_id == job["id"]
    asked = json.loads(entry.after_summary)
    assert asked["content"] == "both"
    assert asked["recordings"] == 2


def test_the_bundle_is_written_in_parts_not_held_whole(w: dict[str, Any]) -> None:
    db = w["db"]
    project = db.get(Project, w["project_id"])
    sel = bundle.Selection(content="both", scope="finished")
    beats: list[int] = []
    entries = bundle.select_entries(db, project, sel, "Asia/Kolkata")
    made = bundle.Bundle(
        db=db,
        storage=w["app"].state.storage,
        cipher=None,
        project=project,
        selection=sel,
        entries=entries,
        export_id="x",
        requested_by="test",
        on_entry=lambda: beats.append(1),
    )
    parts = list(made.parts())
    assert len(beats) == len(entries) == 2  # a sign of life after every recording
    assert len(parts) > 3, "sent piece by piece"
    assert zipfile.ZipFile(io.BytesIO(b"".join(parts))).testzip() is None
    assert len(made.written) == len(zipfile.ZipFile(io.BytesIO(b"".join(parts))).namelist()) - 1


def test_filters_choose_the_recordings_and_bad_ones_are_refused(w: dict[str, Any]) -> None:
    pa, base = w["pa"], w["base"]

    def count(**params: Any) -> Any:
        got = pa.get(f"{base}/export/summary", params={"scope": "finished", **params})
        return got.json()["recordings"] if got.status_code == 200 else got.status_code

    everything = pa.get(f"{base}/export/summary", params={"scope": "finished"}).json()
    assert (everything["recordings"], everything["face_to_face"], everything["telephony"]) == (
        2,
        1,
        1,
    )
    assert everything["audio_bytes"] > 0
    assert everything["file_name"].startswith("both_PHONE_")
    assert count(mode="TELEPHONY") == 1
    assert count(mode="FACE_TO_FACE") == 1
    assert count(language="hi") == 2
    assert count(scope="approved") == 0  # nothing is approved yet
    today = datetime.now(UTC).date()
    assert (
        count(
            recorded_from=str(today - timedelta(days=1)), recorded_to=str(today + timedelta(days=1))
        )
        == 2
    )
    assert count(recorded_to=str(today - timedelta(days=2))) == 0
    assert count(content="metadata") == 2
    assert (
        pa.get(
            f"{base}/export/summary", params={"content": "metadata", "scope": "finished"}
        ).json()["audio_bytes"]
        == 0
    )

    # What makes no sense is refused, not guessed (EXP-008).
    assert count(language="ta") == 422  # nobody in this project speaks it
    assert count(language="x") == 422
    assert count(mode="RADIO") == 422
    assert count(content="everything") == 422
    assert count(recorded_from=str(today), recorded_to=str(today - timedelta(days=1))) == 422
    assert count(recorded_from="yesterday") == 422
    assert count(originals="true", content="metadata") == 422
    nothing = pa.post(
        f"{base}/exports", json={"scope": "finished", "recorded_to": str(today - timedelta(days=2))}
    )
    assert (nothing.status_code, nothing.json()["error"]["code"]) == (422, "NOTHING_TO_EXPORT")
    assert pa.post(f"{base}/exports", json={"table_format": "xlsx"}).status_code == 422

    # One mode only: the other folder is not in the bundle; TSV when asked for.
    phone_only = opened(w, ask(w, content="audio", mode="TELEPHONY", table_format="tsv"))
    names = phone_only.namelist()
    assert [n for n in names if n.endswith(".wav")]
    assert not [n for n in names if n.startswith("face_to_face/")]
    assert not [n for n in names if "/metadata/" in n or "/consent/" in n]
    assert "recordings.tsv" in names
    assert "recordings.csv" not in names
    raw = phone_only.read("recordings.tsv").decode("utf-8-sig")
    assert "\t" in raw.splitlines()[0]
    assert "," not in raw.splitlines()[0]
    only = rows_of(phone_only, "recordings.tsv", "\t")
    assert [r["mode"] for r in only] == ["TELEPHONY"]
    assert only[0]["metadata_file"] == ""

    # Who may export: not the moderator; a project that is not theirs is not there at all.
    assert w["mod"].get(f"{base}/export/summary").status_code == 403
    assert w["mod"].post(f"{base}/exports", json={}).status_code == 403
    assert w["mod"].get(f"{base}/exports").status_code == 403
    make_user(w["db"], "pa.other@example.org", ["PROJECT_ADMIN"])
    outsider = w["api"]("pa.other@example.org")
    assert outsider.get(f"{base}/exports").status_code == 404
    assert outsider.post(f"{base}/exports", json={}).status_code == 404


def test_original_files_and_personal_data_need_the_right_to_export_them(
    w: dict[str, Any],
) -> None:
    base = w["base"]
    project = w["db"].get(Project, w["project_id"])
    make_user(w["db"], "cv@example.org", ["CLIENT_VIEWER"], projects=[project])
    w["cv"] = w["api"]("cv@example.org")

    # The client gets delivery files; what was recorded before processing is for the project's
    # own people, and personal data for those who may export it (EXP-004).
    plain = ask(w, "cv", content="audio")
    assert plain["state"] == "READY"
    assert not [n for n in opened(w, plain).namelist() if "/originals/" in n]
    assert w["cv"].post(f"{base}/exports", json={"originals": True}).status_code == 403
    assert w["cv"].post(f"{base}/exports", json={"contact": True}).status_code == 403
    assert w["pa"].post(f"{base}/exports", json={"contact": True}).status_code == 403
    assert w["cv"].get(f"{base}/export/summary", params={"originals": "true"}).status_code == 403

    with_originals = ask(w, "pa", content="audio", originals=True)
    assert with_originals["state"] == "READY", with_originals
    archive = opened(w, with_originals)
    originals = sorted(n for n in archive.namelist() if "/originals/" in n)
    assert [n.split("/")[0] for n in originals] == ["face_to_face", "telephony"]
    assert "browser_original" in originals[0]
    assert "provider_original_mixed" in originals[1]
    row = json.loads(archive.read("recordings.json"))[0]
    assert len(row["original_files"]) == 1
    jsonschema.validate(
        json.loads(archive.read("recordings.json")),
        json.loads(archive.read("schema/recordings.schema.json")),
    )
    # A bundle is handed only to someone who could have asked for it.
    link = f"{base}/exports/{with_originals['id']}/download-link"
    assert w["pa"].post(link).status_code == 200
    assert w["cv"].post(link).status_code == 403

    personal = ask(w, "sa", content="metadata", contact=True)
    assert personal["state"] == "READY", personal
    archive = opened(w, personal)
    people = {p["name"]: p for p in rows_of(archive, "participants.csv")}
    # A cell that starts with + is written as text, so a spreadsheet never runs it as a formula.
    assert people["Asha"]["phone"] == "'" + A_PHONE
    assert (
        "phone numbers and email addresses: keep it accordingly"
        in archive.read("README.txt").decode()
    )
    link = f"{base}/exports/{personal['id']}/download-link"
    assert w["sa"].post(link).status_code == 200
    assert w["pa"].post(link).status_code == 403
    asked = w["db"].scalar(
        select(AuditLog).where(
            AuditLog.action == "export.requested", AuditLog.entity_id == personal["id"]
        )
    )
    assert asked is not None
    assert json.loads(asked.after_summary)["contact"] is True


def test_links_are_short_lived_and_audited_and_bundles_expire(w: dict[str, Any]) -> None:
    base, pa, db = w["base"], w["pa"], w["db"]
    job = ask(w, content="metadata")
    link = pa.post(f"{base}/exports/{job['id']}/download-link")
    assert link.status_code == 200, link.text
    body = link.json()
    assert body["valid_seconds"] == 300
    assert "X-Amz-Expires=300" in body["url"]
    assert "X-Amz-Signature=" in body["url"]
    assert "response-content-disposition=attachment" in body["url"]
    assert body["file_name"] == job["file_name"]
    assert body["sha256"] == job["sha256"]
    assert pa.post(f"{base}/exports/{job['id']}/download-link").status_code == 200
    after = pa.get(f"{base}/exports/{job['id']}").json()
    assert after["downloads"] == 2
    assert after["last_downloaded_at"]
    links = db.scalars(select(AuditLog).where(AuditLog.action == "export.download_link")).all()
    assert len(links) == 2
    assert json.loads(links[0].after_summary)["sha256"] == job["sha256"]
    listed = pa.get(f"{base}/exports").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == job["id"]

    # Past its time: no link any more, and the sweep takes the bundle out of storage (EXP-010).
    db.execute(
        update(ExportJob)
        .where(ExportJob.id == job["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db.commit()
    late = pa.post(f"{base}/exports/{job['id']}/download-link")
    assert (late.status_code, late.json()["error"]["code"]) == (409, "EXPORT_EXPIRED")
    assert stored(w, job["id"]) is not None
    key = db.scalar(select(ExportJob.storage_key).where(ExportJob.id == job["id"]))
    sweep_exports(w["app"])
    db.expire_all()
    assert pa.get(f"{base}/exports/{job['id']}").json()["state"] == "EXPIRED"
    assert not [
        o
        for o in w["s3"].list_objects_v2(Bucket=BUCKET).get("Contents", [])
        if o["Key"].endswith(key)
    ]
    gone = pa.post(f"{base}/exports/{job['id']}/download-link")
    assert (gone.status_code, gone.json()["error"]["code"]) == (409, "EXPORT_NOT_READY")

    # A person can also remove a bundle before its time; that is audited too.
    second = ask(w, content="metadata")
    assert stored(w, second["id"]) is not None
    removed = pa.delete(f"{base}/exports/{second['id']}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["state"] == "EXPIRED"
    assert stored(w, second["id"]) is None
    assert pa.delete(f"{base}/exports/{second['id']}").status_code == 409
    assert db.scalar(select(AuditLog).where(AuditLog.action == "export.removed")) is not None
    assert pa.get(f"{base}/exports/{second['id']}").json()["sha256"] == second["sha256"]


def test_a_job_that_stopped_is_tried_again_and_a_damaged_file_stops_the_export(
    w: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, pa, db, app = w["base"], w["pa"], w["db"], w["app"]
    job = ask(w, content="metadata")
    first_key = db.scalar(select(ExportJob.storage_key).where(ExportJob.id == job["id"]))

    def state() -> Any:
        db.expire_all()
        return db.get(ExportJob, job["id"])

    # A worker that died half-way leaves the job RUNNING: the sweep puts it back in the queue,
    # and a worker makes it (EXP-009).
    def stalled(attempts: int) -> None:
        db.execute(
            update(ExportJob)
            .where(ExportJob.id == job["id"])
            .values(
                state="RUNNING",
                attempts=attempts,
                claimed_at=datetime.now(UTC) - timedelta(hours=3),
                storage_key=None,
            )
        )
        db.commit()

    stalled(1)
    assert pa.delete(f"{base}/exports/{job['id']}").status_code == 409  # being made
    assert jobs.sweep(db, app.state.settings, app.state.storage) == []  # just put back
    assert state().state == "QUEUED"
    assert jobs.run(db, app.state.settings, app.state.storage, None, job["id"]) == "READY"
    assert jobs.run(db, app.state.settings, app.state.storage, None, job["id"]) is None
    again = state()
    # Each try has its own object in storage, so one given up cannot spoil the next.
    assert (again.state, again.attempts) == ("READY", 2)
    assert first_key.endswith(f"{job['id']}-1.zip")
    assert again.storage_key.endswith(f"{job['id']}-2.zip")
    # A try that finishes after the job was taken from it writes nothing and leaves nothing.
    db.execute(update(ExportJob).where(ExportJob.id == job["id"]).values(state="QUEUED"))
    db.commit()
    real_stream = bundle.Bundle.parts

    def overtaken(self: bundle.Bundle) -> Any:
        yield from real_stream(self)
        with app.state.session_factory() as other:  # the sweep and another worker
            other.execute(update(ExportJob).where(ExportJob.id == job["id"]).values(attempts=9))
            other.commit()

    monkeypatch.setattr(bundle.Bundle, "parts", overtaken)
    assert jobs.run(db, app.state.settings, app.state.storage, None, job["id"]) == "RUNNING"
    monkeypatch.undo()
    assert not [
        o
        for o in w["s3"].list_objects_v2(Bucket=BUCKET).get("Contents", [])
        if o["Key"].endswith(f"{job['id']}-3.zip")
    ]
    db.execute(update(ExportJob).where(ExportJob.id == job["id"]).values(state="READY", attempts=2))
    db.commit()
    # A waiting job the first hand-off lost is sent again once it has waited long enough.
    db.execute(
        text(
            "UPDATE export_jobs SET state = 'QUEUED', updated_at = now() - interval '1 hour'"
            " WHERE id = :id"
        ),
        {"id": job["id"]},
    )
    db.commit()
    assert sweep_exports(app) == 1
    assert state().state == "READY"
    # Three tries, then it is a failure a person can read.
    stalled(3)
    jobs.sweep(db, app.state.settings, app.state.storage)
    failed = pa.get(f"{base}/exports/{job['id']}").json()
    assert failed["state"] == "FAILED"
    assert "three times" in failed["error"]

    # A project cannot pile up exports.
    for _ in range(3):
        db.add(
            ExportJob(
                project_id=w["project_id"],
                requested_by=db.scalar(select(ExportJob.requested_by).limit(1)),
                content="audio",
                scope="finished",
                table_format="csv",
                state="QUEUED",
                file_name="waiting.zip",
            )
        )
    db.commit()
    busy = pa.post(f"{base}/exports", json={"scope": "finished"})
    assert (busy.status_code, busy.json()["error"]["code"]) == (409, "TOO_MANY_EXPORTS")
    db.execute(
        update(ExportJob).where(ExportJob.file_name == "waiting.zip").values(state="EXPIRED")
    )
    db.commit()

    # A stored file that is not what was stored: the export stops, says why, and leaves no
    # half bundle behind (EXP-005).
    asset = db.scalar(
        select(AudioAsset).where(
            AudioAsset.kind == "FTF_DERIVED_PCM", AudioAsset.deleted_at.is_(None)
        )
    )
    name = next(
        o["Key"]
        for o in w["s3"].list_objects_v2(Bucket=BUCKET)["Contents"]
        if o["Key"].endswith(asset.storage_key)
    )
    w["s3"].put_object(Bucket=BUCKET, Key=name, Body=b"RIFF-not-the-file")
    damaged = ask(w, content="audio")
    assert damaged["state"] == "FAILED", damaged
    assert "does not match its checksum" in damaged["error"]
    assert damaged["sha256"] is None
    assert damaged["size_bytes"] == 0
    assert stored(w, damaged["id"]) is None
    assert not [
        o
        for o in w["s3"].list_objects_v2(Bucket=BUCKET).get("Contents", [])
        if o["Key"].endswith(f"{damaged['id']}.zip")
    ]
    assert pa.post(f"{base}/exports/{damaged['id']}/download-link").status_code == 409
    # Metadata alone does not read the audio, so it still exports.
    assert ask(w, content="metadata")["state"] == "READY"
    # Without a worker the hand-off runs in this process and never raises into the request.
    run_export_inline(app, damaged["id"])


def test_reports_come_as_csv_or_tsv_that_spreadsheets_read(w: dict[str, Any]) -> None:
    base, pa = w["base"], w["pa"]
    as_csv = pa.get(f"{base}/export", params={"content": "progress"})
    assert as_csv.headers["content-type"].startswith("text/csv")
    assert as_csv.content[:3] == b"\xef\xbb\xbf"  # read as UTF-8 by spreadsheet software
    rows = list(csv.DictReader(io.StringIO(as_csv.content.decode("utf-8-sig"))))
    assert {r["mode"] for r in rows} == {"TELEPHONY", "FACE_TO_FACE"}
    as_tsv = pa.get(f"{base}/export", params={"content": "progress", "format": "tsv"})
    assert as_tsv.headers["content-type"].startswith("text/tab-separated-values")
    assert ".tsv" in as_tsv.headers["content-disposition"]
    tab_rows = list(csv.DictReader(io.StringIO(as_tsv.content.decode("utf-8-sig")), delimiter="\t"))
    assert [r["task_code"] for r in tab_rows] == [r["task_code"] for r in rows]
    people = pa.get(f"{base}/export", params={"content": "participants", "format": "tsv"})
    assert people.status_code == 200
    # Recordings no longer come from this address: they are asked for as a bundle.
    assert pa.get(f"{base}/export", params={"content": "audio"}).status_code == 422
    assert pa.get(f"{base}/export", params={"format": "xlsx"}).status_code == 422
