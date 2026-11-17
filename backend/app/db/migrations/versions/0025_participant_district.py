"""participants.district: where the participant lives, for the dashboard filter (D-121)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-17 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("district", sa.String(100), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("participants", "district")
