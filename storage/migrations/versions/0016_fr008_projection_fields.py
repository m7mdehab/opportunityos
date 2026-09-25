"""0016_fr008_projection_fields

Add normalized target/title fields and independent score components to the
persisted FR-008 feed projection. Existing projection rows remain nullable and
are populated only by a later projection refresh.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_fr008_projection_fields"
down_revision: Union[str, None] = "0015_fr008_tracker_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feed_projection", sa.Column("title_level", sa.String(length=24), nullable=True))
    op.add_column("feed_projection", sa.Column("target_tier", sa.String(length=24), nullable=True))
    op.add_column("feed_projection", sa.Column("preference_score", sa.Float(), nullable=True))
    op.add_column("feed_projection", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.create_index(
        "ix_feed_projection_truth_title_family",
        "feed_projection",
        ["truth_pack_hash", "title_family"],
    )
    op.create_index(
        "ix_feed_projection_truth_title_level",
        "feed_projection",
        ["truth_pack_hash", "title_level"],
    )
    op.create_index(
        "ix_feed_projection_truth_target_tier",
        "feed_projection",
        ["truth_pack_hash", "target_tier"],
    )
    op.create_index(
        "ix_feed_projection_truth_preference",
        "feed_projection",
        ["truth_pack_hash", "preference_score"],
    )
    op.create_index(
        "ix_feed_projection_truth_confidence",
        "feed_projection",
        ["truth_pack_hash", "confidence_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_feed_projection_truth_confidence", table_name="feed_projection")
    op.drop_index("ix_feed_projection_truth_preference", table_name="feed_projection")
    op.drop_index("ix_feed_projection_truth_target_tier", table_name="feed_projection")
    op.drop_index("ix_feed_projection_truth_title_level", table_name="feed_projection")
    op.drop_index("ix_feed_projection_truth_title_family", table_name="feed_projection")
    op.drop_column("feed_projection", "confidence_score")
    op.drop_column("feed_projection", "preference_score")
    op.drop_column("feed_projection", "target_tier")
    op.drop_column("feed_projection", "title_level")
