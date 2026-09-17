from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR

from storage.models import Base


class FeedProjectionRecord(Base):
    """Persisted founder-facing feed state for one opportunity/profile version.

    This table is deliberately denormalized. Interactive feed/search/filter
    requests should read it directly rather than reconstructing visibility or
    qualification state across the opportunity corpus in Python.
    """

    __tablename__ = "feed_projection"

    id = Column(String(160), primary_key=True)
    opportunity_id = Column(
        String(64),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    opportunity_content_hash = Column(String(64), nullable=False)
    truth_pack_hash = Column(String(64), nullable=False)
    projection_version = Column(String(32), nullable=False)

    title = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=False)
    source_id = Column(String(128), nullable=False)
    source_url = Column(Text, nullable=False)
    posted_date = Column(String(64), nullable=True)
    track = Column(String(32), nullable=False)
    opportunity_type = Column(String(32), nullable=True)
    title_family = Column(String(64), nullable=True)
    seniority_level = Column(String(24), nullable=False)
    work_mode = Column(String(16), nullable=False)
    location_country = Column(String(2), nullable=True)
    location_city = Column(String(128), nullable=True)
    location_region = Column(Text, nullable=True)
    remote_scope = Column(String(24), nullable=False)
    remote_scope_regions = Column(Text, nullable=True)
    employment_type = Column(String(24), nullable=False)

    qualification_decision = Column(String(32), nullable=False)
    fit_score = Column(Float, nullable=False)
    priority_score = Column(Float, nullable=False)
    reasons_json = Column(Text, nullable=False)

    red_line_match = Column(Boolean, nullable=False, default=False)
    excluded_industry_match = Column(Boolean, nullable=False, default=False)
    visible = Column(Boolean, nullable=False, default=True)
    visibility_reason = Column(Text, nullable=True)

    search_text = Column(Text, nullable=False, default="")
    search_tsv = Column(Text().with_variant(TSVECTOR(), "postgresql"), nullable=True)

    evaluated_at = Column(DateTime(timezone=True), nullable=False)
    projected_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "truth_pack_hash",
            name="uq_feed_projection_opportunity_truth_pack",
        ),
        Index(
            "ix_feed_projection_truth_visible_rank",
            "truth_pack_hash",
            "visible",
            "priority_score",
        ),
        Index(
            "ix_feed_projection_truth_decision_score",
            "truth_pack_hash",
            "qualification_decision",
            "fit_score",
        ),
        Index(
            "ix_feed_projection_truth_posted",
            "truth_pack_hash",
            "posted_date",
        ),
        Index("ix_feed_projection_source_id", "source_id"),
        Index("ix_feed_projection_title_family", "title_family"),
        Index("ix_feed_projection_work_mode", "work_mode"),
        Index("ix_feed_projection_location_country", "location_country"),
        Index(
            "ix_feed_projection_search_tsv",
            "search_tsv",
            postgresql_using="gin",
        ),
    )


def projection_identity(opportunity_id: str, truth_pack_hash: str) -> str:
    """Stable, inspectable identity for the current per-profile projection row."""

    return f"{opportunity_id}:{truth_pack_hash}"
