"""BC-2 compact recommendation state for the founder feed."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028_bc2_recommendation"
down_revision: Union[str, None] = "0027_bc1_recommendation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FOUNDER_FEED = """
CREATE OR REPLACE VIEW public.founder_feed WITH (security_invoker = true) AS
SELECT fp.id, fp.opportunity_id, fp.opportunity_content_hash,
  fp.truth_pack_hash, fp.projection_version, fp.title, fp.organization,
  fp.source_id, fp.source_url, fp.posted_date, fp.track, fp.opportunity_type,
  fp.title_family, fp.seniority_level, fp.work_mode, fp.location_country,
  fp.location_city, fp.location_region, fp.remote_scope,
  fp.remote_scope_regions, fp.employment_type, fp.qualification_decision,
  fp.fit_score, fp.priority_score, fp.reasons_json, fp.red_line_match,
  fp.excluded_industry_match, fp.visible, fp.visibility_reason,
  fp.evaluated_at, fp.projected_at, o.is_stale, o.reverified_at,
  o.created_at AS opportunity_created_at,
  split_part(fp.source_id, ':', 1) AS source_family,
  fp.role_relevance_class, fp.role_relevance_reason,
  fp.founder_geo_state, fp.founder_geo_reason,
  fp.application_url, fp.application_route, fp.application_access,
  fp.application_access_reason,
  fp.recommendation_state, fp.recommendation_reasons_json,
  fp.recommendation_priority, fp.learned_affinity
FROM public.feed_projection fp
JOIN public.opportunities o ON o.id = fp.opportunity_id
"""

_FOUNDER_FEED_ACTIVITY = """
CREATE OR REPLACE VIEW public.founder_feed_activity
WITH (security_invoker = true) AS
SELECT f.id, f.opportunity_id, f.opportunity_content_hash, f.truth_pack_hash,
  f.projection_version, f.title, f.organization, f.source_id, f.source_url,
  f.posted_date, f.track, f.opportunity_type, f.title_family,
  f.seniority_level, f.work_mode, f.location_country, f.location_city,
  f.location_region, f.remote_scope, f.remote_scope_regions,
  f.employment_type, f.qualification_decision, f.fit_score, f.priority_score,
  f.reasons_json, f.red_line_match, f.excluded_industry_match, f.visible,
  f.visibility_reason, f.evaluated_at, f.projected_at,
  a.action_state, a.snoozed_until, a.action_updated_at, a.feedback_label,
  a.feedback_count, a.feedback_updated_at, a.has_activity,
  f.is_stale, f.reverified_at, f.opportunity_created_at, f.source_family,
  f.role_relevance_class, f.role_relevance_reason, f.founder_geo_state,
  f.founder_geo_reason, f.application_url, f.application_route,
  f.application_access, f.application_access_reason,
  f.recommendation_state, f.recommendation_reasons_json,
  f.recommendation_priority, f.learned_affinity
FROM public.founder_feed f
LEFT JOIN public.founder_activity_state a ON a.opportunity_id=f.opportunity_id
"""

_FOUNDER_FEED_FR008 = """
CREATE OR REPLACE VIEW public.founder_feed_fr008
WITH (security_invoker = true) AS
SELECT f.id, f.opportunity_id, f.opportunity_content_hash, f.truth_pack_hash,
  f.projection_version, f.title, f.organization, f.source_id, f.source_url,
  f.posted_date, f.track, f.opportunity_type, f.title_family,
  f.seniority_level, f.work_mode, f.location_country, f.location_city,
  f.location_region, f.remote_scope, f.remote_scope_regions,
  f.employment_type, f.qualification_decision, f.fit_score, f.priority_score,
  f.reasons_json, f.red_line_match, f.excluded_industry_match, f.visible,
  f.visibility_reason, f.evaluated_at, f.projected_at,
  f.action_state, f.snoozed_until, f.action_updated_at, f.feedback_label,
  f.feedback_count, f.feedback_updated_at, f.has_activity,
  CASE WHEN f.work_mode='remote' THEN 0 ELSE 1 END AS remote_rank,
  f.is_stale, f.reverified_at, f.opportunity_created_at, f.source_family,
  f.role_relevance_class, f.role_relevance_reason, f.founder_geo_state,
  f.founder_geo_reason, f.application_url, f.application_route,
  f.application_access, f.application_access_reason,
  f.recommendation_state, f.recommendation_reasons_json,
  f.recommendation_priority, f.learned_affinity
FROM public.founder_feed_activity f
"""

_FOUNDER_FEED_ACTIVITY_BC1 = """
CREATE VIEW public.founder_feed_activity WITH (security_invoker = true) AS
SELECT f.id, f.opportunity_id, f.opportunity_content_hash, f.truth_pack_hash,
  f.projection_version, f.title, f.organization, f.source_id, f.source_url,
  f.posted_date, f.track, f.opportunity_type, f.title_family,
  f.seniority_level, f.work_mode, f.location_country, f.location_city,
  f.location_region, f.remote_scope, f.remote_scope_regions,
  f.employment_type, f.qualification_decision, f.fit_score, f.priority_score,
  f.reasons_json, f.red_line_match, f.excluded_industry_match, f.visible,
  f.visibility_reason, f.evaluated_at, f.projected_at,
  a.action_state, a.snoozed_until, a.action_updated_at,
  a.feedback_label, a.feedback_count, a.feedback_updated_at, a.has_activity
FROM public.founder_feed f
LEFT JOIN public.founder_activity_state a ON a.opportunity_id=f.opportunity_id
"""

_FOUNDER_FEED_FR008_BC1 = """
CREATE VIEW public.founder_feed_fr008 WITH (security_invoker = true) AS
SELECT f.id, f.opportunity_id, f.opportunity_content_hash, f.truth_pack_hash,
  f.projection_version, f.title, f.organization, f.source_id, f.source_url,
  f.posted_date, f.track, f.opportunity_type, f.title_family,
  f.seniority_level, f.work_mode, f.location_country, f.location_city,
  f.location_region, f.remote_scope, f.remote_scope_regions,
  f.employment_type, f.qualification_decision, f.fit_score, f.priority_score,
  f.reasons_json, f.red_line_match, f.excluded_industry_match, f.visible,
  f.visibility_reason, f.evaluated_at, f.projected_at,
  f.action_state, f.snoozed_until, f.action_updated_at, f.feedback_label,
  f.feedback_count, f.feedback_updated_at, f.has_activity,
  CASE WHEN f.work_mode='remote' THEN 0 ELSE 1 END AS remote_rank
FROM public.founder_feed_activity f
"""


def upgrade() -> None:
    op.add_column("feed_projection", sa.Column(
        "recommendation_state", sa.String(length=16), nullable=False,
        server_default="review",
    ))
    op.add_column("feed_projection", sa.Column(
        "recommendation_reasons_json", sa.Text(), nullable=False,
        server_default="[]",
    ))
    op.add_column("feed_projection", sa.Column(
        "recommendation_priority", sa.Float(), nullable=True,
    ))
    op.add_column("feed_projection", sa.Column(
        "learned_affinity", sa.Float(), nullable=True,
    ))
    op.create_check_constraint(
        "ck_feed_projection_recommendation_state",
        "feed_projection",
        "recommendation_state IN ('for_you','review','excluded')",
    )
    op.create_index(
        "ix_feed_projection_recommendation_rank",
        "feed_projection",
        ["truth_pack_hash", "recommendation_state", "recommendation_priority"],
    )
    # Recreate dependent compatibility views so PostgREST exposes the new
    # compact fields while preserving security-invoker mode and read grants.
    op.execute(_FOUNDER_FEED)
    op.execute(_FOUNDER_FEED_ACTIVITY)
    op.execute(_FOUNDER_FEED_FR008)
    op.execute("GRANT SELECT ON public.founder_feed TO authenticated")
    op.execute("GRANT SELECT ON public.founder_feed_activity TO authenticated")
    op.execute("GRANT SELECT ON public.founder_feed_fr008 TO authenticated")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public.founder_feed_fr008")
    op.execute("DROP VIEW IF EXISTS public.founder_feed_activity")
    op.execute("DROP VIEW IF EXISTS public.founder_feed")
    op.execute("""
      CREATE VIEW public.founder_feed WITH (security_invoker = true) AS
      SELECT fp.id, fp.opportunity_id, fp.opportunity_content_hash,
        fp.truth_pack_hash, fp.projection_version, fp.title, fp.organization,
        fp.source_id, fp.source_url, fp.posted_date, fp.track,
        fp.opportunity_type, fp.title_family, fp.seniority_level, fp.work_mode,
        fp.location_country, fp.location_city, fp.location_region,
        fp.remote_scope, fp.remote_scope_regions, fp.employment_type,
        fp.qualification_decision, fp.fit_score, fp.priority_score,
        fp.reasons_json, fp.red_line_match, fp.excluded_industry_match,
        fp.visible, fp.visibility_reason, fp.evaluated_at, fp.projected_at,
        o.is_stale, o.reverified_at, o.created_at AS opportunity_created_at,
        split_part(fp.source_id, ':', 1) AS source_family,
        fp.role_relevance_class, fp.role_relevance_reason,
        fp.founder_geo_state, fp.founder_geo_reason,
        fp.application_url, fp.application_route, fp.application_access,
        fp.application_access_reason
      FROM public.feed_projection fp
      JOIN public.opportunities o ON o.id = fp.opportunity_id
    """)
    op.execute(_FOUNDER_FEED_ACTIVITY_BC1)
    op.execute(_FOUNDER_FEED_FR008_BC1)
    op.execute("GRANT SELECT ON public.founder_feed TO authenticated")
    op.execute("GRANT SELECT ON public.founder_feed_activity TO authenticated")
    op.execute("GRANT SELECT ON public.founder_feed_fr008 TO authenticated")
    op.drop_index("ix_feed_projection_recommendation_rank", table_name="feed_projection")
    op.drop_constraint("ck_feed_projection_recommendation_state", "feed_projection", type_="check")
    for column in (
        "learned_affinity", "recommendation_priority",
        "recommendation_reasons_json", "recommendation_state",
    ):
        op.drop_column("feed_projection", column)
