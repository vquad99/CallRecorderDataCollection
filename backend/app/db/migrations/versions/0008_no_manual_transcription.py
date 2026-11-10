"""no manual transcription: drop the Transcriber role, transcript permissions and statuses (D-062)

The owner's decision (2026-11-10): this is a data collection tool; AI transcription stays as a
per-project option, nobody transcribes or reviews transcripts by hand. Removed: the TRANSCRIBER
role, the transcripts.edit / transcripts.review / transcripts.reopen permissions, the task statuses
TRANSCRIPTION_PENDING / TRANSCRIPTION_IN_PROGRESS / TRANSCRIPT_QC and the project transcription
guidelines. A task now ends at audio QC: AUDIO_QC -> APPROVED, REJECTED or RETURNED.

No task can be in a removed status (only the platform's own modules could move it there and none
did), so the upgrade refuses to run if one is found instead of guessing where it should go.
Accounts that held the Transcriber role keep their other roles; an account left with none can sign
in but sees nothing until an administrator gives it a role.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-10 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REMOVED_STATUSES = ("TRANSCRIPTION_PENDING", "TRANSCRIPTION_IN_PROGRESS", "TRANSCRIPT_QC")
REMOVED_PERMISSIONS = ("transcripts.edit", "transcripts.review", "transcripts.reopen")

_KEPT = (
    "'DRAFT', 'ASSIGNED', 'IN_PROGRESS', 'RECORDED', 'AUDIO_QC', 'APPROVED', 'REJECTED', "
    "'RETURNED', 'CANCELLED', 'ON_HOLD'"
)
_ALL = (
    "'DRAFT', 'ASSIGNED', 'IN_PROGRESS', 'RECORDED', 'AUDIO_QC', 'TRANSCRIPTION_PENDING', "
    "'TRANSCRIPTION_IN_PROGRESS', 'TRANSCRIPT_QC', 'APPROVED', 'REJECTED', 'RETURNED', "
    "'CANCELLED', 'ON_HOLD'"
)

# Grants as they were at revision 0002, restored on downgrade.
_OLD_GRANTS = {
    "SUPER_ADMIN": REMOVED_PERMISSIONS,
    "PROJECT_ADMIN": ("transcripts.reopen",),
    "QC_EXECUTIVE": ("transcripts.review",),
}
_OLD_TRANSCRIBER = (
    "dashboard.view",
    "notes.view",
    "participants.view",
    "projects.view",
    "recordings.view",
    "tasks.view",
    "transcripts.edit",
)


def _constraints(statuses: str, roles: str) -> None:
    op.drop_constraint(op.f("ck_tasks_status_allowed"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_held_from_allowed"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_task_assignments_role_allowed"), "task_assignments", type_="check")
    op.create_check_constraint(op.f("ck_tasks_status_allowed"), "tasks", f"status IN ({statuses})")
    op.create_check_constraint(
        op.f("ck_tasks_held_from_allowed"),
        "tasks",
        f"held_from IS NULL OR held_from IN ({statuses})",
    )
    op.create_check_constraint(
        op.f("ck_task_assignments_role_allowed"), "task_assignments", f"role_code IN ({roles})"
    )


def upgrade() -> None:
    bind = op.get_bind()
    stuck = bind.execute(
        sa.text("SELECT count(*) FROM tasks WHERE status IN :s OR held_from IN :s").bindparams(
            sa.bindparam("s", expanding=True)
        ),
        {"s": list(REMOVED_STATUSES)},
    ).scalar_one()
    if stuck:
        raise RuntimeError(
            f"{stuck} task(s) are in a transcription status; move them before upgrading (D-062)"
        )
    op.execute("DELETE FROM task_assignments WHERE role_code = 'TRANSCRIBER'")
    _constraints(_KEPT, "'MODERATOR', 'QC_EXECUTIVE'")

    op.execute(
        "DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE code = 'TRANSCRIBER')"
    )
    removed = {"codes": list(REMOVED_PERMISSIONS)}
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE code = 'TRANSCRIBER') OR permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        removed,
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"), removed)
    op.execute("DELETE FROM roles WHERE code = 'TRANSCRIBER'")

    op.drop_index(
        op.f("ix_project_transcription_guidelines_project_id"),
        table_name="project_transcription_guidelines",
    )
    op.drop_table("project_transcription_guidelines")


def downgrade() -> None:
    op.create_table(
        "project_transcription_guidelines",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("guideline_text", sa.Text(), nullable=False),
        sa.Column("verbatim", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_project_transcription_guidelines_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_transcription_guidelines_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_transcription_guidelines")),
        sa.UniqueConstraint(
            "project_id", "version", name="uq_project_transcription_guidelines_version"
        ),
    )
    op.create_index(
        op.f("ix_project_transcription_guidelines_project_id"),
        "project_transcription_guidelines",
        ["project_id"],
        unique=False,
    )
    op.execute("INSERT INTO roles (code, name) VALUES ('TRANSCRIBER', 'Transcriber')")
    bind = op.get_bind()
    for code in REMOVED_PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions (code, description) VALUES (:code, '')"),
            {"code": code},
        )
    grants = dict(_OLD_GRANTS)
    grants["TRANSCRIBER"] = _OLD_TRANSCRIBER
    for role, codes in grants.items():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = ANY(:codes) "
                "WHERE r.code = :role ON CONFLICT DO NOTHING"
            ),
            {"codes": list(codes), "role": role},
        )
    _constraints(_ALL, "'MODERATOR', 'TRANSCRIBER', 'QC_EXECUTIVE'")
