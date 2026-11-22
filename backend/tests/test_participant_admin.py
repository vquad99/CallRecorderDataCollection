"""Participants section (D-073): add many from a file, assign to another project, remove; the
consent form is emailed by itself and an answer counts at once (D-129).

Requirements: PART-006, PART-014, PART-016
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import update

from app.modules.participants.models import ConsentRecord
from app.modules.projects.models import Project
from tests import test_recordings
from tests.conftest import make_participant, make_project, make_user
from tests.test_portal import FORM, _token, _visitor

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


def _with_form(world: dict[str, Any]) -> None:
    db = world["db"]
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=FORM))
    db.commit()


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
    # The project has no consent form yet: nothing is sent, and the rows say what to do (D-129).
    # The file has no speaker details: added, and the rows say they are missing (D-143).
    assert [r["message"] for r in done["rows"] if r["ok"]] == [
        "Added (speaker details missing: add them with Edit before making tasks). "
        "Write the project's consent form, then send it."
    ] * 2
    bad = pa.post(f"{base}/import", json={"csv": "label\nx\n"})
    assert bad.json()["error"]["code"] == "INVALID_CSV"
    assert world["mod"].post(f"{base}/import", json={"csv": CSV}).status_code == 403


def test_the_check_finds_what_add_would_refuse_and_a_second_import_adds_nobody(
    world: dict[str, Any],
) -> None:
    """PART-05: the file check fails a phone number someone already has, someone already in the
    project (same name and email), and a person repeated in the file, as Add does. The same
    file sent again adds nobody a second time."""
    pa, base = world["pa"], _base(world)
    make_participant(pa, world["project"].id, "Kiran", phone="+919811100001")
    pa.post(
        base, json={"display_label": "Lata", "language_code": "hi", "email": "lata@example.org"}
    )
    csv = (
        "name,phone,email,language\n"
        "Kiran Again,+919811100001,kiran.again@example.org,hi\n"
        "lata,,LATA@example.org,hi\n"
        "Tara Naik,,tara@example.org,hi\n"
        "Tara Naik,,tara@example.org,hi\n"
        "Usha Naik,,tara@example.org,hi\n"
    )
    before = pa.get(base).json()["total"]
    preview = pa.post(f"{base}/import", json={"csv": csv}).json()
    rows = [(r["ok"], r["message"]) for r in preview["rows"]]
    lata = next(p for p in pa.get(base).json()["items"] if p["display_label"] == "Lata")
    assert rows[0] == (False, "A participant with this phone number already exists")
    assert rows[1] == (False, f"Already in this project as {lata['participant_code']}")
    assert rows[2][0] is True
    assert rows[3] == (False, "This person is repeated in this file")
    assert rows[4][0] is True, "a family may share one address"
    done = pa.post(f"{base}/import", json={"csv": csv, "confirm": True}).json()
    assert [r["ok"] for r in done["rows"]] == [False, False, True, False, True]
    assert done["created"] == 2
    again = pa.post(f"{base}/import", json={"csv": csv, "confirm": True}).json()
    assert again["created"] == 0
    assert {r["message"].split(" as ")[0] for r in again["rows"] if not r["ok"]} >= {
        "Already in this project"
    }
    assert pa.get(base).json()["total"] == before + 2


def test_a_value_too_long_for_the_file_fails_its_row_only(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PART-06: the file has the form's limits, so a row the database could not hold fails on
    its own at the check; the other rows are added and emailed their consent form."""
    from sqlalchemy.exc import DataError

    from app.modules.participants import service

    pa, base = world["pa"], _base(world)
    _with_form(world)
    csv = (
        "name,email,language,dialect\n"
        f"Asha,asha.k@example.org,hi,{'d' * 101}\n"
        f"Bina,bina.k@example.org,hi-{'x' * 8}-{'y' * 8}-{'z' * 8}-{'w' * 8},\n"
        "Chitra,chitra.k@example.org,hi,\n"
    )
    for confirm in (False, True):
        rows = pa.post(f"{base}/import", json={"csv": csv, "confirm": confirm}).json()["rows"]
        assert [(r["ok"], r["message"].split(".")[0]) for r in rows[:2]] == [
            (False, "Dialect is too long (at most 100 characters)"),
            (False, "Language code is too long (at most 35 characters)"),
        ]
        assert rows[2]["ok"] is True
    assert rows[2]["message"].endswith("Consent form emailed.")
    # Should the database still refuse a row, that row fails and the others stay added.
    real = service.create_participant

    def refuse_dana(*args: Any, **kwargs: Any) -> Any:
        if args[5].display_label == "Dana":
            raise DataError("INSERT", {}, Exception("value too long"))
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "create_participant", refuse_dana)
    two = "name,email,language\nDana,dana@example.org,hi\nEla,ela@example.org,hi\n"
    done = pa.post(f"{base}/import", json={"csv": two, "confirm": True})
    assert done.status_code == 200, done.text
    assert [r["ok"] for r in done.json()["rows"]] == [False, True]
    assert done.json()["rows"][0]["message"] == (
        "This row could not be saved: a value is too long or not valid"
    )
    assert done.json()["rows"][1]["message"].endswith("Consent form emailed.")


def test_bulk_assign_and_remove_report_each_participant(world: dict[str, Any]) -> None:
    db, pa, base = world["db"], world["pa"], _base(world)
    other = make_project(db, "SECOND")
    other.consent_text = "I agree to the second project."
    outside = make_project(db, "OUTSIDE")
    pa_user = pa.get("/api/v1/auth/me").json()["id"]
    from app.modules.projects.models import ProjectMembership

    db.add(ProjectMembership(user_id=pa_user, project_id=other.id))
    db.commit()
    with_mail = make_participant(pa, world["project"].id, "Kiran")
    without = make_participant(pa, world["project"].id, "Lata")
    # Saved before every participant needed an email (D-128).
    from app.modules.participants.models import Participant

    db.execute(update(Participant).where(Participant.id == without["id"]).values(email_enc=None))
    db.commit()
    ids = [with_mail["id"], without["id"]]
    # Emailing the form again in bulk (D-139) skips people who already agreed.
    resent = pa.post(f"{base}/bulk", json={"action": "send_consent", "participant_ids": ids})
    assert {r["message"] for r in resent.json()["results"]} == {"Already agreed: no form sent"}

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
    # They get the other project's consent form by themselves (D-129).
    assert [r["message"] for r in moved["results"]] == [
        "Assigned. Consent form emailed.",
        "Assigned. No email address: add one with Edit, then email the consent form.",
    ]
    there = {
        p["id"]: p for p in pa.get(f"/api/v1/projects/{other.id}/participants").json()["items"]
    }
    assert len(there) == 2
    assert (there[with_mail["id"]]["link_active"], there[without["id"]]["link_active"]) == (
        True,
        False,
    )
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


def test_an_agreement_counts_at_once_with_nobody_to_review_it(world: dict[str, Any]) -> None:
    """D-129: no staff review; the answer is accepted the moment the participant gives it."""
    pa, base = world["pa"], _base(world)
    _with_form(world)
    chitra = make_participant(pa, world["project"].id, "Chitra", agreed=False)
    c = chitra["id"]
    row = next(p for p in pa.get(base).json()["items"] if p["id"] == c)
    assert row["consent_status"] == "NONE"
    api, head = _visitor(world, _token(world, c))
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    row = next(p for p in pa.get(base).json()["items"] if p["id"] == c)
    assert row["consent_status"] == "GIVEN"
    assert "consent_review" not in row
    gone = pa.post(f"{base}/{c}/consent-review", json={"decision": "APPROVED"})
    assert gone.status_code == 404, "there is no review any more"
    # A client viewer has no list of the project's people at all (D-112).
    make_user(world["db"], "cv@example.org", ["CLIENT_VIEWER"], projects=[world["project"]])
    assert world["api"]("cv@example.org").get(base).status_code == 403


def test_one_consent_form_can_be_viewed_and_downloaded(world: dict[str, Any]) -> None:
    db, pa, base = world["db"], world["pa"], _base(world)
    _with_form(world)
    c = make_participant(pa, world["project"].id, "Chitra", agreed=False)["id"]
    blank = pa.get(f"{base}/{c}/consent-form").json()
    assert (blank["answered"], blank["current"], blank["form_text"]) == (False, None, FORM)
    api, head = _visitor(world, _token(world, c))
    api.post("/api/v1/portal/consent", json={"decision": "REFUSED"}, headers=head)
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text="New"))
    db.commit()
    form = pa.get(f"{base}/{c}/consent-form").json()
    assert form["form_text"] == FORM, "the text that was answered, not the project's new text"
    assert form["current"] == {
        "status": "GIVEN",
        "answered_at": form["current"]["answered_at"],
        "policy_version": "1",
    }
    assert [e["status"] for e in form["earlier"]] == ["REFUSED"]
    got = pa.get(f"{base}/{c}/consent-form/file")
    assert got.status_code == 200
    code = next(p for p in pa.get(base).json()["items"] if p["id"] == c)["participant_code"]
    assert got.headers["content-disposition"] == f'attachment; filename="consent_VOICE_{code}.html"'
    for expected in (code, FORM, "Agreed", "Did not agree"):
        assert expected in got.text, expected
    assert "Review" not in got.text
    assert "Chitra" not in got.text, "by code only"
    # QC staff and clients have no consent access.
    assert world["api"]("qc@example.org").get(f"{base}/{c}/consent-form").status_code == 403


def test_an_answer_on_a_link_handed_out_by_staff_says_so(world: dict[str, Any]) -> None:
    """D-088: whoever was shown a link could have answered on it; with nobody reviewing answers
    (D-129) the consent record says how the answer came in. Staff are no longer shown links, but
    one handed out before still works and still says so."""
    from app.modules.auth.security import hash_token
    from app.modules.participants.models import ParticipantPortalLink

    db, pa, base = world["db"], world["pa"], _base(world)
    _with_form(world)
    c = make_participant(pa, world["project"].id, "Chitra", agreed=False)["id"]
    token = _token(world, c)
    db.execute(
        update(ParticipantPortalLink)
        .where(ParticipantPortalLink.token_hash == hash_token(token))
        .values(shown_to_staff=True)
    )
    db.commit()
    api, head = _visitor(world, token)
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert "handed out by staff" in pa.get(f"{base}/{c}/consent-form/file").text


def test_recording_waits_for_consent_from_both_participants(world: dict[str, Any]) -> None:
    """D-119: recording starts only while both participants' answers on the consent form are
    "agreed". A task is only made for people who agreed (D-129), so this guards the answers
    from before D-129: one sent back by staff does not count, nor does consent a moderator
    noted for the session; agreeing again does."""
    from tests.test_recordings import START

    db, mod = world["db"], world["mod"]
    _with_form(world)
    tid, a = world["task"]["id"], world["task"]["participant_a"]["id"]

    def missing() -> list[str]:
        found: list[str] = mod.get(f"/api/v1/tasks/{tid}").json()["consent_missing"]
        return found

    def side_a() -> tuple[str | None, bool]:
        p = mod.get(f"/api/v1/tasks/{tid}").json()["participant_a"]
        assert "consent_review" not in p, "nobody reviews answers (D-129)"
        return p["consent_status"], p["may_record"]

    assert (missing(), side_a()) == ([], ("GIVEN", True))
    db.execute(
        update(ConsentRecord)
        .where(ConsentRecord.participant_id == uuid.UUID(a))
        .values(review_status="REJECTED", review_note="Unclear")
    )
    db.add(
        ConsentRecord(
            participant_id=uuid.UUID(a),
            project_id=world["project"].id,
            task_id=uuid.UUID(tid),
            status="GIVEN",
            method="VERBAL_NOTED",
            policy_version="1",
            captured_by=uuid.UUID(mod.get("/api/v1/auth/me").json()["id"]),
        )
    )
    db.commit()
    assert (missing(), side_a()) == (["A"], (None, False))
    early = mod.post(f"/api/v1/tasks/{tid}/recordings", json=START)
    assert (early.status_code, early.json()["error"]["code"]) == (409, "CONSENT_MISSING")
    api, head = _visitor(world, _token(world, a))
    api.post("/api/v1/portal/consent", json={"decision": "GIVEN"}, headers=head)
    assert (missing(), side_a()) == ([], ("GIVEN", True))
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

    # Saved before the rule: emailing the consent form again names the problem, and a correction
    # needs an email.
    db.execute(_update(Participant).where(Participant.id == pid).values(email_enc=None))
    db.commit()
    again = pa.post(f"{base}/{pid}/portal-link/email")
    assert (again.status_code, again.json()["error"]["code"]) == (409, "NO_EMAIL")
    assert "Add one with Edit" in again.json()["error"]["message"]
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


def test_the_consent_form_goes_again_to_everyone_chosen_who_has_not_agreed(
    world: dict[str, Any],
) -> None:
    """D-139: tick several participants and email them this project's consent form again; people
    who already agreed are skipped and named."""
    from app.modules.participants.router import CONSENT_EMAILED, CONSENT_FORM_MISSING

    db, pa, base = world["db"], world["pa"], _base(world)
    waiting = [make_participant(pa, world["project"].id, n, agreed=False) for n in ("Ravi", "Uma")]
    done = make_participant(pa, world["project"].id, "Zoya")
    ids = [p["id"] for p in (*waiting, done)]

    body = {"action": "send_consent", "participant_ids": ids}
    no_form = pa.post(f"{base}/bulk", json=body).json()
    assert {r["message"] for r in no_form["results"] if r["ok"]} == {CONSENT_FORM_MISSING}

    db.execute(update(Project).where(Project.id == world["project"].id).values(consent_text=FORM))
    db.commit()
    sent = pa.post(f"{base}/bulk", json=body).json()
    assert (sent["done"], sent["failed"]) == (2, 1)
    by_code = {r["participant_code"]: r for r in sent["results"]}
    assert by_code[done["participant_code"]]["message"] == "Already agreed: no form sent"
    assert all(by_code[p["participant_code"]]["message"] == CONSENT_EMAILED for p in waiting)
    # Someone not in the project, or who does not exist, is named as not found, in its place.
    from app.modules.participants.models import Participant

    elsewhere = Participant(participant_code="P990001", display_label="Kavi", language_code="hi")
    db.add(elsewhere)
    db.commit()
    nobody = str(uuid.uuid4())
    chosen = [nobody, done["id"], str(elsewhere.id)]
    mixed = pa.post(f"{base}/bulk", json={"action": "send_consent", "participant_ids": chosen})
    assert [
        (r["participant_id"], r["participant_code"], r["ok"], r["message"])
        for r in mixed.json()["results"]
    ] == [
        (nobody, "?", False, "Participant not found"),
        (done["id"], done["participant_code"], False, "Already agreed: no form sent"),
        (str(elsewhere.id), "?", False, "Participant not found"),
    ]
    # Only people who manage participants may do it.
    assert world["mod"].post(f"{base}/bulk", json=body).status_code == 403
