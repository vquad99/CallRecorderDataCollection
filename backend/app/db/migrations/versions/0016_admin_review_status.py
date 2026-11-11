"""task status ADMIN_REVIEW: a QC pass goes to the project admin for the final approval (D-092)

The moderator now listens at RECORDED and sends the recording to QC (no new status for that), and
a pass at QC moves the task to ADMIN_REVIEW instead of APPROVED. Only the status lists change.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-11 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "'DRAFT', 'ASSIGNED', 'IN_PROGRESS', 'RECORDED', 'AUDIO_QC', 'APPROVED', 'REJECTED', "
    "'RETURNED', 'CANCELLED', 'ON_HOLD'"
)
_AFTER = (
    "'DRAFT', 'ASSIGNED', 'IN_PROGRESS', 'RECORDED', 'AUDIO_QC', 'ADMIN_REVIEW', 'APPROVED', "
    "'REJECTED', 'RETURNED', 'CANCELLED', 'ON_HOLD'"
)


def _constraints(statuses: str) -> None:
    op.drop_constraint(op.f("ck_tasks_status_allowed"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_held_from_allowed"), "tasks", type_="check")
    op.create_check_constraint(op.f("ck_tasks_status_allowed"), "tasks", f"status IN ({statuses})")
    op.create_check_constraint(
        op.f("ck_tasks_held_from_allowed"),
        "tasks",
        f"held_from IS NULL OR held_from IN ({statuses})",
    )


def upgrade() -> None:
    _constraints(_AFTER)


def downgrade() -> None:
    stuck = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM tasks WHERE status = 'ADMIN_REVIEW' OR held_from = 'ADMIN_REVIEW'"
            )
        )
        .scalar()
    )
    if stuck:
        raise RuntimeError(f"{stuck} task(s) are in ADMIN_REVIEW: decide them before downgrading")
    _constraints(_BEFORE)
