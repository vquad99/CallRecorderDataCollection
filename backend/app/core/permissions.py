"""Central role and permission registry (ROLE-009).

This module is the single source the database is seeded from (migration 0002) and that tests compare
against. Permission checks at runtime read the database (role_permissions), never this mapping.
Scope ("own projects", "assigned items") is enforced in each service on top of the permission.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    PROJECT_ADMIN = "PROJECT_ADMIN"
    MODERATOR = "MODERATOR"
    TRANSCRIBER = "TRANSCRIBER"
    QC_EXECUTIVE = "QC_EXECUTIVE"
    CLIENT_VIEWER = "CLIENT_VIEWER"


class Perm(StrEnum):
    SETTINGS_MANAGE = "settings.manage"
    USERS_MANAGE = "users.manage"
    AUDIT_VIEW = "audit.view"
    WEBHOOKS_VIEW = "webhooks.view"
    PROJECTS_CREATE = "projects.create"
    PROJECTS_VIEW = "projects.view"
    PROJECTS_MANAGE = "projects.manage"
    PROJECTS_MEMBERS = "projects.members"
    PARTICIPANTS_VIEW = "participants.view"
    PARTICIPANTS_MANAGE = "participants.manage"
    PARTICIPANTS_CONTACT = "participants.contact"
    PARTICIPANTS_EXPORT = "participants.export"
    CONSENT_CAPTURE = "consent.capture"
    CONSENT_VIEW = "consent.view"
    TASKS_VIEW = "tasks.view"
    TASKS_ASSIGN = "tasks.assign"
    CALLS_START = "calls.start"
    CALLS_END = "calls.end"
    RECORDINGS_CREATE = "recordings.create"
    RECORDINGS_VIEW = "recordings.view"
    RECORDINGS_DOWNLOAD = "recordings.download"
    AUDIO_QC_REVIEW = "audio_qc.review"
    TRANSCRIPTS_EDIT = "transcripts.edit"
    TRANSCRIPTS_REVIEW = "transcripts.review"
    TRANSCRIPTS_REOPEN = "transcripts.reopen"
    ASR_VIEW = "asr.view"
    ASR_MANAGE = "asr.manage"
    EXPORTS_CREATE = "exports.create"
    DASHBOARD_VIEW = "dashboard.view"
    NOTES_VIEW = "notes.view"
    ASSETS_DELETE = "assets.delete"


ROLE_LABELS: dict[Role, str] = {
    Role.SUPER_ADMIN: "Super Admin",
    Role.PROJECT_ADMIN: "Project Admin",
    Role.MODERATOR: "Moderator",
    Role.TRANSCRIBER: "Transcriber",
    Role.QC_EXECUTIVE: "QC Executive",
    Role.CLIENT_VIEWER: "Client Viewer",
}

# Mirrors docs/ARCHITECTURE.md section 5 (checked by tests/test_permissions.py). Super Admin holds
# every permission except starting calls and recording face-to-face, which belong to the assigned
# moderator only.
ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.SUPER_ADMIN: frozenset(Perm) - {Perm.CALLS_START, Perm.RECORDINGS_CREATE},
    Role.PROJECT_ADMIN: frozenset(
        {
            Perm.PROJECTS_VIEW,
            Perm.PROJECTS_MANAGE,
            Perm.PROJECTS_MEMBERS,
            Perm.PARTICIPANTS_VIEW,
            Perm.PARTICIPANTS_MANAGE,
            Perm.PARTICIPANTS_CONTACT,
            Perm.CONSENT_VIEW,
            Perm.TASKS_VIEW,
            Perm.TASKS_ASSIGN,
            Perm.CALLS_END,
            Perm.RECORDINGS_VIEW,
            Perm.RECORDINGS_DOWNLOAD,
            Perm.TRANSCRIPTS_REOPEN,
            Perm.EXPORTS_CREATE,
            Perm.DASHBOARD_VIEW,
            Perm.AUDIT_VIEW,
            Perm.NOTES_VIEW,
            Perm.ASSETS_DELETE,
        }
    ),
    Role.MODERATOR: frozenset(
        {
            Perm.PROJECTS_VIEW,
            Perm.PARTICIPANTS_VIEW,
            Perm.PARTICIPANTS_CONTACT,
            Perm.CONSENT_CAPTURE,
            Perm.CONSENT_VIEW,
            Perm.TASKS_VIEW,
            Perm.CALLS_START,
            Perm.CALLS_END,
            Perm.RECORDINGS_CREATE,
            Perm.RECORDINGS_VIEW,
            Perm.DASHBOARD_VIEW,
            Perm.NOTES_VIEW,
        }
    ),
    Role.TRANSCRIBER: frozenset(
        {
            Perm.PROJECTS_VIEW,
            Perm.PARTICIPANTS_VIEW,
            Perm.TASKS_VIEW,
            Perm.RECORDINGS_VIEW,
            Perm.TRANSCRIPTS_EDIT,
            Perm.DASHBOARD_VIEW,
            Perm.NOTES_VIEW,
        }
    ),
    Role.QC_EXECUTIVE: frozenset(
        {
            Perm.PROJECTS_VIEW,
            Perm.PARTICIPANTS_VIEW,
            Perm.TASKS_VIEW,
            Perm.RECORDINGS_VIEW,
            Perm.AUDIO_QC_REVIEW,
            Perm.TRANSCRIPTS_REVIEW,
            Perm.DASHBOARD_VIEW,
            Perm.NOTES_VIEW,
        }
    ),
    Role.CLIENT_VIEWER: frozenset(
        {
            Perm.PROJECTS_VIEW,
            Perm.PARTICIPANTS_VIEW,
            Perm.RECORDINGS_VIEW,
            Perm.RECORDINGS_DOWNLOAD,
            Perm.EXPORTS_CREATE,
            Perm.DASHBOARD_VIEW,
        }
    ),
}
