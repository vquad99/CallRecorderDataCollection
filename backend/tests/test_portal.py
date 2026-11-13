"""Participant personal page (D-067): a private link, the consent form, the participant's own
sessions - and nothing else.

Requirements: PART-006, PART-013, PART-014, ROLE-001
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from app.modules.participants.models import ConsentRecord, ParticipantPortalLink
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from tests import test_recordings
from tests.conftest import Api, make_participant
from tests.test_recordings import _record, chunks

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world

FORM = "I agree that my voice is recorded and used for speech research."


def _setup(world: dict[str, Any], text: str = FORM) -> tuple[str, str, str]:
    """Returns (project id, participant A's id, A's personal token)."""
    db, pid = world["db"], str(world["project"].id)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=text))
    db.commit()
    a = world["task"]["participant_a"]["id"]
    made = world["pa"].post(f"/api/v1/projects/{pid}/participants/{a}/portal-link")
    assert made.status_code == 201, made.text
    url = made.json()["url"]
    assert "/portal#" in url, "the secret sits after #, which browsers never send to a server"
    return pid, a, url.split("#", 1)[1]


def _visitor(world: dict[str, Any], token: str) -> tuple[Api, dict[str, str]]:
    from fastapi.testclient import TestClient

    api = Api(TestClient(world["app"]))  # no session: a participant has no account
    api.client.get("/api/v1/auth/csrf")
    return api, {"X-Portal-Token": token}


def test_the_page_shows_only_the_participants_own_sessions(world: dict[str, Any]) -> None:
    _record(world, chunks(60, 0))
    pid, _, token = _setup(world)
    other = make_participant(world["pa"], pid, "Chitra")  # same project, on no task
    other_token = (
        world["pa"]
        .post(f"/api/v1/projects/{pid}/participants/{other['id']}/portal-link")
        .json()["url"]
        .split("#", 1)[1]
    )
    api, head = _visitor(world, token)
    page = api.get("/api/v1/portal/me", headers=head)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["participant_code"] == world["task"]["participant_a"]["participant_code"]
    assert body["consent_text"] == FORM
    assert body["consent_status"] is None
    assert [s["task_code"] for s in body["sessions"]] == [world["task"]["task_code"]]
    assert body["sessions"][0]["state"] == "Recorded, being checked"
    assert body["sessions"][0]["minutes"] == 1.0
    assert body["display_name"] == "Asha", "the participant sees their own details (D-100)"
    text = page.text
    for private in ("Bina", "display_label", "storage_key", "moderator"):
        assert private not in text, private
    theirs = api.get("/api/v1/portal/me", headers={"X-Portal-Token": other_token}).json()
    assert theirs["sessions"] == []


def test_accepted_minutes_count_only_approved_sessions(world: dict[str, Any]) -> None:
    _record(world, chunks(120, 0))
    _, _, token = _setup(world)
    api, head = _visitor(world, token)
    assert api.get("/api/v1/portal/me", headers=head).json()["accepted_minutes"] == 0
    db = world["db"]
    db.execute(update(Task).where(Task.id == world["task"]["id"]).values(status="APPROVED"))
    db.commit()
    body = api.get("/api/v1/portal/me", headers=head).json()
    assert (body["accepted_minutes"], body["sessions"][0]["state"]) == (2.0, "Accepted")
    # Their own share for payment: half of each accepted conversation (D-095, D-100).
    assert (body["recorded_minutes"], body["payable_minutes"]) == (2.0, 1.0)


def test_the_participant_answers_and_withdraws_consent_themselves(world: dict[str, Any]) -> None:
    pid, a, token = _setup(world)
    api, head = _visitor(world, token)
    nothing = api.post("/api/v1/portal/consent", json={"decision": "WITHDRAWN"}, headers=head)
    assert nothing.json()["error"]["code"] == "NOTHING_TO_WITHDRAW"
    given = api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert given.status_code == 200, given.text
    assert given.json()["consent_status"] == "GIVEN"
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)  # again: no-op
    gone = api.post("/api/v1/portal/consent", json={"decision": "WITHDRAWN"}, headers=head)
    assert gone.json()["consent_status"] == "WITHDRAWN"
    db = world["db"]
    rows = db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.task_id.is_(None))
        .order_by(ConsentRecord.created_at)
    ).all()
    assert [(r.status, r.method, r.captured_by) for r in rows] == [
        ("GIVEN", "DIGITAL", None),
        ("WITHDRAWN", "DIGITAL", None),
    ]
    # Staff see the participant's own answers in the consent history.
    history = world["pa"].get(f"/api/v1/projects/{pid}/participants/{a}/consent").json()
    assert [h["status"] for h in history if h["captured_by"] is None] == ["WITHDRAWN", "GIVEN"]
    # No CSRF token, no change (a hostile page cannot answer for the participant).
    bare = api.client.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert bare.status_code == 403


def test_without_a_consent_form_nothing_can_be_answered(world: dict[str, Any]) -> None:
    _, _, token = _setup(world, text="")
    api, head = _visitor(world, token)
    answer = api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert answer.json()["error"]["code"] == "CONSENT_FORM_MISSING"


def test_wrong_expired_replaced_and_revoked_links_all_answer_the_same(
    world: dict[str, Any],
) -> None:
    pid, a, token = _setup(world)
    api, _ = _visitor(world, token)

    def ask(t: str) -> tuple[int, Any]:
        r = api.get("/api/v1/portal/me", headers={"X-Portal-Token": t})
        return r.status_code, r.json()["error"]["code"] if r.status_code != 200 else None

    never = ask("x" * 43)
    assert never == (404, "LINK_INVALID")
    assert api.get("/api/v1/portal/me").status_code == 422  # no header at all
    db = world["db"]
    assert db.scalar(select(ParticipantPortalLink.token_hash)) != token, "only a hash is stored"
    # Replaced: a new link ends the old one.
    world["pa"].post(f"/api/v1/projects/{pid}/participants/{a}/portal-link")
    assert ask(token) == never
    newer = (
        world["pa"]
        .post(f"/api/v1/projects/{pid}/participants/{a}/portal-link")
        .json()["url"]
        .split("#", 1)[1]
    )
    assert ask(newer) == (200, None)
    # Expired.
    db.execute(
        update(ParticipantPortalLink)
        .where(ParticipantPortalLink.revoked_at.is_(None))
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db.commit()
    assert ask(newer) == never
    # Revoked by staff.
    last = (
        world["pa"]
        .post(f"/api/v1/projects/{pid}/participants/{a}/portal-link")
        .json()["url"]
        .split("#", 1)[1]
    )
    assert (
        world["pa"].delete(f"/api/v1/projects/{pid}/participants/{a}/portal-link").status_code
        == 204
    )
    assert ask(last) == never


def test_only_people_who_manage_participants_create_links(world: dict[str, Any]) -> None:
    pid = str(world["project"].id)
    a = world["task"]["participant_a"]["id"]
    for who in (world["mod"], world["api"]("qc@example.org")):
        assert who.post(f"/api/v1/projects/{pid}/participants/{a}/portal-link").status_code == 403


def test_the_consent_record_downloads_with_the_recording(world: dict[str, Any]) -> None:
    rid = _record(world, chunks(2, 0))
    task = world["task"]
    for who in ("participant_a", "participant_b"):
        ok = world["mod"].post(
            f"/api/v1/tasks/{task['id']}/consent",
            json={
                "participant_id": task[who]["id"],
                "status": "GIVEN",
                "method": "VERBAL_RECORDED",
                "note": "",
            },
        )
        assert ok.status_code in (200, 201, 409), ok.text
    _, _, token = _setup(world)
    api, head = _visitor(world, token)
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    # The project's form changes afterwards: the record keeps the text that was answered.
    db = world["db"]
    db.execute(
        update(Project).where(Project.id == world["project"].id).values(consent_text="New text")
    )
    db.commit()
    got = world["pa"].get(f"/api/v1/recordings/{rid}/consent-form")
    assert got.status_code == 200, got.text
    assert got.headers["content-type"].startswith("text/html")
    assert got.headers["content-disposition"] == (
        f'attachment; filename="consent_{task["task_code"]}_{rid}.html"'
    )
    html = got.text
    assert task["participant_a"]["participant_code"] in html
    assert task["participant_b"]["participant_code"] in html
    assert FORM in html, "the text the participant answered"
    assert "New text" not in html
    assert "The participant" in html
    assert "SHA-256" in html, "ties the record to the audio files"
    for private in ("Asha", "Bina"):
        assert private not in html, "participants appear by code only"
    # Same right as downloading the audio: a moderator may listen but not download.
    assert world["mod"].get(f"/api/v1/recordings/{rid}/consent-form").status_code == 403
    assert (
        world["pa"].get("/api/v1/recordings/00000000-0000-0000-0000-000000000001/consent-form")
    ).status_code == 404


def test_the_consent_link_is_emailed_to_the_participant(
    world: dict[str, Any], tmp_path: Any
) -> None:
    from pathlib import Path

    pid = str(world["project"].id)
    pa = world["pa"]
    a = world["task"]["participant_a"]["id"]
    no_email = pa.post(f"/api/v1/projects/{pid}/participants/{a}/portal-link/email")
    assert (no_email.status_code, no_email.json()["error"]["code"]) == (409, "NO_EMAIL")
    bad = pa.patch(
        f"/api/v1/projects/{pid}/participants/{a}",
        json={"display_label": "Asha", "language_code": "hi", "email": "not-an-email"},
    )
    assert bad.json()["error"]["code"] == "INVALID_EMAIL"
    saved = pa.patch(
        f"/api/v1/projects/{pid}/participants/{a}",
        json={"display_label": "Asha", "language_code": "hi", "email": "Asha@Example.org"},
    )
    assert saved.status_code == 200, saved.text
    assert (saved.json()["email"], saved.json()["has_email"]) == ("Asha@example.org", True)
    # A correction that does not mention the email keeps it.
    kept = pa.patch(
        f"/api/v1/projects/{pid}/participants/{a}",
        json={"display_label": "Asha K", "language_code": "hi"},
    )
    assert kept.json()["has_email"] is True
    # The moderator sees that there is an address, never the address itself.
    seen = world["mod"].get(f"/api/v1/projects/{pid}/participants/{a}").json()
    assert (seen["email"], seen["has_email"]) == (None, True)
    sent = pa.post(f"/api/v1/projects/{pid}/participants/{a}/portal-link/email")
    assert sent.status_code == 200, sent.text
    assert sent.json()["sent"] is True
    outbox = Path(world["app"].state.settings.email_file_dir)
    mails = sorted(outbox.glob("*.eml"), key=lambda f: f.stat().st_mtime)
    text = mails[-1].read_text()
    assert "To: Asha@example.org" in text
    assert "/portal#" in text.replace("=\n", "")
    token = text.replace("=\n", "").split("/portal#", 1)[1].split()[0]
    api, _ = _visitor(world, token)
    assert api.get("/api/v1/portal/me", headers={"X-Portal-Token": token}).status_code == 200
    # Removing the address stops further emails.
    pa.patch(
        f"/api/v1/projects/{pid}/participants/{a}",
        json={"display_label": "Asha K", "language_code": "hi", "email": ""},
    )
    again = pa.post(f"/api/v1/projects/{pid}/participants/{a}/portal-link/email")
    assert again.json()["error"]["code"] == "NO_EMAIL"
