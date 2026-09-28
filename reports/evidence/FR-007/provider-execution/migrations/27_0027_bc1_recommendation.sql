BEGIN;

-- Running upgrade 0026_fr008_live_actions -> 0027_bc1_recommendation

ALTER TABLE opportunities ADD COLUMN role_relevance_class VARCHAR(16) DEFAULT 'unknown' NOT NULL;

ALTER TABLE opportunities ADD COLUMN role_relevance_reason VARCHAR(160) DEFAULT 'not classified' NOT NULL;

ALTER TABLE opportunities ADD COLUMN founder_geo_state VARCHAR(24) DEFAULT 'review' NOT NULL;

ALTER TABLE opportunities ADD COLUMN founder_geo_reason VARCHAR(160) DEFAULT 'not classified' NOT NULL;

ALTER TABLE opportunities ADD COLUMN application_url TEXT;

ALTER TABLE opportunities ADD COLUMN application_route VARCHAR(16) DEFAULT 'unknown' NOT NULL;

ALTER TABLE opportunities ADD COLUMN application_access VARCHAR(24) DEFAULT 'unknown' NOT NULL;

ALTER TABLE opportunities ADD COLUMN application_access_reason VARCHAR(160) DEFAULT 'not classified' NOT NULL;

ALTER TABLE opportunities ADD CONSTRAINT ck_opportunities_role_relevance_class CHECK (role_relevance_class IN ('core','adjacent','non_target','unknown'));

ALTER TABLE opportunities ADD CONSTRAINT ck_opportunities_founder_geo_state CHECK (founder_geo_state IN ('eligible','likely_eligible','review','ineligible'));

ALTER TABLE opportunities ADD CONSTRAINT ck_opportunities_application_route CHECK (application_route IN ('employer','ats','intermediary','source','email','dm','unknown'));

ALTER TABLE opportunities ADD CONSTRAINT ck_opportunities_application_access CHECK (application_access IN ('direct_free','free_intermediary','free_account_required','premium_or_gated','manual_only','unknown'));

ALTER TABLE feed_projection ADD COLUMN role_relevance_class VARCHAR(16) DEFAULT 'unknown' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN role_relevance_reason VARCHAR(160) DEFAULT 'not classified' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN founder_geo_state VARCHAR(24) DEFAULT 'review' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN founder_geo_reason VARCHAR(160) DEFAULT 'not classified' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN application_url TEXT;

ALTER TABLE feed_projection ADD COLUMN application_route VARCHAR(16) DEFAULT 'unknown' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN application_access VARCHAR(24) DEFAULT 'unknown' NOT NULL;

ALTER TABLE feed_projection ADD COLUMN application_access_reason VARCHAR(160) DEFAULT 'not classified' NOT NULL;

ALTER TABLE feed_projection ADD CONSTRAINT ck_feed_projection_role_relevance_class CHECK (role_relevance_class IN ('core','adjacent','non_target','unknown'));

ALTER TABLE feed_projection ADD CONSTRAINT ck_feed_projection_founder_geo_state CHECK (founder_geo_state IN ('eligible','likely_eligible','review','ineligible'));

ALTER TABLE feed_projection ADD CONSTRAINT ck_feed_projection_application_route CHECK (application_route IN ('employer','ats','intermediary','source','email','dm','unknown'));

ALTER TABLE feed_projection ADD CONSTRAINT ck_feed_projection_application_access CHECK (application_access IN ('direct_free','free_intermediary','free_account_required','premium_or_gated','manual_only','unknown'));

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
JOIN public.opportunities o ON o.id = fp.opportunity_id;

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
LEFT JOIN public.founder_cv_selections c ON c.opportunity_id=o.id;

UPDATE alembic_version SET version_num='0027_bc1_recommendation' WHERE alembic_version.version_num = '0026_fr008_live_actions';

COMMIT;

