"""security hardening: last accepted authenticator time step

A one-time code is accepted once only (RFC 6238 section 5.2; DECISIONS.md D-050).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_last_step")
