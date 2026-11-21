"""Device details per speaker; the moderator's reminders (D-147)

- projects.device_fields: which device details the moderator fills for each speaker before a task
  goes to QC. Every existing project asks all five (the first client's list, Konkani, NLTM).
- projects.recording_reminders: the lines the moderator reads before recording and before calling
  (the speaker-ID line or not, topics, what to avoid, face-to-face and phone tips). Every existing
  project gets the first client's text.
- task_device_details: one row per task and participant: device make and model, Bluetooth or
  wired earphones, loudspeaker on; who saved it and when.

Going back drops the table and the two columns.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-22 10:00:00
"""

import json
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The first client's lists as they read when this ran (projects/moderation.py).
DEVICE_FIELDS = [
    "device_make",
    "device_model",
    "bluetooth_earphones",
    "wired_earphones",
    "loudspeaker_on",
]
REMINDERS = {
    "speaker_id": True,
    "topics": [
        "daily activities",
        "education",
        "agriculture",
        "food and cooking",
        "travel",
        "shopping",
        "health and fitness in general",
        "weather",
        "work and hobbies",
    ],
    "avoid": [
        "politics",
        "religion",
        "obscene talk",
        "hate or killing",
        "other sensitive topics",
        "personal information",
    ],
    "face_to_face": [
        "Record in a quiet place; both speakers stay in one place (sitting or standing).",
        "Place the recording device between the two speakers, no more than 2.5 feet from each "
        "mouth, and do not move it.",
    ],
    "telephony": [
        "Each speaker is in a quiet place and stays in one place (sitting or standing).",
        "Hold the handset near the mouth and keep the loudspeaker off.",
        "No ringtones or notification sounds during the call.",
    ],
}
TABLE = "task_device_details"


def _jsonb(value: object) -> sa.TextClause:
    return sa.text("'" + json.dumps(value).replace("'", "''") + "'::jsonb")


def _stamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "device_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_jsonb(DEVICE_FIELDS),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "recording_reminders",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_jsonb(REMINDERS),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_projects_device_fields_list"), "projects", "jsonb_typeof(device_fields) = 'array'"
    )
    op.create_check_constraint(
        op.f("ck_projects_recording_reminders_object"),
        "projects",
        "jsonb_typeof(recording_reminders) = 'object'",
    )
    op.create_table(
        TABLE,
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("device_make", sa.String(60), nullable=True),
        sa.Column("device_model", sa.String(60), nullable=True),
        sa.Column("bluetooth_earphones", sa.Boolean(), nullable=True),
        sa.Column("wired_earphones", sa.Boolean(), nullable=True),
        sa.Column("loudspeaker_on", sa.Boolean(), nullable=True),
        sa.Column("filled_by", sa.Uuid(), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f(f"fk_{TABLE}_task_id_tasks"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f(f"fk_{TABLE}_participant_id_participants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["filled_by"],
            ["users.id"],
            name=op.f(f"fk_{TABLE}_filled_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint("task_id", "participant_id", name=op.f(f"uq_{TABLE}_task_id")),
    )
    op.create_index(op.f(f"ix_{TABLE}_participant_id"), TABLE, ["participant_id"])


def downgrade() -> None:
    op.drop_index(op.f(f"ix_{TABLE}_participant_id"), table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_constraint(op.f("ck_projects_recording_reminders_object"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_device_fields_list"), "projects", type_="check")
    op.drop_column("projects", "recording_reminders")
    op.drop_column("projects", "device_fields")
