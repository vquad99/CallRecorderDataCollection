"""system_settings: editable platform configuration such as capacity targets (CAP-001, DB-001)."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

VALUE_TYPES = ("text", "int", "bool")


class SystemSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint("value_type IN ('text', 'int', 'bool')", name="value_type_allowed"),
    )

    key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_int: Mapped[int | None] = mapped_column(BigInteger)
    # References users.id once the users table exists (Phase 2 migration adds the foreign key).
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
