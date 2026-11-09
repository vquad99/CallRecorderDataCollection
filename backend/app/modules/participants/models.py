"""Participants, their project links and consent records (PART-*)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CONSENT_STATUSES = ("GIVEN", "REFUSED", "WITHDRAWN")
CONSENT_METHODS = ("VERBAL_RECORDED", "VERBAL_NOTED", "WRITTEN", "DIGITAL")


class Participant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "participants"
    __table_args__ = (
        CheckConstraint("participant_code ~ '^P[0-9]{6,}$'", name="code_format"),
        Index("ix_participants_phone_hash", "phone_hash"),
    )
    participant_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    display_label: Mapped[str] = mapped_column(String(200), nullable=False)
    # Phone number encrypted with DATA_ENCRYPTION_KEY; the keyed hash finds duplicates without
    # decrypting; the two-digit hint lets masked views show "......12".
    phone_e164_enc: Mapped[str | None] = mapped_column(Text)
    phone_hash: Mapped[str | None] = mapped_column(String(64))
    phone_hint: Mapped[str | None] = mapped_column(String(2))
    language_code: Mapped[str] = mapped_column(String(35), nullable=False)
    dialect: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    deletion_reason: Mapped[str | None] = mapped_column(Text)


class ParticipantProjectLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "participant_project_links"
    __table_args__ = (
        UniqueConstraint("participant_id", "project_id", name="uq_participant_project_links_pair"),
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class ConsentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per consent event; the newest row for (participant, task) is the current status."""

    __tablename__ = "consent_records"
    __table_args__ = (
        CheckConstraint(f"status IN {CONSENT_STATUSES}", name="status_allowed"),
        CheckConstraint(f"method IN {CONSENT_METHODS}", name="method_allowed"),
        Index("ix_consent_records_participant_task", "participant_id", "task_id"),
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    captured_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
