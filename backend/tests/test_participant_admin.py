"""Participants section (D-073): add many from a file, assign to another project, remove, send
consent forms in bulk, and approve or reject a participant's own consent answer.

Requirements: PART-016, PART-017, PART-014
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import update

from app.modules.projects.models import Project
from tests import test_recordings
from tests.conftest import make_participant, make_project, make_user
from tests.test_portal import FORM, _visitor

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world

CSV = (
    "name,phone,email,language,dialect\n"
    "Kiran,+919811100001,kiran@example.org,hi,\n"
    "Lata,,,hi,\n"
    ",+919811100003,,hi,\n"
    "Mohan,+919811100001,,hi,\n"
    "Nila,,not-an-email,hi,\n"
    "Omar,,,Hindi!,\n"
)


def _base(world: dict[str, Any]) -> str:
    return f"/api/v1/projects/{world['project'].id}/participants"


def _link_from_another_admin(world: dict[str, Any], a: str) -> str:
    """A personal link handed out by a second Project Admin: the one who hands out a link may
    not review the answer given on it (D-088), so the tests review as world["pa"]."""
    make_user(world["db"], "pa2@example.org", ["PROJECT_ADMIN"], projects=[world["project"]])
    made = world["api"]("pa2@example.org").post(f"{_base(world)}/{a}/portal-link")
    return str(made.json()["url"].split("#", 1)[1])


def test_a_file_is_checked_first_and_only_good_rows_are_added(world: dict[str, Any]) -> None:
    pa, base = world["pa"], _base(world)
    before = pa.get(base).json()["total"]
    preview = pa.post(f"{base}/import", json={"csv": CSV}).json()
    assert [r["ok"] for r in preview["rows"]] == [True, True, False, False, False, False]
    assert (preview["ready"], preview["created"]) == (2, 0)
    assert pa.get(base).json()["total"] == before, "a preview adds nobody"
    messages = [r["message"] for r in preview["rows"]]
    assert "Name is missing" in messages[2]
    assert "repeated" in messages[3]
    assert "email" in messages[4].lower()
    done = pa.post(f"{base}/import", json={"csv": CSV, "confirm": True}).json()
    assert done["created"] == 2
    assert pa.get(base).json()["total"] == before + 2
    assert all(r["participant_code"] for r in done["rows"] if r["ok"])
    bad = pa.post(f"{base}/import", json={"csv": "label\nx\n"})
    assert bad.json()["error"]["code"] == "INVALID_CSV"
    assert world["mod"].post(f"{base}/import", json={"csv": CSV}).status_code == 403


def test_bulk_send_assign_and_remove_report_each_participant(world: dict[str, Any]) -> None:
    db, pa, base = world["db"], world["pa"], _base(world)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=FORM))
    other = make_project(db, "SECOND")
    outside = make_project(db, "OUTSIDE")
    pa_user = pa.get("/api/v1/auth/me").json()["id"]
    from app.modules.projects.models import ProjectMembership

    db.add(ProjectMembership(user_id=pa_user, project_id=other.id))
    db.commit()
    with_mail = make_participant(pa, world["project"].id, "Kiran")
    pa.patch(
        f"{base}/{with_mail['id']}",
        json={"display_label": "Kiran", "language_code": "hi", "email": "kiran@example.org"},
    )
    without = make_participant(pa, world["project"].id, "Lata")
    ids = [with_mail["id"], without["id"]]

    sent = pa.post(f"{base}/bulk", json={"action": "send_consent", "participant_ids": ids}).json()
    assert (sent["done"], sent["failed"]) == (1, 1)
    assert [r["ok"] for r in sent["results"]] == [True, False]
    assert "no email" in sent["results"][1]["message"]
    listed = {p["id"]: p for p in pa.get(base).json()["items"]}
    assert listed[with_mail["id"]]["link_active"] is True
    assert listed[without["id"]]["link_active"] is False

    assert (
        pa.post(f"{base}/bulk", json={"action": "assign", "participant_ids": ids}).json()["error"][
            "code"
        ]
        == "TARGET_REQUIRED"
    )
    hidden = pa.post(
        f"{base}/bulk",
        json={"action": "assign", "participant_ids": ids, "target_project_id": str(outside.id)},
    )
    assert hidden.status_code == 404, "a project the caller is not in looks missing"
    moved = pa.post(
        f"{base}/bulk",
        json={"action": "assign", "participant_ids": ids, "target_project_id": str(other.id)},
    ).json()
    assert moved["done"] == 2
    assert pa.get(f"/api/v1/projects/{other.id}/participants").json()["total"] == 2
    again = pa.post(
        f"{base}/bulk",
        json={"action": "assign", "participant_ids": ids, "target_project_id": str(other.id)},
    ).json()
    assert (again["done"], again["failed"]) == (0, 2)

    no_reason = pa.post(f"{base}/bulk", json={"action": "remove", "participant_ids": ids})
    assert no_reason.json()["error"]["code"] == "REASON_REQUIRED"
    on_task = world["task"]["participant_a"]["id"]
    removed = pa.post(
        f"{base}/bulk",
        json={"action": "remove", "participant_ids": [*ids, on_task], "reason": "left the study"},
    ).json()
    assert (removed["done"], removed["failed"]) == (2, 1), "someone on an open task stays"
    assert (
        world["mod"]
        .post(f"{base}/bulk", json={"action": "remove", "participant_ids": ids, "reason": "x"})
        .status_code
        == 403
    )


def test_a_consent_answer_is_approved_or_sent_back(world: dict[str, Any]) -> None:
    db, pa, base = world["db"], world["pa"], _base(world)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=FORM))
    db.commit()
    a = world["task"]["participant_a"]["id"]
    nothing = pa.post(f"{base}/{a}/consent-review", json={"decision": "APPROVED"})
    assert nothing.json()["error"]["code"] == "NOTHING_TO_REVIEW"
    token = _link_from_another_admin(world, a)
    api, head = _visitor(world, token)
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    row = next(p for p in pa.get(base).json()["items"] if p["id"] == a)
    assert (row["consent_status"], row["consent_review"]) == ("GIVEN", "PENDING")

    no_note = pa.post(f"{base}/{a}/consent-review", json={"decision": "REJECTED"})
    assert no_note.json()["error"]["code"] == "NOTE_REQUIRED"
    back = pa.post(
        f"{base}/{a}/consent-review", json={"decision": "REJECTED", "note": "Wrong person answered"}
    )
    assert back.status_code == 200, back.text
    page = api.get("/api/v1/portal/me", headers=head).json()
    assert (page["consent_review"], page["consent_review_note"]) == (
        "REJECTED",
        "Wrong person answered",
    )
    # The participant answers again; it waits for review again and can then be approved.
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert api.get("/api/v1/portal/me", headers=head).json()["consent_review"] == "PENDING"
    ok = pa.post(f"{base}/{a}/consent-review", json={"decision": "APPROVED"})
    assert ok.json()["review_status"] == "APPROVED"
    row = next(p for p in pa.get(base).json()["items"] if p["id"] == a)
    assert row["consent_review"] == "APPROVED"
    # Moderators and QC cannot review; a moderator on the task sees the state only.
    assert (
        world["mod"].post(f"{base}/{a}/consent-review", json={"decision": "APPROVED"}).status_code
        == 403
    )
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[world["project"]])
    client_row = next(
        p for p in world["api"]("cv@example.org").get(base).json()["items"] if p["id"] == a
    )
    assert (client_row["consent_status"], client_row["consent_review"]) == (None, None)


def test_one_consent_form_can_be_viewed_and_downloaded(world: dict[str, Any]) -> None:
    db, pa, base = world["db"], world["pa"], _base(world)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=FORM))
    db.commit()
    a = world["task"]["participant_a"]["id"]
    blank = pa.get(f"{base}/{a}/consent-form").json()
    assert (blank["answered"], blank["current"], blank["form_text"]) == (False, None, FORM)
    token = _link_from_another_admin(world, a)
    api, head = _visitor(world, token)
    api.post("/api/v1/portal/consent", json={"decision": "REFUSED"}, headers=head)
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    pa.post(f"{base}/{a}/consent-review", json={"decision": "APPROVED"})
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text="New"))
    db.commit()
    form = pa.get(f"{base}/{a}/consent-form").json()
    assert form["form_text"] == FORM, "the text that was answered, not the project's new text"
    assert (form["current"]["status"], form["current"]["review_status"]) == ("GIVEN", "APPROVED")
    assert [e["status"] for e in form["earlier"]] == ["REFUSED"]
    got = pa.get(f"{base}/{a}/consent-form/file")
    assert got.status_code == 200
    code = world["task"]["participant_a"]["participant_code"]
    assert got.headers["content-disposition"] == f'attachment; filename="consent_VOICE_{code}.html"'
    for expected in (code, FORM, "Agreed", "Approved", "Did not agree"):
        assert expected in got.text, expected
    assert "Asha" not in got.text, "by code only"
    # QC staff and clients have no consent access.
    assert world["api"]("qc@example.org").get(f"{base}/{a}/consent-form").status_code == 403


def test_whoever_hands_out_a_link_cannot_approve_the_answer_given_on_it(
    world: dict[str, Any],
) -> None:
    """D-088: an admin could open the personal link, answer "I agree" and approve it."""
    db, pa, base = world["db"], world["pa"], _base(world)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=FORM))
    db.commit()
    a = world["task"]["participant_a"]["id"]
    token = pa.post(f"{base}/{a}/portal-link").json()["url"].split("#", 1)[1]
    api, head = _visitor(world, token)
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    own = pa.post(f"{base}/{a}/consent-review", json={"decision": "APPROVED"})
    assert own.json()["error"]["code"] == "SAME_PERSON"
    record = pa.get(f"{base}/{a}/consent-form/file").text
    assert "handed out by staff" in record
    make_user(db, "pa3@example.org", ["PROJECT_ADMIN"], projects=[world["project"]])
    other = world["api"]("pa3@example.org").post(
        f"{base}/{a}/consent-review", json={"decision": "APPROVED"}
    )
    assert other.json()["review_status"] == "APPROVED"
