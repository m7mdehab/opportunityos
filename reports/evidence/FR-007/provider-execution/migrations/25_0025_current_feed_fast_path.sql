BEGIN;

-- Running upgrade 0024_founder_jwt_claims -> 0025_current_feed_fast_path

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
JOIN public.opportunities o ON o.id = fp.opportunity_id;

UPDATE alembic_version SET version_num='0025_current_feed_fast_path' WHERE alembic_version.version_num = '0024_founder_jwt_claims';

COMMIT;

