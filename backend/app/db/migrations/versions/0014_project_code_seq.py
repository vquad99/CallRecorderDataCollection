"""project codes are given by the platform: PRJ0001, PRJ0002, ... (D-083)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-11 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE project_code_seq START 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS project_code_seq")
