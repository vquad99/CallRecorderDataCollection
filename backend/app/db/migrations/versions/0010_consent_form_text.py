"""consent records keep the form text the participant answered (D-068)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-10 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "consent_records", sa.Column("form_text", sa.Text(), server_default="", nullable=False)
    )
    # Answers given before this column existed: the project's current form is the best record.
    op.execute(
        "UPDATE consent_records c SET form_text = p.consent_text FROM projects p "
        "WHERE p.id = c.project_id AND c.captured_by IS NULL AND c.task_id IS NULL"
    )


def downgrade() -> None:
    op.drop_column("consent_records", "form_text")
