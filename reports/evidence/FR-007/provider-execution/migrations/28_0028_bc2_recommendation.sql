BEGIN;

-- Running upgrade 0027_bc1_recommendation -> 0028_bc2_recommendation

ALTER TABLE feed_projection ADD COLUMN recommendation_state VARCHAR(16) DEFAULT 'review' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN recommendation_reasons_json TEXT DEFAULT '[]' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN recommendation_priority FLOAT;

ALTER TABLE feed_projection ADD COLUMN learned_affinity FLOAT;

ALTER TABLE feed_projection ADD CONSTRAINT ck_feed_projection_recommendation_state CHECK (recommendation_state IN ('for_you','review','excluded'));

CREATE INDEX ix_feed_projection_recommendation_rank ON feed_projection (truth_pack_hash, recommendation_state, recommendation_priority);

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
JOIN public.opportunities o ON o.id = fp.opportunity_id;

CREATE OR REPLACE VIEW public.founder_feed_activity
WITH (security_invoker = true) AS
SELECT f.id, f.opportunity_id, f.opportunity_content_hash, f.truth_pack_hash,
  f.projection_version, f.title, f.organization, f.source_id, f.source_url,
  f.posted_date, f.track, f.opportunity_type, f.title_family,
  f.seniority_level, f.work_mode, f.location_country, f.location_city,
  f.location_region, f.remote_scope, f.remote_scope_regions,
  f.employment_type, f.qualification_decision, f.fit_score, f.priority_score,
  f.reasons_json, f.red_line_match, f.excluded_industry_match, f.visible,
  f.visibility_reason, f.evaluated_at, f.projected_at, f.is_stale,
  f.reverified_at, f.opportunity_created_at, f.source_family,
  a.action_state, a.snoozed_until, a.action_updated_at, a.feedback_label,
  a.feedback_count, a.feedback_updated_at, a.has_activity,
  f.role_relevance_class, f.role_relevance_reason, f.founder_geo_state,
  f.founder_geo_reason, f.application_url, f.application_route,
  f.application_access, f.application_access_reason,
  f.recommendation_state, f.recommendation_reasons_json,
  f.recommendation_priority, f.learned_affinity
FROM public.founder_feed f
LEFT JOIN public.founder_activity_state a ON a.opportunity_id=f.opportunity_id;

CREATE OR REPLACE VIEW public.founder_feed_fr008
WITH (security_invoker = true) AS
SELECT f.id, f.opportunity_id, f.opportunity_content_hash, f.truth_pack_hash,
  f.projection_version, f.title, f.organization, f.source_id, f.source_url,
  f.posted_date, f.track, f.opportunity_type, f.title_family,
  f.seniority_level, f.work_mode, f.location_country, f.location_city,
  f.location_region, f.remote_scope, f.remote_scope_regions,
  f.employment_type, f.qualification_decision, f.fit_score, f.priority_score,
  f.reasons_json, f.red_line_match, f.excluded_industry_match, f.visible,
  f.visibility_reason, f.evaluated_at, f.projected_at, f.is_stale,
  f.reverified_at, f.opportunity_created_at, f.source_family,
  f.action_state, f.snoozed_until, f.action_updated_at, f.feedback_label,
  f.feedback_count, f.feedback_updated_at, f.has_activity,
  CASE WHEN f.work_mode='remote' THEN 0 ELSE 1 END AS remote_rank,
  f.role_relevance_class, f.role_relevance_reason, f.founder_geo_state,
  f.founder_geo_reason, f.application_url, f.application_route,
  f.application_access, f.application_access_reason,
  f.recommendation_state, f.recommendation_reasons_json,
  f.recommendation_priority, f.learned_affinity
FROM public.founder_feed_activity f;

DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
          GRANT SELECT ON public.founder_feed TO authenticated;
          GRANT SELECT ON public.founder_feed_activity TO authenticated;
          GRANT SELECT ON public.founder_feed_fr008 TO authenticated;
        END IF;
      END $$;

UPDATE alembic_version SET version_num='0028_bc2_recommendation' WHERE alembic_version.version_num = '0027_bc1_recommendation';

COMMIT;

