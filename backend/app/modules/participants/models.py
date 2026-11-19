"""Participants, their project links and consent records (PART-*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, get_args

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ColumnElement,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    and_,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# WITHDRAWN only on answers given before D-129 (nobody can withdraw since).
ConsentStatus = Literal["GIVEN", "REFUSED", "WITHDRAWN"]
# Everything but DIGITAL (the participant's own answer) was noted by a moderator before D-129.
ConsentMethod = Literal["VERBAL_RECORDED", "VERBAL_NOTED", "WRITTEN", "DIGITAL"]
CONSENT_STATUSES: tuple[str, ...] = get_args(ConsentStatus)
CONSENT_METHODS: tuple[str, ...] = get_args(ConsentMethod)


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
    # Optional email address, encrypted; used to send the participant their personal link.
    email_enc: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str] = mapped_column(String(35), nullable=False)
    dialect: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    # Where the participant lives, free text; the dashboard filters by it (D-121).
    district: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
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
    """One row per consent event. What the rows mean is decided in `consent.py` only: the newest
    own answer of a participant in a project is their consent there (D-129)."""

    __tablename__ = "consent_records"
    __table_args__ = (
        CheckConstraint(f"status IN {CONSENT_STATUSES}", name="status_allowed"),
        CheckConstraint(f"method IN {CONSENT_METHODS}", name="method_allowed"),
        Index("ix_consent_records_participant_task", "participant_id", "task_id"),
        # A task's own consent records (task page, delete check), without the participant.
        Index("ix_consent_records_task", "task_id"),
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
    # The moderator who noted it for a task (before D-129); empty when the participant answered
    # the consent form themselves on their personal page (method DIGITAL, D-067).
    captured_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    # Set when the participant answered on a link that was shown to this staff member, who could
    # have typed the answer: the consent record says so (D-088).
    link_shown_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # The consent form text the participant answered (their own answers only, D-068), kept so a
    # later change of the project's form cannot change what they agreed to.
    form_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # The staff review of an own "agree" answer that existed from D-073 to D-129, kept as history:
    # APPROVED or REJECTED (with a note) on older answers, empty on answers since. A REJECTED
    # answer does not count as agreed (consent.word); nothing else reads these columns.
    review_status: Mapped[str | None] = mapped_column(String(20))
    review_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @hybrid_property
    def is_own_answer(self) -> bool:
        """The participant's own answer on the project's consent form (D-067): not noted for a
        task, not recorded by staff."""
        return self.task_id is None and self.captured_by is None

    @is_own_answer.inplace.expression
    @classmethod
    def _is_own_answer_expression(cls) -> ColumnElement[bool]:
        return and_(cls.task_id.is_(None), cls.captured_by.is_(None))


class ParticipantPortalLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A participant's personal page link for one project (D-067). Only the hash of the secret is
    stored; the link itself is shown once, to the staff member who creates it."""

    __tablename__ = "participant_portal_links"
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # True when the link was shown to the staff member (copy and hand over), false when only
    # emailed to the participant: an answer on a shown link may have been typed by staff (D-088).
    # Links are only emailed now; older rows may still be true.
    shown_to_staff: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
