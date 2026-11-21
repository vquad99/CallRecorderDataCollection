"""projects: speaker rules; participants: any person's age (D-145)

- projects.speaker_min_age (20) and speaker_max_age (60): the ages the project takes (1 to 120,
  the youngest not above the oldest), and projects.required_speaker_details (every speaker detail):
  what a person needs before a task. The first client's numbers are only the defaults; existing
  projects get them, so nothing changes for them.
- participants.age: the check is now what fits any person (1 to 120) instead of the client's 20 to
  60; each project holds its people to its own range in the app (participants/speakers.py).

Going back puts the 20 to 60 check back for new values only (NOT VALID): ages saved meanwhile
outside it are kept.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-21 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The speaker details as they were named when this ran (participants/speakers.FIELDS).
SPEAKER_DETAILS = (
    "age",
    "gender",
    "current_state",
    "current_district",
    "current_pincode",
    "native_state",
    "district",
    "native_pincode",
    "native_language",
    "education",
    "education_medium",
    "recording_state",
    "recording_district",
    "recording_pincode",
)
EVERY_DETAIL = "'[" + ", ".join(f'"{name}"' for name in SPEAKER_DETAILS) + "]'::jsonb"


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("speaker_min_age", sa.Integer(), server_default="20", nullable=False),
    )
    op.add_column(
        "projects",
        sa.Column("speaker_max_age", sa.Integer(), server_default="60", nullable=False),
    )
    op.add_column(
        "projects",
        sa.Column(
            "required_speaker_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(EVERY_DETAIL),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_projects_speaker_age_range"),
        "projects",
        "speaker_min_age BETWEEN 1 AND 120 AND speaker_max_age BETWEEN 1 AND 120"
        " AND speaker_min_age <= speaker_max_age",
    )
    op.create_check_constraint(
        op.f("ck_projects_required_speaker_details_list"),
        "projects",
        "jsonb_typeof(required_speaker_details) = 'array'",
    )
    op.drop_constraint(op.f("ck_participants_age_range"), "participants", type_="check")
    op.create_check_constraint(
        op.f("ck_participants_age_range"), "participants", "age IS NULL OR age BETWEEN 1 AND 120"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_participants_age_range"), "participants", type_="check")
    op.execute(
        "ALTER TABLE participants ADD CONSTRAINT ck_participants_age_range "
        "CHECK (age IS NULL OR age BETWEEN 20 AND 60) NOT VALID"
    )
    op.drop_constraint(op.f("ck_projects_required_speaker_details_list"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_speaker_age_range"), "projects", type_="check")
    op.drop_column("projects", "required_speaker_details")
    op.drop_column("projects", "speaker_max_age")
    op.drop_column("projects", "speaker_min_age")
