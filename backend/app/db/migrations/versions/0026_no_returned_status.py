"""Task status RETURNED removed (D-118); index on consent_records.task_id

D-118 took "return to record again" out of the workflow. Tasks still at RETURNED go back to
ASSIGNED (DRAFT when nobody is assigned to record them), each with a status history entry by the
platform saying why; a task on hold from RETURNED will resume to that status instead. Then
RETURNED leaves the allowed statuses.

The index serves the task page and the task delete check, which look up a task's own consent
records without knowing the participant.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-17 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "'DRAFT', 'ASSIGNED', 'IN_PROGRESS', 'RECORDED', 'AUDIO_QC', 'ADMIN_REVIEW', 'APPROVED', "
    "'REJECTED', 'RETURNED', 'CANCELLED', 'ON_HOLD'"
)
_AFTER = (
    "'DRAFT', 'ASSIGNED', 'IN_PROGRESS', 'RECORDED', 'AUDIO_QC', 'ADMIN_REVIEW', 'APPROVED', "
    "'REJECTED', 'CANCELLED', 'ON_HOLD'"
)
# Returned tasks go to ASSIGNED when a moderator is on them, otherwise to DRAFT; each move is
# written to the task's history, by the platform (no actor).
_MOVE = """
WITH moved AS (
    UPDATE tasks
    SET status = CASE WHEN EXISTS (
            SELECT 1 FROM task_assignments a
            WHERE a.task_id = tasks.id AND a.role_code = 'MODERATOR' AND a.active
        ) THEN 'ASSIGNED' ELSE 'DRAFT' END,
        reason_code = NULL,
        updated_at = now()
    WHERE status = 'RETURNED'
    RETURNING id, status
)
INSERT INTO task_status_history (task_id, from_status, to_status, actor_id, reason_code, comment)
SELECT id, 'RETURNED', status, NULL, NULL,
       'Return was removed (D-118): moved out of Returned by the platform'
FROM moved
"""
# A task on hold from RETURNED resumes to where a returned task now goes.
_HELD = """
UPDATE tasks
SET held_from = CASE WHEN EXISTS (
        SELECT 1 FROM task_assignments a
        WHERE a.task_id = tasks.id AND a.role_code = 'MODERATOR' AND a.active
    ) THEN 'ASSIGNED' ELSE 'DRAFT' END,
    updated_at = now()
WHERE held_from = 'RETURNED'
"""


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
    op.create_index("ix_consent_records_task", "consent_records", ["task_id"])
    bind = op.get_bind()
    bind.execute(sa.text(_MOVE))
    bind.execute(sa.text(_HELD))
    _constraints(_AFTER)


def downgrade() -> None:
    # The tasks moved out of RETURNED stay where they are: the history says what happened.
    _constraints(_BEFORE)
    op.drop_index("ix_consent_records_task", table_name="consent_records")
