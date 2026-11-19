"""Participant personal page (D-067): a private link, the consent form, the participant's own
sessions - and nothing else. The answer counts at once and an "I agree" is final (D-129).

Requirements: PART-006, PART-013, PART-014, ROLE-001
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from app.modules.participants.models import ConsentRecord, ParticipantPortalLink
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from tests import test_recordings
from tests.conftest import Api, drop_email, make_participant
from tests.test_recordings import _record, chunks

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world

FORM = "I agree that my voice is recorded and used for speech research."


def _setup(
    world: dict[str, Any], text: str = FORM, participant: str | None = None
) -> tuple[str, str, str]:
    """Returns (project id, the participant's id, their personal token); participant A unless
    another is named."""
    db, pid = world["db"], str(world["project"].id)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=text))
    db.commit()
    who = participant or world["task"]["participant_a"]["id"]
    return pid, who, _token(world, who)


def _token(world: dict[str, Any], participant: str) -> str:
    """A personal link as the consent email carries it (made here without sending one); the
    secret after "#"."""
    from app.modules.participants.models import Participant
    from app.modules.portal import service as portal

    db = world["db"]
    pa = uuid.UUID(world["pa"].get("/api/v1/auth/me").json()["id"])
    person = db.get_one(Participant, uuid.UUID(participant))
    url, _ = portal._issue(db, world["app"].state.settings, world["project"], person, pa, None)
    assert "/portal#" in url, "the secret sits after #, which browsers never send to a server"
    return str(url.split("#", 1)[1])


def _visitor(world: dict[str, Any], token: str) -> tuple[Api, dict[str, str]]:
    from fastapi.testclient import TestClient

    api = Api(TestClient(world["app"]))  # no session: a participant has no account
    api.client.get("/api/v1/auth/csrf")
    return api, {"X-Portal-Token": token}


def test_the_page_shows_only_the_participants_own_sessions(world: dict[str, Any]) -> None:
    _record(world, chunks(60, 0))
    pid, _, token = _setup(world)
    other = make_participant(world["pa"], pid, "Chitra", agreed=False)  # on no task
    other_token = _token(world, other["id"])
    api, head = _visitor(world, token)
    page = api.get("/api/v1/portal/me", headers=head)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["participant_code"] == world["task"]["participant_a"]["participant_code"]
    assert body["consent_text"] == FORM
    assert body["consent_status"] == "GIVEN", "a task is only made for people who agreed"
    assert "consent_review" not in body
    assert [s["task_code"] for s in body["sessions"]] == [world["task"]["task_code"]]
    assert body["sessions"][0]["state"] == "Recorded, being checked"
    assert body["sessions"][0]["minutes"] == 1.0
    assert body["display_name"] == "Asha", "the participant sees their own details (D-100)"
    text = page.text
    for private in ("Bina", "display_label", "storage_key", "moderator"):
        assert private not in text, private
    theirs = api.get("/api/v1/portal/me", headers={"X-Portal-Token": other_token}).json()
    assert (theirs["sessions"], theirs["consent_status"], theirs["consent_at"]) == ([], None, None)


def test_accepted_minutes_count_only_approved_sessions(world: dict[str, Any]) -> None:
    _record(world, chunks(120, 0))
    _, _, token = _setup(world)
    api, head = _visitor(world, token)
    assert api.get("/api/v1/portal/me", headers=head).json()["accepted_minutes"] == 0
    db = world["db"]
    db.execute(update(Task).where(Task.id == world["task"]["id"]).values(status="APPROVED"))
    db.commit()
    body = api.get("/api/v1/portal/me", headers=head).json()
    # Their own share: half of each 2-minute conversation (D-095, D-100, D-111).
    assert (body["accepted_minutes"], body["sessions"][0]["state"]) == (1.0, "Accepted")
    assert (body["recorded_minutes"], body["payable_minutes"]) == (1.0, 1.0)


def test_an_answer_counts_at_once_and_an_agreement_is_final(world: dict[str, Any]) -> None:
    """D-129: no staff review, no withdrawing; "I do not agree" may become "I agree" later."""
    pid = str(world["project"].id)
    chitra = make_participant(world["pa"], pid, "Chitra", agreed=False)
    _, c, token = _setup(world, participant=chitra["id"])
    api, head = _visitor(world, token)

    def answer(decision: str) -> Any:
        return api.post("/api/v1/portal/consent", json={"decision": decision}, headers=head)

    withdraw = answer("WITHDRAWN")
    assert (withdraw.status_code, withdraw.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert answer("REFUSED").json()["consent_status"] == "REFUSED"
    assert answer("REFUSED").status_code == 200  # the same answer again changes nothing
    given = answer("GIVEN")
    assert given.status_code == 200, given.text
    assert given.json()["consent_status"] == "GIVEN"
    assert given.json()["consent_at"]
    assert answer("GIVEN").status_code == 200  # a second click changes nothing
    changed = answer("REFUSED")
    assert (changed.status_code, changed.json()["error"]["code"]) == (409, "ALREADY_AGREED")
    assert changed.json()["error"]["message"] == (
        "You have already agreed to this consent form. Your answer cannot be changed."
    )
    rows = (
        world["db"]
        .scalars(
            select(ConsentRecord)
            .where(ConsentRecord.participant_id == uuid.UUID(chitra["id"]))
            .order_by(ConsentRecord.created_at)
        )
        .all()
    )
    assert [(r.status, r.method, r.captured_by, r.review_status) for r in rows] == [
        ("REFUSED", "DIGITAL", None, None),
        ("GIVEN", "DIGITAL", None, None),
    ]
    # Staff see it agreed at once, with nothing to review; the history keeps both answers.
    listed = world["pa"].get(f"/api/v1/projects/{pid}/participants").json()["items"]
    row = next(p for p in listed if p["id"] == c)
    assert row["consent_status"] == "GIVEN"
    assert "consent_review" not in row
    history = world["pa"].get(f"/api/v1/projects/{pid}/participants/{c}/consent").json()
    assert [h["status"] for h in history] == ["GIVEN", "REFUSED"]
    # No CSRF token, no change (a hostile page cannot answer for the participant).
    bare = api.client.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert bare.status_code == 403


def test_an_agreement_sent_back_before_d129_can_be_given_again(world: dict[str, Any]) -> None:
    """An "agree" staff sent back in the review that existed before D-129 is not agreed: the page
    asks for an answer again, and the new one counts at once."""
    pid = str(world["project"].id)
    chitra = make_participant(world["pa"], pid, "Chitra", agreed=False)
    _, c, token = _setup(world, participant=chitra["id"])
    api, head = _visitor(world, token)
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    db = world["db"]
    db.execute(
        update(ConsentRecord)
        .where(ConsentRecord.participant_id == uuid.UUID(c))
        .values(review_status="REJECTED", review_note="Wrong person answered")
    )
    db.commit()
    page = api.get("/api/v1/portal/me", headers=head).json()
    assert (page["consent_status"], page["consent_at"]) == (None, None)
    form = world["pa"].get(f"/api/v1/projects/{pid}/participants/{c}/consent-form").json()
    assert (form["answered"], form["current"]) == (False, None)
    assert [e["status"] for e in form["earlier"]] == ["GIVEN"]
    again = api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert again.json()["consent_status"] == "GIVEN"


def test_without_a_consent_form_nothing_can_be_answered(world: dict[str, Any]) -> None:
    pid = str(world["project"].id)
    chitra = make_participant(world["pa"], pid, "Chitra", agreed=False)
    _, _, token = _setup(world, text="", participant=chitra["id"])
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
    newer = _token(world, a)
    assert ask(token) == never
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
    last = _token(world, a)
    assert (
        world["pa"].delete(f"/api/v1/projects/{pid}/participants/{a}/portal-link").status_code
        == 204
    )
    assert ask(last) == never


def test_staff_are_never_given_a_participants_link(world: dict[str, Any]) -> None:
    """The link goes only to the participant's email: whoever holds it can answer the consent
    form, so there is no way for staff to be shown it."""
    pid = str(world["project"].id)
    a = world["task"]["participant_a"]["id"]
    for who in (world["pa"], world["mod"]):
        gone = who.post(f"/api/v1/projects/{pid}/participants/{a}/portal-link")
        assert gone.status_code in (404, 405), gone.text
        assert "portal#" not in gone.text
    assert world["db"].scalar(select(ParticipantPortalLink.id)) is None


def test_the_consent_record_downloads_with_the_recording(world: dict[str, Any]) -> None:
    """The consent record holds what each participant answered on their page, with the form
    text they answered (D-068); nothing is noted for the session any more (D-129)."""
    pid = str(world["project"].id)
    _setup(world)  # the project's consent form
    people = [make_participant(world["pa"], pid, n, agreed=False) for n in ("Chitra", "Devi")]
    for person in people:
        api, head = _visitor(world, _token(world, person["id"]))
        given = api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
        assert given.status_code == 200, given.text
    task = world["pa"].post(
        "/api/v1/tasks",
        json={
            "project_id": pid,
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": people[0]["id"],
            "participant_b_id": people[1]["id"],
        },
    )
    assert task.status_code == 201, task.text
    task = task.json()
    mod_id = world["mod"].get("/api/v1/auth/me").json()["id"]
    world["pa"].post(f"/api/v1/tasks/{task['id']}/assign", json={"user_id": mod_id})
    world["mod"].post(f"/api/v1/tasks/{task['id']}/transition", json={"to": "IN_PROGRESS"})
    rid = _record({**world, "task": task}, chunks(2, 0))
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
    for person in people:
        assert person["participant_code"] in html
    assert html.count(FORM) == 2, "the text each participant answered"
    assert "New text" not in html
    assert "The participant" in html
    assert "noted for this session" not in html, "nothing noted, nothing shown"
    assert "SHA-256" in html, "ties the record to the audio files"
    for private in ("Chitra", "Devi"):
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
    drop_email(world["db"], a)  # saved before every participant needed an email (D-128)
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
    assert "withdraw" not in text.replace("=\n", ""), "nobody can withdraw (D-129)"
    assert "/portal#" in text.replace("=\n", "")
    token = text.replace("=\n", "").split("/portal#", 1)[1].split()[0]
    api, _ = _visitor(world, token)
    assert api.get("/api/v1/portal/me", headers={"X-Portal-Token": token}).status_code == 200
    # The address cannot be removed: the consent form is sent there (D-128).
    removed = pa.patch(
        f"/api/v1/projects/{pid}/participants/{a}",
        json={"display_label": "Asha K", "language_code": "hi", "email": ""},
    )
    assert removed.json()["error"]["code"] == "EMAIL_REQUIRED"
    assert pa.get(f"/api/v1/projects/{pid}/participants/{a}").json()["has_email"] is True
