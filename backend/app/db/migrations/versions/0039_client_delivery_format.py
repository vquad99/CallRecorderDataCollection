"""The client's delivery format for exports (D-149)

- projects.export_layout (CLIENT), speaker_id_style (NUMBER), conversation_id_style (CON_NUMBER)
  and audio_name_pattern ({a}_{b}_{a_pin}_{b_pin}_{conversation}): how a project's exports are
  laid out and named (projects/delivery.py). Every existing project gets the client's delivery
  format, the owner's rule for every project; PLATFORM stays available on the Rules tab.
- export_jobs.missing (0): how many values and files a bundle in the client's format does not have
  (the rows of its MISSING.csv).

Going back drops the columns.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-22 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As projects/delivery.py read when this ran.
COLUMNS = (
    ("export_layout", 10, "CLIENT"),
    ("speaker_id_style", 10, "NUMBER"),
    ("conversation_id_style", 12, "CON_NUMBER"),
    ("audio_name_pattern", 100, "{a}_{b}_{a_pin}_{b_pin}_{conversation}"),
)
CHECKS = {
    "export_layout_allowed": "export_layout IN ('CLIENT', 'PLATFORM')",
    "speaker_id_style_allowed": "speaker_id_style IN ('NUMBER', 'CODE')",
    "conversation_id_style_allowed": "conversation_id_style IN ('CON_NUMBER', 'CODE')",
}


def upgrade() -> None:
    for name, length, default in COLUMNS:
        op.add_column(
            "projects",
            sa.Column(name, sa.String(length), server_default=default, nullable=False),
        )
    for name, sql in CHECKS.items():
        op.create_check_constraint(op.f(f"ck_projects_{name}"), "projects", sql)
    op.add_column(
        "export_jobs", sa.Column("missing", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("export_jobs", "missing")
    for name in CHECKS:
        op.drop_constraint(op.f(f"ck_projects_{name}"), "projects", type_="check")
    for name, _, _ in reversed(COLUMNS):
        op.drop_column("projects", name)
