"""query indexes for the busiest lists and the background jobs (owner's list, O5)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-10 08:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_tasks_project_created", "tasks", ["project_id", "created_at"])
    op.create_index("ix_audit_logs_project_created", "audit_logs", ["project_id", "created_at"])
    op.create_index(
        "ix_recordings_unfinished",
        "recordings",
        ["updated_at"],
        postgresql_where=sa.text("state IN ('UPLOADED', 'PROCESSING')"),
    )
    op.create_index(
        "ix_audio_assets_retention",
        "audio_assets",
        ["project_id", "kind", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_audio_assets_retention", table_name="audio_assets")
    op.drop_index("ix_recordings_unfinished", table_name="recordings")
    op.drop_index("ix_audit_logs_project_created", table_name="audit_logs")
    op.drop_index("ix_tasks_project_created", table_name="tasks")
