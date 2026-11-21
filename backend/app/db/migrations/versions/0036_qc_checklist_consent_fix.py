"""QC checklist; sending a task back for its consent form (D-146)

- projects.qc_checklist: the questions the QC Executive answers Yes or No for each recording.
  Every existing project gets the first client's list (Konkani, NLTM) as its own; a project
  changes it on its Rules tab.
- audio_qc_results.checklist: a decision's answers, with the questions as they read then; empty
  for the automatic check and for decisions made before. A decision's outcome may now be
  SEND_BACK_CONSENT: the audio is fine but a signed consent form is not.
- audio_qc_drafts: a QC Executive's answers not yet sent, one per task.
- tasks: status CONSENT_FIX, "Consent form to fix": the moderator uploads a new scan and sends the
  same recording back to QC.

Going back moves tasks waiting for a consent form back to Audio QC (with a history entry by the
platform) and holds new decisions to the old outcomes only (NOT VALID): decisions that sent a task
back stay as they are.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-21 23:30:00
"""

import json
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The first client's checklist as it read when this ran (audio_qc/checklist.DEFAULT_QC_CHECKLIST):
# conversation items fail on No; speaker items are observations.
_CONVERSATION = (
    ("correct_speaker_ids", "Both speakers have unique IDs that match the registered participants"),
    ("speaker_id_announced", "Each speaker clearly says their speaker ID at the start"),
    ("two_speakers", "The conversation is between exactly two speakers"),
    ("no_third_person", "No third person speaks or interrupts"),
    ("within_max_duration", "The conversation is within the maximum length (15 minutes)"),
    ("natural_conversation", "Natural conversation, not read from a script"),
    (
        "suitable_topic",
        "A common topic: nothing political, religious, obscene, hateful or sensitive",
    ),
    ("no_personal_information", "Speakers do not share personal information"),
    ("quiet_environment", "Relatively quiet: no road, TV, crying babies or vehicles"),
    ("speakers_stationary", "Both speakers stay in one place (sitting or standing)"),
    ("short_fillers", "Fillers (uh, um) never last more than 3 seconds"),
    ("no_ringtone_overlap", "No ringtone or notification sound overlaps the speech"),
    ("correct_recording_mode", "Correctly recorded as face-to-face or phone call"),
)
_SPEAKER = (
    ("speech_intelligible", "Is speech intelligible?"),
    ("speech_slurring", "Is speech slurred?"),
    ("speech_stammering", "Is stammering present?"),
    ("is_non_native_speech_present", "Is non-native speech present?"),
    ("noisy_background", "Is background noise present?"),
    ("good_pace_of_speech", "Is the pace of speech good?"),
    ("is_this_natural_human_voice", "Is this a natural human voice?"),
    ("low_speaker_volume", "Is the speaker's volume low?"),
    ("speaker_far_from_microphone", "Is the speaker far from the microphone?"),
    ("microphone_saturation", "Is microphone saturation present?"),
    ("echo_in_audio", "Is echo present?"),
    ("read_speech", "Does the speech sound read?"),
    ("impromptu_speech", "Is the speech impromptu?"),
    ("notifications_telephonic_sounds", "Are notification or phone sounds present?"),
    ("speaker_breath_sounds", "Are breath sounds present?"),
)
CHECKLIST = [
    {"key": k, "question": q, "scope": "conversation", "fails_on": "no", "required": True}
    for k, q in _CONVERSATION
] + [
    {"key": k, "question": q, "scope": "speaker", "fails_on": None, "required": True}
    for k, q in _SPEAKER
]
CHECKLIST_SQL = "'" + json.dumps(CHECKLIST).replace("'", "''") + "'::jsonb"

_STATUSES = (
    "'DRAFT', 'ASSIGNED', 'IN_PROGRESS', 'RECORDED', 'AUDIO_QC', 'ADMIN_REVIEW', 'APPROVED', "
    "'REJECTED', 'CANCELLED', 'ON_HOLD'"
)
_OUTCOMES = "'PASS', 'NEEDS_REVIEW', 'FAIL', 'RETURN'"
DRAFTS = "audio_qc_drafts"

# Tasks waiting for a consent form go back to Audio QC, each with a history entry by the platform.
_BACK_TO_QC = """
WITH moved AS (
    UPDATE tasks SET status = 'AUDIO_QC', reason_code = NULL, updated_at = now()
    WHERE status = 'CONSENT_FIX'
    RETURNING id
)
INSERT INTO task_status_history (task_id, from_status, to_status, actor_id, reason_code, comment)
SELECT id, 'CONSENT_FIX', 'AUDIO_QC', NULL, NULL,
       'Consent form to fix was removed (going back from 0036): back to Audio QC'
FROM moved
"""


def _stamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _task_statuses(statuses: str) -> None:
    op.drop_constraint(op.f("ck_tasks_status_allowed"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_held_from_allowed"), "tasks", type_="check")
    op.create_check_constraint(op.f("ck_tasks_status_allowed"), "tasks", f"status IN ({statuses})")
    op.create_check_constraint(
        op.f("ck_tasks_held_from_allowed"),
        "tasks",
        f"held_from IS NULL OR held_from IN ({statuses})",
    )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "qc_checklist",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(CHECKLIST_SQL),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_projects_qc_checklist_list"), "projects", "jsonb_typeof(qc_checklist) = 'array'"
    )
    op.add_column(
        "audio_qc_results",
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_constraint(op.f("ck_audio_qc_results_outcome_allowed"), "audio_qc_results", "check")
    op.create_check_constraint(
        op.f("ck_audio_qc_results_outcome_allowed"),
        "audio_qc_results",
        f"outcome IN ({_OUTCOMES}, 'SEND_BACK_CONSENT')",
    )
    op.create_table(
        DRAFTS,
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("saved_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f(f"fk_{DRAFTS}_task_id_tasks"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["saved_by"],
            ["users.id"],
            name=op.f(f"fk_{DRAFTS}_saved_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DRAFTS}")),
        sa.UniqueConstraint("task_id", name=op.f(f"uq_{DRAFTS}_task_id")),
    )
    _task_statuses(f"{_STATUSES}, 'CONSENT_FIX'")


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(_BACK_TO_QC))
    bind.execute(sa.text("UPDATE tasks SET held_from = 'AUDIO_QC' WHERE held_from = 'CONSENT_FIX'"))
    _task_statuses(_STATUSES)
    op.drop_table(DRAFTS)
    op.drop_constraint(op.f("ck_audio_qc_results_outcome_allowed"), "audio_qc_results", "check")
    op.execute(
        "ALTER TABLE audio_qc_results ADD CONSTRAINT ck_audio_qc_results_outcome_allowed "
        f"CHECK (outcome IN ({_OUTCOMES})) NOT VALID"
    )
    op.drop_column("audio_qc_results", "checklist")
    op.drop_constraint(op.f("ck_projects_qc_checklist_list"), "projects", type_="check")
    op.drop_column("projects", "qc_checklist")
