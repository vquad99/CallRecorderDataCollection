"""Fixes from the review of 2026-11-17, one test per fix.

Requirements: SEC-005, SEC-006, SEC-007, SEC-010, SEC-011, ROLE-010, TEL-010, PART-006
"""

from __future__ import annotations

import asyncio
import json
import smtplib
import ssl
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select

from app.core import middleware
from app.core.email import OutgoingEmail, SmtpSender
from app.core.middleware import RequestLimitsMiddleware
from app.db.session import create_db_engine
from app.modules.participants.consent import SideConsent
from app.modules.participants.models import ConsentRecord, Participant
from app.modules.tasks.models import Task
from tests.conftest import Api, build_settings, make_participant, make_project, make_user

# ---------------------------------------------------------------- no database


def test_starttls_checks_the_mail_servers_certificate(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class FakeSmtp:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            seen["host"] = host

        def __enter__(self) -> FakeSmtp:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def starttls(self, context: ssl.SSLContext | None = None) -> None:
            seen["context"] = context

        def login(self, user: str, password: str) -> None:
            return None

        def send_message(self, message: Any) -> None:
            seen["sent"] = True

    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    settings = build_settings(email_backend="smtp", smtp_host="mail.example.org")
    SmtpSender(settings).send(OutgoingEmail(to="a@example.org", subject="s", body="b"))
    context = seen["context"]
    assert isinstance(context, ssl.SSLContext), "a context, not Python's accept-anything default"
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert seen["sent"] is True


def test_database_errors_never_carry_the_values() -> None:
    engine = create_db_engine(build_settings())
    assert engine.hide_parameters is True
    engine.dispose()


Result = tuple[int, dict[str, Any] | None, list[bytes], int]


def _limits(received: list[bytes]) -> RequestLimitsMiddleware:
    """The middleware in front of an application that reads the whole body into `received`."""

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        while True:
            message = await receive()
            received.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return RequestLimitsMiddleware(downstream, default_limit=10_000, chunk_limit=100_000)


async def _acall(
    limits: RequestLimitsMiddleware,
    received: list[bytes],
    method: str,
    path: str,
    headers: dict[str, str],
    parts: list[bytes],
) -> Result:
    """Calls the middleware the way a server would. Returns (status, error body, what the
    application received, how many body messages were read from the client)."""
    reads = 0
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal reads
        reads += 1
        index = reads - 1
        if index < len(parts):
            return {
                "type": "http.request",
                "body": parts[index],
                "more_body": index < len(parts) - 1,
            }
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    await limits(scope, receive, send)
    status = sent[0]["status"]
    body = b"".join(m.get("body", b"") for m in sent[1:])
    error = json.loads(body)["error"] if status != 200 else None
    return status, error, received, reads


def _call(method: str, path: str, headers: dict[str, str], parts: list[bytes]) -> Result:
    received: list[bytes] = []
    return asyncio.run(_acall(_limits(received), received, method, path, headers, parts))


SIGNED_IN = {"cookie": "ccp_session=abc; csrf_token=t", "x-csrf-token": "t"}


def test_a_change_without_the_csrf_token_is_refused_before_its_body_is_read() -> None:
    for headers in (
        {"cookie": "ccp_session=abc"},  # no CSRF cookie, no header
        {"cookie": "ccp_session=abc; csrf_token=t"},  # no header
        {"cookie": "ccp_session=abc", "x-csrf-token": "t"},  # no cookie
    ):
        status, error, received, reads = _call(
            "POST", "/api/v1/projects", headers, [b'{"name": "x"}']
        )
        assert error is not None
        assert (status, error["code"], reads, received) == (403, "CSRF_FAILED", 0, [])


def test_a_change_without_a_session_is_refused_before_its_body_is_read() -> None:
    headers = {"cookie": "csrf_token=t", "x-csrf-token": "t"}
    status, error, received, reads = _call(
        "PUT", "/api/v1/recordings/x/chunks/0", headers, [b"\0" * 4000]
    )
    assert error is not None
    assert (status, error["code"], reads, received) == (401, "UNAUTHENTICATED", 0, [])


@pytest.mark.parametrize("path", sorted(middleware.SESSIONLESS_WRITES))
def test_sign_in_password_links_and_the_participant_page_work_without_a_session(
    path: str,
) -> None:
    headers = {"cookie": "csrf_token=t", "x-csrf-token": "t"}
    status, _, received, _ = _call("POST", path, headers, [b"{}"])
    assert (status, received) == (200, [b"{}"])


def test_a_body_in_pieces_reaches_the_application_unchanged() -> None:
    pieces = [b'{"a": "', b"x" * 3000, b'"}']
    status, _, received, reads = _call("POST", "/api/v1/projects", SIGNED_IN, pieces)
    assert status == 200
    assert b"".join(received) == b"".join(pieces)
    assert reads == 3


def test_a_nul_split_across_pieces_is_still_found() -> None:
    status, error, received, _ = _call(
        "POST", "/api/v1/projects", SIGNED_IN, [b'{"a": "x\\u00', b'00"}']
    )
    assert error is not None
    assert (status, error["code"], received) == (422, "VALIDATION_ERROR", [])


def test_large_bodies_are_read_a_few_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middleware, "BODY_READ_WAIT_SECONDS", 0.05)
    received: list[bytes] = []
    limits = _limits(received)

    async def busy() -> Result:
        for _ in range(middleware.BODY_READ_SLOTS):
            await limits._large_reads.acquire()  # every slot taken
        return await _acall(
            limits,
            received,
            "PUT",
            "/api/v1/recordings/x/chunks/0",
            SIGNED_IN,  # no Content-Length: a body of unknown size waits for a turn
            [b"\0" * 4000],
        )

    status, error, received, reads = asyncio.run(busy())
    assert error is not None
    assert (status, error["code"], reads, received) == (503, "BUSY", 0, [])


def test_consent_follows_the_newest_word() -> None:
    """D-119 and calling: the newer of the noted consent and the own answer decides."""

    def record(status: str, minute: int, *, own: bool, review: str | None = None) -> Any:
        return ConsentRecord(
            participant_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            task_id=None if own else uuid.uuid4(),
            captured_by=None if own else uuid.uuid4(),
            status=status,
            method="DIGITAL" if own else "VERBAL_NOTED",
            policy_version="1",
            review_status=review,
            created_at=datetime(2026, 11, 17, 10, minute, tzinfo=UTC),
        )

    def side(*records: Any) -> SideConsent:
        s = SideConsent("A", uuid.uuid4())
        for r in records:
            (s.own if r.is_own_answer else s.noted).append(r)
        return s

    noted_yes = record("GIVEN", 1, own=False)
    later_no = record("WITHDRAWN", 2, own=True)
    assert (side(noted_yes).may_record, side(noted_yes).says_no) == (True, False)
    assert (side(noted_yes, later_no).may_record, side(noted_yes, later_no).says_no) == (
        False,
        True,
    )
    newer_yes = record("GIVEN", 3, own=False)
    assert side(noted_yes, later_no, newer_yes).says_no is False
    sent_back = record("GIVEN", 4, own=True, review="REJECTED")
    assert (side(sent_back).may_record, side(sent_back).says_no) == (False, False)
    assert side().may_record is False


# ---------------------------------------------------------------- on a database


@pytest.fixture
def two_projects(db: Any, new_api: Any) -> dict[str, Any]:
    """OWN (the callers' project) and OTHER (another project, with its own people)."""
    own, other = make_project(db, "OWN"), make_project(db, "OTHER")
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[own])
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    make_user(db, "mod@example.org", ["MODERATOR"], projects=[own])
    make_user(db, "qc.other@example.org", ["QC_EXECUTIVE"], projects=[other])
    make_user(db, "mod.other@example.org", ["MODERATOR"], projects=[other])
    root: Api = new_api()
    assert root.login("root@example.org").status_code == 200
    pa: Api = new_api()
    assert pa.login("pa@example.org").status_code == 200
    mine = [make_participant(pa, own.id, name) for name in ("Asha", "Bina")]
    theirs = [make_participant(root, other.id, name) for name in ("Chitra", "Devi")]
    return {"db": db, "own": own, "other": other, "pa": pa, "mine": mine, "theirs": theirs}


@pytest.mark.db
def test_list_pages_are_bounded(two_projects: dict[str, Any]) -> None:
    pa: Api = two_projects["pa"]
    project = two_projects["own"].id
    for path in (
        "/api/v1/tasks",
        "/api/v1/projects",
        f"/api/v1/projects/{project}/participants",
        "/api/v1/audit-logs",
        f"/api/v1/projects/{project}/exports",
        "/api/v1/calls",
    ):
        far = pa.get(path, params={"page": 10_001})
        assert (far.status_code, far.json()["error"]["code"]) == (422, "VALIDATION_ERROR"), path


@pytest.mark.db
def test_bulk_actions_refuse_participants_of_another_project(two_projects: dict[str, Any]) -> None:
    w = two_projects
    db = w["db"]
    base = f"/api/v1/projects/{w['own'].id}/participants/bulk"
    foreign = [p["id"] for p in w["theirs"]]
    removed = (
        w["pa"]
        .post(base, json={"action": "remove", "participant_ids": foreign, "reason": "Moved away"})
        .json()
    )
    assert (removed["done"], removed["failed"]) == (0, 2)
    assert all(r["message"] == "Participant not found" for r in removed["results"])
    assert all(r["participant_code"] == "?" for r in removed["results"]), "no code leaks"
    sent = w["pa"].post(base, json={"action": "send_consent", "participant_ids": foreign}).json()
    assert (sent["done"], sent["failed"]) == (0, 2)
    db.expire_all()
    still = db.scalar(
        select(func.count())
        .select_from(Participant)
        .where(
            Participant.id.in_([uuid.UUID(x) for x in foreign]), Participant.deleted_at.is_(None)
        )
    )
    assert still == 2


@pytest.mark.db
def test_task_import_refuses_participant_codes_of_another_project(
    two_projects: dict[str, Any],
) -> None:
    w = two_projects
    a, b = (p["participant_code"] for p in w["theirs"])
    mine_a = w["mine"][0]["participant_code"]
    csv = f"participant_a,participant_b\n{a},{b}\n{mine_a},{b}\n"
    body = {"project_id": str(w["own"].id), "csv": csv, "confirm": True}
    result = w["pa"].post("/api/v1/tasks/import", json=body).json()
    assert result["created"] == 0
    assert [r["ok"] for r in result["rows"]] == [False, False]
    assert all("is not in this project" in r["message"] for r in result["rows"])
    assert w["db"].scalar(select(func.count()).select_from(Task)) == 0


@pytest.mark.db
def test_qc_and_moderator_from_another_project_cannot_be_assigned(
    two_projects: dict[str, Any],
) -> None:
    w = two_projects
    pa: Api = w["pa"]
    a, b = w["mine"]
    task = pa.post(
        "/api/v1/tasks",
        json={
            "project_id": str(w["own"].id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": a["id"],
            "participant_b_id": b["id"],
        },
    ).json()
    db = w["db"]
    from app.modules.auth.models import User

    def user_id(email: str) -> str:
        return str(db.scalar(select(User.id).where(User.email == email)))

    qc = pa.post(
        f"/api/v1/tasks/{task['id']}/assign-qc", json={"user_id": user_id("qc.other@example.org")}
    )
    assert (qc.status_code, qc.json()["error"]["code"]) == (422, "NOT_PROJECT_MEMBER")
    mod = pa.post(
        f"/api/v1/tasks/{task['id']}/assign", json={"user_id": user_id("mod.other@example.org")}
    )
    assert (mod.status_code, mod.json()["error"]["code"]) == (422, "NOT_PROJECT_MEMBER")
    created = pa.post(
        "/api/v1/tasks",
        json={
            "project_id": str(w["own"].id),
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": a["id"],
            "participant_b_id": w["theirs"][0]["id"],
        },
    )
    assert (created.status_code, created.json()["error"]["code"]) == (
        422,
        "PARTICIPANT_NOT_IN_PROJECT",
    )
