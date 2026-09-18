"""0007_source_schedules

Revision ID: 0007_source_schedules
Revises: 0006_feed_projection
Create Date: 2026-09-18 00:00:00.000000

FR-007 Wave 11: persist source scheduling, cadence, next-due, and cooldown state
so scheduler decisions survive process restarts with no all-source warm-up storm.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_source_schedules"
down_revision: Union[str, None] = "0006_feed_projection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# This revision does not change founder-filter seed defaults.
_D3_FILTER_SEED_OVERRIDES = {}


def upgrade() -> None:
    op.create_table(
        "source_schedules",
        sa.Column("source_id", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("cadence_hours", sa.Float(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("next_due_at", sa.DateTime(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_source_schedules_next_due_at",
        "source_schedules",
        ["next_due_at"],
        unique=False,
    )
    op.create_index(
        "ix_source_schedules_cooldown_until",
        "source_schedules",
        ["cooldown_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_schedules_cooldown_until", table_name="source_schedules")
    op.drop_index("ix_source_schedules_next_due_at", table_name="source_schedules")
    op.drop_table("source_schedules")
