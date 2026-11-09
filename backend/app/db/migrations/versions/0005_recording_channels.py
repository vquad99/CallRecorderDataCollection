"""recording channels: device channel count, frames received

The original file now keeps every channel the browser delivers (D-048). `samples_received` counted
float32 values, which equals frames only for one channel, so it becomes `frames_received` (existing
rows are all single-channel, so their values are already frame counts). `device_channel_count`
stores what the browser reported for the microphone, separately from the channels captured.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09 23:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recordings", sa.Column("device_channel_count", sa.Integer(), nullable=True))
    op.alter_column("recordings", "samples_received", new_column_name="frames_received")


def downgrade() -> None:
    op.alter_column("recordings", "frames_received", new_column_name="samples_received")
    op.drop_column("recordings", "device_channel_count")
