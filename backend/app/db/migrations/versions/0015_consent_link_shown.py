"""a personal link shown to staff is marked, and an answer on it names that person (D-088)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-11 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "participant_portal_links",
        sa.Column("shown_to_staff", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("consent_records", sa.Column("link_shown_to", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_consent_records_link_shown_to_users"),
        "consent_records",
        "users",
        ["link_shown_to"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_consent_records_link_shown_to_users"), "consent_records", type_="foreignkey"
    )
    op.drop_column("consent_records", "link_shown_to")
    op.drop_column("participant_portal_links", "shown_to_staff")
