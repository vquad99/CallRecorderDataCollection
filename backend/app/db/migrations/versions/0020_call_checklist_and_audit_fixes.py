"""call checklist, poor-quality cancel reason, calls by time, one-channel telephony rule (D-103)

- calls.checklist: what the moderator confirmed on the call, with the time of each tick
- cancel reason POOR_QUALITY and event kind CHECKLIST
- an index on calls.dialled_at for the analytics and the list of all calls
- project audio rules for telephony move from 2 channels to 1: the phone provider records the call
  together, so with 2 every phone recording failed the automatic check. No telephony recording
  existed before this release, so no rule that anyone relied on is changed.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-13 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS_BEFORE = "'NO_ANSWER', 'WRONG_NUMBER', 'CALL_DROPPED', 'CONSENT_REFUSED', 'OTHER'"
_REASONS_AFTER = (
    "'NO_ANSWER', 'WRONG_NUMBER', 'CALL_DROPPED', 'POOR_QUALITY', 'CONSENT_REFUSED', 'OTHER'"
)
_KINDS_BEFORE = (
    "'DIAL_REQUESTED', 'DIAL_ACCEPTED', 'DIAL_FAILED', 'CALL_CLOSED', 'CALL_CANCELLED', "
    "'SEARCHING', 'MATCHED', 'MATCH_CHOSEN', 'NEEDS_MATCH', 'SEARCH_ERROR', 'DOWNLOADED', "
    "'FETCH_ERROR', 'FETCH_FAILED', 'RETRY_REQUESTED', 'RECORDED'"
)
_KINDS_AFTER = (
    "'DIAL_REQUESTED', 'DIAL_ACCEPTED', 'DIAL_FAILED', 'CALL_CLOSED', 'CALL_CANCELLED', "
    "'CHECKLIST', 'SEARCHING', 'MATCHED', 'MATCH_CHOSEN', 'NEEDS_MATCH', 'SEARCH_ERROR', "
    "'DOWNLOADED', 'FETCH_ERROR', 'FETCH_FAILED', 'RETRY_REQUESTED', 'RECORDED'"
)


def _constraints(reasons: str, kinds: str) -> None:
    op.drop_constraint(op.f("ck_calls_cancel_reason_allowed"), "calls", type_="check")
    op.create_check_constraint(
        op.f("ck_calls_cancel_reason_allowed"),
        "calls",
        f"cancel_reason IS NULL OR cancel_reason IN ({reasons})",
    )
    op.drop_constraint(op.f("ck_call_events_kind_allowed"), "call_events", type_="check")
    op.create_check_constraint(
        op.f("ck_call_events_kind_allowed"), "call_events", f"kind IN ({kinds})"
    )


def upgrade() -> None:
    op.add_column("calls", sa.Column("checklist", sa.Text(), server_default="{}", nullable=False))
    op.create_index("ix_calls_dialled_at", "calls", ["dialled_at"], unique=False)
    _constraints(_REASONS_AFTER, _KINDS_AFTER)
    op.execute(
        "UPDATE project_audio_rules SET channels = 1, updated_at = now() "
        "WHERE mode = 'TELEPHONY' AND channels = 2"
    )


def downgrade() -> None:
    op.execute("UPDATE calls SET cancel_reason = 'OTHER' WHERE cancel_reason = 'POOR_QUALITY'")
    op.execute("DELETE FROM call_events WHERE kind = 'CHECKLIST'")
    _constraints(_REASONS_BEFORE, _KINDS_BEFORE)
    op.drop_index("ix_calls_dialled_at", table_name="calls")
    op.drop_column("calls", "checklist")
    # The telephony audio rules stay at 1 channel: which of them were 2 before is not known.
