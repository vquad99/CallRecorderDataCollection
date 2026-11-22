"""tasks: an index on each participant (PERF-10)

- ix_tasks_participant_a_id and ix_tasks_participant_b_id: a participant's tasks are looked up as
  participant_a_id = X OR participant_b_id = X (the participant's details and personal page, the
  pairing tally and minutes of the participants list, the open-task check before a delete). With
  an index on each side the database combines two index scans instead of reading every task of
  the project, or every task at all.

Going back drops them.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-22 22:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIDES = ("participant_a_id", "participant_b_id")


def upgrade() -> None:
    for column in SIDES:
        op.create_index(op.f(f"ix_tasks_{column}"), "tasks", [column], unique=False)


def downgrade() -> None:
    for column in reversed(SIDES):
        op.drop_index(op.f(f"ix_tasks_{column}"), table_name="tasks")
