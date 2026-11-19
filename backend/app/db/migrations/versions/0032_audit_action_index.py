"""audit_logs: an index on action for the audit viewer's filter

- ix_audit_logs_action with text_pattern_ops, so both action = 'x' and action LIKE 'x.%' use it
  whatever the database's collation

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-19 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_action",
        "audit_logs",
        ["action"],
        postgresql_ops={"action": "text_pattern_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
