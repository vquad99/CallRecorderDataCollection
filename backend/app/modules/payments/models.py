"""A project's payment rates (D-137): rupees per approved minute, for moderators and for
participants."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_rates"
    __table_args__ = (
        CheckConstraint(
            "(moderator_rate IS NULL OR moderator_rate >= 0)"
            " AND (participant_rate IS NULL OR participant_rate >= 0)",
            name="rates_not_negative",
        ),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Null: no rate set yet; the minutes are shown without an amount.
    moderator_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    participant_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
