"""The phone seat's password, encrypted (D-130)

A moderator's TxContact seat comes with a password: their sign-in to TxContact's Chirp app. The
Super Admin keeps it with the seat; it is stored encrypted with DATA_ENCRYPTION_KEY, like a
participant's phone number, and shown only to a Super Admin or the moderator, each time audited.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-18 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telephony_password_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "telephony_password_enc")
