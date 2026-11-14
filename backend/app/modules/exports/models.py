"""Export bundles made in the background (EXP-009, EXP-010, D-105)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# QUEUED: asked for, not started. RUNNING: a worker is making the bundle. READY: the bundle is in
# storage and can be downloaded until it expires. FAILED: it could not be made (the reason is
# kept). EXPIRED: the bundle was removed from storage, by its age or by a person.
EXPORT_STATES = ("QUEUED", "RUNNING", "READY", "FAILED", "EXPIRED")
OPEN_STATES = ("QUEUED", "RUNNING")
BUNDLE_CONTENTS = ("audio", "metadata", "both")
SCOPES = ("approved", "finished")
TABLE_FORMATS = ("csv", "tsv")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ExportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint(_in("state", EXPORT_STATES), name="state_allowed"),
        CheckConstraint(_in("content", BUNDLE_CONTENTS), name="content_allowed"),
        CheckConstraint(_in("scope", SCOPES), name="scope_allowed"),
        CheckConstraint(_in("table_format", TABLE_FORMATS), name="table_format_allowed"),
        # The Export tab's question: a project's exports, newest first.
        Index("ix_export_jobs_project_created", "project_id", "created_at"),
        # The sweep's question: exports still to make, and bundles still in storage.
        Index(
            "ix_export_jobs_live",
            "state",
            postgresql_where=text("state IN ('QUEUED', 'RUNNING', 'READY')"),
        ),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    content: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    table_format: Mapped[str] = mapped_column(String(5), nullable=False)
    # What was chosen: mode, language, dates, originals, contact details (see bundle.Selection).
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recordings: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    files: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    storage_key: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
