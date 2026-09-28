"""Persist compact role, Egypt-eligibility, and application-route signals.

All fields are additive with safe defaults so currently deployed workers can
continue writing while the next BC tranches begin consuming the new contract.
No corpus backfill or source activation is performed by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_bc1_recommendation"
down_revision: Union[str, None] = "0026_fr008_live_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FEED_VIEW = """
CREATE OR REPLACE VIEW public.founder_feed
WITH (security_invoker = true)
AS
SELECT
  fp.id, fp.opportunity_id, fp.opportunity_content_hash, fp.truth_pack_hash,
  fp.projection_version, fp.title, fp.organization, fp.source_id,
  fp.source_url, fp.posted_date, fp.track, fp.opportunity_type,
  fp.title_family, fp.seniority_level, fp.work_mode, fp.location_country,
  fp.location_city, fp.location_region, fp.remote_scope,
  fp.remote_scope_regions, fp.employment_type, fp.qualification_decision,
  fp.fit_score, fp.priority_score, fp.reasons_json, fp.red_line_match,
  fp.excluded_industry_match, fp.visible, fp.visibility_reason,
  fp.evaluated_at, fp.projected_at,
  o.is_stale, o.reverified_at, o.created_at AS opportunity_created_at,
  split_part(fp.source_id, ':', 1) AS source_family,
  fp.role_relevance_class, fp.role_relevance_reason,
  fp.founder_geo_state, fp.founder_geo_reason,
  fp.application_url, fp.application_route, fp.application_access,
  fp.application_access_reason
FROM public.feed_projection fp
JOIN public.opportunities o ON o.id = fp.opportunity_id
"""

_DETAIL_VIEW = """
CREATE OR REPLACE VIEW public.founder_opportunity_detail
WITH (security_invoker = true)
AS
SELECT o.id, o.title, o.organization, o.source_id, o.source_url, o.track,
  o.description, o.deadline, o.posted_date, o.is_stale, o.reverified_at,
  o.work_mode, o.work_mode_source, o.location_country, o.location_city,
  o.location_region, o.remote_scope, o.remote_scope_regions,
  o.employment_type, o.seniority_level, o.compensation_min, o.compensation_max,
  o.compensation_currency, o.compensation_period, o.title_family, o.title_level,
  o.family_key, e.truth_pack_hash, e.qualification_decision, e.fit_score,
  e.dimension_scores_json, e.reasons_json, e.evaluation_detail_json,
  e.policy_version, e.evaluated_at, c.variant AS cv_variant,
  c.object_path AS cv_object_path, c.sha256 AS cv_sha256,
  o.role_relevance_class, o.role_relevance_reason,
  o.founder_geo_state, o.founder_geo_reason,
  o.application_url, o.application_route, o.application_access,
  o.application_access_reason
FROM public.opportunities o
LEFT JOIN LATERAL (
  SELECT * FROM public.match_evaluations
  WHERE opportunity_id=o.id ORDER BY evaluated_at DESC LIMIT 1
) e ON true
LEFT JOIN public.founder_cv_selections c ON c.opportunity_id=o.id
"""


def upgrade() -> None:
    for table in ("opportunities", "feed_projection"):
        op.add_column(table, sa.Column(
            "role_relevance_class", sa.String(length=16), nullable=False,
            server_default="unknown",
        ))
        op.add_column(table, sa.Column(
            "role_relevance_reason", sa.String(length=160), nullable=False,
            server_default="not classified",
        ))
        op.add_column(table, sa.Column(
            "founder_geo_state", sa.String(length=24), nullable=False,
            server_default="review",
        ))
        op.add_column(table, sa.Column(
            "founder_geo_reason", sa.String(length=160), nullable=False,
            server_default="not classified",
        ))
        op.add_column(table, sa.Column("application_url", sa.Text(), nullable=True))
        op.add_column(table, sa.Column(
            "application_route", sa.String(length=16), nullable=False,
            server_default="unknown",
        ))
        op.add_column(table, sa.Column(
            "application_access", sa.String(length=24), nullable=False,
            server_default="unknown",
        ))
        op.add_column(table, sa.Column(
            "application_access_reason", sa.String(length=160), nullable=False,
            server_default="not classified",
        ))
        op.create_check_constraint(
            f"ck_{table}_role_relevance_class",
            table,
            "role_relevance_class IN ('core','adjacent','non_target','unknown')",
        )
        op.create_check_constraint(
            f"ck_{table}_founder_geo_state",
            table,
            "founder_geo_state IN ('eligible','likely_eligible','review','ineligible')",
        )
        op.create_check_constraint(
            f"ck_{table}_application_route",
            table,
            "application_route IN ('employer','ats','intermediary','source','email','dm','unknown')",
        )
        op.create_check_constraint(
            f"ck_{table}_application_access",
            table,
            "application_access IN ('direct_free','free_intermediary','free_account_required','premium_or_gated','manual_only','unknown')",
        )

    op.execute(_FEED_VIEW)
    op.execute(_DETAIL_VIEW)


def downgrade() -> None:
    # Restore the prior public view shape before removing its backing columns.
    op.execute("""
      CREATE OR REPLACE VIEW public.founder_feed
      WITH (security_invoker = true) AS
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
        split_part(fp.source_id, ':', 1) AS source_family
      FROM public.feed_projection fp
      JOIN public.opportunities o ON o.id = fp.opportunity_id
    """)
    for table in ("feed_projection", "opportunities"):
        for constraint in (
            "role_relevance_class", "founder_geo_state",
            "application_route", "application_access",
        ):
            op.drop_constraint(f"ck_{table}_{constraint}", table, type_="check")
        for column in (
            "application_access_reason", "application_access", "application_route",
            "application_url", "founder_geo_reason", "founder_geo_state",
            "role_relevance_reason", "role_relevance_class",
        ):
            op.drop_column(table, column)
