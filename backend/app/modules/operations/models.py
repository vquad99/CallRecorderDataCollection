"""What the platform found wrong with itself and told the people who run it (OPS-006, D-109)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OperationAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One kind of problem (a row per code). `active` while the problem is there; the row stays
    afterwards as the record of when it was seen and when it went away."""

    __tablename__ = "operation_alerts"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When an email last named this problem; empty while nobody has been told.
    last_emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
