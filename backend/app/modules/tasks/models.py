"""Recording tasks, assignments, status history and comments (TASK-*)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

TASK_STATUSES = (
    "DRAFT",
    "ASSIGNED",
    "IN_PROGRESS",
    "RECORDED",
    "AUDIO_QC",
    "TRANSCRIPTION_PENDING",
    "TRANSCRIPTION_IN_PROGRESS",
    "TRANSCRIPT_QC",
    "APPROVED",
    "REJECTED",
    "RETURNED",
    "CANCELLED",
    "ON_HOLD",
)
PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")
ASSIGNMENT_ROLES = ("MODERATOR", "TRANSCRIBER", "QC_EXECUTIVE")


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(f"status IN {TASK_STATUSES}", name="status_allowed"),
        CheckConstraint(
            f"held_from IS NULL OR held_from IN {TASK_STATUSES}", name="held_from_allowed"
        ),
        CheckConstraint(f"priority IN {PRIORITIES}", name="priority_allowed"),
        CheckConstraint("recording_mode IN ('TELEPHONY', 'FACE_TO_FACE')", name="mode_allowed"),
        CheckConstraint("participant_a_id <> participant_b_id", name="two_different_participants"),
        CheckConstraint("task_code ~ '^T[0-9]{6,}$'", name="code_format"),
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_due_at", "due_at"),
    )
    task_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    recording_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    held_from: Mapped[str | None] = mapped_column(String(30))
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default="NORMAL")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    participant_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False
    )
    participant_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False
    )
    reason_code: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class TaskAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_assignments"
    __table_args__ = (
        CheckConstraint(f"role_code IN {ASSIGNMENT_ROLES}", name="role_allowed"),
        Index(
            "uq_task_assignments_one_active",
            "task_id",
            "role_code",
            unique=True,
            postgresql_where=text("active"),
        ),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role_code: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskStatusHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_status_history"
    __table_args__ = (Index("ix_task_status_history_task_created", "task_id", "created_at"),)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason_code: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class TaskComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_comments"
    __table_args__ = (Index("ix_task_comments_task_created", "task_id", "created_at"),)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
