"""Project management: create, configure, lifecycle, members, isolation; a save over someone
else's newer one refused, an archived project read only, a member with open tasks kept, audit
entries that show what changed, names on one line.

Requirements: PROJ-001, PROJ-002, PROJ-003, PROJ-004, PROJ-005, PROJ-006, PROJ-007, PROJ-008, PROJ-009, PROJ-010, PROJ-012, USER-003, CAP-003, SEC-001
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update

from app.core.errors import AppError
from app.modules.audit.models import AuditLog
from app.modules.projects.models import Project, ProjectRetentionRule
from app.modules.projects.service import ensure_accepts_new_work
from app.modules.tasks.models import TaskAssignment
from tests.conftest import Api, make_participant, make_project, make_user, read_outbox, set_status

pytestmark = pytest.mark.db

# A project records one type (D-153): this one phone calls.
NEW_PROJECT = {
    "code": "hindi-01",
    "name": "Hindi conversations",
    "allows_telephony": True,
    "allows_face_to_face": False,
    "target_telephony_hours_per_day": "62.5",
    "target_face_to_face_hours_per_day": "0",
}


@pytest.fixture
def admin(db: Any, new_api: Any) -> Api:
    make_user(db, "root@example.org", ["SUPER_ADMIN"])
    api: Api = new_api()
    api.login("root@example.org")
    return api


def test_create_project_with_spec_defaults(admin: Api) -> None:
    response = admin.post("/api/v1/projects", json=NEW_PROJECT)
    assert response.status_code == 201
    project = response.json()
    assert project["code"] == "HINDI-01"
    assert project["status"] == "DRAFT"
    assert project["accepts_new_work"] is False
    rules = {r["mode"]: r for r in project["audio_rules"]}
    assert list(rules) == ["TELEPHONY"], "an audio rule for the project's one type"
    assert (
        rules["TELEPHONY"]["sample_rate"],
        rules["TELEPHONY"]["bit_depth"],
        rules["TELEPHONY"]["channels"],
    ) == (16000, 16, 2)  # stereo: TxContact's recordings are 16 kHz stereo (D-134)
    assert rules["TELEPHONY"]["max_silence_pct"] == "25.00"
    assert rules["TELEPHONY"]["max_clipping_pct"] is None
    face = admin.post(
        "/api/v1/projects",
        json={
            **NEW_PROJECT,
            "code": "face-01",
            "allows_telephony": False,
            "allows_face_to_face": True,
            "target_telephony_hours_per_day": "0",
        },
    ).json()
    assert [(r["mode"], r["channels"]) for r in face["audio_rules"]] == [("FACE_TO_FACE", 1)]
    dup = admin.post("/api/v1/projects", json=NEW_PROJECT)
    assert dup.json()["error"]["code"] == "PROJECT_CODE_TAKEN"


def test_a_project_without_a_code_gets_the_next_prj_code(admin: Api) -> None:
    """D-083: the New project form has no code field; the platform gives PRJ0001, PRJ0002, ..."""
    body = {k: v for k, v in NEW_PROJECT.items() if k != "code"}
    first = admin.post("/api/v1/projects", json=body)
    second = admin.post("/api/v1/projects", json={**body, "name": "Second"})
    assert first.status_code == second.status_code == 201
    codes = [first.json()["code"], second.json()["code"]]
    assert all(c.startswith("PRJ") and c[3:].isdigit() and len(c) >= 7 for c in codes)
    assert int(codes[1][3:]) > int(codes[0][3:])
    # The list shows the newest project first, so one just created is on the first page however
    # many there are.
    codes = [p["code"] for p in admin.get("/api/v1/projects").json()["items"]]
    assert codes == sorted(codes, reverse=True)
    assert codes[0].startswith("PRJ")


def test_mode_and_target_validation(admin: Api) -> None:
    """D-153: one recording type per project, never both or neither; a daily target only for it."""
    for both in (False, True):
        answer = admin.post(
            "/api/v1/projects",
            json={**NEW_PROJECT, "allows_telephony": both, "allows_face_to_face": both},
        )
        assert answer.status_code == 422, answer.text
        assert answer.json()["error"]["code"] == "ONE_RECORDING_TYPE"
        assert answer.json()["error"]["message"] == (
            "Choose one recording type: face-to-face or phone call. Make another project for "
            "the other."
        )
    mismatch = admin.post(
        "/api/v1/projects",
        json={**NEW_PROJECT, "code": "X2", "target_face_to_face_hours_per_day": "5"},
    )
    assert mismatch.json()["error"]["code"] == "MODE_NOT_ALLOWED"


def test_languages_audio_rules_retention(admin: Api, db: Any) -> None:
    pid = admin.post("/api/v1/projects", json=NEW_PROJECT).json()["id"]
    langs = admin.put(
        f"/api/v1/projects/{pid}/languages",
        json={
            "languages": [
                {"language_code": "hi", "dialect": "Awadhi"},
                {"language_code": "hi", "dialect": ""},
            ]
        },
    )
    assert [(x["language_code"], x["dialect"]) for x in langs.json()["languages"]] == [
        ("hi", ""),
        ("hi", "Awadhi"),
    ]
    rule = {
        "sample_rate": 16000,
        "bit_depth": 16,
        "max_silence_pct": "20",
        "max_clipping_pct": "0.5",
        "min_duration_seconds": 300,
        "max_duration_seconds": 3600,
    }
    ok = admin.put(
        f"/api/v1/projects/{pid}/audio-rules",
        json={"rules": [{**rule, "mode": "TELEPHONY", "channels": 2}]},
    )
    assert ok.status_code == 200
    assert {r["mode"]: r["max_silence_pct"] for r in ok.json()["audio_rules"]} == {
        "TELEPHONY": "20.00",
    }
    # PROJ-13: the audit entry shows every setting before and after, in the same form.
    [entry] = _entries(db, "project.audio_rules_changed")
    common = {"mode": "TELEPHONY", "sample_rate": 16000, "bit_depth": 16, "channels": 2}
    assert json.loads(entry.before_summary or "") == {
        "rules": [
            {
                **common,
                "max_silence_pct": "25.00",
                "max_clipping_pct": None,
                "min_duration_seconds": 0,
                "max_duration_seconds": None,
            }
        ]
    }
    assert json.loads(entry.after_summary or "") == {
        "rules": [
            {
                **common,
                "max_silence_pct": "20.00",
                "max_clipping_pct": "0.50",
                "min_duration_seconds": 300,
                "max_duration_seconds": 3600,
            }
        ]
    }
    again = admin.put(
        f"/api/v1/projects/{pid}/audio-rules",
        json={"rules": [{**rule, "mode": "TELEPHONY", "channels": 2}]},
    )
    assert again.status_code == 200
    assert len(_entries(db, "project.audio_rules_changed")) == 1, "nothing changed: no entry"
    for rules in (
        [{**rule, "mode": "FACE_TO_FACE", "channels": 1}],  # its own type missing
        [
            {**rule, "mode": "TELEPHONY", "channels": 2},
            {**rule, "mode": "FACE_TO_FACE", "channels": 1},  # a type it does not record
        ],
    ):
        wrong = admin.put(f"/api/v1/projects/{pid}/audio-rules", json={"rules": rules})
        assert wrong.json()["error"]["code"] == "MODE_NOT_ALLOWED"
    retention = admin.put(
        f"/api/v1/projects/{pid}/retention",
        json={"rules": [{"asset_kind": "BROWSER_ORIGINAL", "retain_days": 90}]},
    )
    assert retention.json()["retention_rules"] == [
        {"asset_kind": "BROWSER_ORIGINAL", "retain_days": 90}
    ]


def _entries(db: Any, action: str) -> list[AuditLog]:
    db.expire_all()
    return list(
        db.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at)
        ).all()
    )


def test_retention_rules_are_for_the_files_kept_in_storage(admin: Api, db: Any) -> None:
    """PROJ-01: a rule can be saved only for the kinds of file a recording keeps in storage (the
    originals and the delivery files); a rule saved before for another kind still shows."""
    pid = admin.post("/api/v1/projects", json=NEW_PROJECT).json()["id"]
    path = f"/api/v1/projects/{pid}/retention"
    for kind in ("EXPORT_PACKAGE", "TRANSCRIPT_FILE", "CONSENT_RECORDING"):
        refused = admin.put(path, json={"rules": [{"asset_kind": kind, "retain_days": 90}]})
        assert refused.status_code == 422, kind
        assert refused.json()["error"]["code"] == "VALIDATION_ERROR"
    kinds = [
        "BROWSER_ORIGINAL",
        "FTF_DERIVED_PCM",
        "PROVIDER_ORIGINAL_MIXED",
        "TELEPHONY_DERIVED_PCM",
    ]
    saved = admin.put(path, json={"rules": [{"asset_kind": k, "retain_days": 30} for k in kinds]})
    assert saved.status_code == 200, saved.text
    db.add(
        ProjectRetentionRule(project_id=uuid.UUID(pid), asset_kind="EXPORT_PACKAGE", retain_days=7)
    )
    db.commit()
    shown = admin.get(f"/api/v1/projects/{pid}")
    assert shown.status_code == 200, shown.text
    assert {"asset_kind": "EXPORT_PACKAGE", "retain_days": 7} in shown.json()["retention_rules"]


def test_a_save_over_someone_elses_newer_save_is_refused(admin: Api, db: Any) -> None:
    """PROJ-03: a page sends back the `updated_at` it loaded; a save made since by someone else
    is not undone by its older copy (409 PROJECT_CHANGED). Left out, nothing is compared."""
    made = admin.post("/api/v1/projects", json=NEW_PROJECT).json()
    pid, opened = made["id"], made["updated_at"]
    url = f"/api/v1/projects/{pid}"
    body = {k: v for k, v in NEW_PROJECT.items() if k != "code"}
    theirs = admin.patch(url, json={**body, "description": "Theirs", "expected_updated_at": opened})
    assert theirs.status_code == 200, theirs.text
    assert theirs.json()["updated_at"] != opened
    assert admin.get(url).json()["updated_at"] == theirs.json()["updated_at"]

    stale = admin.patch(url, json={**body, "description": "Mine", "expected_updated_at": opened})
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"] == {
        "code": "PROJECT_CHANGED",
        "message": "Someone else saved this project after you opened it. Reload the page to see "
        "their changes, then save again.",
        "request_id": stale.json()["error"]["request_id"],
    }
    assert admin.get(url).json()["description"] == "Theirs", "their save stands"
    assert len(_entries(db, "project.updated")) == 1

    current = theirs.json()["updated_at"]
    mine = admin.patch(url, json={**body, "description": "Mine", "expected_updated_at": current})
    assert mine.status_code == 200, mine.text
    assert mine.json()["description"] == "Mine"
    unchecked = admin.patch(url, json={**body, "description": "No check"})
    assert unchecked.status_code == 200, unchecked.text
    naive = admin.patch(url, json={**body, "expected_updated_at": "2026-11-22T10:00:00"})
    assert naive.json()["error"]["code"] == "VALIDATION_ERROR", "a time without its zone"


def test_a_name_is_one_line(admin: Api) -> None:
    """PROJ-11: line breaks and runs of spaces in a name become one space; only spaces is no
    name."""
    made = admin.post("/api/v1/projects", json={**NEW_PROJECT, "name": " Konkani\nphase   2 "})
    assert made.status_code == 201, made.text
    assert made.json()["name"] == "Konkani phase 2"
    url = f"/api/v1/projects/{made.json()['id']}"
    body = {k: v for k, v in NEW_PROJECT.items() if k != "code"}
    renamed = admin.patch(url, json={**body, "name": "Konkani\r\nphase" + chr(0x2028) + "3"})
    assert renamed.json()["name"] == "Konkani phase 3"
    for blank in ("   ", "\n\t"):
        refused = admin.patch(url, json={**body, "name": blank})
        assert refused.status_code == 422, blank
        assert refused.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_line_break_in_a_project_name_does_not_stop_its_consent_emails(
    admin: Api, db: Any, outbox: Path
) -> None:
    """PROJ-11: a project named before names were one line still emails its consent form, with
    the name on one line in the subject."""
    project = make_project(db, "BREAK")
    db.execute(
        update(Project)
        .where(Project.id == project.id)
        .values(name="Konkani" + chr(0x2028) + "phase\n2", consent_text="I agree to be recorded.")
    )
    db.commit()
    joined = admin.post(
        f"/api/v1/projects/{project.id}/participants",
        json={"display_label": "Asha", "language_code": "hi", "email": "asha@example.org"},
    )
    assert joined.status_code == 201, joined.text
    assert joined.json()["consent_email"] == "Consent form emailed."
    [mail] = [m for m in read_outbox(outbox) if "To: asha@example.org" in m]
    assert "Subject: Consent form for Konkani phase 2\n" in mail


def test_lifecycle_rules_and_archived_projects_take_no_new_work(admin: Api, db: Any) -> None:
    pid = admin.post("/api/v1/projects", json=NEW_PROJECT).json()["id"]

    def status(s: str, reason: str | None = None) -> Any:
        return admin.post(f"/api/v1/projects/{pid}/status", json={"status": s, "reason": reason})

    assert status("COMPLETED").json()["error"]["code"] == "INVALID_TRANSITION"
    assert status("ACTIVE").json()["accepts_new_work"] is True
    assert status("ARCHIVED").json()["error"]["code"] == "REASON_REQUIRED"
    archived = status("ARCHIVED", "Collection finished").json()
    assert archived["status"] == "ARCHIVED"
    assert (
        admin.patch(
            f"/api/v1/projects/{pid}", json={k: v for k, v in NEW_PROJECT.items() if k != "code"}
        ).json()["error"]["code"]
        == "PROJECT_ARCHIVED"
    )
    # PROJ-05: read only means its languages, audio rules and retention too ...
    rule = {"mode": "TELEPHONY", "sample_rate": 8000, "bit_depth": 16, "channels": 2}
    rule |= {"max_silence_pct": "99", "min_duration_seconds": 0}
    for path, body in (
        ("languages", {"languages": [{"language_code": "hi", "dialect": ""}]}),
        ("audio-rules", {"rules": [rule]}),
        ("retention", {"rules": [{"asset_kind": "BROWSER_ORIGINAL", "retain_days": 1}]}),
    ):
        refused = admin.put(f"/api/v1/projects/{pid}/{path}", json=body)
        assert refused.status_code == 409, path
        assert refused.json()["error"] == {
            "code": "PROJECT_ARCHIVED",
            "message": "Reopen the project before editing it",
            "request_id": refused.json()["error"]["request_id"],
        }
    kept = admin.get(f"/api/v1/projects/{pid}").json()
    assert (kept["languages"], kept["retention_rules"]) == ([], [])
    assert kept["audio_rules"][0]["max_silence_pct"] == "25.00"
    # ... but not its team: removing someone is how their access ends.
    worker = make_user(db, "worker@example.org", ["MODERATOR"])
    members = f"/api/v1/projects/{pid}/members"
    assert admin.post(members, json={"user_id": str(worker.id)}).status_code == 204
    assert admin.delete(f"{members}/{worker.id}").status_code == 204
    from app.modules.projects.models import Project

    db.expire_all()
    with pytest.raises(AppError) as info:
        ensure_accepts_new_work(db.get(Project, archived["id"]))
    assert info.value.code == "PROJECT_NOT_ACCEPTING_WORK"
    assert status("ACTIVE").json()["error"]["code"] == "REASON_REQUIRED"
    assert status("ACTIVE", "Client asked for more").json()["status"] == "ACTIVE"


def test_project_isolation_between_project_admins(db: Any, new_api: Any) -> None:
    mine, other = make_project(db, "MINE"), make_project(db, "OTHER")
    make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[mine])
    api: Api = new_api()
    api.login("pa@example.org")
    assert [p["code"] for p in api.get("/api/v1/projects").json()["items"]] == ["MINE"]
    assert api.get(f"/api/v1/projects/{other.id}").status_code == 404
    assert (
        api.put(f"/api/v1/projects/{other.id}/languages", json={"languages": []}).status_code == 404
    )
    assert api.get(f"/api/v1/projects/{mine.id}").status_code == 200
    assert api.post("/api/v1/projects", json=NEW_PROJECT).status_code == 403


def test_members_add_remove_and_disabled_users(admin: Api, db: Any) -> None:
    project = make_project(db, "TEAM")
    worker = make_user(db, "worker@example.org", ["MODERATOR"])
    gone = make_user(db, "gone@example.org", ["MODERATOR"], status="DISABLED")
    assert (
        admin.post(
            f"/api/v1/projects/{project.id}/members", json={"user_id": str(worker.id)}
        ).status_code
        == 204
    )
    assert (
        admin.post(
            f"/api/v1/projects/{project.id}/members", json={"user_id": str(worker.id)}
        ).json()["error"]["code"]
        == "ALREADY_MEMBER"
    )
    assert (
        admin.post(f"/api/v1/projects/{project.id}/members", json={"user_id": str(gone.id)}).json()[
            "error"
        ]["code"]
        == "USER_DISABLED"
    )
    members = admin.get(f"/api/v1/projects/{project.id}/members").json()
    assert [m["email"] for m in members] == ["worker@example.org"]
    assert admin.delete(f"/api/v1/projects/{project.id}/members/{worker.id}").status_code == 204
    assert admin.get(f"/api/v1/projects/{project.id}/members").json() == []


def test_a_member_with_open_tasks_stays_until_they_are_reassigned(admin: Api, db: Any) -> None:
    """PROJ-06: removed from the project, a moderator could no longer open their tasks and nobody
    else would have them. While work here still needs them they stay (409
    MEMBER_HAS_OPEN_TASKS); a moderator whose tasks went on to QC, or a QC Executive whose
    tasks wait for the admin, may go."""
    project = make_project(db, "OPEN")
    mod = make_user(db, "mod@example.org", ["MODERATOR"], projects=[project])
    other = make_user(db, "mod2@example.org", ["MODERATOR"], projects=[project])
    qc = make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[project])
    a = make_participant(admin, project.id, "Asha")
    b = make_participant(admin, project.id, "Bina")

    def task() -> dict[str, Any]:
        made = admin.post(
            "/api/v1/tasks",
            json={
                "project_id": str(project.id),
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": a["id"],
                "participant_b_id": b["id"],
            },
        )
        assert made.status_code == 201, made.text
        assigned = admin.post(
            f"/api/v1/tasks/{made.json()['id']}/assign", json={"user_id": str(mod.id)}
        )
        assert assigned.status_code == 200, assigned.text
        result: dict[str, Any] = assigned.json()
        return result

    first, second = task(), task()
    members = f"/api/v1/projects/{project.id}/members"
    refused = admin.delete(f"{members}/{mod.id}")
    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["code"] == "MEMBER_HAS_OPEN_TASKS"
    codes = f"{first['task_code']}, {second['task_code']}"
    assert error["message"] == (
        f"mod still has 2 open tasks in this project ({codes}). Reassign them, or let them "
        "finish, before removing this person."
    )
    assert error["details"] == [
        {"open_tasks": 2, "task_codes": [first["task_code"], second["task_code"]]}
    ]
    assert mod.email in [m["email"] for m in admin.get(members).json()], "still a member"

    # One reassigned, the other gone on to QC: nothing here needs them any more.
    moved = admin.post(
        f"/api/v1/tasks/{first['id']}/assign",
        json={"user_id": str(other.id), "reason": "Leaving the project"},
    )
    assert moved.status_code == 200, moved.text
    set_status(db, second["id"], "AUDIO_QC")
    assert admin.delete(f"{members}/{mod.id}").status_code == 204

    # A QC Executive with a recording to check stays; once it waits for the admin, may go.
    db.add(TaskAssignment(task_id=uuid.UUID(second["id"]), user_id=qc.id, role_code="QC_EXECUTIVE"))
    db.commit()
    waiting = admin.delete(f"{members}/{qc.id}")
    assert waiting.json()["error"]["message"].startswith(
        f"qc still has 1 open task in this project ({second['task_code']}). Reassign it"
    )
    set_status(db, second["id"], "ADMIN_REVIEW")
    assert admin.delete(f"{members}/{qc.id}").status_code == 204


def test_member_candidates_lists_active_non_members_only(admin: Api, db: Any, new_api: Any) -> None:
    project = make_project(db, "PICK")
    member = make_user(db, "member@example.org", ["MODERATOR"], projects=[project])
    make_user(db, "free@example.org", ["QC_EXECUTIVE"])
    make_user(db, "off@example.org", ["QC_EXECUTIVE"], status="DISABLED")
    emails = [
        c["email"] for c in admin.get(f"/api/v1/projects/{project.id}/member-candidates").json()
    ]
    assert "free@example.org" in emails
    assert "member@example.org" not in emails
    assert "off@example.org" not in emails
    viewer: Api = new_api()
    viewer.login(member.email)
    assert viewer.get(f"/api/v1/projects/{project.id}/member-candidates").status_code == 403


def test_saving_the_same_lists_again_is_not_an_error(admin: Api, db: Any) -> None:
    """Found by the Option B route sweep: the second save of an unchanged list was a 500 (the new
    row was inserted before the old one was deleted, hitting the unique key)."""
    pid = make_project(db, "TWICE").id
    languages = {
        "languages": [
            {"language_code": "hi", "dialect": ""},
            {"language_code": "ta", "dialect": "Madurai"},
        ]
    }
    for days in (30, 30, 60):
        saved = admin.put(f"/api/v1/projects/{pid}/languages", json=languages)
        assert saved.status_code == 200, saved.text
        kept = admin.put(
            f"/api/v1/projects/{pid}/retention",
            json={"rules": [{"asset_kind": "FTF_DERIVED_PCM", "retain_days": days}]},
        )
        assert kept.status_code == 200, kept.text
    assert kept.json()["retention_rules"] == [{"asset_kind": "FTF_DERIVED_PCM", "retain_days": 60}]
    assert len(saved.json()["languages"]) == 2
    # PROJ-13: a save that changes nothing is no audit entry.
    assert len(_entries(db, "project.languages_changed")) == 1
    retention = _entries(db, "project.retention_changed")
    assert [json.loads(e.after_summary or "") for e in retention] == [
        {"FTF_DERIVED_PCM": 30},
        {"FTF_DERIVED_PCM": 60},
    ]
