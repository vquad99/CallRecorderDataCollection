"""the moderator marks the conversation within the call (D-113)

- calls: record_started_at, record_stopped_at
- call event kinds RECORDING_STARTED, RECORDING_STOPPED

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-16 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "'DIAL_REQUESTED', 'DIAL_ACCEPTED', 'DIAL_FAILED', 'CALL_CLOSED', 'CALL_CANCELLED', "
    "'CHECKLIST', 'B_DIAL_REQUESTED', 'B_DIAL_ACCEPTED', 'B_DIAL_FAILED', 'SEARCHING', "
    "'MATCHED', 'MATCH_CHOSEN', 'NEEDS_MATCH', 'SEARCH_ERROR', 'DOWNLOADED', 'FETCH_ERROR', "
    "'FETCH_FAILED', 'RETRY_REQUESTED', 'RECORDED'"
)
_AFTER = (
    "'DIAL_REQUESTED', 'DIAL_ACCEPTED', 'DIAL_FAILED', 'CALL_CLOSED', 'CALL_CANCELLED', "
    "'CHECKLIST', 'B_DIAL_REQUESTED', 'B_DIAL_ACCEPTED', 'B_DIAL_FAILED', "
    "'RECORDING_STARTED', 'RECORDING_STOPPED', 'SEARCHING', "
    "'MATCHED', 'MATCH_CHOSEN', 'NEEDS_MATCH', 'SEARCH_ERROR', 'DOWNLOADED', 'FETCH_ERROR', "
    "'FETCH_FAILED', 'RETRY_REQUESTED', 'RECORDED'"
)


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_call_events_kind_allowed"), "call_events", type_="check")
    op.create_check_constraint(
        op.f("ck_call_events_kind_allowed"), "call_events", f"kind IN ({kinds})"
    )


def upgrade() -> None:
    op.add_column(
        "calls", sa.Column("record_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "calls", sa.Column("record_stopped_at", sa.DateTime(timezone=True), nullable=True)
    )
    _kinds(_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM call_events WHERE kind IN ('RECORDING_STARTED', 'RECORDING_STOPPED')")
    _kinds(_BEFORE)
    op.drop_column("calls", "record_stopped_at")
    op.drop_column("calls", "record_started_at")
