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
from tests.conftest import give_consent, make_participant, make_project, make_user
from tests.test_portal import FORM, _visitor

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world

CSV = (
    "name,phone,email,language,dialect\n"
    "Kiran,+919811100001,kiran@example.org,hi,\n"
    "Lata,,lata@example.org,hi,\n"
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
    # Saved before every participant needed an email (D-128).
    from app.modules.participants.models import Participant

    db.execute(update(Participant).where(Participant.id == without["id"]).values(email_enc=None))
    db.commit()
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
    # A client viewer has no list of the project's people at all (D-112).
    make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[world["project"]])
    assert world["api"]("cv@example.org").get(base).status_code == 403


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


def test_recording_waits_for_consent_from_both_participants(world: dict[str, Any]) -> None:
    """D-119: consent noted by the moderator, or the participant's own "agree" on the consent
    form (not sent back), lets recording start; the newest word counts."""
    from tests.test_recordings import START

    db, pa, mod, base = world["db"], world["pa"], world["mod"], _base(world)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=FORM))
    db.commit()
    tid, a = world["task"]["id"], world["task"]["participant_a"]["id"]

    def missing() -> list[str]:
        found: list[str] = mod.get(f"/api/v1/tasks/{tid}").json()["consent_missing"]
        return found

    assert missing() == ["A", "B"]
    early = mod.post(f"/api/v1/tasks/{tid}/recordings", json=START)
    assert (early.status_code, early.json()["error"]["code"]) == (409, "CONSENT_MISSING")
    # A agrees on their own consent form: that counts, while it waits for review.
    api, head = _visitor(world, _link_from_another_admin(world, a))
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert missing() == ["B"]

    def side_a() -> tuple[str | None, str | None, str | None, bool]:
        p = mod.get(f"/api/v1/tasks/{tid}").json()["participant_a"]
        return p["consent_status"], p["consent_source"], p["consent_review"], p["may_record"]

    # D-127: the task page reads the answer from the form; nobody ticks it.
    assert side_a() == ("GIVEN", "FORM", "PENDING", True)
    # Staff send the answer back: it no longer counts.
    back = pa.post(f"{base}/{a}/consent-review", json={"decision": "REJECTED", "note": "Unclear"})
    assert back.status_code == 200, back.text
    assert missing() == ["A", "B"]
    assert side_a() == ("GIVEN", "FORM", "REJECTED", False)
    # The moderator notes both: recording may start.
    give_consent(mod, tid)
    assert missing() == []
    # A withdraws on their page afterwards: the newest word counts.
    api.post("/api/v1/portal/consent", json={"decision": "WITHDRAWN"}, headers=head)
    assert missing() == ["A"]
    again = mod.post(f"/api/v1/tasks/{tid}/recordings", json=START)
    assert again.json()["error"]["code"] == "CONSENT_MISSING"
    give_consent(mod, tid)
    assert mod.post(f"/api/v1/tasks/{tid}/recordings", json=START).status_code == 201


def test_a_participant_has_a_district(world: dict[str, Any]) -> None:
    """D-121: district on the form, when corrected and in the file upload (the dashboard filter
    is in test_dashboard_filters)."""
    pa, base = world["pa"], _base(world)
    made = pa.post(
        base,
        json={
            "display_label": "Ravi",
            "language_code": "hi",
            "district": " Pune ",
            "email": "ravi@example.org",
        },
    )
    assert made.status_code == 201, made.text
    assert made.json()["district"] == "Pune"
    rid = made.json()["id"]
    fixed = pa.patch(
        f"{base}/{rid}",
        json={"display_label": "Ravi", "language_code": "hi", "district": "Nashik"},
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["district"] == "Nashik"
    csv = "name,phone,email,language,dialect,district\nSita,,sita@example.org,hi,,Thane\n"
    added = pa.post(f"{base}/import", json={"csv": csv, "confirm": True})
    assert added.status_code == 200, added.text
    assert added.json()["created"] == 1
    sita = next(p for p in pa.get(base, params={"search": "Sita"}).json()["items"])
    assert sita["district"] == "Thane"
    long_name = "d" * 101
    too_long = pa.post(
        f"{base}/import",
        json={"csv": f"name,email,language,district\nX,x@example.org,hi,{long_name}\n"},
    )
    assert too_long.json()["rows"][0]["ok"] is False


def test_every_participant_has_an_email(world: dict[str, Any]) -> None:
    """D-128: the consent form goes by email, so a participant cannot be added, uploaded or kept
    without one; someone saved before gets one with their next correction."""
    from sqlalchemy import update as _update

    from app.modules.participants.models import Participant

    db, pa, base = world["db"], world["pa"], _base(world)
    without = pa.post(base, json={"display_label": "Noor", "language_code": "hi"})
    assert (without.status_code, without.json()["error"]["code"]) == (422, "EMAIL_REQUIRED")
    blank = pa.post(base, json={"display_label": "Noor", "language_code": "hi", "email": " "})
    assert blank.json()["error"]["code"] == "EMAIL_REQUIRED"
    rows = pa.post(
        f"{base}/import", json={"csv": "name,phone,email,language,dialect\nNoor,,,hi,\n"}
    ).json()["rows"]
    assert (rows[0]["ok"], rows[0]["message"]) == (False, "Email is missing")

    made = pa.post(
        base, json={"display_label": "Noor", "language_code": "hi", "email": "noor@example.org"}
    )
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    body = {"display_label": "Noor", "language_code": "hi"}
    removed = pa.patch(f"{base}/{pid}", json={**body, "email": ""})
    assert removed.json()["error"]["code"] == "EMAIL_REQUIRED"
    assert pa.patch(f"{base}/{pid}", json=body).status_code == 200  # not sent: kept

    # Saved before the rule: the consent form names the problem, and a correction needs an email.
    db.execute(_update(Participant).where(Participant.id == pid).values(email_enc=None))
    db.commit()
    sent = pa.post(f"{base}/bulk", json={"action": "send_consent", "participant_ids": [pid]})
    assert sent.json()["results"][0]["ok"] is False
    assert "Add one with Edit" in sent.json()["results"][0]["message"]
    assert pa.patch(f"{base}/{pid}", json=body).json()["error"]["code"] == "EMAIL_REQUIRED"
    fixed = pa.patch(f"{base}/{pid}", json={**body, "email": "noor@example.org"})
    assert fixed.status_code == 200, fixed.text


def test_the_task_names_its_participants_for_people_who_may_see_them(
    world: dict[str, Any],
) -> None:
    """D-128: the task page shows each participant's name to the project's managers and the
    task's moderator, and whether they have an email."""
    tid = world["task"]["id"]
    for who in ("pa", "mod"):
        side_a = world[who].get(f"/api/v1/tasks/{tid}").json()["participant_a"]
        assert side_a["display_label"], who
        assert side_a["has_email"] is True
