"""a session can view the app as another user, read-only (D-100)

The Super Admin's "View as": while sessions.view_as_user_id is set, that session sees the app with
the other user's roles and projects, and every change is refused.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-13 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("view_as_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_sessions_view_as_user_id_users"),
        "sessions",
        "users",
        ["view_as_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_sessions_view_as_user_id_users"), "sessions", type_="foreignkey")
    op.drop_column("sessions", "view_as_user_id")
