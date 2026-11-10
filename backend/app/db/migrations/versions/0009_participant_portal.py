"""participant personal page: links, consent form text, self-recorded consent (D-067)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-10 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("consent_text", sa.Text(), server_default="", nullable=False)
    )
    op.alter_column("consent_records", "captured_by", existing_type=sa.Uuid(), nullable=True)
    op.create_table(
        "participant_portal_links",
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_participant_portal_links_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_participant_portal_links_participant_id_participants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_participant_portal_links_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participant_portal_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_participant_portal_links_token_hash")),
    )
    op.create_index(
        op.f("ix_participant_portal_links_participant_id"),
        "participant_portal_links",
        ["participant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_participant_portal_links_participant_id"),
        table_name="participant_portal_links",
    )
    op.drop_table("participant_portal_links")
    # Self-recorded consent has no staff member; it cannot be kept under the old rule.
    op.execute("DELETE FROM consent_records WHERE captured_by IS NULL")
    op.alter_column("consent_records", "captured_by", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("projects", "consent_text")
