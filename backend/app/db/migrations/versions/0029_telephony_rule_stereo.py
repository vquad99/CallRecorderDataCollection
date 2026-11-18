"""Phone recordings are stereo: telephony audio rules at the old 1-channel default become 2 (D-134)

TxContact delivers its recordings as WAV, 16 kHz, stereo, and the delivery file keeps both
channels, so on a rule of 1 channel every phone recording failed the automatic check ("More
tracks than the project"). Telephony rules still at D-103's default of 1 move to 2; a rule a
project already set to 2 is left alone, and face-to-face rules are not touched.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-18 16:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE project_audio_rules SET channels = 2, updated_at = now() "
        "WHERE mode = 'TELEPHONY' AND channels = 1"
    )


def downgrade() -> None:
    # Back to D-103's default. Which rules were 2 before the upgrade is not known: all become 1.
    op.execute(
        "UPDATE project_audio_rules SET channels = 1, updated_at = now() "
        "WHERE mode = 'TELEPHONY' AND channels = 2"
    )
