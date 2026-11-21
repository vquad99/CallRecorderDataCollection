"""Consent online or by upload, and participants' scanned documents (D-144): the project option,
the signed consent form and the address proof (upload, replace, history, view links), the file
checks and the size limit, the one consent rule for tasks, calls and recording, who may do what,
and what removing a participant does to the files.

Requirements: PART-006, PART-008, PART-009, PART-016, SEC-001, SEC-006, SEC-010, STOR-005, PROJ-001
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from app.main import create_app
from app.modules.audit.models import AuditLog
from app.modules.participants import consent, documents
from app.modules.participants.models import ParticipantDocument
from app.modules.recordings import service as recordings
from tests.conftest import (
    Api,
    build_settings,
    make_participant,
    make_project,
    make_user,
    read_outbox,
    set_status,
)

pytestmark = pytest.mark.db
BUCKET = "ccp-docs"
ROOT = Path(__file__).resolve().parents[2]
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def s3() -> Iterator[Any]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture
def app(migrated_db: str, s3: Any, outbox: Path) -> Any:
    return create_app(
        build_settings(
            database_url=migrated_db,
            email_file_dir=str(outbox),
            storage_bucket=BUCKET,
            storage_access_key_id="test-key",
            storage_secret_access_key="test-secret",
        )
    )


@pytest.fixture
def world(app: Any) -> Iterator[dict[str, Any]]:
    """An Upload project (KOK) with its admin, two moderators, a QC Executive and a Client Viewer,
    and an Online project (ONL) with an admin of its own."""
    clients: list[TestClient] = []

    def api(email: str) -> Api:
        client = TestClient(app)
        clients.append(client)
        a = Api(client)
        assert a.login(email).status_code == 200
        return a

    with app.state.session_factory() as db:
        kok = make_project(db, "KOK")
        kok.consent_mode = "UPLOAD"
        onl = make_project(db, "ONL")
        db.commit()
        users = {
            "pa": make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[kok]),
            "mod": make_user(db, "mod@example.org", ["MODERATOR"], projects=[kok]),
            "mod2": make_user(db, "mod2@example.org", ["MODERATOR"], projects=[kok]),
            "qc": make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[kok]),
            "qc2": make_user(db, "qc2@example.org", ["QC_EXECUTIVE"], projects=[kok]),
            "cv": make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[kok]),
            "opa": make_user(db, "opa@example.org", ["PROJECT_ADMIN"], projects=[onl]),
        }
        yield {
            "app": app,
            "db": db,
            "kok": kok,
            "onl": onl,
            "users": users,
            "api": api,
            "pa": api("pa@example.org"),
        }
    for c in clients:
        c.close()


def docs_url(project_id: Any, participant_id: Any) -> str:
    return f"/api/v1/projects/{project_id}/participants/{participant_id}/documents"


def put(
    api: Api,
    project_id: Any,
    participant_id: Any,
    kind: str,
    data: bytes,
    name: str = "scan.pdf",
    content_type: str = "application/pdf",
) -> Any:
    return api.post(
        f"{docs_url(project_id, participant_id)}/{kind}",
        json=None,
        content=data,
        headers={"Content-Type": content_type, "X-File-Name": name},
    )


def new_task(world: dict[str, Any], a: Any, b: Any) -> Any:
    return world["pa"].post(
        "/api/v1/tasks",
        json={
            "project_id": str(world["kok"].id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": a["id"],
            "participant_b_id": b["id"],
        },
    )


def signed_pair(world: dict[str, Any]) -> tuple[Any, Any]:
    """Two participants of the Upload project, each with a signed consent form uploaded."""
    kok = world["kok"].id
    a = make_participant(world["pa"], kok, "Asha", agreed=False)
    b = make_participant(world["pa"], kok, "Bina", agreed=False)
    for p in (a, b):
        assert put(world["pa"], kok, p["id"], "consent-form", PDF).status_code == 201
    return a, b


def task_with_staff(world: dict[str, Any]) -> tuple[Any, Any, Any]:
    """A task of the Upload project with its moderator (mod) and QC Executive (qc)."""
    a, b = signed_pair(world)
    task = new_task(world, a, b).json()
    users = world["users"]
    assigned = world["pa"].post(
        f"/api/v1/tasks/{task['id']}/assign", json={"user_id": str(users["mod"].id)}
    )
    assert assigned.status_code == 200, assigned.text
    qc = world["pa"].post(
        f"/api/v1/tasks/{task['id']}/assign-qc", json={"user_id": str(users["qc"].id)}
    )
    assert qc.status_code == 200, qc.text
    return task, a, b


def audits(db: Any, action: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


# ---------------------------------------------------------------- the project option


def test_projects_take_consent_online_unless_set_to_upload_and_the_change_is_audited(
    world: dict[str, Any],
) -> None:
    pa, db = world["pa"], world["db"]
    sa_email = "sa@example.org"
    make_user(db, sa_email, ["SUPER_ADMIN"])
    sa = world["api"](sa_email)
    made = sa.post(
        "/api/v1/projects",
        json={"name": "New", "allows_telephony": True, "allows_face_to_face": False},
    )
    assert made.status_code == 201, made.text
    assert made.json()["consent_mode"] == "ONLINE"
    project = pa.get(f"/api/v1/projects/{world['kok'].id}").json()
    assert project["consent_mode"] == "UPLOAD"
    body = {
        k: project[k]
        for k in (
            "name",
            "description",
            "allows_telephony",
            "allows_face_to_face",
            "phone_visibility_policy",
            "consent_policy_version",
            "consent_text",
        )
    }
    bad = pa.patch(f"/api/v1/projects/{world['kok'].id}", json={**body, "consent_mode": "PAPER"})
    assert bad.status_code == 422
    changed = pa.patch(
        f"/api/v1/projects/{world['kok'].id}", json={**body, "consent_mode": "ONLINE"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["consent_mode"] == "ONLINE"
    [entry] = audits(db, "project.updated")
    assert '"consent_mode": "UPLOAD"' in (entry.before_summary or "")
    assert '"consent_mode": "ONLINE"' in (entry.after_summary or "")


def test_nothing_is_emailed_in_an_upload_project(world: dict[str, Any], outbox: Path) -> None:
    pa, kok = world["pa"], world["kok"].id
    world["kok"].consent_text = "Please agree."
    world["db"].commit()
    added = pa.post(
        f"/api/v1/projects/{kok}/participants",
        json={
            "display_label": "Asha",
            "language_code": "hi",
            "email": "asha@example.org",
        },
    )
    assert added.status_code == 201, added.text
    assert added.json()["consent_email"] == consent.BY_UPLOAD
    assert added.json()["has_consent_form"] is False
    pid = added.json()["id"]
    again = pa.post(f"/api/v1/projects/{kok}/participants/{pid}/portal-link/email")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CONSENT_BY_UPLOAD"
    bulk = pa.post(
        f"/api/v1/projects/{kok}/participants/bulk",
        json={"action": "send_consent", "participant_ids": [pid]},
    )
    assert bulk.status_code == 409
    assert bulk.json()["error"]["code"] == "CONSENT_BY_UPLOAD"
    imported = pa.post(
        f"/api/v1/projects/{kok}/participants/import",
        json={"csv": "name,phone,email,language\nBina,,bina@example.org,hi\n", "confirm": True},
    )
    assert imported.status_code == 200, imported.text
    assert consent.BY_UPLOAD in imported.json()["rows"][0]["message"]
    assert read_outbox(outbox) == []


# ---------------------------------------------------------------- upload, replace, view


def test_a_signed_form_is_stored_privately_and_replacing_it_keeps_the_history(
    world: dict[str, Any], s3: Any
) -> None:
    pa, db, kok = world["pa"], world["db"], world["kok"].id
    p = make_participant(pa, kok, "Asha", agreed=False)
    first = put(pa, kok, p["id"], "consent-form", PDF, name="Asha%20form.pdf")
    assert first.status_code == 201, first.text
    out = first.json()
    assert out["kind"] == "CONSENT_FORM"
    assert out["file_name"] == "Asha form.pdf"
    assert out["content_type"] == "application/pdf"
    assert out["size_bytes"] == len(PDF)
    assert out["uploaded_by"] == "pa"
    assert out["replaced_at"] is None
    stored = db.get(ParticipantDocument, uuid.UUID(out["id"]))
    body = s3.get_object(Bucket=BUCKET, Key=stored.storage_key)
    assert body["Body"].read() == PDF
    assert body["ContentType"] == "application/pdf"
    assert stored.storage_key.startswith("documents/")
    assert "Asha" not in stored.storage_key

    second = put(pa, kok, p["id"], "consent-form", JPEG, name="photo.jpg", content_type="image/png")
    assert second.status_code == 201, second.text
    assert second.json()["content_type"] == "image/jpeg"  # from the bytes, not the browser
    listed = pa.get(docs_url(kok, p["id"])).json()
    assert listed["consent_mode"] == "UPLOAD"
    assert listed["consent_form"]["id"] == second.json()["id"]
    assert [d["id"] for d in listed["earlier"]] == [out["id"]]
    assert listed["earlier"][0]["replaced_by"] == "pa"
    assert listed["earlier"][0]["replaced_at"] is not None
    assert listed["may_upload_consent_form"]
    assert listed["may_upload_address_proof"]
    assert listed["max_bytes"] == documents.MAX_DOCUMENT_BYTES
    db.expire_all()
    current = db.scalars(
        select(ParticipantDocument).where(ParticipantDocument.replaced_at.is_(None))
    ).all()
    assert [d.id for d in current] == [uuid.UUID(second.json()["id"])]
    # The older file stays in storage for the record.
    assert s3.get_object(Bucket=BUCKET, Key=stored.storage_key)["Body"].read() == PDF

    [uploaded] = audits(db, "participant.document_uploaded")
    [replaced] = audits(db, "participant.document_replaced")
    assert uploaded.entity_id == out["id"]
    assert out["id"] in (replaced.before_summary or "")
    for entry in (uploaded, replaced):
        text = (entry.before_summary or "") + (entry.after_summary or "")
        assert "%PDF" not in text
        assert "JFIF" not in text
        assert "Asha" not in text
        assert "CONSENT_FORM" in text


def test_a_view_link_is_short_lived_opens_in_the_browser_and_is_audited(
    world: dict[str, Any],
) -> None:
    pa, db, kok = world["pa"], world["db"], world["kok"].id
    p = make_participant(pa, kok, "Asha", agreed=False)
    doc = put(pa, kok, p["id"], "address-proof", PNG, name="proof.png").json()
    link = pa.post(f"{docs_url(kok, p['id'])}/{doc['id']}/url")
    assert link.status_code == 200, link.text
    assert link.json()["expires_in"] == world["app"].state.settings.signed_url_seconds
    assert "X-Amz-Expires" in link.json()["url"]
    assert "attachment" not in link.json()["url"]
    [entry] = audits(db, "participant.document_view_link")
    assert entry.entity_id == doc["id"]
    assert "ADDRESS_PROOF" in (entry.after_summary or "")


def test_only_pdf_jpeg_and_png_are_taken_whatever_the_name_or_type_says(
    world: dict[str, Any],
) -> None:
    pa, kok = world["pa"], world["kok"].id
    p = make_participant(pa, kok, "Asha", agreed=False)
    for data, name, content_type in (
        (b"<html><script>alert(1)</script></html>", "form.pdf", "application/pdf"),
        (b"GIF89a" + b"\x00" * 20, "form.gif", "image/gif"),
        (b"PK\x03\x04" + b"\x00" * 20, "form.docx", "application/octet-stream"),
        (b"hello", "form.txt", "text/plain"),
    ):
        refused = put(pa, kok, p["id"], "consent-form", data, name, content_type)
        assert refused.status_code == 422, (name, refused.text)
        assert refused.json()["error"]["code"] == "INVALID_FILE_TYPE"
        assert "PDF, JPEG or PNG" in refused.json()["error"]["message"]
    empty = put(pa, kok, p["id"], "consent-form", b"")
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "INVALID_FILE"
    assert pa.get(docs_url(kok, p["id"])).json()["consent_form"] is None
    unknown = put(pa, kok, p["id"], "passport", PDF)
    assert unknown.status_code == 422


def test_ten_mb_is_taken_and_one_byte_more_is_refused(world: dict[str, Any]) -> None:
    pa, kok = world["pa"], world["kok"].id
    p = make_participant(pa, kok, "Asha", agreed=False)
    limit = documents.MAX_DOCUMENT_BYTES
    assert limit == 10 * 1024 * 1024
    biggest = PDF + b"\x00" * (limit - len(PDF))
    assert put(pa, kok, p["id"], "consent-form", biggest).status_code == 201
    too_big = put(pa, kok, p["id"], "consent-form", biggest + b"\x00")
    assert too_big.status_code == 413
    assert too_big.json()["error"]["message"] == documents.TOO_LARGE
    assert "10 MB" in documents.TOO_LARGE
    with pytest.raises(Exception, match="larger than 10 MB"):
        documents.file_type(biggest + b"\x00")
    # Other requests keep their own, smaller limit.
    json_too_big = pa.post(
        f"/api/v1/projects/{kok}/participants/import",
        json={"csv": "x" * (3 * 1024 * 1024), "confirm": False},
    )
    assert json_too_big.status_code == 413


def test_the_web_server_and_the_form_allow_the_same_10_mb() -> None:
    conf = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    block = re.search(r"documents/\(consent-form\|address-proof\)\$ \{(.*?)\}", conf, re.S)
    assert block, "nginx needs its own location for document uploads"
    size = re.search(r"client_max_body_size (\d+)m;", block.group(1))
    assert size
    assert int(size.group(1)) * 1024 * 1024 == documents.MAX_DOCUMENT_BYTES
    assert "client_max_body_size 9m;" in conf  # everything else stays as it was
    form = (ROOT / "frontend" / "src" / "api" / "work.ts").read_text(encoding="utf-8")
    mb = re.search(r"MAX_DOCUMENT_MB = (\d+);", form)
    assert mb
    assert int(mb.group(1)) * 1024 * 1024 == documents.MAX_DOCUMENT_BYTES


def test_a_consent_form_is_uploaded_only_where_the_project_takes_uploads(
    world: dict[str, Any],
) -> None:
    onl, db = world["onl"].id, world["db"]
    opa = world["api"]("opa@example.org")
    p = make_participant(opa, onl, "Ola", agreed=False)
    refused = put(opa, onl, p["id"], "consent-form", PDF)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "CONSENT_ONLINE"
    assert put(opa, onl, p["id"], "address-proof", PDF).status_code == 201
    listed = opa.get(docs_url(onl, p["id"])).json()
    assert listed["consent_mode"] == "ONLINE"
    assert listed["may_upload_consent_form"] is False
    assert listed["address_proof"] is not None
    row = opa.get(f"/api/v1/projects/{onl}/participants").json()["items"][0]
    assert row["has_address_proof"] is True
    assert row["has_consent_form"] is False
    assert db.scalar(select(ParticipantDocument.kind)) == "ADDRESS_PROOF"


# ---------------------------------------------------------------- consent that counts


def test_an_uploaded_form_is_consent_for_tasks(world: dict[str, Any]) -> None:
    pa, kok = world["pa"], world["kok"].id
    a = make_participant(pa, kok, "Asha", agreed=False)
    b = make_participant(pa, kok, "Bina", agreed=False)
    refused = new_task(world, a, b)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "CONSENT_REQUIRED"
    assert "no signed consent form" in refused.json()["error"]["message"]
    put(pa, kok, a["id"], "consent-form", PDF)
    still = new_task(world, a, b)
    assert still.status_code == 422
    assert still.json()["error"]["details"][0]["participants"] == [b["participant_code"]]
    put(pa, kok, b["id"], "consent-form", PNG, name="b.png", content_type="image/png")
    made = new_task(world, a, b)
    assert made.status_code == 201, made.text
    task = made.json()
    assert task["consent_mode"] == "UPLOAD"
    assert task["consent_missing"] == []
    for party in (task["participant_a"], task["participant_b"]):
        assert party["consent_status"] == "UPLOADED"
        assert party["may_record"] is True
        assert party["consent_at"] is not None
        assert party["consent_form"]["kind"] == "CONSENT_FORM"
        assert party["can_upload_consent_form"] is True
    rows = pa.get(f"/api/v1/projects/{kok}/participants").json()["items"]
    assert {r["consent_status"] for r in rows} == {"UPLOADED"}
    assert {r["has_consent_form"] for r in rows} == {True}
    assert {r["has_address_proof"] for r in rows} == {False}


def test_an_online_agreement_still_counts_in_an_upload_project(world: dict[str, Any]) -> None:
    pa, kok = world["pa"], world["kok"].id
    a = make_participant(pa, kok, "Asha")  # agreed online
    b = make_participant(pa, kok, "Bina", agreed=False)
    put(pa, kok, b["id"], "consent-form", PDF)
    made = new_task(world, a, b)
    assert made.status_code == 201, made.text
    assert made.json()["participant_a"]["consent_status"] == "GIVEN"
    assert made.json()["participant_a"]["consent_form"] is None
    assert made.json()["participant_b"]["consent_status"] == "UPLOADED"


RECORDER = {
    "native_sample_rate": 16000,
    "channel_count": 1,
    "echo_cancellation": False,
    "noise_suppression": False,
    "auto_gain_control": False,
}


def test_a_form_counts_only_while_the_project_takes_uploads(world: dict[str, Any]) -> None:
    """The recorder (like a call) checks the same rule: it opens on uploaded forms, and not once
    the project is back to taking consent online."""
    pa, db = world["pa"], world["db"]
    task, _, _ = task_with_staff(world)
    mod = world["api"]("mod@example.org")
    started = mod.post(f"/api/v1/tasks/{task['id']}/transition", json={"to": "IN_PROGRESS"})
    assert started.status_code == 200, started.text
    first = mod.post(f"/api/v1/tasks/{task['id']}/recordings", json=RECORDER)
    assert first.status_code == 201, first.text
    mod.post(f"/api/v1/recordings/{first.json()['id']}/discard", json={"reason": "test"})
    world["kok"].consent_mode = "ONLINE"
    db.commit()
    detail = pa.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["consent_missing"] == ["A", "B"]
    assert detail["participant_a"]["consent_status"] is None
    assert detail["participant_a"]["consent_form"] is None
    again = mod.post(f"/api/v1/tasks/{task['id']}/recordings", json=RECORDER)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CONSENT_MISSING"
    a, b = (detail["participant_a"], detail["participant_b"])
    refused = new_task(world, a, b)
    assert refused.status_code == 422
    assert "not agreed" in refused.json()["error"]["message"]
    # Nothing was thrown away: back to Upload, the forms count again.
    world["kok"].consent_mode = "UPLOAD"
    db.commit()
    assert pa.get(f"/api/v1/tasks/{task['id']}").json()["consent_missing"] == []


def test_the_rule_is_the_same_in_the_consent_module(world: dict[str, Any]) -> None:
    db, kok = world["db"], world["kok"]
    a, b = signed_pair(world)
    standing = consent.standings(db, kok, [uuid.UUID(a["id"]), uuid.UUID(b["id"])])
    assert {s.status for s in standing.values()} == {"UPLOADED"}
    assert all(s.consented for s in standing.values())
    assert consent.Standing().status is None
    assert not consent.Standing().consented


# ---------------------------------------------------------------- who may do what


def test_the_task_moderator_sees_and_replaces_the_consent_form_but_not_the_address_proof(
    world: dict[str, Any],
) -> None:
    pa, kok = world["pa"], world["kok"].id
    task, a, _ = task_with_staff(world)
    proof = put(pa, kok, a["id"], "address-proof", PDF).json()
    mod = world["api"]("mod@example.org")
    listed = mod.get(docs_url(kok, a["id"]))
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["consent_form"] is not None
    assert body["address_proof"] is None
    assert body["may_view_address_proof"] is False
    assert body["may_upload_consent_form"] is True
    assert body["may_upload_address_proof"] is False
    assert all(d["kind"] == "CONSENT_FORM" for d in body["earlier"])
    replaced = put(mod, kok, a["id"], "consent-form", JPEG, name="better.jpg")
    assert replaced.status_code == 201, replaced.text
    assert replaced.json()["uploaded_by"] == "mod"
    assert mod.post(f"{docs_url(kok, a['id'])}/{replaced.json()['id']}/url").status_code == 200
    assert put(mod, kok, a["id"], "address-proof", PDF).status_code == 403
    assert mod.post(f"{docs_url(kok, a['id'])}/{proof['id']}/url").status_code == 404
    detail = mod.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["participant_a"]["consent_form"]["id"] == replaced.json()["id"]
    assert detail["participant_a"]["can_upload_consent_form"] is True


def test_the_moderator_loses_access_when_the_task_is_closed(world: dict[str, Any]) -> None:
    kok, db = world["kok"].id, world["db"]
    task, a, _ = task_with_staff(world)
    mod = world["api"]("mod@example.org")
    for status in ("APPROVED", "REJECTED", "CANCELLED"):
        set_status(db, uuid.UUID(task["id"]), status)
        assert mod.get(docs_url(kok, a["id"])).status_code == 403, status
        assert put(mod, kok, a["id"], "consent-form", PDF).status_code == 403, status
    set_status(db, uuid.UUID(task["id"]), "ON_HOLD", held_from="ASSIGNED")
    assert mod.get(docs_url(kok, a["id"])).status_code == 200


def test_the_qc_executive_of_the_task_may_look_but_not_upload(world: dict[str, Any]) -> None:
    pa, kok = world["pa"], world["kok"].id
    task, a, b = task_with_staff(world)
    proof = put(pa, kok, a["id"], "address-proof", PDF).json()
    qc = world["api"]("qc@example.org")
    for person in (a, b):
        listed = qc.get(docs_url(kok, person["id"]))
        assert listed.status_code == 200, listed.text
        assert listed.json()["consent_form"] is not None
        assert listed.json()["address_proof"] is None
        assert listed.json()["may_upload_consent_form"] is False
        form_id = listed.json()["consent_form"]["id"]
        assert qc.post(f"{docs_url(kok, person['id'])}/{form_id}/url").status_code == 200
        assert put(qc, kok, person["id"], "consent-form", PDF).status_code == 403
    assert qc.post(f"{docs_url(kok, a['id'])}/{proof['id']}/url").status_code == 404
    detail = qc.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["participant_a"]["consent_form"] is not None
    assert detail["participant_a"]["can_upload_consent_form"] is False


def test_everyone_else_in_the_project_is_refused(world: dict[str, Any]) -> None:
    pa, kok = world["pa"], world["kok"].id
    task, a, _ = task_with_staff(world)
    form = pa.get(docs_url(kok, a["id"])).json()["consent_form"]
    for email in ("mod2@example.org", "qc2@example.org", "cv@example.org"):
        other = world["api"](email)
        assert other.get(docs_url(kok, a["id"])).status_code == 403, email
        assert other.post(f"{docs_url(kok, a['id'])}/{form['id']}/url").status_code == 403, email
        assert put(other, kok, a["id"], "consent-form", PDF).status_code in (403, 404), email
        party = other.get(f"/api/v1/tasks/{task['id']}")
        if party.status_code == 200:  # the Client Viewer does not see tasks at all
            assert party.json()["participant_a"]["consent_form"] is None
            assert party.json()["participant_a"]["can_upload_consent_form"] is False


def test_ids_from_another_project_answer_not_found(world: dict[str, Any]) -> None:
    pa, kok, onl = world["pa"], world["kok"].id, world["onl"].id
    opa = world["api"]("opa@example.org")
    ours = make_participant(pa, kok, "Asha", agreed=False)
    form = put(pa, kok, ours["id"], "consent-form", PDF).json()
    theirs = make_participant(opa, onl, "Ola", agreed=False)
    proof = put(opa, onl, theirs["id"], "address-proof", PDF).json()
    # Not a member of the other project: like a project that does not exist.
    assert pa.get(docs_url(onl, theirs["id"])).status_code == 404
    assert opa.get(docs_url(kok, ours["id"])).status_code == 404
    assert put(opa, kok, ours["id"], "address-proof", PDF).status_code == 404
    assert opa.post(f"{docs_url(kok, ours['id'])}/{form['id']}/url").status_code == 404
    # Their participant through our project, and their document through our participant.
    assert pa.get(docs_url(kok, theirs["id"])).status_code == 404
    assert put(pa, kok, theirs["id"], "address-proof", PDF).status_code == 404
    assert pa.post(f"{docs_url(kok, ours['id'])}/{proof['id']}/url").status_code == 404
    assert pa.post(f"{docs_url(kok, ours['id'])}/{uuid.uuid4()}/url").status_code == 404


def test_the_address_proof_is_the_persons_in_every_project(world: dict[str, Any]) -> None:
    """One address proof for the person; a consent form belongs to its project only."""
    pa, db, kok, onl = world["pa"], world["db"], world["kok"], world["onl"]
    p = make_participant(pa, kok.id, "Asha", agreed=False)
    put(pa, kok.id, p["id"], "consent-form", PDF)
    put(pa, kok.id, p["id"], "address-proof", PNG, name="p.png", content_type="image/png")
    make_user(db, "both@example.org", ["PROJECT_ADMIN"], projects=[kok, onl])
    both = world["api"]("both@example.org")
    assert (
        both.post(
            f"/api/v1/projects/{onl.id}/participants/link",
            json={"participant_code": p["participant_code"]},
        ).status_code
        == 201
    )
    there = both.get(docs_url(onl.id, p["id"])).json()
    assert there["address_proof"] is not None
    assert there["consent_form"] is None


# ---------------------------------------------------------------- removal and storage upkeep


def test_removing_a_participant_deletes_the_address_proof_and_keeps_the_signed_form(
    world: dict[str, Any], s3: Any
) -> None:
    pa, db, kok = world["pa"], world["db"], world["kok"].id
    p = make_participant(pa, kok, "Asha", agreed=False)
    form = put(pa, kok, p["id"], "consent-form", PDF).json()
    put(pa, kok, p["id"], "address-proof", PDF)
    put(pa, kok, p["id"], "address-proof", PNG, name="p.png", content_type="image/png")
    removed = pa.post(
        f"/api/v1/projects/{kok}/participants/{p['id']}/delete", json={"reason": "Asked to go"}
    )
    assert removed.status_code == 200, removed.text
    db.expire_all()
    docs = {d.id: d for d in db.scalars(select(ParticipantDocument))}
    proofs = [d for d in docs.values() if d.kind == "ADDRESS_PROOF"]
    assert len(proofs) == 2
    assert all(d.removed_at is not None for d in proofs)
    for d in proofs:
        with pytest.raises(Exception, match=r"NoSuchKey|Not Found|404"):
            s3.get_object(Bucket=BUCKET, Key=d.storage_key)
    kept = docs[uuid.UUID(form["id"])]
    assert kept.removed_at is None
    assert s3.get_object(Bucket=BUCKET, Key=kept.storage_key)["Body"].read() == PDF
    listed = pa.get(docs_url(kok, p["id"])).json()
    assert listed["address_proof"] is None
    assert listed["earlier"] == []
    assert listed["consent_form"]["id"] == form["id"]
    assert listed["may_upload_consent_form"] is False
    assert put(pa, kok, p["id"], "consent-form", PDF).status_code == 409


def test_storage_upkeep_keeps_documents_and_replaced_versions(world: dict[str, Any]) -> None:
    pa, db, kok = world["pa"], world["db"], world["kok"].id
    p = make_participant(pa, kok, "Asha", agreed=False)
    put(pa, kok, p["id"], "consent-form", PDF)
    put(pa, kok, p["id"], "consent-form", PNG, name="p.png", content_type="image/png")
    storage = world["app"].state.storage
    storage.put_bytes("documents/stray", PDF, content_type="application/pdf", sha256="x")
    orphans = recordings.storage_orphans(db, storage, timedelta(0))
    assert [o.key for o in orphans] == ["documents/stray"]
