"""payments: rates per project, and who may see payments (D-137)

- payment_rates: one row per project with the rupees paid per approved minute to moderators and
  to participants (either may be unset), and who changed them last
- permission payments.manage, for the Super Admin and the Project Admin

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-18 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "payments.manage"
GRANTED_TO = ("SUPER_ADMIN", "PROJECT_ADMIN")


def upgrade() -> None:
    op.create_table(
        "payment_rates",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("moderator_rate", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("participant_rate", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
            "(moderator_rate IS NULL OR moderator_rate >= 0)"
            " AND (participant_rate IS NULL OR participant_rate >= 0)",
            name=op.f("ck_payment_rates_rates_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_payment_rates_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_payment_rates_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_rates")),
        sa.UniqueConstraint("project_id", name=op.f("uq_payment_rates_project_id")),
    )
    bind = op.get_bind()
    bind.execute(
        sa.text("INSERT INTO permissions (code, description) VALUES (:code, '')"),
        {"code": PERMISSION},
    )
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r, permissions p "
            "WHERE r.code = ANY(:roles) AND p.code = :code"
        ),
        {"roles": list(GRANTED_TO), "code": PERMISSION},
    )


def downgrade() -> None:
    bind = op.get_bind()
    removed = {"code": PERMISSION}
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = :code)"
        ),
        removed,
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = :code"), removed)
    op.drop_table("payment_rates")
