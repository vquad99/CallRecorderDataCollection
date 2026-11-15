"""participant B rung into the call by the platform (D-111)

- calls: b_dial_attempts, b_dialled_at, b_dial_status, b_reference, b_phone_hint
- call event kinds B_DIAL_REQUESTED, B_DIAL_ACCEPTED, B_DIAL_FAILED

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-15 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_BEFORE = (
    "'DIAL_REQUESTED', 'DIAL_ACCEPTED', 'DIAL_FAILED', 'CALL_CLOSED', 'CALL_CANCELLED', "
    "'CHECKLIST', 'SEARCHING', 'MATCHED', 'MATCH_CHOSEN', 'NEEDS_MATCH', 'SEARCH_ERROR', "
    "'DOWNLOADED', 'FETCH_ERROR', 'FETCH_FAILED', 'RETRY_REQUESTED', 'RECORDED'"
)
_KINDS_AFTER = (
    "'DIAL_REQUESTED', 'DIAL_ACCEPTED', 'DIAL_FAILED', 'CALL_CLOSED', 'CALL_CANCELLED', "
    "'CHECKLIST', 'B_DIAL_REQUESTED', 'B_DIAL_ACCEPTED', 'B_DIAL_FAILED', 'SEARCHING', "
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
        "calls",
        sa.Column("b_dial_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("calls", sa.Column("b_dialled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("b_dial_status", sa.String(length=20), nullable=True))
    op.add_column("calls", sa.Column("b_reference", sa.String(length=100), nullable=True))
    op.add_column("calls", sa.Column("b_phone_hint", sa.String(length=2), nullable=True))
    _kinds(_KINDS_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM call_events WHERE kind LIKE 'B_DIAL_%'")
    _kinds(_KINDS_BEFORE)
    for column in (
        "b_phone_hint",
        "b_reference",
        "b_dial_status",
        "b_dialled_at",
        "b_dial_attempts",
    ):
        op.drop_column("calls", column)
