"""Consent accepted at once; nobody notes consent for a task any more (D-129)

The owner's decision (2026-11-17): a participant's "I agree" on their consent form counts at once,
with no staff review, and moderators no longer note consent on a task. Answers still waiting for a
review become accepted (APPROVED). Answers staff had sent back (REJECTED) keep that mark: they do
not count as agreed until the participant answers again. The `consent.capture` permission, which
only allowed noting consent on a task, is removed. Consent noted before stays as history.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-17 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REMOVED_PERMISSION = "consent.capture"
# Grants as they were before this revision, restored on downgrade.
_OLD_GRANTS = ("SUPER_ADMIN", "MODERATOR")


def upgrade() -> None:
    op.execute(
        "UPDATE consent_records SET review_status = 'APPROVED', updated_at = now() "
        "WHERE review_status = 'PENDING' AND task_id IS NULL AND captured_by IS NULL"
    )
    bind = op.get_bind()
    removed = {"code": REMOVED_PERMISSION}
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = :code)"
        ),
        removed,
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = :code"), removed)


def downgrade() -> None:
    # The answers accepted here stay accepted: there is no telling which ones waited for review.
    bind = op.get_bind()
    bind.execute(
        sa.text("INSERT INTO permissions (code, description) VALUES (:code, '')"),
        {"code": REMOVED_PERMISSION},
    )
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r, permissions p "
            "WHERE r.code = ANY(:roles) AND p.code = :code"
        ),
        {"roles": list(_OLD_GRANTS), "code": REMOVED_PERMISSION},
    )
