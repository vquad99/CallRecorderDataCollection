"""participants may have an email address, encrypted (consent link by email)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-10 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("participants", sa.Column("email_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("participants", "email_enc")
