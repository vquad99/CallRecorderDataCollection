"""export bundles made in the background (EXP-009, EXP-010, D-105)

- export_jobs: one row per export a person asked for, with what was chosen, its state, where the
  bundle is in storage, its checksum, when it expires and how often it was downloaded

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-14 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("table_format", sa.String(length=5), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("recordings", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("files", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("downloads", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('QUEUED', 'RUNNING', 'READY', 'FAILED', 'EXPIRED')",
            name=op.f("ck_export_jobs_state_allowed"),
        ),
        sa.CheckConstraint(
            "content IN ('audio', 'metadata', 'both')",
            name=op.f("ck_export_jobs_content_allowed"),
        ),
        sa.CheckConstraint(
            "scope IN ('approved', 'finished')", name=op.f("ck_export_jobs_scope_allowed")
        ),
        sa.CheckConstraint(
            "table_format IN ('csv', 'tsv')", name=op.f("ck_export_jobs_table_format_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_export_jobs_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_export_jobs_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_jobs")),
    )
    op.create_index(
        "ix_export_jobs_project_created", "export_jobs", ["project_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_export_jobs_live",
        "export_jobs",
        ["state"],
        unique=False,
        postgresql_where=sa.text("state IN ('QUEUED', 'RUNNING', 'READY')"),
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_live", table_name="export_jobs")
    op.drop_index("ix_export_jobs_project_created", table_name="export_jobs")
    op.drop_table("export_jobs")
