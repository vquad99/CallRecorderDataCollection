"""Project management: create, configure, lifecycle, members, isolation.

Requirements: PROJ-001, PROJ-002, PROJ-003, PROJ-004, PROJ-005, PROJ-006, PROJ-007, PROJ-008, PROJ-009, PROJ-010, PROJ-012, USER-003, CAP-003
"""

from typing import Any

import pytest

from app.core.errors import AppError
from app.modules.projects.service import ensure_accepts_new_work
from tests.conftest import Api, make_project, make_user

pytestmark = pytest.mark.db

NEW_PROJECT = {
    "code": "hindi-01",
    "name": "Hindi conversations",
    "allows_telephony": True,
    "allows_face_to_face": True,
    "target_telephony_hours_per_day": "62.5",
    "target_face_to_face_hours_per_day": "62.5",
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
    assert (
        rules["TELEPHONY"]["sample_rate"],
        rules["TELEPHONY"]["bit_depth"],
        rules["TELEPHONY"]["channels"],
    ) == (16000, 16, 1)  # one channel: the phone provider records the call together (D-103)
    assert rules["FACE_TO_FACE"]["channels"] == 1
    assert rules["TELEPHONY"]["max_silence_pct"] == "25.00"
    assert rules["TELEPHONY"]["max_clipping_pct"] is None
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


def test_mode_and_target_validation(admin: Api) -> None:
    none = admin.post(
        "/api/v1/projects",
        json={**NEW_PROJECT, "allows_telephony": False, "allows_face_to_face": False},
    )
    assert none.json()["error"]["code"] == "MODE_REQUIRED"
    mismatch = admin.post(
        "/api/v1/projects", json={**NEW_PROJECT, "code": "X2", "allows_telephony": False}
    )
    assert mismatch.json()["error"]["code"] == "MODE_NOT_ALLOWED"


def test_languages_audio_rules_retention(admin: Api) -> None:
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
        json={
            "rules": [
                {**rule, "mode": "TELEPHONY", "channels": 2},
                {**rule, "mode": "FACE_TO_FACE", "channels": 1},
            ]
        },
    )
    assert ok.status_code == 200
    assert {r["mode"]: r["max_silence_pct"] for r in ok.json()["audio_rules"]} == {
        "FACE_TO_FACE": "20.00",
        "TELEPHONY": "20.00",
    }
    missing_mode = admin.put(
        f"/api/v1/projects/{pid}/audio-rules",
        json={"rules": [{**rule, "mode": "TELEPHONY", "channels": 2}]},
    )
    assert missing_mode.json()["error"]["code"] == "MODE_NOT_ALLOWED"
    retention = admin.put(
        f"/api/v1/projects/{pid}/retention",
        json={"rules": [{"asset_kind": "BROWSER_ORIGINAL", "retain_days": 90}]},
    )
    assert retention.json()["retention_rules"] == [
        {"asset_kind": "BROWSER_ORIGINAL", "retain_days": 90}
    ]


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
