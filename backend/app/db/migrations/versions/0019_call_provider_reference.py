"""calls.provider_reference: the identifier TxContact's dialer returns for each request (D-101)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-13 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("provider_reference", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "provider_reference")
