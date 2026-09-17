"""0006_feed_projection

Revision ID: 0006_feed_projection
Revises: 0005_widen_location_region
Create Date: 2026-09-17 00:00:00.000000

FR-007 Wave 1: persist the founder-facing feed projection so interactive feed
requests read indexed database state rather than rebuilding visibility and
matching state from the full opportunity corpus in Python process memory.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_feed_projection"
down_revision: Union[str, None] = "0005_widen_location_region"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# This revision does not change founder-filter seed defaults.
_D3_FILTER_SEED_OVERRIDES = {}


def upgrade() -> None:
    op.create_table(
        "feed_projection",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column(
            "opportunity_id",
            sa.String(length=64),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("opportunity_content_hash", sa.String(length=64), nullable=False),
        sa.Column("truth_pack_hash", sa.String(length=64), nullable=False),
        sa.Column("projection_version", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("organization", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("posted_date", sa.String(length=64), nullable=True),
        sa.Column("track", sa.String(length=32), nullable=False),
        sa.Column("opportunity_type", sa.String(length=32), nullable=True),
        sa.Column("title_family", sa.String(length=64), nullable=True),
        sa.Column("seniority_level", sa.String(length=24), nullable=False),
        sa.Column("work_mode", sa.String(length=16), nullable=False),
        sa.Column("location_country", sa.String(length=2), nullable=True),
        sa.Column("location_city", sa.String(length=128), nullable=True),
        sa.Column("location_region", sa.Text(), nullable=True),
        sa.Column("remote_scope", sa.String(length=24), nullable=False),
        sa.Column("remote_scope_regions", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.String(length=24), nullable=False),
        sa.Column("qualification_decision", sa.String(length=32), nullable=False),
        sa.Column("fit_score", sa.Float(), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False),
        sa.Column("red_line_match", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("excluded_industry_match", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("visibility_reason", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opportunity_id",
            "truth_pack_hash",
            name="uq_feed_projection_opportunity_truth_pack",
        ),
    )

    op.create_index(
        "ix_feed_projection_truth_visible_rank",
        "feed_projection",
        ["truth_pack_hash", "visible", "priority_score"],
        unique=False,
    )
    op.create_index(
        "ix_feed_projection_truth_decision_score",
        "feed_projection",
        ["truth_pack_hash", "qualification_decision", "fit_score"],
        unique=False,
    )
    op.create_index(
        "ix_feed_projection_truth_posted",
        "feed_projection",
        ["truth_pack_hash", "posted_date"],
        unique=False,
    )
    op.create_index(
        "ix_feed_projection_source_id",
        "feed_projection",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "ix_feed_projection_title_family",
        "feed_projection",
        ["title_family"],
        unique=False,
    )
    op.create_index(
        "ix_feed_projection_work_mode",
        "feed_projection",
        ["work_mode"],
        unique=False,
    )
    op.create_index(
        "ix_feed_projection_location_country",
        "feed_projection",
        ["location_country"],
        unique=False,
    )
    op.create_index(
        "ix_feed_projection_search_tsv",
        "feed_projection",
        ["search_tsv"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_feed_projection_search_tsv", table_name="feed_projection")
    op.drop_index("ix_feed_projection_location_country", table_name="feed_projection")
    op.drop_index("ix_feed_projection_work_mode", table_name="feed_projection")
    op.drop_index("ix_feed_projection_title_family", table_name="feed_projection")
    op.drop_index("ix_feed_projection_source_id", table_name="feed_projection")
    op.drop_index("ix_feed_projection_truth_posted", table_name="feed_projection")
    op.drop_index("ix_feed_projection_truth_decision_score", table_name="feed_projection")
    op.drop_index("ix_feed_projection_truth_visible_rank", table_name="feed_projection")
    op.drop_table("feed_projection")
