"""Effective speech and pauses; a project's audio and progress settings and its targets (D-148)

- audio_assets.effective_ms, longest_pause_ms, pauses_ms: the time someone speaks in the file, the
  longest pause inside the speech and every pause of a second or longer (recordings/media.py).
  Empty for files made before: the backfill (audio_qc/speech.py) measures them after the deploy,
  a few at a time, and notes in speech_error why a file could not be measured. A partial index
  finds the final files still to measure.
- projects.pause_limit_seconds (3), long_pauses_need_review (off), progress_counts (EFFECTIVE).
- projects.target_hours (none), target_speakers (500), target_conversations (600),
  target_age_bands, target_gender, target_modes (the first client's: 20-30 40 %, 30-40 30 %,
  40-50 20 %, 50-60 10 %; 50 % male and female; 50 % face-to-face and phone) and
  target_districts (none). Every existing project gets these values.

Going back drops the columns and the index.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-22 16:00:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The first client's targets as they read when this ran (projects/targets.py).
AGE_BANDS = [
    {"from": 20, "to": 30, "percent": 40},
    {"from": 30, "to": 40, "percent": 30},
    {"from": 40, "to": 50, "percent": 20},
    {"from": 50, "to": 60, "percent": 10},
]
GENDER = {"MALE": 50, "FEMALE": 50}
MODES = {"FACE_TO_FACE": 50, "TELEPHONY": 50}
FINAL_KINDS = "('FTF_DERIVED_PCM', 'TELEPHONY_DERIVED_PCM', 'TELEPHONY_FINAL_STEREO')"
CHECKS = {
    "pause_limit_range": "pause_limit_seconds BETWEEN 1 AND 30",
    "progress_counts_allowed": "progress_counts IN ('EFFECTIVE', 'FULL')",
    "targets_positive": "(target_hours IS NULL OR target_hours >= 0)"
    " AND (target_speakers IS NULL OR target_speakers >= 1)"
    " AND (target_conversations IS NULL OR target_conversations >= 1)",
    "target_age_bands_list": "jsonb_typeof(target_age_bands) = 'array'",
    "target_gender_object": "jsonb_typeof(target_gender) = 'object'",
    "target_modes_object": "jsonb_typeof(target_modes) = 'object'",
    "target_districts_list": "jsonb_typeof(target_districts) = 'array'",
}
PROJECT_COLUMNS = (
    "pause_limit_seconds",
    "long_pauses_need_review",
    "progress_counts",
    "target_hours",
    "target_speakers",
    "target_conversations",
    "target_age_bands",
    "target_gender",
    "target_modes",
    "target_districts",
)


def _jsonb(value: object) -> sa.TextClause:
    return sa.text("'" + json.dumps(value).replace("'", "''") + "'::jsonb")


def _json_column(name: str, default: object) -> sa.Column[object]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=_jsonb(default),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column("audio_assets", sa.Column("effective_ms", sa.BigInteger(), nullable=True))
    op.add_column("audio_assets", sa.Column("longest_pause_ms", sa.Integer(), nullable=True))
    op.add_column(
        "audio_assets", sa.Column("pauses_ms", postgresql.ARRAY(sa.Integer()), nullable=True)
    )
    op.add_column("audio_assets", sa.Column("speech_error", sa.String(200), nullable=True))
    op.create_index(
        "ix_audio_assets_speech_missing",
        "audio_assets",
        ["created_at"],
        postgresql_where=sa.text(
            f"kind IN {FINAL_KINDS} AND effective_ms IS NULL AND speech_error IS NULL"
            " AND deleted_at IS NULL"
        ),
    )
    op.add_column(
        "projects",
        sa.Column("pause_limit_seconds", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "projects",
        sa.Column(
            "long_pauses_need_review", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column(
        "projects",
        sa.Column("progress_counts", sa.String(10), server_default="EFFECTIVE", nullable=False),
    )
    op.add_column("projects", sa.Column("target_hours", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "projects", sa.Column("target_speakers", sa.Integer(), server_default="500", nullable=True)
    )
    op.add_column(
        "projects",
        sa.Column("target_conversations", sa.Integer(), server_default="600", nullable=True),
    )
    op.add_column("projects", _json_column("target_age_bands", AGE_BANDS))
    op.add_column("projects", _json_column("target_gender", GENDER))
    op.add_column("projects", _json_column("target_modes", MODES))
    op.add_column("projects", _json_column("target_districts", []))
    for name, sql in CHECKS.items():
        op.create_check_constraint(op.f(f"ck_projects_{name}"), "projects", sql)


def downgrade() -> None:
    for name in CHECKS:
        op.drop_constraint(op.f(f"ck_projects_{name}"), "projects", type_="check")
    for column in reversed(PROJECT_COLUMNS):
        op.drop_column("projects", column)
    op.drop_index("ix_audio_assets_speech_missing", table_name="audio_assets")
    for column in ("speech_error", "pauses_ms", "longest_pause_ms", "effective_ms"):
        op.drop_column("audio_assets", column)
