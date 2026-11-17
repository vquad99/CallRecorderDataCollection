"""Recordings, uploaded chunks, audio assets and processing history (FTF-*, STOR-*, AUDIO-017)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Subquery,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

RECORDING_STATES = (
    "RECORDING",
    "INTERRUPTED",
    "UPLOADED",
    "PROCESSING",
    "READY",
    "FAILED",
    "DISCARDED",
)


class Recording(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recordings"
    __table_args__ = (
        CheckConstraint(f"state IN {RECORDING_STATES}", name="state_allowed"),
        CheckConstraint("mode IN ('TELEPHONY', 'FACE_TO_FACE')", name="mode_allowed"),
        Index(
            "uq_recordings_one_open_per_task",
            "task_id",
            unique=True,
            postgresql_where=text("state IN ('RECORDING', 'INTERRUPTED')"),
        ),
        # The recovery sweep (every minute) reads only unfinished recordings.
        Index(
            "ix_recordings_unfinished",
            "updated_at",
            postgresql_where=text("state IN ('UPLOADED', 'PROCESSING')"),
        ),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    native_sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    # channel_count: channels the capture delivered (all kept in the original).
    # device_channel_count: what the browser reported for the microphone.
    # channel_handling: how the derived mono file is made, set by the server from channel_count
    # (D-041, D-048).
    channel_count: Mapped[int] = mapped_column(Integer, nullable=False)
    device_channel_count: Mapped[int | None] = mapped_column(Integer)
    channel_handling: Mapped[str] = mapped_column(String(100), nullable=False)
    echo_cancellation: Mapped[bool | None] = mapped_column(Boolean)
    noise_suppression: Mapped[bool | None] = mapped_column(Boolean)
    auto_gain_control: Mapped[bool | None] = mapped_column(Boolean)
    device_label: Mapped[str] = mapped_column(String(300), nullable=False, server_default="")
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    chunks_received: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Sample frames per channel (one frame = one float32 sample for each channel).
    frames_received: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    interrupted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    interruption_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)


class RecordingChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recording_chunks"
    __table_args__ = (UniqueConstraint("recording_id", "seq", name="uq_recording_chunks_seq"),)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    object_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


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
# The file each mode delivers: face-to-face (the recording itself, D-123), and telephony (16 kHz,
# D-101).
FTF_DELIVERY_KIND = "FTF_DERIVED_PCM"
TELEPHONY_DELIVERY_KIND = "TELEPHONY_DERIVED_PCM"
DELIVERY_KINDS = (FTF_DELIVERY_KIND, TELEPHONY_DELIVERY_KIND)
# Files whose length is the conversation's length: the delivery files, and the stereo phone file
# of the first telephony design.
FINAL_KINDS = (*DELIVERY_KINDS, "TELEPHONY_FINAL_STEREO")
# What was recorded before any processing.
ORIGINAL_KINDS = ("BROWSER_ORIGINAL", "PROVIDER_ORIGINAL_MIXED", "PROVIDER_ORIGINAL_TRACK")


class AudioAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        CheckConstraint(f"kind IN {ASSET_KINDS}", name="kind_allowed"),
        UniqueConstraint("recording_id", "kind", "version", name="uq_audio_assets_version"),
        Index("ix_audio_assets_sha256", "sha256"),
        # The retention job's question: live files of one kind in one project, oldest first.
        Index(
            "ix_audio_assets_retention",
            "project_id",
            "kind",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="RESTRICT")
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)
    container: Mapped[str] = mapped_column(String(20), nullable=False)
    codec: Mapped[str] = mapped_column(String(30), nullable=False)
    sample_format: Mapped[str] = mapped_column(String(10), nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    bit_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    peak_dbfs: Mapped[float | None] = mapped_column(Float)
    rms_dbfs: Mapped[float | None] = mapped_column(Float)
    clip_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    clip_pct: Mapped[float] = mapped_column(Float, nullable=False)
    silence_pct: Mapped[float] = mapped_column(Float, nullable=False)
    dynamic_range_db: Mapped[float | None] = mapped_column(Float)
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetProcessingStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_processing_steps"
    __table_args__ = (UniqueConstraint("asset_id", "seq", name="uq_asset_processing_steps_seq"),)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[str] = mapped_column(Text, nullable=False)
    input_sha256: Mapped[str | None] = mapped_column(String(64))
    output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


def final_length_subquery() -> Subquery:
    """(recording_id, ms): each recording's length, from its final file. Lengths stay counted
    after retention deletes the file."""
    return (
        select(AudioAsset.recording_id, func.max(AudioAsset.duration_ms).label("ms"))
        .where(AudioAsset.kind.in_(FINAL_KINDS))
        .group_by(AudioAsset.recording_id)
        .subquery()
    )


def newest_ready_subquery() -> Subquery:
    """(recording_id, task_id, rank): finished recordings, ranked newest first within each task;
    rank 1 is the one a task delivers (re-recorded tasks count once)."""
    return (
        select(
            Recording.id.label("recording_id"),
            Recording.task_id,
            func.row_number()
            .over(partition_by=Recording.task_id, order_by=Recording.started_at.desc())
            .label("rank"),
        )
        .where(Recording.state == "READY")
        .subquery()
    )
