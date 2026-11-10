"""staff review of a participant's own consent answer (D-073)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-11 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("consent_records", sa.Column("review_status", sa.String(20), nullable=True))
    op.add_column(
        "consent_records", sa.Column("review_note", sa.Text(), server_default="", nullable=False)
    )
    op.add_column("consent_records", sa.Column("reviewed_by", sa.Uuid(), nullable=True))
    op.add_column(
        "consent_records", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_consent_records_reviewed_by_users"),
        "consent_records",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Answers the participants already gave wait for a review.
    op.execute(
        "UPDATE consent_records SET review_status = 'PENDING' "
        "WHERE captured_by IS NULL AND task_id IS NULL AND status = 'GIVEN'"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_consent_records_reviewed_by_users"), "consent_records", type_="foreignkey"
    )
    op.drop_column("consent_records", "reviewed_at")
    op.drop_column("consent_records", "reviewed_by")
    op.drop_column("consent_records", "review_note")
    op.drop_column("consent_records", "review_status")
