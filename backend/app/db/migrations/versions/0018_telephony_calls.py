"""phone calls through TxContact: calls, call events, agent seats, telephony delivery file (D-101)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-13 18:00:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_BEFORE = (
    "'PROVIDER_ORIGINAL_TRACK', 'PROVIDER_ORIGINAL_MIXED', 'TELEPHONY_FINAL_STEREO', "
    "'CONSENT_RECORDING', 'BROWSER_ORIGINAL', 'FTF_DERIVED_PCM', 'TRANSCRIPT_FILE', "
    "'EXPORT_PACKAGE'"
)
_KINDS_AFTER = (
    "'PROVIDER_ORIGINAL_TRACK', 'PROVIDER_ORIGINAL_MIXED', 'TELEPHONY_FINAL_STEREO', "
    "'CONSENT_RECORDING', 'BROWSER_ORIGINAL', 'FTF_DERIVED_PCM', 'TELEPHONY_DERIVED_PCM', "
    "'TRANSCRIPT_FILE', 'EXPORT_PACKAGE'"
)
_CALL_STATES = (
    "'DIALLING', 'DIAL_FAILED', 'CANCELLED', 'WAITING_FOR_RECORDING', 'NEEDS_MATCH', "
    "'FETCH_FAILED', 'RECORDED'"
)
_CANCEL_REASONS = "'NO_ANSWER', 'WRONG_NUMBER', 'CALL_DROPPED', 'CONSENT_REFUSED', 'OTHER'"
_EVENT_KINDS = (
    "'DIAL_REQUESTED', 'DIAL_ACCEPTED', 'DIAL_FAILED', 'CALL_CLOSED', 'CALL_CANCELLED', "
    "'SEARCHING', 'MATCHED', 'MATCH_CHOSEN', 'NEEDS_MATCH', 'SEARCH_ERROR', 'DOWNLOADED', "
    "'FETCH_ERROR', 'FETCH_FAILED', 'RETRY_REQUESTED', 'RECORDED'"
)


def _base() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _asset_kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_audio_assets_kind_allowed"), "audio_assets", type_="check")
    op.create_check_constraint(
        op.f("ck_audio_assets_kind_allowed"), "audio_assets", f"kind IN ({kinds})"
    )
    op.drop_constraint(
        op.f("ck_project_retention_rules_asset_kind_allowed"),
        "project_retention_rules",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_project_retention_rules_asset_kind_allowed"),
        "project_retention_rules",
        f"asset_kind IN ({kinds})",
    )


def upgrade() -> None:
    _asset_kinds(_KINDS_AFTER)
    op.add_column("users", sa.Column("telephony_agent_id", sa.String(length=40), nullable=True))
    op.create_table(
        "calls",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("moderator_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("phone_hint", sa.String(length=2), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("dialled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=30), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("provider_session_id", sa.String(length=100), nullable=True),
        sa.Column("provider_file", sa.String(length=300), nullable=True),
        sa.Column("candidates", sa.Text(), server_default="[]", nullable=False),
        sa.Column("fetch_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=50), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("recording_id", sa.Uuid(), nullable=True),
        *_base(),
        sa.CheckConstraint(f"state IN ({_CALL_STATES})", name=op.f("ck_calls_state_allowed")),
        sa.CheckConstraint(
            f"cancel_reason IS NULL OR cancel_reason IN ({_CANCEL_REASONS})",
            name=op.f("ck_calls_cancel_reason_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_calls_task_id_tasks"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_calls_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["moderator_id"],
            ["users.id"],
            name=op.f("fk_calls_moderator_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            name=op.f("fk_calls_recording_id_recordings"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calls")),
    )
    op.create_index(op.f("ix_calls_project_id"), "calls", ["project_id"], unique=False)
    op.create_index(op.f("ix_calls_moderator_id"), "calls", ["moderator_id"], unique=False)
    op.create_index("ix_calls_task_created", "calls", ["task_id", "created_at"], unique=False)
    op.create_index(
        "uq_calls_one_open_per_task",
        "calls",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('DIALLING', 'WAITING_FOR_RECORDING')"),
    )
    op.create_index(
        "uq_calls_provider_session",
        "calls",
        ["provider", "provider_session_id"],
        unique=True,
        postgresql_where=sa.text("provider_session_id IS NOT NULL"),
    )
    op.create_index(
        "ix_calls_waiting",
        "calls",
        ["next_fetch_at"],
        unique=False,
        postgresql_where=sa.text("state = 'WAITING_FOR_RECORDING'"),
    )
    op.create_table(
        "call_events",
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        *_base(),
        sa.CheckConstraint(f"kind IN ({_EVENT_KINDS})", name=op.f("ck_call_events_kind_allowed")),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["calls.id"],
            name=op.f("fk_call_events_call_id_calls"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_call_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_events")),
    )
    op.create_index(
        "ix_call_events_call_created", "call_events", ["call_id", "created_at"], unique=False
    )


def downgrade() -> None:
    used = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM audio_assets WHERE kind = 'TELEPHONY_DERIVED_PCM'"))
        .scalar()
    )
    if used:
        raise RuntimeError(
            f"{used} telephony delivery file(s) exist: remove them before downgrading"
        )
    op.drop_table("call_events")
    op.drop_table("calls")
    op.drop_column("users", "telephony_agent_id")
    op.execute("DELETE FROM project_retention_rules WHERE asset_kind = 'TELEPHONY_DERIVED_PCM'")
    _asset_kinds(_KINDS_BEFORE)
