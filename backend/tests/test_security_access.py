"""Access control over the whole API (owner's test list, Option B).

One estate with two projects: OWN (the callers are members) and a foreign project (they are not).
Every API route is called by every role, plus a moderator of OWN who is not assigned to its tasks:

1. Route inventory: every route of the app is in the table below or in the public / self-service
   lists, so a new route cannot ship without an access rule and a test.
2. Own project: the roles in ``allowed`` get through access control (not 401/403/404, never 5xx);
   every other role is refused with 403 or 404. The allowed sets come from the permission matrix
   (docs/ARCHITECTURE.md section 5) and the recorded rules (DECISIONS.md D-029, D-035, D-046,
   D-049); they are written out, not computed from the code under test.
3. Foreign project: the same requests aimed at the other project's objects are refused for every
   role but Super Admin, with exactly the answer the same caller gets for an object that does not
   exist, so the object's existence is not revealed either.
4. No response a project member receives contains an identifier of the foreign project's objects.
5. Every state-changing route refuses a request without a valid CSRF token.
6. A malformed identifier in any path gives 422, never 500.
7. No response carries a password, secret, token or encrypted field.

Requirements: ROLE-002, ROLE-003, ROLE-004, ROLE-005, ROLE-006, ROLE-007, ROLE-008, ROLE-010, AUTH-011, SEC-007, SEC-010, SEC-011, PART-008, PART-011, STOR-005
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from app.core.permissions import Perm
from app.main import create_app
from tests.conftest import Api, build_settings, make_participant, make_project, make_user
from tests.test_permissions import PUBLIC, SELF_SERVICE_PREFIXES, _route_contexts

pytestmark = pytest.mark.db
BUCKET = "ccp-security"
RATE = 16000
FOREIGN_CODE = "QZFOREIGN"

# Callers: the five roles, plus a moderator who is a member of OWN but assigned to none of its tasks.
SA, PA, MO, MO2, QC, CV = "SA", "PA", "MO", "MO2", "QC", "CV"
CALLERS = [SA, PA, MO, MO2, QC, CV]
EVERY_MEMBER = set(CALLERS)
TASK_VIEWERS = {SA, PA, MO}  # QC sees only tasks assigned to them for audio QC; none here


def _one_second_chunk() -> bytes:
    t = np.arange(RATE) / RATE
    return (0.25 * np.sin(2 * np.pi * 440 * t)).astype("<f4").tobytes()


START = {
    "native_sample_rate": RATE,
    "channel_count": 1,
    "device_channel_count": 1,
    "echo_cancellation": False,
    "noise_suppression": False,
    "auto_gain_control": False,
}


@dataclass
class Side:
    """Identifiers of one project's objects."""

    project: str
    participant: str
    participant_code: str
    spare_participant: str
    task_done: str  # recorded face-to-face task, checked automatically (AUDIO_QC)
    task_open: str  # task with an open recording and a consent record
    recording_done: str
    recording_open: str
    asset: str

    def object_ids(self) -> list[str]:
        return [
            self.project,
            self.participant,
            self.spare_participant,
            self.task_done,
            self.task_open,
            self.recording_done,
            self.recording_open,
            self.asset,
        ]


@dataclass
class Estate:
    callers: dict[str, Api]
    own: Side
    foreign: Side
    spare_user: str
    foreign_moderator: str
    db: Any


def _ghost() -> Side:
    """Identifiers that exist nowhere: the answer for these is what 'not found' looks like."""
    ids = [str(uuid.uuid4()) for _ in range(8)]
    return Side(ids[0], ids[1], "P999999", ids[2], ids[3], ids[4], ids[5], ids[6], ids[7])


def _build_side(db: Any, api: Callable[[str], Api], code: str, admin: str, moderator: str) -> Side:
    pa, mo = api(admin), api(moderator)
    project_id = db.execute(
        text("SELECT id FROM projects WHERE code = :c"), {"c": code}
    ).scalar_one()
    phone = "+919876543210" if code == "OWN" else "+919812345678"  # no duplicate match
    a = make_participant(pa, project_id, "Asha", phone=phone)
    b = make_participant(pa, project_id, "Bina")
    spare = make_participant(pa, project_id, f"Spare {code}")
    mod_id = str(
        db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": moderator}).scalar_one()
    )

    def new_task() -> str:
        task = pa.post(
            "/api/v1/tasks",
            json={
                "project_id": str(project_id),
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": a["id"],
                "participant_b_id": b["id"],
            },
        )
        assert task.status_code == 201, task.text
        tid: str = task.json()["id"]
        assert pa.post(f"/api/v1/tasks/{tid}/assign", json={"user_id": mod_id}).status_code == 200
        moved = mo.post(f"/api/v1/tasks/{tid}/transition", json={"to": "IN_PROGRESS"})
        assert moved.status_code == 200, moved.text
        return tid

    done = new_task()
    rec = mo.post(f"/api/v1/tasks/{done}/recordings", json=START).json()
    data = _one_second_chunk()
    sha = hashlib.sha256(data).hexdigest()
    put = mo.put(
        f"/api/v1/recordings/{rec['id']}/chunks/0",
        content=data,
        headers={"Content-Type": "application/octet-stream", "X-Content-SHA256": sha},
    )
    assert put.status_code == 200, put.text
    assert (
        mo.post(f"/api/v1/recordings/{rec['id']}/complete", json={"chunk_count": 1}).status_code
        == 200
    )
    detail = mo.get(f"/api/v1/recordings/{rec['id']}").json()
    assert detail["state"] == "READY", detail
    # D-092: the moderator sends the recording to QC, so the task reaches AUDIO_QC.
    sent = mo.post(f"/api/v1/tasks/{done}/transition", json={"to": "AUDIO_QC"})
    assert sent.status_code == 200, sent.text
    asset = next(x["id"] for x in detail["assets"] if x["kind"] == "FTF_DERIVED_PCM")

    open_task = new_task()
    consent = mo.post(
        f"/api/v1/tasks/{open_task}/consent",
        json={"participant_id": a["id"], "status": "GIVEN", "method": "VERBAL_NOTED"},
    )
    assert consent.status_code == 201, consent.text
    open_rec = mo.post(f"/api/v1/tasks/{open_task}/recordings", json=START).json()
    assert (
        mo.put(
            f"/api/v1/recordings/{open_rec['id']}/chunks/0",
            content=data,
            headers={"Content-Type": "application/octet-stream", "X-Content-SHA256": sha},
        ).status_code
        == 200
    )
    return Side(
        project=str(project_id),
        participant=a["id"],
        participant_code=a["participant_code"],
        spare_participant=spare["id"],
        task_done=done,
        task_open=open_task,
        recording_done=rec["id"],
        recording_open=open_rec["id"],
        asset=asset,
    )


@pytest.fixture
def estate(migrated_db: str, tmp_path: Path) -> Iterator[Estate]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        app = create_app(
            build_settings(
                database_url=migrated_db,
                storage_bucket=BUCKET,
                storage_access_key_id="test-key",
                storage_secret_access_key="test-secret",
                media_work_dir=str(tmp_path / "media"),
                email_file_dir=str(tmp_path / "outbox"),
            )
        )
        clients: list[TestClient] = []

        def api(email: str) -> Api:
            client = TestClient(app)
            clients.append(client)
            a = Api(client)
            assert a.login(email).status_code == 200, email
            return a

        with app.state.session_factory() as db:
            own, foreign = make_project(db, "OWN"), make_project(db, FOREIGN_CODE)
            make_user(db, "sa@example.org", ["SUPER_ADMIN"])
            make_user(db, "pa@example.org", ["PROJECT_ADMIN"], projects=[own])
            make_user(db, "mo@example.org", ["MODERATOR"], projects=[own])
            make_user(db, "mo2@example.org", ["MODERATOR"], projects=[own])
            make_user(db, "qc@example.org", ["QC_EXECUTIVE"], projects=[own])
            make_user(db, "cv@example.org", ["CLIENT_VIEWER"], projects=[own])
            spare = make_user(db, "spare@example.org", ["MODERATOR"], projects=[own])
            make_user(db, "pa.f@example.org", ["PROJECT_ADMIN"], projects=[foreign])
            mo_f = make_user(db, "mo.f@example.org", ["MODERATOR"], projects=[foreign])
            own_side = _build_side(db, api, "OWN", "pa@example.org", "mo@example.org")
            foreign_side = _build_side(
                db, api, FOREIGN_CODE, "pa.f@example.org", "mo.f@example.org"
            )
            callers = {
                SA: api("sa@example.org"),
                PA: api("pa@example.org"),
                MO: api("mo@example.org"),
                MO2: api("mo2@example.org"),
                QC: api("qc@example.org"),
                CV: api("cv@example.org"),
            }
            yield Estate(callers, own_side, foreign_side, str(spare.id), str(mo_f.id), db)
        for c in clients:
            c.close()


# ------------------------------------------------------------------------------------ route table

Body = Callable[["Estate", Side, str], Any]


@dataclass(frozen=True)
class Case:
    method: str
    template: str
    path: Callable[[Estate, Side], str]
    allowed: frozenset[str]
    perm: Perm  # the permission the route itself requires (documentation; the router checks it)
    body: Body | None = None
    raw: bool = False  # chunk upload: raw bytes, not JSON
    foreign: bool = True  # path names a project-scoped object, so it has a foreign variant
    before: Callable[[Estate], Any] | None = None  # restores state before each own-project call


def case(
    method: str,
    template: str,
    path: Callable[[Estate, Side], str],
    allowed: set[str],
    perm: Perm,
    body: Body | None = None,
    *,
    raw: bool = False,
    foreign: bool = True,
    before: Callable[[Estate], Any] | None = None,
) -> Case:
    return Case(method, template, path, frozenset(allowed), perm, body, raw, foreign, before)


def _project_body(_: Estate, __: Side, ___: str) -> dict[str, Any]:
    return {"name": "Renamed", "allows_telephony": True, "allows_face_to_face": True}


def _csv(_: Estate, __: Side, who: str) -> dict[str, str]:
    return {
        "csv": f"email,display_name,roles\nimported.{who.lower()}@example.org,Imported,MODERATOR\n"
    }


P = "/api/v1/projects/{project_id}"
PP = "/api/v1/projects/{project_id}/participants/{participant_id}"
CASES: list[Case] = [
    # Users, roles, settings: Super Admin only (D-010).
    case(
        "GET", "/api/v1/users", lambda e, s: "/api/v1/users", {SA}, Perm.USERS_MANAGE, foreign=False
    ),
    case(
        "POST",
        "/api/v1/users",
        lambda e, s: "/api/v1/users",
        {SA},
        Perm.USERS_MANAGE,
        lambda e, s, who: {
            "email": f"new.{who.lower()}@example.org",
            "display_name": "New",
            "roles": ["MODERATOR"],
        },
        foreign=False,
    ),
    case(
        "GET",
        "/api/v1/users/export",
        lambda e, s: "/api/v1/users/export",
        {SA},
        Perm.USERS_MANAGE,
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/users/import/preview",
        lambda e, s: "/api/v1/users/import/preview",
        {SA},
        Perm.USERS_MANAGE,
        _csv,
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/users/import/confirm",
        lambda e, s: "/api/v1/users/import/confirm",
        {SA},
        Perm.USERS_MANAGE,
        _csv,
        foreign=False,
    ),
    case(
        "GET",
        "/api/v1/users/{user_id}",
        lambda e, s: f"/api/v1/users/{e.spare_user}",
        {SA},
        Perm.USERS_MANAGE,
        foreign=False,
    ),
    case(
        "PATCH",
        "/api/v1/users/{user_id}",
        lambda e, s: f"/api/v1/users/{e.spare_user}",
        {SA},
        Perm.USERS_MANAGE,
        lambda e, s, who: {"display_name": f"Spare {who}"},
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/users/{user_id}/disable",
        lambda e, s: f"/api/v1/users/{e.spare_user}/disable",
        {SA},
        Perm.USERS_MANAGE,
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/users/{user_id}/enable",
        lambda e, s: f"/api/v1/users/{e.spare_user}/enable",
        {SA},
        Perm.USERS_MANAGE,
        foreign=False,
    ),
    # The consent record goes with a download, so it needs the download right (no moderator).
    case(
        "GET",
        "/api/v1/recordings/{recording_id}/consent-form",
        lambda e, s: f"/api/v1/recordings/{s.recording_done}/consent-form",
        {SA, PA},
        Perm.RECORDINGS_VIEW,
    ),
    case(
        "PUT",
        "/api/v1/users/{user_id}/roles",
        lambda e, s: f"/api/v1/users/{e.spare_user}/roles",
        {SA},
        Perm.USERS_MANAGE,
        lambda e, s, who: {"roles": ["MODERATOR"]},
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/users/{user_id}/send-password-link",
        lambda e, s: f"/api/v1/users/{e.spare_user}/send-password-link",
        {SA},
        Perm.USERS_MANAGE,
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/users/{user_id}/sessions/revoke",
        lambda e, s: f"/api/v1/users/{e.spare_user}/sessions/revoke",
        {SA},
        Perm.USERS_MANAGE,
        foreign=False,
    ),
    case(
        "GET", "/api/v1/roles", lambda e, s: "/api/v1/roles", {SA}, Perm.USERS_MANAGE, foreign=False
    ),
    case(
        "GET",
        "/api/v1/settings",
        lambda e, s: "/api/v1/settings",
        {SA},
        Perm.SETTINGS_MANAGE,
        foreign=False,
    ),
    case(
        "PATCH",
        "/api/v1/settings",
        lambda e, s: "/api/v1/settings",
        {SA},
        Perm.SETTINGS_MANAGE,
        lambda e, s, who: {"values": {"capacity.staff_accounts": 50}},
        foreign=False,
    ),
    # Projects: everyone sees their own; Super Admin creates; Project Admin manages (matrix "O").
    case(
        "GET",
        "/api/v1/projects",
        lambda e, s: "/api/v1/projects",
        EVERY_MEMBER,
        Perm.PROJECTS_VIEW,
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/projects",
        lambda e, s: "/api/v1/projects",
        {SA},
        Perm.PROJECTS_VIEW,
        lambda e, s, who: {**_project_body(e, s, who), "code": f"NEW{who}"},
        foreign=False,
    ),
    case("GET", P, lambda e, s: f"/api/v1/projects/{s.project}", EVERY_MEMBER, Perm.PROJECTS_VIEW),
    case(
        "PATCH",
        P,
        lambda e, s: f"/api/v1/projects/{s.project}",
        {SA, PA},
        Perm.PROJECTS_VIEW,
        _project_body,
    ),
    case(
        "POST",
        P + "/status",
        lambda e, s: f"/api/v1/projects/{s.project}/status",
        {SA, PA},
        Perm.PROJECTS_VIEW,
        lambda e, s, who: {"status": "ACTIVE"},  # already ACTIVE: refused after the access check
    ),
    case(
        "PUT",
        P + "/languages",
        lambda e, s: f"/api/v1/projects/{s.project}/languages",
        {SA, PA},
        Perm.PROJECTS_VIEW,
        lambda e, s, who: {"languages": [{"language_code": "hi", "dialect": ""}]},
    ),
    case(
        "PUT",
        P + "/audio-rules",
        lambda e, s: f"/api/v1/projects/{s.project}/audio-rules",
        {SA, PA},
        Perm.PROJECTS_VIEW,
        lambda e, s, who: {
            "rules": [
                {
                    "mode": "FACE_TO_FACE",
                    "sample_rate": 16000,
                    "bit_depth": 16,
                    "channels": 1,
                    "max_silence_pct": "25",
                    "min_duration_seconds": 0,
                }
            ]
        },
    ),
    case(
        "PUT",
        P + "/retention",
        lambda e, s: f"/api/v1/projects/{s.project}/retention",
        {SA, PA},
        Perm.PROJECTS_VIEW,
        lambda e, s, who: {"rules": [{"asset_kind": "FTF_DERIVED_PCM", "retain_days": 365}]},
    ),
    case(
        "GET",
        P + "/members",
        lambda e, s: f"/api/v1/projects/{s.project}/members",
        EVERY_MEMBER,
        Perm.PROJECTS_VIEW,
    ),
    case(
        "GET",
        P + "/member-candidates",
        lambda e, s: f"/api/v1/projects/{s.project}/member-candidates",
        {SA, PA},
        Perm.PROJECTS_VIEW,
    ),
    case(
        "POST",
        P + "/members",
        lambda e, s: f"/api/v1/projects/{s.project}/members",
        {SA, PA},
        Perm.PROJECTS_VIEW,
        lambda e, s, who: {"user_id": e.spare_user},
    ),
    case(
        "DELETE",
        P + "/members/{user_id}",
        lambda e, s: f"/api/v1/projects/{s.project}/members/{e.spare_user}",
        {SA, PA},
        Perm.PROJECTS_VIEW,
        before=lambda e: e.callers[SA].post(
            f"/api/v1/projects/{e.own.project}/members", json={"user_id": e.spare_user}
        ),
    ),
    # Participants: identity tier for every member role (D-035); managers change them; contact
    # export needs its explicit grant (Super Admin only today); consent history for managers and the
    # moderator on an open task with that person (matrix "A", D-049).
    case(
        "GET",
        P + "/participants",
        lambda e, s: f"/api/v1/projects/{s.project}/participants",
        EVERY_MEMBER,
        Perm.PARTICIPANTS_VIEW,
    ),
    case(
        "POST",
        P + "/participants",
        lambda e, s: f"/api/v1/projects/{s.project}/participants",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
        lambda e, s, who: {"display_label": f"Made by {who}", "language_code": "hi"},
    ),
    case(
        "POST",
        P + "/participants/link",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/link",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
        lambda e, s, who: {"participant_code": s.participant_code},  # already linked: 409
    ),
    case(
        "GET",
        P + "/export/summary",
        lambda e, s: f"/api/v1/projects/{s.project}/export/summary",
        {SA, PA, CV},
        Perm.EXPORTS_CREATE,
    ),
    case(
        "GET",
        P + "/export",
        lambda e, s: f"/api/v1/projects/{s.project}/export?content=progress",
        {SA, PA, CV},
        Perm.EXPORTS_CREATE,
    ),
    case(
        "GET",
        P + "/participants/link-candidates",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/link-candidates",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
    ),
    case(
        "GET",
        P + "/participants/export",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/export",
        {SA},
        Perm.PARTICIPANTS_VIEW,
    ),
    case(
        "GET",
        PP,
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}",
        EVERY_MEMBER,
        Perm.PARTICIPANTS_VIEW,
    ),
    case(
        "PATCH",
        PP,
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.spare_participant}",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
        lambda e, s, who: {"display_label": f"Fixed by {who}", "language_code": "hi"},
    ),
    case(
        "POST",
        PP + "/delete",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.spare_participant}/delete",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
        lambda e, s, who: {"reason": "security test"},
    ),
    case(
        "POST",
        P + "/participants/import",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/import",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
        lambda e, s, who: {"csv": "name,language\nImported,hi\n"},
    ),
    case(
        "POST",
        P + "/participants/bulk",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/bulk",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
        lambda e, s, who: {"action": "send_consent", "participant_ids": [s.participant]},
    ),
    case(
        "GET",
        PP + "/consent-form",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}/consent-form",
        {SA, PA, MO},
        Perm.PARTICIPANTS_VIEW,
    ),
    case(
        "GET",
        PP + "/consent-form/file",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}/consent-form/file",
        {SA, PA, MO},
        Perm.PARTICIPANTS_VIEW,
    ),
    case(
        "POST",
        PP + "/consent-review",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}/consent-review",
        {SA, PA},
        Perm.PARTICIPANTS_VIEW,
        lambda e, s, who: {"decision": "APPROVED"},
    ),
    case(
        "POST",
        PP + "/portal-link",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}/portal-link",
        {SA, PA},
        Perm.PARTICIPANTS_MANAGE,
    ),
    case(
        "POST",
        PP + "/portal-link/email",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}/portal-link/email",
        {SA, PA},
        Perm.PARTICIPANTS_MANAGE,
        before=lambda e: None,
    ),
    case(
        "DELETE",
        PP + "/portal-link",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}/portal-link",
        {SA, PA},
        Perm.PARTICIPANTS_MANAGE,
    ),
    case(
        "GET",
        PP + "/consent",
        lambda e, s: f"/api/v1/projects/{s.project}/participants/{s.participant}/consent",
        {SA, PA, MO},
        Perm.PARTICIPANTS_VIEW,
    ),
    # Tasks: visible to managers and the assigned moderator; Client Viewers see none (matrix "-").
    case(
        "GET",
        "/api/v1/tasks",
        lambda e, s: "/api/v1/tasks",
        {SA, PA, MO, MO2, QC},
        Perm.TASKS_VIEW,
        foreign=False,
    ),
    case(
        "POST",
        "/api/v1/tasks",
        lambda e, s: "/api/v1/tasks",
        {SA, PA},
        Perm.TASKS_VIEW,
        lambda e, s, who: {
            "project_id": s.project,
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": s.participant,
            "participant_b_id": s.spare_participant,
        },
    ),
    case(
        "POST",
        "/api/v1/tasks/import",
        lambda e, s: "/api/v1/tasks/import",
        {SA, PA},
        Perm.TASKS_VIEW,
        lambda e, s, who: {"project_id": s.project, "csv": "participant_a,participant_b\n"},
    ),
    case(
        "GET",
        "/api/v1/tasks/{task_id}",
        lambda e, s: f"/api/v1/tasks/{s.task_done}",
        TASK_VIEWERS,
        Perm.TASKS_VIEW,
    ),
    case(
        "POST",
        "/api/v1/tasks/{task_id}/assign",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/assign",
        {SA, PA},
        Perm.TASKS_VIEW,
        lambda e, s, who: {"user_id": e.foreign_moderator},  # not a member: refused after access
    ),
    case(
        "POST",
        "/api/v1/tasks/{task_id}/transition",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/transition",
        TASK_VIEWERS,
        Perm.TASKS_VIEW,
        lambda e, s, who: {"to": "IN_PROGRESS"},  # never valid from AUDIO_QC: 409 after access
    ),
    # Audio QC (D-079): read by task viewers, assigned by managers, decided by the task's QC
    # Executive (none assigned here) or the Super Admin; a Project Admin reads only (matrix O(R)).
    case(
        "GET",
        "/api/v1/tasks/{task_id}/audio-qc",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/audio-qc",
        TASK_VIEWERS,
        Perm.TASKS_VIEW,
    ),
    case(
        "POST",
        "/api/v1/tasks/{task_id}/assign-qc",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/assign-qc",
        {SA, PA},
        Perm.TASKS_VIEW,
        lambda e, s, who: {"user_id": e.foreign_moderator},  # not a member: refused after access
    ),
    case(
        "POST",
        "/api/v1/tasks/{task_id}/audio-qc/decision",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/audio-qc/decision",
        {SA},
        Perm.TASKS_VIEW,
        lambda e, s, who: {"outcome": "FAIL"},  # no reason: refused after access, task unchanged
    ),
    case(
        "POST",
        "/api/v1/tasks/{task_id}/audio-qc/recheck",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/audio-qc/recheck",
        {SA, PA},
        Perm.TASKS_VIEW,
    ),
    # The details file goes with a download, so it needs the download right (D-079).
    case(
        "GET",
        "/api/v1/recordings/{recording_id}/metadata",
        lambda e, s: f"/api/v1/recordings/{s.recording_done}/metadata",
        {SA, PA},
        Perm.RECORDINGS_DOWNLOAD,
    ),
    case(
        "POST",
        "/api/v1/tasks/{task_id}/consent",
        lambda e, s: f"/api/v1/tasks/{s.task_open}/consent",
        {MO},  # only the assigned moderator records consent (D-051)
        Perm.TASKS_VIEW,
        lambda e, s, who: {
            "participant_id": s.participant,
            "status": "GIVEN",
            "method": "VERBAL_NOTED",
        },
    ),
    case(
        "POST",
        "/api/v1/tasks/{task_id}/comments",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/comments",
        TASK_VIEWERS,
        Perm.TASKS_VIEW,
        lambda e, s, who: {"body": f"note from {who}"},
    ),
    case(
        "GET",
        "/api/v1/tasks/{task_id}/timeline",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/timeline",
        TASK_VIEWERS,
        Perm.TASKS_VIEW,
    ),
    case(
        "GET",
        "/api/v1/audit-logs",
        lambda e, s: "/api/v1/audit-logs",
        {SA, PA},
        Perm.AUDIT_VIEW,
        foreign=False,
    ),
    # Recordings: only the assigned moderator records (Super Admin excluded, D-029); only the
    # moderator who started a recording changes it; downloads for managers; Client Viewers receive
    # final files through exports, not recording links (D-046).
    case(
        "POST",
        "/api/v1/tasks/{task_id}/recordings",
        lambda e, s: f"/api/v1/tasks/{s.task_open}/recordings",
        {MO},
        Perm.RECORDINGS_VIEW,
        lambda e, s, who: START,
    ),
    case(
        "GET",
        "/api/v1/tasks/{task_id}/recordings",
        lambda e, s: f"/api/v1/tasks/{s.task_done}/recordings",
        TASK_VIEWERS,
        Perm.RECORDINGS_VIEW,
    ),
    case(
        "GET",
        "/api/v1/recordings/{recording_id}",
        lambda e, s: f"/api/v1/recordings/{s.recording_done}",
        TASK_VIEWERS,
        Perm.RECORDINGS_VIEW,
    ),
    case(
        "PUT",
        "/api/v1/recordings/{recording_id}/chunks/{seq}",
        lambda e, s: f"/api/v1/recordings/{s.recording_open}/chunks/1",
        {MO},
        Perm.RECORDINGS_VIEW,
        raw=True,
    ),
    case(
        "POST",
        "/api/v1/recordings/{recording_id}/complete",
        lambda e, s: f"/api/v1/recordings/{s.recording_open}/complete",
        {MO},
        Perm.RECORDINGS_VIEW,
        lambda e, s, who: {"chunk_count": 99},  # parts missing: 409 after the access check
    ),
    case(
        "POST",
        "/api/v1/recordings/{recording_id}/interrupted",
        lambda e, s: f"/api/v1/recordings/{s.recording_open}/interrupted",
        {MO},
        Perm.RECORDINGS_VIEW,
        lambda e, s, who: {"reason": "security test"},
    ),
    case(
        "POST",
        "/api/v1/recordings/{recording_id}/discard",
        lambda e, s: f"/api/v1/recordings/{s.recording_open}/discard",
        {MO},
        Perm.RECORDINGS_VIEW,
        lambda e, s, who: {"reason": "security test"},
    ),
    case(
        "POST",
        "/api/v1/assets/{asset_id}/url",
        lambda e, s: f"/api/v1/assets/{s.asset}/url",
        TASK_VIEWERS,
        Perm.RECORDINGS_VIEW,
        lambda e, s, who: {"purpose": "play"},
    ),
    # Storage usage: project administrators only (D-049).
    case(
        "GET",
        "/api/v1/storage/usage",
        lambda e, s: "/api/v1/storage/usage",
        {SA, PA},
        Perm.DASHBOARD_VIEW,
        foreign=False,
    ),
    # System status: the Super Admin only (owner 2026-11-11).
    case(
        "GET",
        "/api/v1/system/status",
        lambda e, s: "/api/v1/system/status",
        {SA},
        Perm.SETTINGS_MANAGE,
        foreign=False,
    ),
    # Dashboard: every role sees its own project's numbers; a foreign project answers like a
    # missing one (the view each role gets is checked in test_dashboard.py).
    case(
        "GET",
        "/api/v1/dashboard",
        lambda e, s: f"/api/v1/dashboard?project_id={s.project}",
        EVERY_MEMBER,
        Perm.DASHBOARD_VIEW,
    ),
]
# Same route, different purpose: a download link needs recordings.download (no moderator).
DOWNLOAD = case(
    "POST",
    "/api/v1/assets/{asset_id}/url",
    lambda e, s: f"/api/v1/assets/{s.asset}/url",
    {SA, PA},
    Perm.RECORDINGS_VIEW,
    lambda e, s, who: {"purpose": "download"},
)


def _send(api: Api, c: Case, e: Estate, side: Side, who: str) -> Any:
    path = c.path(e, side)
    if c.raw:
        data = _one_second_chunk()
        return api.put(
            path,
            content=data,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
            },
        )
    method = c.method.lower()
    if c.method in ("GET", "DELETE"):
        return getattr(api, method)(path)
    return getattr(api, method)(path, json=c.body(e, side, who) if c.body else {})


def _app_routes() -> set[tuple[str, str]]:
    return {(m, ctx.path) for ctx in _route_contexts() for m in ctx.methods - {"HEAD", "OPTIONS"}}


# ------------------------------------------------------------------------------------------- tests


def test_every_route_has_an_access_rule() -> None:
    covered = {(c.method, c.template) for c in CASES}
    self_service = {(m, p) for m, p in _app_routes() if p.startswith(SELF_SERVICE_PREFIXES)}
    missing = sorted(_app_routes() - covered - PUBLIC - self_service)
    stale = sorted(covered - _app_routes())
    assert not missing, f"routes with no access rule in this file: {missing}"
    assert not stale, f"rules for routes that no longer exist: {stale}"


def test_every_role_against_every_route(estate: Estate) -> None:
    problems: list[str] = []
    member_bodies: list[tuple[str, str, str]] = []
    for c in [*CASES, DOWNLOAD]:
        for who in CALLERS:
            if c.before:
                c.before(estate)
            response = _send(estate.callers[who], c, estate, estate.own, who)
            status = response.status_code
            label = f"{who} {c.method} {c.template}"
            if status >= 500:
                problems.append(f"{label}: server error {status}")
            elif who in c.allowed and status in (401, 403, 404):
                problems.append(f"{label}: refused with {status} but the rules allow it")
            elif who not in c.allowed and status not in (403, 404):
                problems.append(f"{label}: got {status}, must be refused (403/404)")
            if who != SA:
                member_bodies.append(
                    (label, response.headers.get("content-type", ""), response.text)
                )
        if c.foreign:
            for who in CALLERS:
                if who == SA:
                    continue
                status = _send(estate.callers[who], c, estate, estate.foreign, who).status_code
                ghost = _send(estate.callers[who], c, estate, _ghost(), who).status_code
                if status not in (403, 404) or status != ghost:
                    problems.append(
                        f"{who} {c.method} {c.template} on the foreign project: got {status},"
                        f" for a missing object {ghost} (must be equal, and 403/404)"
                    )
    # Filters naming the foreign project must not return its data either.
    for who in (PA, MO, MO2, QC):
        for path in (
            f"/api/v1/tasks?project_id={estate.foreign.project}",
            f"/api/v1/audit-logs?project_id={estate.foreign.project}",
        ):
            response = estate.callers[who].get(path)
            member_bodies.append((f"{who} GET {path}", "", response.text))

    secret_ids = [*estate.foreign.object_ids(), FOREIGN_CODE]
    for label, _, body_text in member_bodies:
        leaked = [x for x in secret_ids if x in body_text]
        if leaked:
            problems.append(f"{label}: response contains the foreign project's {leaked}")
    assert not problems, "\n".join(problems)


def test_every_state_changing_route_requires_the_csrf_token(estate: Estate) -> None:
    api = estate.callers[SA]
    unsafe = sorted((m, p) for m, p in _app_routes() if m in ("POST", "PUT", "PATCH", "DELETE"))
    problems = []
    for method, template in unsafe:
        path = re.sub(r"\{seq\}", "0", template)
        path = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
        for header in ({}, {"X-CSRF-Token": "forged-token-value"}):
            response = getattr(api.client, method.lower())(
                path, **({} if method == "DELETE" else {"json": {}}), headers=header
            )
            code = (response.json().get("error") or {}).get("code") if response.content else None
            if (response.status_code, code) != (403, "CSRF_FAILED"):
                problems.append(
                    f"{method} {template} header={header}: {response.status_code} {code}"
                )
    assert not problems, "\n".join(problems)


def test_malformed_identifiers_are_rejected_not_crashing(estate: Estate) -> None:
    api = estate.callers[SA]
    problems = []
    for method, template in sorted(_app_routes()):
        if "{" not in template:
            continue
        path = re.sub(r"\{[^}]+\}", "not-an-id'%20OR%20'1'='1", template)
        kwargs: dict[str, Any] = {} if method in ("GET", "DELETE") else {"json": {}}
        status = getattr(api, method.lower())(path, **kwargs).status_code
        if status != 422:
            problems.append(f"{method} {template}: {status}")
    assert not problems, "\n".join(problems)


FORBIDDEN_KEY = re.compile(r"password|secret|token|totp|_enc$|_hash$|cipher", re.IGNORECASE)


def _keys(value: Any) -> Iterator[str]:
    """Keys that carry a value; a yes/no flag such as ``password_set`` reveals nothing secret."""
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(v, bool) and v is not None:
                yield str(k)
            yield from _keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v)


def test_no_response_carries_credentials_or_encrypted_fields(estate: Estate) -> None:
    found = []
    for who in CALLERS:
        api = estate.callers[who]
        for c in CASES:
            if c.method != "GET" or "export" in c.template:
                continue
            response = _send(api, c, estate, estate.own, who)
            if response.headers.get("content-type", "").startswith("application/json"):
                bad = {k for k in _keys(response.json()) if FORBIDDEN_KEY.search(k)}
                if bad:
                    found.append(f"{who} GET {c.template}: {sorted(bad)}")
        me = api.get("/api/v1/auth/me").json()
        if bad := {k for k in _keys(me) if FORBIDDEN_KEY.search(k)}:
            found.append(f"{who} GET /api/v1/auth/me: {sorted(bad)}")
    session_cookie = estate.callers[SA].client.cookies.get("ccp_session") or ""
    assert session_cookie
    for c in CASES:
        if c.method == "GET":
            text = _send(estate.callers[SA], c, estate, estate.own, SA).text
            if session_cookie in text:
                found.append(f"GET {c.template}: echoes the session token")
    assert not found, "\n".join(found)


def test_foreign_objects_cannot_be_pulled_in_through_a_request_body(estate: Estate) -> None:
    own, foreign = estate.own, estate.foreign
    pa, mo, sa = estate.callers[PA], estate.callers[MO], estate.callers[SA]
    attempts = {
        "PA links the foreign participant into OWN": pa.post(
            f"/api/v1/projects/{own.project}/participants/link",
            json={"participant_code": foreign.participant_code},
        ),
        "PA builds an OWN task from foreign participants": pa.post(
            "/api/v1/tasks",
            json={
                "project_id": own.project,
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": foreign.participant,
                "participant_b_id": own.participant,
            },
        ),
        "SA builds an OWN task from foreign participants": sa.post(
            "/api/v1/tasks",
            json={
                "project_id": own.project,
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": foreign.participant,
                "participant_b_id": own.participant,
            },
        ),
        "PA assigns the foreign project's moderator to an OWN task": pa.post(
            f"/api/v1/tasks/{own.task_open}/assign", json={"user_id": estate.foreign_moderator}
        ),
        "MO records consent on an OWN task for a foreign participant": mo.post(
            f"/api/v1/tasks/{own.task_open}/consent",
            json={"participant_id": foreign.participant, "status": "GIVEN", "method": "WRITTEN"},
        ),
    }
    accepted = {
        k: (r.status_code, r.text[:200]) for k, r in attempts.items() if r.status_code < 400
    }
    assert not accepted, accepted
