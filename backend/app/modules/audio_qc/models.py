"""Audio quality control records (AQC-001..009, D-079).

One result per check run: the automatic check right after a recording is ready (no reviewer), and
each QC Executive decision (with reviewer). The automatic result lists every check it made in
audio_qc_checks, with what was measured and the limit it was held to.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

OUTCOMES = ("PASS", "NEEDS_REVIEW", "FAIL", "RETURN")
CHECK_STATES = ("PASS", "FAIL", "REVIEW", "INFO", "NOT_APPLICABLE")


class AudioQcResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audio_qc_results"
    __table_args__ = (CheckConstraint(f"outcome IN {OUTCOMES}", name="outcome_allowed"),)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="RESTRICT")
    )
    automated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    # What the automatic check measured on the delivery file, kept with the result.
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    silence_pct: Mapped[float | None] = mapped_column(Float)
    clip_pct: Mapped[float | None] = mapped_column(Float)
    peak_dbfs: Mapped[float | None] = mapped_column(Float)
    rms_dbfs: Mapped[float | None] = mapped_column(Float)
    dynamic_range_db: Mapped[float | None] = mapped_column(Float)
    duplicate_of_recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT")
    )
    checks: Mapped[list[AudioQcCheck]] = relationship(
        cascade="all, delete-orphan", order_by="AudioQcCheck.position", lazy="selectin"
    )


class AudioQcCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audio_qc_checks"
    __table_args__ = (CheckConstraint(f"state IN {CHECK_STATES}", name="state_allowed"),)
    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_qc_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    measured: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    expected: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
