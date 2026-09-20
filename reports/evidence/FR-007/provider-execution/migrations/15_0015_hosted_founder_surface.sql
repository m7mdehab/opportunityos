BEGIN;

-- Running upgrade 0014_backup_heartbeat -> 0015_hosted_founder_surface

DROP VIEW IF EXISTS public.founder_feed;

CREATE VIEW public.founder_feed
WITH (security_invoker = true)
AS
WITH ranked AS (
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
    row_number() OVER (
      PARTITION BY fp.opportunity_id
      ORDER BY (fp.fit_score IS NOT NULL) DESC,
               fp.projected_at DESC,
               fp.evaluated_at DESC,
               fp.truth_pack_hash DESC,
               fp.id DESC
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
FROM ranked
WHERE rn = 1;

CREATE VIEW public.founder_source_overview
      WITH (security_invoker = true)
      AS
      WITH automated AS (
        SELECT split_part(s.source_id, ':', 1) AS source_family,
               s.source_id,
               count(f.opportunity_id) FILTER (WHERE f.is_stale IS FALSE AND f.visible IS TRUE)::integer AS opportunity_count,
               count(f.opportunity_id) FILTER (WHERE f.is_stale IS FALSE AND f.visible IS FALSE)::integer AS hidden_count,
               max(s.last_success_at) AS last_success_at,
               max(s.last_status) AS last_status,
               max(s.next_due_at) AS next_due_at,
               false AS manual_only
          FROM public.source_schedules s
          LEFT JOIN public.founder_feed f ON f.source_id = s.source_id
         GROUP BY split_part(s.source_id, ':', 1), s.source_id
      ), manual AS (
        SELECT families.source_family,
               NULL::varchar(128) AS source_id,
               0::integer AS opportunity_count,
               0::integer AS hidden_count,
               NULL::timestamp AS last_success_at,
               NULL::varchar(32) AS last_status,
               NULL::timestamp AS next_due_at,
               true AS manual_only
          FROM (VALUES
            ('ai_jobs_net'), ('arc_dev'), ('bayt'), ('cambly'), ('chegg'),
            ('contra'), ('freelancer'), ('gulftalent'), ('indeed'), ('jobicy'),
            ('justremote'), ('khamsat'), ('linkedin'), ('mostaql'), ('naukrigulf'),
            ('otta'), ('peopleperhour'), ('preply'), ('reddit'), ('remote_co'),
            ('superprof'), ('toptal'), ('tutor'), ('upwork'), ('wellfound'),
            ('working_nomads'), ('wuzzuf'), ('wyzant'), ('ycombinator')
          ) AS families(source_family)
      )
      SELECT * FROM automated
      UNION ALL
      SELECT * FROM manual;

CREATE OR REPLACE FUNCTION public.founder_dashboard_daily(
        p_days integer DEFAULT 7,
        p_high_fit_threshold double precision DEFAULT 80
      )
      RETURNS TABLE(
        date date,
        fetched integer,
        unique_new integer,
        qualified integer,
        high_fit integer,
        opened integer,
        labelled integer,
        applied integer,
        hidden_by_filters integer
      )
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public
      AS $$
      BEGIN
        IF NOT public.opos_is_founder() THEN
          RAISE EXCEPTION 'authorized founder required';
        END IF;
        IF p_days IS NULL OR p_days < 1 OR p_days > 90 THEN
          RAISE EXCEPTION 'days must be between 1 and 90';
        END IF;
        IF p_high_fit_threshold IS NULL
           OR p_high_fit_threshold <> p_high_fit_threshold
           OR p_high_fit_threshold < 0 OR p_high_fit_threshold > 100 THEN
          RAISE EXCEPTION 'high fit threshold must be between 0 and 100';
        END IF;
        RETURN QUERY
        WITH calendar AS (
          SELECT generate_series(
            current_date - (p_days - 1), current_date, interval '1 day'
          )::date AS day
        )
        SELECT c.day,
          COALESCE((SELECT sum(r.raw_ingested)::integer FROM source_poll_runs r
                    WHERE r.started_at >= c.day AND r.started_at < c.day + 1), 0),
          COALESCE((SELECT count(*)::integer FROM opportunities o
                    WHERE o.created_at >= c.day AND o.created_at < c.day + 1), 0),
          COALESCE((SELECT count(*)::integer FROM match_evaluations e
                    WHERE e.evaluated_at >= c.day AND e.evaluated_at < c.day + 1
                      AND e.qualification_decision = 'qualified'), 0),
          COALESCE((SELECT count(*)::integer FROM match_evaluations e
                    WHERE e.evaluated_at >= c.day AND e.evaluated_at < c.day + 1
                      AND e.fit_score >= p_high_fit_threshold), 0),
          COALESCE((SELECT count(*)::integer FROM founder_opportunity_views v
                    WHERE v.viewed_at >= c.day AND v.viewed_at < c.day + 1), 0),
          COALESCE((SELECT count(*)::integer FROM founder_feedback f
                    WHERE f.created_at >= c.day AND f.created_at < c.day + 1), 0),
          COALESCE((SELECT count(*)::integer FROM outbound_actions a
                    WHERE a.created_at >= c.day AND a.created_at < c.day + 1
                      AND a.action_status = 'submitted'), 0),
          COALESCE((SELECT count(DISTINCT f.opportunity_id)::integer
                    FROM founder_feed f
                    WHERE f.opportunity_created_at >= c.day
                      AND f.opportunity_created_at < c.day + 1
                      AND f.is_stale IS FALSE
                      AND f.visibility_reason IS NOT NULL
                      AND f.visibility_reason <> ''
                      AND EXISTS (
                        SELECT 1
                          FROM regexp_split_to_table(
                            replace(replace(replace(replace(replace(f.visibility_reason, '[', ''), ']', ''), '"', ''), '{', ''), '}', ''), ','
                          ) AS reason
                         WHERE reason <> '' AND reason NOT LIKE 'facet:%'
                      )), 0)
        FROM calendar c ORDER BY c.day DESC;
      END;
      $$;

REVOKE ALL ON public.founder_feed FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            EXECUTE 'REVOKE ALL ON public.founder_feed FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'REVOKE ALL ON public.founder_feed FROM authenticated';
            EXECUTE 'GRANT SELECT ON public.founder_feed TO authenticated';
          END IF;
        END $$;

REVOKE ALL ON public.founder_source_overview FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            EXECUTE 'REVOKE ALL ON public.founder_source_overview FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'REVOKE ALL ON public.founder_source_overview FROM authenticated';
            EXECUTE 'GRANT SELECT ON public.founder_source_overview TO authenticated';
          END IF;
        END $$;

REVOKE ALL ON FUNCTION public.founder_dashboard_daily(integer, double precision) FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION public.founder_dashboard_daily(integer, double precision) FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.founder_dashboard_daily(integer, double precision) TO authenticated';
      END IF;
    END $$;

UPDATE alembic_version SET version_num='0015_hosted_founder_surface' WHERE alembic_version.version_num = '0014_backup_heartbeat';

COMMIT;

