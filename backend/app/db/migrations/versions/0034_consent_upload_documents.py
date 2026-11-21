"""projects: consent online or by upload; participant_documents (D-144)

- projects.consent_mode: ONLINE (every existing project: the participant agrees on their personal
  page, as before) or UPLOAD (staff upload a scanned signed consent form).
- participant_documents: uploaded files - a participant's signed consent form for one project and
  their address proof (one for the person). A new upload replaces the current one; the older row
  stays with replaced_at. One current document per kind (per project for consent forms).

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-21 18:00:00
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "participant_documents"
CURRENT = "replaced_at IS NULL AND removed_at IS NULL"


def _stamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("consent_mode", sa.String(10), server_default="ONLINE", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_projects_consent_mode_allowed"), "projects", "consent_mode IN ('ONLINE', 'UPLOAD')"
    )
    op.create_table(
        TABLE,
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        _stamp("uploaded_at"),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.CheckConstraint(
            "kind IN ('CONSENT_FORM', 'ADDRESS_PROOF')", name=op.f(f"ck_{TABLE}_kind_allowed")
        ),
        sa.CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name=op.f(f"ck_{TABLE}_content_type_allowed"),
        ),
        sa.CheckConstraint(
            "(kind = 'CONSENT_FORM') = (project_id IS NOT NULL)",
            name=op.f(f"ck_{TABLE}_project_for_consent_form"),
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f(f"ck_{TABLE}_size_positive")),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f(f"fk_{TABLE}_participant_id_participants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f(f"fk_{TABLE}_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f(f"fk_{TABLE}_uploaded_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by"],
            ["users.id"],
            name=op.f(f"fk_{TABLE}_replaced_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint("storage_key", name=op.f(f"uq_{TABLE}_storage_key")),
    )
    op.create_index(
        "uq_participant_documents_current_consent_form",
        TABLE,
        ["participant_id", "project_id"],
        unique=True,
        postgresql_where=sa.text(f"kind = 'CONSENT_FORM' AND {CURRENT}"),
    )
    op.create_index(
        "uq_participant_documents_current_address_proof",
        TABLE,
        ["participant_id"],
        unique=True,
        postgresql_where=sa.text(f"kind = 'ADDRESS_PROOF' AND {CURRENT}"),
    )
    op.create_index("ix_participant_documents_participant_kind", TABLE, ["participant_id", "kind"])


def downgrade() -> None:
    op.drop_table(TABLE)
    op.drop_constraint(op.f("ck_projects_consent_mode_allowed"), "projects", type_="check")
    op.drop_column("projects", "consent_mode")
