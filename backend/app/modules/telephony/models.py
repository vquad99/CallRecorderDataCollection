"""Phone calls and their event history (TEL-018, TEL-027, D-101)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# DIALLING: the provider took the request to ring participant A; the moderator is on the call.
# WAITING_FOR_RECORDING: the moderator closed the call; the platform is looking for its recording.
# NEEDS_MATCH: the platform could not tell which of the provider's calls is this one (or found none
#   in time); a person picks it, or asks for another search.
# FETCH_FAILED: the recording was found but could not be downloaded or read; a person retries.
# RECORDED: the recording is stored and the task moved to Recorded.
# DIAL_FAILED / CANCELLED: no recording is expected.
CALL_STATES = (
    "DIALLING",
    "DIAL_FAILED",
    "CANCELLED",
    "WAITING_FOR_RECORDING",
    "NEEDS_MATCH",
    "FETCH_FAILED",
    "RECORDED",
)
OPEN_STATES = ("DIALLING", "WAITING_FOR_RECORDING")
CANCEL_REASONS = ("NO_ANSWER", "WRONG_NUMBER", "CALL_DROPPED", "CONSENT_REFUSED", "OTHER")
EVENT_KINDS = (
    "DIAL_REQUESTED",
    "DIAL_ACCEPTED",
    "DIAL_FAILED",
    "CALL_CLOSED",
    "CALL_CANCELLED",
    "SEARCHING",
    "MATCHED",
    "MATCH_CHOSEN",
    "NEEDS_MATCH",
    "SEARCH_ERROR",
    "DOWNLOADED",
    "FETCH_ERROR",
    "FETCH_FAILED",
    "RETRY_REQUESTED",
    "RECORDED",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Call(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calls"
    __table_args__ = (
        CheckConstraint(_in("state", CALL_STATES), name="state_allowed"),
        CheckConstraint(
            f"cancel_reason IS NULL OR {_in('cancel_reason', CANCEL_REASONS)}",
            name="cancel_reason_allowed",
        ),
        # One live call per task: a second "Start call" cannot ring a participant twice.
        Index(
            "uq_calls_one_open_per_task",
            "task_id",
            unique=True,
            postgresql_where=text("state IN ('DIALLING', 'WAITING_FOR_RECORDING')"),
        ),
        # A provider recording belongs to one call only.
        Index(
            "uq_calls_provider_session",
            "provider",
            "provider_session_id",
            unique=True,
            postgresql_where=text("provider_session_id IS NOT NULL"),
        ),
        # The fetch sweep (every minute) reads only calls waiting for their recording.
        Index(
            "ix_calls_waiting",
            "next_fetch_at",
            postgresql_where=text("state = 'WAITING_FOR_RECORDING'"),
        ),
        Index("ix_calls_task_created", "task_id", "created_at"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    moderator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(40), nullable=False)
    # Last two digits of the number rung, for people to recognise it; never the full number.
    phone_hint: Mapped[str] = mapped_column(String(2), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    dialled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    provider_session_id: Mapped[str | None] = mapped_column(String(100))
    provider_file: Mapped[str | None] = mapped_column(String(300))
    # Calls the platform could not choose between (JSON list of safe fields; no phone numbers).
    candidates: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    fetch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(50))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT")
    )


class CallEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "call_events"
    __table_args__ = (
        CheckConstraint(_in("kind", EVENT_KINDS), name="kind_allowed"),
        Index("ix_call_events_call_created", "call_id", "created_at"),
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    detail: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
