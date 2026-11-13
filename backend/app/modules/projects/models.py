"""Projects and their configuration (PROJ-*)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PROJECT_STATUSES = ("DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED")
RECORDING_MODES = ("TELEPHONY", "FACE_TO_FACE")
PHONE_POLICIES = ("ADMINS_ONLY", "ASSIGNED_MODERATOR")
ASSET_KINDS = (
    "PROVIDER_ORIGINAL_TRACK",
    "PROVIDER_ORIGINAL_MIXED",
    "TELEPHONY_FINAL_STEREO",
    "CONSENT_RECORDING",
    "BROWSER_ORIGINAL",
    "FTF_DERIVED_PCM",
    "TELEPHONY_DERIVED_PCM",
    "TRANSCRIPT_FILE",
    "EXPORT_PACKAGE",
)


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
