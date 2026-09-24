"""Use the Storage V2 one-current-projection invariant in the Founder feed."""
from typing import Sequence, Union

from alembic import op

revision: str = "0025_current_feed_fast_path"
down_revision: Union[str, None] = "0024_founder_jwt_claims"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CURRENT_FEED = """
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
  split_part(fp.source_id, ':', 1) AS source_family
FROM public.feed_projection fp
JOIN public.opportunities o ON o.id = fp.opportunity_id
"""


def upgrade() -> None:
    # 0022 enforces one current feed_projection row per opportunity. The old
    # row_number window was retained from the multi-truth-pack design and
    # needlessly ranked/joined the full feed for every page and exact count.
    op.execute(_CURRENT_FEED)


def downgrade() -> None:
    op.execute("""
      CREATE OR REPLACE VIEW public.founder_feed
      WITH (security_invoker = true) AS
      WITH ranked AS (
        SELECT fp.id, fp.opportunity_id, fp.opportunity_content_hash,
          fp.truth_pack_hash, fp.projection_version, fp.title,
          fp.organization, fp.source_id, fp.source_url, fp.posted_date,
          fp.track, fp.opportunity_type, fp.title_family, fp.seniority_level,
          fp.work_mode, fp.location_country, fp.location_city,
          fp.location_region, fp.remote_scope, fp.remote_scope_regions,
          fp.employment_type, fp.qualification_decision, fp.fit_score,
          fp.priority_score, fp.reasons_json, fp.red_line_match,
          fp.excluded_industry_match, fp.visible, fp.visibility_reason,
          fp.evaluated_at, fp.projected_at, o.is_stale, o.reverified_at,
          o.created_at AS opportunity_created_at,
          split_part(fp.source_id, ':', 1) AS source_family,
          row_number() OVER (
            PARTITION BY fp.opportunity_id
            ORDER BY (fp.fit_score IS NOT NULL) DESC, fp.projected_at DESC,
              fp.evaluated_at DESC, fp.truth_pack_hash DESC, fp.id DESC
          ) AS rn
        FROM public.feed_projection fp
        JOIN public.opportunities o ON o.id = fp.opportunity_id
      )
      SELECT id, opportunity_id, opportunity_content_hash, truth_pack_hash,
        projection_version, title, organization, source_id, source_url,
        posted_date, track, opportunity_type, title_family, seniority_level,
        work_mode, location_country, location_city, location_region,
        remote_scope, remote_scope_regions, employment_type,
        qualification_decision, fit_score, priority_score, reasons_json,
        red_line_match, excluded_industry_match, visible, visibility_reason,
        evaluated_at, projected_at, is_stale, reverified_at,
        opportunity_created_at, source_family
      FROM ranked WHERE rn = 1
    """)
