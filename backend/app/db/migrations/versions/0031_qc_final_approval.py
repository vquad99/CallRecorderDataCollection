"""projects: "QC pass is the final approval" (D-138)

- projects.qc_final_approval, off for every project: a QC pass still goes to the project admin's
  review until a project turns it on. Tasks waiting for admin review are not moved.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-18 18:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "qc_final_approval", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "qc_final_approval")
