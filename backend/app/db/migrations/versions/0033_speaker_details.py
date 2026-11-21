"""participants: speaker details; projects: pairing rules (D-143)

- participants: age, gender, current state/district/PIN code, native state and PIN code (the
  native district is the existing `district`), native language, education and its medium, and
  state/district/PIN code during the recording. All empty for people saved before; codes, the age
  range and PIN codes are kept valid by constraints (the list of states is checked by the app).
- projects.max_conversations_per_speaker (3; empty = no limit) and projects.unique_pairs (on): the
  task rules. Existing projects get them too.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-21 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("age", sa.Integer()),
    ("gender", sa.String(10)),
    ("current_state", sa.String(60)),
    ("current_district", sa.String(100)),
    ("current_pincode", sa.String(6)),
    ("native_state", sa.String(60)),
    ("native_pincode", sa.String(6)),
    ("native_language", sa.String(50)),
    ("education", sa.String(20)),
    ("education_medium", sa.String(20)),
    ("recording_state", sa.String(60)),
    ("recording_district", sa.String(100)),
    ("recording_pincode", sa.String(6)),
)
PINCODES = ("current_pincode", "native_pincode", "recording_pincode")
EDUCATION = ("PRIMARY", "SECONDARY", "HIGHER_SECONDARY", "DIPLOMA", "BACHELORS", "MASTERS", "PHD")


def _one_of(column: str, codes: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(c) for c in codes)})"


CHECKS = {
    "age_range": "age IS NULL OR age BETWEEN 20 AND 60",
    "gender_allowed": _one_of("gender", ("MALE", "FEMALE")),
    "education_allowed": _one_of("education", (*EDUCATION, "OTHER")),
    "education_medium_allowed": _one_of("education_medium", ("ENGLISH", "NON_ENGLISH")),
    "pincode_format": " AND ".join(f"({c} IS NULL OR {c} ~ '^[1-9][0-9]{{5}}$')" for c in PINCODES),
}


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column("participants", sa.Column(name, kind, nullable=True))
    for name, sql in CHECKS.items():
        op.create_check_constraint(op.f(f"ck_participants_{name}"), "participants", sql)
    op.add_column(
        "projects",
        sa.Column("max_conversations_per_speaker", sa.Integer(), server_default="3", nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("unique_pairs", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_projects_max_conversations_range"),
        "projects",
        "max_conversations_per_speaker IS NULL OR max_conversations_per_speaker >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_projects_max_conversations_range"), "projects", type_="check")
    op.drop_column("projects", "unique_pairs")
    op.drop_column("projects", "max_conversations_per_speaker")
    for name in CHECKS:
        op.drop_constraint(op.f(f"ck_participants_{name}"), "participants", type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column("participants", name)
