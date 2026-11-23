"""Fixes from the security audit of 2026-11-23 (D-160), one test (or a few) per finding.

Requirements: SEC-001, SEC-005, SEC-006, SEC-007, SEC-011, SEC-014, AUTH-009, EXP-004

V-01 export removal, V-02 adding members, V-03 rate limits with made-up cookies, V-04 older reset
links, V-05 common passwords, V-06 the account-wide lock, V-08 names in emails, V-09 file content
and the virus check, V-10 days off the calendar, V-11 the app's own database role, V-14 phone
numbers from other projects. V-07 (ids in API paths) is tested in the frontend
(src/api/client.test.ts); V-12 and V-13 changed documents and test data only.
"""

from __future__ import annotations

import socket
import struct
import threading
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.core import filecheck, virus
from app.core.errors import AppError
from app.main import create_app
from app.modules.audit.models import AuditLog
from app.modules.auth import passwords
from app.modules.auth.models import LoginAttempt, User
from app.modules.exports.models import ExportJob
from app.modules.operations.service import DUPLICATE_PROBES_ALERT, find_problems
from app.modules.participants.service import HIDDEN_DUPLICATES_PER_DAY
from app.modules.projects.models import Project
from tests.conftest import (
    SPEAKER_DETAILS,
    TEST_PASSWORD,
    Api,
    build_settings,
    link_token,
    make_participant,
    make_project,
    make_user,
    read_outbox,
)

# ---------------------------------------------------------------- no database


@pytest.mark.parametrize(
    "password",
    [
        "aaaaaaaaaaaa",  # one character
        "abababababab",  # two
        "abcdefghijkl",  # the alphabet
        "123456789012",  # digits in a row
        "lkjhgfdsapoi",  # a keyboard row backwards
        "Password2026!",  # a common word with digits added
        "Qwertyuiop123",
        "dubdesk12345",  # the platform's name
        "asha.verma2026",  # the account's own name
    ],
)
def test_common_and_trivial_passwords_are_refused(password: str) -> None:
    assert passwords.weakness(password, "asha.verma@example.org") is not None


@pytest.mark.parametrize(
    "password", ["correct-horse-battery-staple", "Tea at 4 by the river", "8sK!p2#xQz7m"]
)
def test_ordinary_good_passwords_pass(password: str) -> None:
    assert passwords.weakness(password, "asha.verma@example.org") is None


def _png(extra: bytes = b"") -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    pixels = zlib.compress(b"\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
        + extra
    )


JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x11" * 200 + b"\xff\xd9"


def _pdf(body: bytes) -> bytes:
    return b"%PDF-1.7\n" + body + b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


CATALOG = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"


def _refused(data: bytes, content_type: str) -> bool:
    """Whether the content check refuses the file (always as 422 INVALID_FILE_CONTENT)."""
    try:
        filecheck.check_document(data, content_type)
    except AppError as error:
        return (error.status_code, error.code) == (422, "INVALID_FILE_CONTENT")
    return False


def test_plain_documents_pass_the_content_check() -> None:
    assert not _refused(_png(), "image/png")
    assert not _refused(_png(b"\x00\x00"), "image/png")  # zero padding is harmless
    assert not _refused(JPEG, "image/jpeg")
    assert not _refused(JPEG + b"\x00" * 8, "image/jpeg")
    assert not _refused(_pdf(CATALOG), "application/pdf")
    # Picture data in a stream is not read as names, even when its bytes spell /JS by chance.
    picture = zlib.compress(b"\x01/JS \x02" * 50)
    image = (
        b"3 0 obj\n<< /Type /XObject /Subtype /Image /Filter /FlateDecode /Length "
        + str(len(picture)).encode()
        + b" >>\nstream\n"
        + picture
        + b"\nendstream\nendobj\n"
    )
    assert not _refused(_pdf(CATALOG + image), "application/pdf")
    # A link (/URI) is allowed.
    link = b"4 0 obj\n<< /Type /Action /S /URI /URI (https://example.org) >>\nendobj\n"
    assert not _refused(_pdf(CATALOG + link), "application/pdf")


def test_documents_carrying_more_than_a_page_are_refused() -> None:
    page = b"<html><script>alert(1)</script></html>"
    assert _refused(_png(page), "image/png")  # HTML after the image
    assert _refused(JPEG + page, "image/jpeg")
    assert _refused(b"\xff\xd8\xff\xe0" + page, "image/jpeg")  # no end marker
    assert _refused(b"\x89PNG\r\n\x1a\n" + page, "image/png")
    assert _refused(b"%PDF-1.4\n" + page, "application/pdf")  # not a whole PDF
    assert _refused(_pdf(CATALOG + page), "application/pdf")
    script = b"5 0 obj\n<< /Type /Action /S /JavaScript /JS (app.alert(1)) >>\nendobj\n"
    assert _refused(_pdf(CATALOG + script), "application/pdf")
    hidden = b"5 0 obj\n<< /S /J#61vaScript /J#53 (app.alert(1)) >>\nendobj\n"
    assert _refused(_pdf(CATALOG + hidden), "application/pdf")
    launch = b"5 0 obj\n<< /Type /Action /S /Launch /F (cmd.exe) >>\nendobj\n"
    assert _refused(_pdf(CATALOG + launch), "application/pdf")
    attached = b"6 0 obj\n<< /Type /EmbeddedFile /Length 3 >>\nstream\nabc\nendstream\nendobj\n"
    assert _refused(_pdf(CATALOG + attached), "application/pdf")
    # The same action inside a compressed object stream.
    packed = zlib.compress(b"7 0 << /S /JavaScript /JS (app.alert(1)) >>")
    objstm = (
        b"8 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length "
        + str(len(packed)).encode()
        + b" >>\nstream\n"
        + packed
        + b"\nendstream\nendobj\n"
    )
    assert _refused(_pdf(CATALOG + objstm), "application/pdf")


class FakeClamd:
    """A ClamAV daemon that answers INSTREAM with a fixed verdict."""

    def __init__(self, verdict: bytes) -> None:
        self.verdict = verdict
        self.received = b""
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        conn, _ = self.server.accept()
        with conn:
            buf = b""
            while not buf.endswith(b"\0\0\0\0"):
                more = conn.recv(65536)
                if not more:
                    break
                buf += more
            self.received = buf
            conn.sendall(self.verdict + b"\0")

    def close(self) -> None:
        self.server.close()


def test_the_virus_check_refuses_an_infected_file_and_passes_a_clean_one() -> None:
    clean = FakeClamd(b"stream: OK")
    try:
        virus.scan(build_settings(clamav_host="127.0.0.1", clamav_port=clean.port), b"a page")
        clean.thread.join(5)
        assert clean.received.startswith(b"zINSTREAM\0")
        assert b"a page" in clean.received
    finally:
        clean.close()
    infected = FakeClamd(b"stream: Eicar-Test-Signature FOUND")
    try:
        with pytest.raises(AppError) as refused:
            virus.scan(
                build_settings(clamav_host="127.0.0.1", clamav_port=infected.port), b"a page"
            )
        assert refused.value.status_code == 422
        assert refused.value.code == "INFECTED_FILE"
    finally:
        infected.close()


def test_without_a_scanner_uploads_wait_only_when_the_scan_is_required() -> None:
    closed = socket.create_server(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()  # nothing listens there now
    virus.scan(build_settings(), b"x")  # no scanner set up: nothing to do
    virus.scan(build_settings(clamav_host="127.0.0.1", clamav_port=port), b"x")  # logged only
    with pytest.raises(AppError) as waiting:
        virus.scan(
            build_settings(clamav_host="127.0.0.1", clamav_port=port, clamav_required=True), b"x"
        )
    assert waiting.value.status_code == 503


# ---------------------------------------------------------------- with the database


@pytest.fixture
def people(db: Any, new_api: Any) -> dict[str, Any]:
    own, other = make_project(db, "OWN"), make_project(db, "OTHER")
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[own])
    make_user(db, "pa.other@example.org", ["PROJECT_ADMIN"], projects=[other])
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[own])
    make_user(db, "mod@example.org", ["MODERATOR"])
    out: dict[str, Any] = {"db": db, "own": own, "other": other}
    for who, email in (
        ("root", "root@example.org"),
        ("pa", "pa@example.org"),
        ("pa_other", "pa.other@example.org"),
        ("cv", "cv@example.org"),
    ):
        api: Api = new_api()
        assert api.login(email).status_code == 200
        out[who] = api
    return out


def _job(db: Any, project: Project, by: str, state: str = "QUEUED") -> ExportJob:
    requester = db.scalar(select(User).where(User.email == by))
    job = ExportJob(
        project_id=project.id,
        requested_by=requester.id,
        state=state,
        content="metadata",
        scope="finished",
        table_format="csv",
        filters={"layout": "PLATFORM"},
        file_name=f"export_{project.code}.zip",
    )
    db.add(job)
    db.commit()
    return job


def test_a_client_viewer_removes_only_their_own_exports(people: dict[str, Any]) -> None:
    db, own, cv, pa = people["db"], people["own"], people["cv"], people["pa"]
    own.export_layout = "PLATFORM"
    db.commit()
    admins = _job(db, own, "pa@example.org")
    theirs = _job(db, own, "cv@example.org")
    base = f"/api/v1/projects/{own.id}/exports"
    listed = {j["id"]: j["can_remove"] for j in cv.get(base).json()["items"]}
    assert listed == {str(admins.id): False, str(theirs.id): True}
    refused = cv.delete(f"{base}/{admins.id}")
    assert refused.status_code == 403, refused.text
    db.expire_all()
    assert db.get(ExportJob, admins.id).state == "QUEUED"
    assert cv.delete(f"{base}/{theirs.id}").status_code == 200
    assert pa.get(base).json()["items"][0]["can_remove"] is True
    assert pa.delete(f"{base}/{admins.id}").status_code == 200
    # The list stays visible to a Client Viewer in the client's format too (D-149 left it so).
    own.export_layout = "CLIENT"
    db.commit()
    assert cv.get(base).status_code == 200


def test_a_project_admin_cannot_add_a_super_admin_by_id(people: dict[str, Any]) -> None:
    db, own, pa = people["db"], people["own"], people["pa"]
    root = db.scalar(select(User).where(User.email == "root@example.org"))
    mod = db.scalar(select(User).where(User.email == "mod@example.org"))
    refused = pa.post(f"/api/v1/projects/{own.id}/members", json={"user_id": str(root.id)})
    assert refused.status_code == 404, refused.text
    assert (
        pa.post(f"/api/v1/projects/{own.id}/members", json={"user_id": str(mod.id)}).status_code
        == 204
    )
    # A Super Admin may still add one.
    assert (
        people["root"]
        .post(f"/api/v1/projects/{own.id}/members", json={"user_id": str(root.id)})
        .status_code
        == 204
    )


@pytest.fixture
def tight_app(migrated_db: str, outbox: Path) -> FastAPI:
    return create_app(
        build_settings(
            database_url=migrated_db,
            email_file_dir=str(outbox),
            rate_limit_reads_per_minute=5,
            rate_limit_writes_per_minute=5,
        )
    )


def test_made_up_session_cookies_get_no_more_requests_than_none(
    tight_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import ratelimit

    frozen = (int(ratelimit.time.time()) // 60) * 60 + 1
    monkeypatch.setattr(ratelimit.time, "time", lambda: float(frozen))
    with TestClient(tight_app) as client:
        client.get("/api/v1/auth/csrf")
        token = client.cookies.get("csrf_token")
        codes = []
        for _ in range(7):
            client.cookies.set("ccp_session", uuid.uuid4().hex)
            answer = client.post(
                "/api/v1/auth/password/reset",
                json={"token": "x" * 43, "new_password": "correct-horse-battery-staple"},
                headers={"X-CSRF-Token": token or ""},
            )
            codes.append(answer.status_code)
        assert codes[:5] == [400] * 5
        assert codes[5:] == [429, 429]
    with TestClient(tight_app) as client:
        codes = []
        for _ in range(7):
            client.cookies.set("ccp_session", uuid.uuid4().hex)
            codes.append(client.get("/api/v1/projects").status_code)
        # The csrf read above used one of the address's 5: four 401s, then refused.
        assert codes == [401] * 4 + [429] * 3


def test_only_the_newest_password_link_works(db: Any, new_api: Any, outbox: Path) -> None:
    make_user(db, "asha@example.org", ["MODERATOR"])
    api: Api = new_api()
    api.client.get("/api/v1/auth/csrf")
    for _ in range(2):
        assert (
            api.post("/api/v1/auth/password/forgot", json={"email": "asha@example.org"}).status_code
            == 202
        )
    older, newer = (link_token(m) for m in read_outbox(outbox)[-2:])
    assert older != newer
    new_password = "a fresh long passphrase 7"
    stale = api.post(
        "/api/v1/auth/password/reset", json={"token": older, "new_password": new_password}
    )
    assert stale.status_code == 400
    assert (
        api.post(
            "/api/v1/auth/password/reset", json={"token": newer, "new_password": new_password}
        ).status_code
        == 204
    )


def test_a_common_password_is_refused_when_set(db: Any, new_api: Any) -> None:
    make_user(db, "bina@example.org", ["MODERATOR"])
    api: Api = new_api()
    assert api.login("bina@example.org").status_code == 200
    weak = api.post(
        "/api/v1/auth/password/change",
        json={"current_password": TEST_PASSWORD, "new_password": "Password12345!"},
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "WEAK_PASSWORD"


def test_strangers_cannot_lock_the_owner_out_of_an_address_they_used(db: Any, new_api: Any) -> None:
    make_user(db, "owner@example.org", ["MODERATOR"])
    now = datetime.now(UTC)
    # 50 failures from 50 other addresses: the account-wide ceiling.
    for n in range(50):
        db.add(
            LoginAttempt(
                email="owner@example.org", ip=f"203.0.113.{n}", succeeded=False, created_at=now
            )
        )
    db.commit()
    stranger: Api = new_api()
    assert stranger.login("owner@example.org").status_code == 429  # an address never used
    # The owner signed in from this address last week: it is not held up by the ceiling.
    db.add(
        LoginAttempt(
            email="owner@example.org",
            ip="testclient",
            succeeded=True,
            created_at=now - timedelta(days=7),
        )
    )
    db.commit()
    owner: Api = new_api()
    assert owner.login("owner@example.org").status_code == 200


def test_names_in_emails_stay_on_one_line(people: dict[str, Any], outbox: Path) -> None:
    made = people["root"].post(
        "/api/v1/users",
        json={
            "email": "nl@example.org",
            "display_name": "Asha\n\nIMPORTANT: visit http://example.invalid\n\nThanks",
            "roles": ["MODERATOR"],
        },
    )
    assert made.status_code == 201, made.text
    assert (
        made.json()["user"]["display_name"] == "Asha IMPORTANT: visit http://example.invalid Thanks"
    )
    body = read_outbox(outbox)[-1]
    assert "Hello Asha IMPORTANT: visit http://example.invalid Thanks," in body


def test_days_off_the_calendar_are_refused_not_a_server_error(people: dict[str, Any]) -> None:
    root = people["root"]
    for url in (
        "/api/v1/dashboard?date_to=9999-12-31",
        "/api/v1/dashboard?date_from=0001-01-01",
        "/api/v1/payments/moderators?date_to=9999-12-31",
        "/api/v1/payments/participants?date_from=1900-01-01",
        f"/api/v1/projects/{people['own'].id}/export/summary?recorded_to=9999-12-31",
    ):
        answer = root.get(url)
        assert answer.status_code == 422, (url, answer.text)


def test_the_apps_database_role_cannot_change_the_audit_log(migrated_db: str) -> None:
    from app.db.roles import grant_app_role

    owner = create_engine(migrated_db)
    name = f"ccp_app_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    try:
        assert grant_app_role(owner, name, password) == "created"
        assert grant_app_role(owner, name, None) == "updated"
        url = make_url(migrated_db).set(username=name, password=password)
        app_engine = create_engine(url)
        try:
            with app_engine.begin() as conn:
                conn.execute(text("SELECT count(*) FROM audit_logs"))
                conn.execute(text("SELECT count(*) FROM users"))
            for statement in (
                "UPDATE audit_logs SET action = action",
                "DELETE FROM audit_logs",
                "DROP TRIGGER audit_logs_no_update_delete ON audit_logs",
                "CREATE TABLE sneaky (id int)",
                "DELETE FROM alembic_version",
            ):
                with (
                    pytest.raises(Exception, match=r"permission denied|must be owner"),
                    app_engine.begin() as conn,
                ):
                    conn.execute(text(statement))
        finally:
            app_engine.dispose()
    finally:
        with owner.begin() as conn:
            conn.execute(text(f'DROP OWNED BY "{name}"'))
            conn.execute(text(f'DROP ROLE IF EXISTS "{name}"'))
        owner.dispose()


def test_numbers_from_other_projects_are_not_shown_in_a_preview(people: dict[str, Any]) -> None:
    db, own, other = people["db"], people["own"], people["other"]
    make_participant(people["pa_other"], other.id, "Chitra", phone="+919812345670")
    preview = people["pa"].post(
        f"/api/v1/projects/{own.id}/participants/import",
        json={
            "csv": "name,phone,email,language\nChitra Again,+919812345670,chitra2@example.org,hi\n",
            "confirm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    row = preview.json()["rows"][0]
    assert row["ok"] is True, row
    assert "already exists" not in row["message"]
    # Adding is still refused (one person keeps one participant ID), and audited.
    added = people["pa"].post(
        f"/api/v1/projects/{own.id}/participants",
        json={
            "display_label": "Chitra Again",
            "phone": "+919812345670",
            "email": "chitra3@example.org",
            "language_code": "hi",
            **SPEAKER_DETAILS,
        },
    )
    assert added.status_code == 409
    refused = db.scalar(select(AuditLog).where(AuditLog.action == "participant.duplicate_refused"))
    assert refused is not None


def test_testing_many_numbers_is_stopped_and_reported(people: dict[str, Any]) -> None:
    db, own, other = people["db"], people["own"], people["other"]
    make_participant(people["pa_other"], other.id, "Devi", phone="+919812345671")
    pa_id = db.scalar(select(User.id).where(User.email == "pa@example.org"))
    for _ in range(HIDDEN_DUPLICATES_PER_DAY):
        db.add(
            AuditLog(
                action="participant.duplicate_refused",
                entity_type="participant",
                actor_id=pa_id,
            )
        )
    db.commit()
    stopped = people["pa"].post(
        f"/api/v1/projects/{own.id}/participants",
        json={
            "display_label": "Devi Again",
            "phone": "+919812345671",
            "email": "devi2@example.org",
            "language_code": "hi",
            **SPEAKER_DETAILS,
        },
    )
    assert stopped.status_code == 429, stopped.text
    assert stopped.json()["error"]["code"] == "DUPLICATE_LIMIT"
    assert HIDDEN_DUPLICATES_PER_DAY >= DUPLICATE_PROBES_ALERT
    codes = [p.code for p in find_problems(db, build_settings(), {})]
    assert "DUPLICATE_PROBING" in codes
