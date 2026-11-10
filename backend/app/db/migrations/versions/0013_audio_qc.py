"""audio quality check results and the two new measurements (D-079)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-11 12:00:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[Any]]:
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


def upgrade() -> None:
    # Files measured before this release keep empty values; nothing is made up for them.
    op.add_column("audio_assets", sa.Column("dynamic_range_db", sa.Float(), nullable=True))
    op.add_column(
        "audio_assets", sa.Column("content_fingerprint", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_audio_assets_content_fingerprint"),
        "audio_assets",
        ["content_fingerprint"],
        unique=False,
    )
    op.create_table(
        "audio_qc_results",
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("automated", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=True),
        sa.Column("comment", sa.Text(), server_default="", nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("silence_pct", sa.Float(), nullable=True),
        sa.Column("clip_pct", sa.Float(), nullable=True),
        sa.Column("peak_dbfs", sa.Float(), nullable=True),
        sa.Column("rms_dbfs", sa.Float(), nullable=True),
        sa.Column("dynamic_range_db", sa.Float(), nullable=True),
        sa.Column("duplicate_of_recording_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "outcome IN ('PASS', 'NEEDS_REVIEW', 'FAIL', 'RETURN')",
            name=op.f("ck_audio_qc_results_outcome_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["audio_assets.id"],
            name=op.f("fk_audio_qc_results_asset_id_audio_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_recording_id"],
            ["recordings.id"],
            name=op.f("fk_audio_qc_results_duplicate_of_recording_id_recordings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_audio_qc_results_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            name=op.f("fk_audio_qc_results_recording_id_recordings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_audio_qc_results_reviewer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_audio_qc_results_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audio_qc_results")),
    )
    for column in ("project_id", "recording_id", "task_id"):
        op.create_index(
            op.f(f"ix_audio_qc_results_{column}"), "audio_qc_results", [column], unique=False
        )
    op.create_table(
        "audio_qc_checks",
        sa.Column("result_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("measured", sa.String(length=200), server_default="", nullable=False),
        sa.Column("expected", sa.String(length=200), server_default="", nullable=False),
        sa.Column("message", sa.Text(), server_default="", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "state IN ('PASS', 'FAIL', 'REVIEW', 'INFO', 'NOT_APPLICABLE')",
            name=op.f("ck_audio_qc_checks_state_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["audio_qc_results.id"],
            name=op.f("fk_audio_qc_checks_result_id_audio_qc_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audio_qc_checks")),
    )
    op.create_index(
        op.f("ix_audio_qc_checks_result_id"), "audio_qc_checks", ["result_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audio_qc_checks_result_id"), table_name="audio_qc_checks")
    op.drop_table("audio_qc_checks")
    for column in ("task_id", "recording_id", "project_id"):
        op.drop_index(op.f(f"ix_audio_qc_results_{column}"), table_name="audio_qc_results")
    op.drop_table("audio_qc_results")
    op.drop_index(op.f("ix_audio_assets_content_fingerprint"), table_name="audio_assets")
    op.drop_column("audio_assets", "content_fingerprint")
    op.drop_column("audio_assets", "dynamic_range_db")
