"""The QC checklist and sending a task back for its consent form (D-146): the checklist as a
project setting with the first client's list as the default, the QC Executive's answers (a draft
kept while ticking, the answers kept with the decision as they read then), the consent check of
signed forms, Pass / Reject / Send back for consent, the moderator's new scan and Send back to QC
with the same recording, and who may do what.

Requirements: AQC-008, TASK-002, TASK-003, TASK-004, PROJ-001, PART-006, PART-016
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.modules.audio_qc import checklist
from app.modules.audio_qc.models import AudioQcDraft, AudioQcResult
from app.modules.audit.models import AuditLog
from app.modules.recordings.models import Recording
from app.modules.tasks import workflow
from tests import test_audio_qc, test_recordings
from tests.conftest import Api, make_user, set_status
from tests.test_audio_qc import answers, passing
from tests.test_participant_documents import JPEG, PDF, put

pytestmark = pytest.mark.db

app = test_recordings.app
s3 = test_recordings.s3
world = test_recordings.world
audio_rule = test_audio_qc.audio_rule

FRONTEND_LIST = (
    Path(__file__).resolve().parents[2] / "frontend/src/features/projects/qcChecklist.ts"
)

PROJECT_FIELDS = (
    "name",
    "description",
    "allows_telephony",
    "allows_face_to_face",
    "target_telephony_hours_per_day",
    "target_face_to_face_hours_per_day",
    "phone_visibility_policy",
    "consent_policy_version",
    "consent_text",
    "qc_final_approval",
    "max_conversations_per_speaker",
    "unique_pairs",
    "consent_mode",
    "speaker_min_age",
    "speaker_max_age",
    "required_speaker_details",
)


def _patch(api: Api, pid: Any, **changes: Any) -> Any:
    """The project's PATCH with everything as it is but `changes` (the PATCH takes it whole)."""
    current = api.get(f"/api/v1/projects/{pid}").json()
    return api.patch(
        f"/api/v1/projects/{pid}", json={**{k: current[k] for k in PROJECT_FIELDS}, **changes}
    )


def _decide(api: Api, tid: str, **body: Any) -> Any:
    return api.post(f"/api/v1/tasks/{tid}/audio-qc/decision", json=body)


def _view(api: Api, tid: str) -> dict[str, Any]:
    response = api.get(f"/api/v1/tasks/{tid}/audio-qc/checklist")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _error(response: Any) -> str:
    code: str = response.json()["error"]["code"]
    return code


def _uploads(world: dict[str, Any]) -> tuple[str, str]:
    """The project takes signed consent forms; both people of the task have one on file."""
    db, pa = world["db"], world["pa"]
    world["project"].consent_mode = "UPLOAD"
    db.commit()
    task = pa.get(f"/api/v1/tasks/{world['task']['id']}").json()
    a, b = task["participant_a"]["id"], task["participant_b"]["id"]
    for pid in (a, b):
        assert put(pa, world["project"].id, pid, "consent-form", PDF).status_code == 201
    return a, b


def _audits(db: Any, action: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


# ------------------------------------------------------------------------ the project setting


def test_a_project_starts_with_the_clients_checklist_and_changes_it(
    world: dict[str, Any],
) -> None:
    db, pa = world["db"], world["pa"]
    pid = world["project"].id
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    root = world["api"]("root@example.org")
    made = root.post(
        "/api/v1/projects",
        json={"name": "Konkani", "allows_telephony": False, "allows_face_to_face": True},
    )
    assert made.status_code == 201, made.text
    default = made.json()["qc_checklist"]
    assert default == list(checklist.DEFAULT_QC_CHECKLIST)
    assert len(default) == 28
    assert {i["scope"] for i in default[:13]} == {"conversation"}
    assert all(i["fails_on"] == "no" and i["required"] for i in default[:13])
    assert all(i["fails_on"] is None and i["required"] for i in default[13:])
    assert pa.get(f"/api/v1/projects/{pid}").json()["qc_checklist"] == default

    mine = [
        {"key": "two_speakers", "question": "Exactly two people talk", "scope": "conversation",
         "fails_on": "no", "required": True},
        {"key": "music", "question": "Is music playing?", "scope": "speaker", "fails_on": "yes",
         "required": False},
    ]  # fmt: skip
    saved = _patch(pa, pid, qc_checklist=mine)
    assert saved.status_code == 200, saved.text
    assert saved.json()["qc_checklist"] == mine
    [entry] = _audits(db, "project.updated")
    assert '"Exactly two people talk"' in (entry.after_summary or "")
    # Left out, the checklist stays as it is; a change of something else does not repeat it.
    kept = _patch(pa, pid, description="Konkani talk")
    assert kept.json()["qc_checklist"] == mine
    assert "qc_checklist" not in (_audits(db, "project.updated")[-1].after_summary or "")


@pytest.mark.parametrize(
    ("items", "says"),
    [
        ([{"key": "Two Speakers", "question": "Q"}], "item 1: the key must be lowercase"),
        ([{"key": "a_"}], "item 1: the key must be lowercase"),
        ([{"key": "x" * 51}], None),
        ([{"key": "ok"}, {"key": "ok"}], "item 2: the key ok is used twice"),
        ([{"key": "ok", "question": "   "}], "item 1: write the question"),
        ([{"key": "ok", "question": "q" * 201}], None),
        ([{"key": "ok", "scope": "room"}], None),
        ([{"key": "ok", "fails_on": "maybe"}], None),
        ([{"key": f"k{i}"} for i in range(61)], None),
    ],
)
def test_a_checklist_is_checked_when_saved(
    world: dict[str, Any], items: list[dict[str, Any]], says: str | None
) -> None:
    base = {"question": "Is it fine?", "scope": "conversation", "fails_on": "no", "required": True}
    response = _patch(world["pa"], world["project"].id, qc_checklist=[base | i for i in items])
    assert response.status_code == 422, response.text
    if says:
        assert _error(response) == "INVALID_QC_CHECKLIST"
        assert says in response.json()["error"]["message"]
    else:
        assert _error(response) == "VALIDATION_ERROR"
    item = checklist.DEFAULT_QC_CHECKLIST[0]
    assert checklist.clean([item | {"question": "  Two   words "}])[0]["question"] == "Two words"


def test_only_project_admins_change_the_checklist_and_not_in_an_archived_project(
    world: dict[str, Any],
) -> None:
    pid = world["project"].id
    qc = world["api"]("qc@example.org")
    assert _patch(world["mod"], pid, qc_checklist=[]).status_code == 403
    assert (
        qc.get(f"/api/v1/projects/{pid}").json()["qc_checklist"][0]["key"] == "correct_speaker_ids"
    )
    db = world["db"]
    world["project"].status = "ARCHIVED"
    db.commit()
    assert _error(_patch(world["pa"], pid, qc_checklist=[])) == "PROJECT_ARCHIVED"


# --------------------------------------------------------------- answers, drafts and decisions


def test_qc_ticks_a_draft_that_a_reload_keeps(world: dict[str, Any]) -> None:
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    qc = test_audio_qc._assign_qc(world)
    view = _view(qc, tid)
    assert (view["can_answer"], view["consent_check"], view["draft"], view["latest"]) == (
        True,
        False,
        None,
        None,
    )
    assert [i["key"] for i in view["items"]] == [i["key"] for i in checklist.DEFAULT_QC_CHECKLIST]
    draft = {
        "conversation": {"two_speakers": "yes", "no_such_question": "yes"},
        "speakers": {"A": {"echo_in_audio": "no"}, "B": {"read_speech": None}},
        "consent": {"A": "yes"},
    }
    saved = qc.put(f"/api/v1/tasks/{tid}/audio-qc/draft", json=draft)
    assert saved.status_code == 200, saved.text
    again = _view(qc, tid)["draft"]
    # A question not in the checklist is dropped; this Online project asks no consent check.
    assert again["answers"] == {
        "conversation": {"two_speakers": "yes"},
        "speakers": {"A": {"echo_in_audio": "no"}, "B": {}},
        "consent": {},
    }
    assert again["saved_by_name"] == "qc"
    # Only the person who decides sees or saves it.
    pa: Api = world["pa"]
    assert _view(pa, tid)["draft"] is None
    assert _view(pa, tid)["can_answer"] is False
    assert pa.put(f"/api/v1/tasks/{tid}/audio-qc/draft", json=draft).status_code == 403
    assert world["mod"].put(f"/api/v1/tasks/{tid}/audio-qc/draft", json=draft).status_code == 403
    bad = qc.put(f"/api/v1/tasks/{tid}/audio-qc/draft", json={"conversation": {"x": "maybe"}})
    assert bad.status_code == 422
    # The decision takes the draft's place.
    assert _decide(qc, tid, **passing(qc, tid)).status_code == 200
    assert world["db"].scalar(select(AudioQcDraft.id)) is None
    assert _error(qc.put(f"/api/v1/tasks/{tid}/audio-qc/draft", json=draft)) == "TASK_NOT_IN_QC"


def test_pass_needs_every_required_answer_and_none_failing(world: dict[str, Any]) -> None:
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    qc = test_audio_qc._assign_qc(world)
    full = answers(qc, tid)
    code = world["pa"].get(f"/api/v1/tasks/{tid}").json()["participant_b"]["participant_code"]

    nothing = _decide(qc, tid, outcome="PASS")
    assert _error(nothing) == "CHECKLIST_INCOMPLETE"
    assert "Both speakers have unique IDs" in nothing.json()["error"]["message"]
    one_short = {**full, "speakers": {**full["speakers"], "B": {}}}
    short = _decide(qc, tid, outcome="PASS", answers=one_short)
    assert _error(short) == "CHECKLIST_INCOMPLETE"
    assert f"{code}: Is speech intelligible?" in short.json()["error"]["message"]
    noisy = {**full, "conversation": {**full["conversation"], "quiet_environment": "no"}}
    failed = _decide(qc, tid, outcome="PASS", answers=noisy)
    assert _error(failed) == "CHECKLIST_FAILED"
    assert failed.json()["error"]["details"][0]["questions"] == [
        "Relatively quiet: no road, TV, crying babies or vehicles"
    ]
    # Observations never fail: every speaker answer may be Yes or No.
    observed = {
        **full,
        "speakers": {side: dict.fromkeys(full["speakers"]["A"], "no") for side in ("A", "B")},
    }
    assert _error(_decide(qc, tid, outcome="SEND_BACK_CONSENT", answers=observed, comment="x")) == (
        "CONSENT_ONLINE"
    )
    assert world["pa"].get(f"/api/v1/tasks/{tid}").json()["status"] == "AUDIO_QC"
    passed = _decide(qc, tid, outcome="PASS", answers={**observed, "consent": {"A": "no"}})
    assert passed.status_code == 200, passed.text
    assert passed.json()["task_status"] == "ADMIN_REVIEW"
    stored = world["db"].scalar(select(AudioQcResult).where(AudioQcResult.automated.is_(False)))
    snap = stored.checklist
    assert snap["consent_check"] is False
    assert [p["consent"] for p in snap["participants"]] == [None, None], "Online: not asked"
    assert snap["participants"][1]["participant_code"] == code
    assert snap["participants"][0]["answers"]["speech_intelligible"] == "no"
    assert snap["failing"] == []


def test_reject_keeps_whatever_was_answered_and_everyone_on_the_task_reads_it(
    world: dict[str, Any],
) -> None:
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    qc = test_audio_qc._assign_qc(world)
    rejected = _decide(
        qc,
        tid,
        outcome="FAIL",
        reason_code="WRONG_SPEAKERS",
        comment="A third voice",
        answers={"conversation": {"no_third_person": "no", "two_speakers": "yes"}},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["task_status"] == "REJECTED"
    for api in (world["pa"], world["mod"], qc):
        latest = _view(api, tid)["latest"]
        assert (latest["outcome"], latest["reviewer_name"], latest["comment"]) == (
            "FAIL",
            "qc",
            "A third voice",
        )
        assert latest["decided_at"]
        assert latest["conversation"] == {"no_third_person": "no", "two_speakers": "yes"}
        assert latest["failing"] == [{"key": "no_third_person", "side": None, "answer": "no"}]
    [entry] = _audits(world["db"], "audio_qc.decision")
    assert '"failing": ["no_third_person"]' in (entry.after_summary or "")
    # Someone who does not see the task reads nothing.
    make_user(world["db"], "qc9@example.org", ["QC_EXECUTIVE"], projects=[world["project"]])
    other = world["api"]("qc9@example.org")
    assert other.get(f"/api/v1/tasks/{tid}/audio-qc/checklist").status_code == 404


def test_answers_keep_the_questions_as_they_read_when_given(world: dict[str, Any]) -> None:
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    qc = test_audio_qc._assign_qc(world)
    assert _decide(qc, tid, **passing(qc, tid)).status_code == 200
    pa: Api = world["pa"]
    changed = [
        {**checklist.DEFAULT_QC_CHECKLIST[0], "question": "IDs match"},
        checklist.DEFAULT_QC_CHECKLIST[13],
    ]
    assert _patch(pa, world["project"].id, qc_checklist=changed).status_code == 200
    view = _view(pa, tid)
    assert [i["question"] for i in view["items"]] == ["IDs match", "Is speech intelligible?"]
    latest = view["latest"]
    assert len(latest["items"]) == 28
    assert latest["items"][0]["question"] == checklist.DEFAULT_QC_CHECKLIST[0]["question"]
    assert len(latest["conversation"]) == 13


# ---------------------------------------------------------- the consent check and the send-back


def test_where_signed_forms_are_taken_pass_needs_both_forms_right(world: dict[str, Any]) -> None:
    _uploads(world)
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    qc = test_audio_qc._assign_qc(world)
    assert _view(qc, tid)["consent_check"] is True
    # The QC Executive opens the forms they check (D-144).
    task = qc.get(f"/api/v1/tasks/{tid}").json()
    assert task["participant_a"]["consent_form"]["file_name"] == "scan.pdf"
    unchecked = answers(qc, tid, consent=None)
    assert _error(_decide(qc, tid, outcome="PASS", answers=unchecked)) == "CONSENT_NOT_CHECKED"
    one_wrong = {**unchecked, "consent": {"A": "yes", "B": "no"}}
    assert _error(_decide(qc, tid, outcome="PASS", answers=one_wrong)) == "CONSENT_NOT_OK"
    passed = _decide(qc, tid, **passing(qc, tid))
    assert passed.status_code == 200, passed.text
    snap = world["db"].scalar(
        select(AudioQcResult.checklist).where(AudioQcResult.automated.is_(False))
    )
    assert snap["consent_check"] is True
    assert [p["consent"] for p in snap["participants"]] == ["yes", "yes"]
    assert snap["participants"][0]["consent_form_id"] == task["participant_a"]["consent_form"]["id"]


def test_send_back_for_consent_then_a_new_scan_then_back_to_qc_then_pass(
    world: dict[str, Any],
) -> None:
    a, _ = _uploads(world)
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    db, pa, mod = world["db"], world["pa"], world["mod"]
    qc = test_audio_qc._assign_qc(world)
    code_a = pa.get(f"/api/v1/tasks/{tid}").json()["participant_a"]["participant_code"]
    full = answers(qc, tid)
    form_wrong = {**full, "consent": {"A": "no", "B": "yes"}}

    # What a send-back needs: a form marked No, a comment, the audio checks answered and passing.
    assert _error(_decide(qc, tid, outcome="SEND_BACK_CONSENT", answers=full, comment="x")) == (
        "CONSENT_NOT_MARKED"
    )
    assert _error(_decide(qc, tid, outcome="SEND_BACK_CONSENT", answers=form_wrong)) == (
        "COMMENT_REQUIRED"
    )
    short = {**form_wrong, "conversation": {}}
    assert (
        _error(_decide(qc, tid, outcome="SEND_BACK_CONSENT", answers=short, comment="x"))
        == "CHECKLIST_INCOMPLETE"
    )
    loud = {**form_wrong, "conversation": {**full["conversation"], "no_ringtone_overlap": "no"}}
    assert _error(_decide(qc, tid, outcome="SEND_BACK_CONSENT", answers=loud, comment="x")) == (
        "CHECKLIST_FAILED"
    )
    assert (
        world["mod"]
        .post(
            f"/api/v1/tasks/{tid}/audio-qc/decision",
            json={"outcome": "SEND_BACK_CONSENT", "answers": form_wrong, "comment": "x"},
        )
        .status_code
        == 403
    )

    sent = _decide(
        qc, tid, outcome="SEND_BACK_CONSENT", answers=form_wrong, comment="Not signed on page 2"
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["task_status"] == "CONSENT_FIX"
    task = mod.get(f"/api/v1/tasks/{tid}").json()
    assert task["status"] == "CONSENT_FIX"
    fix = task["consent_fix"]
    assert (fix["comment"], fix["by"], fix["forms_replaced"], fix["can_send_back"]) == (
        "Not signed on page 2",
        "qc",
        False,
        True,
    )
    assert fix["participants"] == [
        {"side": "A", "participant_id": a, "participant_code": code_a, "replaced": False}
    ]
    assert task["allowed_transitions"] == ["AUDIO_QC"]
    assert sorted(pa.get(f"/api/v1/tasks/{tid}").json()["allowed_transitions"]) == [
        "AUDIO_QC",
        "CANCELLED",
    ]
    assert qc.get(f"/api/v1/tasks/{tid}").json()["consent_fix"]["can_send_back"] is False
    history = [e for e in pa.get(f"/api/v1/tasks/{tid}/timeline").json() if e["kind"] == "status"]
    assert (history[-1]["to_status"], history[-1]["actor"]) == ("CONSENT_FIX", "qc")
    assert history[-1]["comment"] == f"Consent form to fix: {code_a}. Not signed on page 2"
    [entry] = _audits(db, "audio_qc.decision")
    assert f'"consent_to_fix": ["{code_a}"]' in (entry.after_summary or "")
    # QC waits; their answers are kept for the next check, the consent check cleared.
    assert _error(_decide(qc, tid, **passing(qc, tid))) == "TASK_NOT_IN_QC"
    assert _view(qc, tid)["can_answer"] is False

    # Back to QC only once the form QC found wrong was replaced; only the moderator or an admin.
    url = f"/api/v1/tasks/{tid}/consent-fix/send-to-qc"
    assert _error(mod.post(url, json={})) == "CONSENT_FORM_NOT_REPLACED"
    via_transition = mod.post(f"/api/v1/tasks/{tid}/transition", json={"to": "AUDIO_QC"})
    assert _error(via_transition) == "CONSENT_FORM_NOT_REPLACED"
    assert qc.post(url, json={}).status_code == 403
    assert world["api"]("mod2@example.org").post(url, json={}).status_code == 404
    pid = world["project"].id
    new_scan = put(mod, pid, a, "consent-form", JPEG, name="again.jpg", content_type="image/jpeg")
    assert new_scan.status_code == 201, new_scan.text
    fix = mod.get(f"/api/v1/tasks/{tid}").json()["consent_fix"]
    assert (fix["forms_replaced"], fix["participants"][0]["replaced"]) == (True, True)
    recordings_before = db.scalar(select(Recording.id).where(Recording.task_id == tid))
    back = mod.post(url, json={"comment": "Signed scan uploaded"})
    assert back.status_code == 200, back.text
    assert (back.json()["status"], back.json()["consent_fix"]) == ("AUDIO_QC", None)
    assert len(db.scalars(select(Recording.id).where(Recording.task_id == tid)).all()) == 1
    assert db.scalar(select(Recording.id).where(Recording.task_id == tid)) == recordings_before
    assert qc.get(f"/api/v1/tasks/{tid}/audio-qc").json()["qc_name"] == "qc", "the QC stays"
    [fixed] = _audits(db, "audio_qc.consent_fixed")
    assert code_a in (fixed.after_summary or "")
    assert _error(mod.post(url, json={})) == "TASK_NOT_IN_CONSENT_FIX"

    view = _view(qc, tid)
    assert view["can_answer"] is True
    assert view["draft"]["answers"]["conversation"] == full["conversation"]
    assert view["draft"]["answers"]["speakers"] == full["speakers"]
    assert view["draft"]["answers"]["consent"] == {}
    assert view["draft"]["saved_by_name"] is None
    assert view["latest"]["outcome"] == "SEND_BACK_CONSENT"
    assert view["latest"]["participants"][0]["consent"] == "no"
    passed = _decide(qc, tid, **passing(qc, tid))
    assert passed.status_code == 200, passed.text
    assert passed.json()["task_status"] == "ADMIN_REVIEW"
    latest = _view(pa, tid)["latest"]
    assert latest["outcome"] == "PASS"
    current = pa.get(f"/api/v1/tasks/{tid}").json()["participant_a"]["consent_form"]
    assert latest["participants"][0]["consent_form_id"] == current["id"]
    assert current["file_name"] == "again.jpg"


def test_a_send_back_where_qc_pass_is_the_final_approval(world: dict[str, Any]) -> None:
    """D-138 with D-146: the pass after the new form approves the task straight away."""
    _uploads(world)
    world["project"].qc_final_approval = True
    world["db"].commit()
    a = world["pa"].get(f"/api/v1/tasks/{world['task']['id']}").json()["participant_a"]["id"]
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    qc = test_audio_qc._assign_qc(world)
    wrong = {**answers(qc, tid), "consent": {"A": "no", "B": "yes"}}
    sent = _decide(qc, tid, outcome="SEND_BACK_CONSENT", answers=wrong, comment="Wrong person")
    assert sent.json()["task_status"] == "CONSENT_FIX"
    assert put(world["pa"], world["project"].id, a, "consent-form", PDF).status_code == 201
    back = world["pa"].post(f"/api/v1/tasks/{tid}/consent-fix/send-to-qc", json={})
    assert back.json()["status"] == "AUDIO_QC", back.text
    assert _decide(qc, tid, **passing(qc, tid)).json()["task_status"] == "APPROVED"


def test_a_task_waiting_for_its_consent_form_can_be_cancelled(world: dict[str, Any]) -> None:
    _uploads(world)
    test_audio_qc._record(world)
    tid = world["task"]["id"]
    qc = test_audio_qc._assign_qc(world)
    wrong = {**answers(qc, tid), "consent": {"A": "yes", "B": "no"}}
    assert (
        _decide(qc, tid, outcome="SEND_BACK_CONSENT", answers=wrong, comment="Blank").json()[
            "task_status"
        ]
        == "CONSENT_FIX"
    )
    assert (
        world["mod"]
        .post(
            f"/api/v1/tasks/{tid}/transition",
            json={"to": "CANCELLED", "reason_code": "CONSENT_REFUSED"},
        )
        .status_code
        == 403
    )
    cancelled = world["pa"].post(
        f"/api/v1/tasks/{tid}/transition",
        json={"to": "CANCELLED", "reason_code": "CONSENT_REFUSED"},
    )
    assert cancelled.json()["status"] == "CANCELLED", cancelled.text


def test_the_workflow_knows_the_consent_fix(world: dict[str, Any]) -> None:
    moderator = workflow.Actor(is_moderator=True)
    admin = workflow.Actor(can_assign=True)
    assert workflow.user_options("CONSENT_FIX", None, moderator) == ["AUDIO_QC"]
    assert workflow.user_options("CONSENT_FIX", None, admin) == ["AUDIO_QC", "CANCELLED"]
    assert workflow.user_options("AUDIO_QC", None, admin) == []
    assert workflow.required_kind("AUDIO_QC", "CONSENT_FIX", None) == "system"
    assert workflow.required_kind("CONSENT_FIX", "ON_HOLD", None) is None
    # Not by hand: only the QC decision sends a task to CONSENT_FIX.
    tid = world["task"]["id"]
    set_status(world["db"], tid, "AUDIO_QC")
    moved = world["pa"].post(f"/api/v1/tasks/{tid}/transition", json={"to": "CONSENT_FIX"})
    assert _error(moved) == "INVALID_TRANSITION"
    # A task put there without QC's request (not through the platform) is not sent on blindly.
    set_status(world["db"], tid, "CONSENT_FIX")
    lost = world["pa"].post(f"/api/v1/tasks/{tid}/consent-fix/send-to-qc", json={})
    assert _error(lost) == "CONSENT_FIX_UNKNOWN"
    assert world["pa"].get(f"/api/v1/tasks/{tid}").json()["consent_fix"] is None


def test_reset_on_the_rules_tab_puts_back_the_same_list() -> None:
    """frontend/src/features/projects/qcChecklist.ts writes the client's list once more for
    "Reset to the client's list"; it must be the one a new project gets."""
    source = FRONTEND_LIST.read_text(encoding="utf-8")
    found = re.findall(
        r'(?:^|\W)(conversation|speaker)\(\s*"([a-z_]+)",\s*"([^"]+)",?\s*\)', source
    )
    assert [
        {
            "key": key,
            "question": question,
            "scope": scope,
            "fails_on": "no" if scope == "conversation" else None,
            "required": True,
        }
        for scope, key, question in found
    ] == list(checklist.DEFAULT_QC_CHECKLIST)
