"""Projects and their configuration (PROJ-*)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.audio_qc.checklist import DEFAULT_QC_CHECKLIST
from app.modules.participants.models import MAX_AGE, MIN_AGE
from app.modules.participants.speakers import FIELDS as SPEAKER_FIELDS
from app.modules.projects import delivery, targets
from app.modules.projects.moderation import DEFAULT_DEVICE_FIELDS, DEFAULT_RECORDING_REMINDERS
from app.modules.recordings.models import ASSET_KINDS

PROJECT_STATUSES = ("DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED")
RECORDING_MODES = ("TELEPHONY", "FACE_TO_FACE")
PHONE_POLICIES = ("ADMINS_ONLY", "ASSIGNED_MODERATOR")
# How participants give consent (D-144): ONLINE, on their personal page (D-067, D-129), or
# UPLOAD, a scanned signed consent form that staff upload.
CONSENT_MODES = ("ONLINE", "UPLOAD")
# Speaker rules (D-145): the first client's numbers are only what a new project starts with;
# each project sets its own on its Rules tab.
DEFAULT_SPEAKER_MIN_AGE, DEFAULT_SPEAKER_MAX_AGE = 20, 60
DEFAULT_REQUIRED_SPEAKER_DETAILS: tuple[str, ...] = tuple(SPEAKER_FIELDS)
# The QC checklist (D-146, audio_qc/checklist.py) a project starts with, as the database writes it.
DEFAULT_QC_CHECKLIST_SQL = (
    "'" + json.dumps(list(DEFAULT_QC_CHECKLIST)).replace("'", "''") + "'::jsonb"
)
# What a project asks of its moderators (D-147, projects/moderation.py), as the database writes it.
DEFAULT_DEVICE_FIELDS_SQL = "'" + json.dumps(list(DEFAULT_DEVICE_FIELDS)) + "'::jsonb"
DEFAULT_RECORDING_REMINDERS_SQL = (
    "'" + json.dumps(DEFAULT_RECORDING_REMINDERS).replace("'", "''") + "'::jsonb"
)


def _jsonb(value: object) -> str:
    return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(_in("status", PROJECT_STATUSES), name="status_allowed"),
        CheckConstraint(
            _in("phone_visibility_policy", PHONE_POLICIES), name="phone_policy_allowed"
        ),
        CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9_-]{1,39}$'", name="code_format"),
        CheckConstraint("allows_telephony OR allows_face_to_face", name="at_least_one_mode"),
        CheckConstraint(
            "target_telephony_hours_per_day >= 0 AND target_face_to_face_hours_per_day >= 0",
            name="targets_non_negative",
        ),
        CheckConstraint(
            "max_conversations_per_speaker IS NULL OR max_conversations_per_speaker >= 1",
            name="max_conversations_range",
        ),
        CheckConstraint(_in("consent_mode", CONSENT_MODES), name="consent_mode_allowed"),
        CheckConstraint(
            f"speaker_min_age BETWEEN {MIN_AGE} AND {MAX_AGE}"
            f" AND speaker_max_age BETWEEN {MIN_AGE} AND {MAX_AGE}"
            " AND speaker_min_age <= speaker_max_age",
            name="speaker_age_range",
        ),
        CheckConstraint(
            "jsonb_typeof(required_speaker_details) = 'array'", name="required_speaker_details_list"
        ),
        CheckConstraint("jsonb_typeof(qc_checklist) = 'array'", name="qc_checklist_list"),
        CheckConstraint("jsonb_typeof(device_fields) = 'array'", name="device_fields_list"),
        CheckConstraint(
            "jsonb_typeof(recording_reminders) = 'object'", name="recording_reminders_object"
        ),
        # D-148: audio and progress settings, and the targets.
        CheckConstraint(
            "pause_limit_seconds BETWEEN {} AND {}".format(*targets.PAUSE_LIMIT_RANGE),
            name="pause_limit_range",
        ),
        CheckConstraint(
            _in("progress_counts", targets.PROGRESS_COUNTS), name="progress_counts_allowed"
        ),
        CheckConstraint(
            "(target_hours IS NULL OR target_hours >= 0)"
            " AND (target_speakers IS NULL OR target_speakers >= 1)"
            " AND (target_conversations IS NULL OR target_conversations >= 1)",
            name="targets_positive",
        ),
        CheckConstraint("jsonb_typeof(target_age_bands) = 'array'", name="target_age_bands_list"),
        CheckConstraint("jsonb_typeof(target_gender) = 'object'", name="target_gender_object"),
        CheckConstraint("jsonb_typeof(target_modes) = 'object'", name="target_modes_object"),
        CheckConstraint("jsonb_typeof(target_districts) = 'array'", name="target_districts_list"),
        # D-149: how exports are laid out and named.
        CheckConstraint(
            _in("export_layout", delivery.EXPORT_LAYOUTS), name="export_layout_allowed"
        ),
        CheckConstraint(
            _in("speaker_id_style", delivery.SPEAKER_ID_STYLES), name="speaker_id_style_allowed"
        ),
        CheckConstraint(
            _in("conversation_id_style", delivery.CONVERSATION_ID_STYLES),
            name="conversation_id_style_allowed",
        ),
    )
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    allows_telephony: Mapped[bool] = mapped_column(nullable=False)
    allows_face_to_face: Mapped[bool] = mapped_column(nullable=False)
    target_telephony_hours_per_day: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, server_default="0"
    )
    target_face_to_face_hours_per_day: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, server_default="0"
    )
    phone_visibility_policy: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="ADMINS_ONLY"
    )
    consent_policy_version: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="1"
    )
    # The consent form participants read and answer on their personal page (D-067).
    consent_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ONLINE: the form is emailed and answered on the personal page; UPLOAD: staff upload each
    # participant's scanned signed form, which counts as consent (D-144, participants/consent.py).
    consent_mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ONLINE")
    # A QC pass approves the task: no admin review in this project (D-138).
    qc_final_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Task rules (D-143, tasks/pairing.py): at most this many conversations per speaker in the
    # project (empty = no limit), and each pair of speakers only once.
    max_conversations_per_speaker: Mapped[int | None] = mapped_column(Integer, server_default="3")
    unique_pairs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Speaker rules (D-145, participants/speakers.py): the ages this project takes, and the speaker
    # details a person needs before a task (keys of speakers.FIELDS, in its order).
    speaker_min_age: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_SPEAKER_MIN_AGE)
    )
    speaker_max_age: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_SPEAKER_MAX_AGE)
    )
    required_speaker_details: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(
            "'[" + ", ".join(f'"{k}"' for k in DEFAULT_REQUIRED_SPEAKER_DETAILS) + "]'::jsonb"
        ),
    )
    # The QC checklist (D-146, audio_qc/checklist.py): what the QC Executive answers Yes or No for
    # each recording, checked when saved. A decision keeps the questions as they read then.
    qc_checklist: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text(DEFAULT_QC_CHECKLIST_SQL)
    )
    # What the moderator fills for each speaker before a task goes to QC (D-147,
    # projects/moderation.DEVICE_FIELDS, in its order), and the reminders they read before
    # recording: {speaker_id, topics, avoid, face_to_face, telephony}.
    device_fields: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text(DEFAULT_DEVICE_FIELDS_SQL)
    )
    recording_reminders: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text(DEFAULT_RECORDING_REMINDERS_SQL)
    )
    # Audio and progress (D-148, projects/targets.py): a silent stretch inside the speech longer
    # than this is a long pause; whether long pauses ask QC for a listen; and what counts as
    # completed minutes (EFFECTIVE speech or the FULL length of approved conversations).
    pause_limit_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(targets.DEFAULT_PAUSE_LIMIT_SECONDS)
    )
    long_pauses_need_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    progress_counts: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=targets.DEFAULT_PROGRESS_COUNTS
    )
    # Targets (D-148), shown on the Progress tab: empty = no target. Age bands
    # [{from, to, percent}], gender {MALE, FEMALE} and modes {FACE_TO_FACE, TELEPHONY} percents,
    # districts [{state, district}] with an equal share each.
    target_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    target_speakers: Mapped[int | None] = mapped_column(
        Integer, server_default=str(targets.DEFAULT_TARGET_SPEAKERS)
    )
    target_conversations: Mapped[int | None] = mapped_column(
        Integer, server_default=str(targets.DEFAULT_TARGET_CONVERSATIONS)
    )
    target_age_bands: Mapped[list[dict[str, int]]] = mapped_column(
        JSONB, nullable=False, server_default=text(_jsonb(list(targets.DEFAULT_TARGET_AGE_BANDS)))
    )
    target_gender: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default=text(_jsonb(targets.DEFAULT_TARGET_GENDER))
    )
    target_modes: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default=text(_jsonb(targets.DEFAULT_TARGET_MODES))
    )
    target_districts: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # How exports are laid out and named (D-149, projects/delivery.py): the client's delivery
    # format (CLIENT) or the platform's own (PLATFORM); speaker and conversation IDs as numbers
    # (001, CON045) or as codes; and the audio file name, made of tokens.
    export_layout: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=delivery.DEFAULT_EXPORT_LAYOUT
    )
    speaker_id_style: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=delivery.DEFAULT_SPEAKER_ID_STYLE
    )
    conversation_id_style: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=delivery.DEFAULT_CONVERSATION_ID_STYLE
    )
    audio_name_pattern: Mapped[str] = mapped_column(
        String(delivery.MAX_AUDIO_NAME_PATTERN),
        nullable=False,
        server_default=delivery.DEFAULT_AUDIO_NAME_PATTERN,
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    # Loaded when a page reads them, not with every project lookup (O5).
    languages: Mapped[list[ProjectLanguage]] = relationship(
        lazy="select", cascade="all, delete-orphan", order_by="ProjectLanguage.language_code"
    )
    audio_rules: Mapped[list[ProjectAudioRule]] = relationship(
        lazy="select", cascade="all, delete-orphan", order_by="ProjectAudioRule.mode"
    )
    retention_rules: Mapped[list[ProjectRetentionRule]] = relationship(
        lazy="select", cascade="all, delete-orphan", order_by="ProjectRetentionRule.asset_kind"
    )


class ProjectLanguage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_languages"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "language_code", "dialect", name="uq_project_languages_entry"
        ),
        CheckConstraint(
            "language_code ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'", name="language_code_format"
        ),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language_code: Mapped[str] = mapped_column(String(35), nullable=False)
    dialect: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")


class ProjectAudioRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_audio_rules"
    __table_args__ = (
        UniqueConstraint("project_id", "mode", name="uq_project_audio_rules_mode"),
        CheckConstraint(_in("mode", RECORDING_MODES), name="mode_allowed"),
        CheckConstraint("channels IN (1, 2)", name="channels_allowed"),
        CheckConstraint("bit_depth IN (16, 24, 32)", name="bit_depth_allowed"),
        CheckConstraint("sample_rate BETWEEN 8000 AND 192000", name="sample_rate_range"),
        CheckConstraint(
            "max_silence_pct BETWEEN 0 AND 100"
            " AND (max_clipping_pct IS NULL OR max_clipping_pct BETWEEN 0 AND 100)",
            name="pct_range",
        ),
        CheckConstraint(
            "min_duration_seconds >= 0 AND (max_duration_seconds IS NULL"
            " OR max_duration_seconds >= min_duration_seconds)",
            name="duration_range",
        ),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    bit_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, nullable=False)
    max_silence_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    # Null = no clipping limit set for this project yet (no invented default, runbook J1).
    max_clipping_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    min_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_duration_seconds: Mapped[int | None] = mapped_column(Integer)


class ProjectRetentionRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_retention_rules"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_kind", name="uq_project_retention_rules_kind"),
        CheckConstraint(_in("asset_kind", ASSET_KINDS), name="asset_kind_allowed"),
        CheckConstraint("retain_days BETWEEN 1 AND 36500", name="retain_days_range"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    retain_days: Mapped[int] = mapped_column(Integer, nullable=False)


class ProjectMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_project_memberships_pair"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
