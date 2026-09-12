"""0005_widen_location_region

Revision ID: 0005_widen_location_region
Revises: 0004_founder_control
Create Date: 2026-09-13 00:00:00.000000

FR-006 recovery: real Himalayas rows can carry a truthful multi-country native
location region longer than 64 characters.  Truncating that value would lose
source truth, so the persisted founder-control field is widened to TEXT.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_widen_location_region"
down_revision: Union[str, None] = "0004_founder_control"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# This revision changes only the opportunity location schema; it does not
# change any founder-filter seed defaults. Keep the explicit empty override
# so FilterSeedSyncTest can compose every post-0003 revision deterministically.
_D3_FILTER_SEED_OVERRIDES = {}


def upgrade() -> None:
    op.alter_column(
        "opportunities",
        "location_region",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "opportunities",
        "location_region",
        existing_type=sa.Text(),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
