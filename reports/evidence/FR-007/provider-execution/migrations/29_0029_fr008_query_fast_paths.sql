BEGIN;

-- Running upgrade 0028_bc2_recommendation -> 0029_fr008_query_fast_paths

CREATE OR REPLACE VIEW public.founder_feed_fr008
WITH (security_invoker = true) AS
WITH latest_event AS (
  SELECT DISTINCT ON (e.opportunity_id)
    e.opportunity_id, e.action_type, e.resulting_state,
    e.snoozed_until, e.created_at
  FROM public.founder_activity_events e
  WHERE public.opos_is_founder()
  ORDER BY e.opportunity_id, e.created_at DESC, e.id DESC
), latest_feedback AS (
  SELECT DISTINCT ON (f.opportunity_id)
    f.opportunity_id, f.feedback_label, f.created_at AS feedback_updated_at
  FROM public.founder_feedback f
  WHERE public.opos_is_founder()
  ORDER BY f.opportunity_id, f.created_at DESC, f.id DESC
), feedback_counts AS (
  SELECT f.opportunity_id, count(*)::integer AS feedback_count
  FROM public.founder_feedback f
  WHERE public.opos_is_founder()
  GROUP BY f.opportunity_id
), legacy_applied AS (
  SELECT DISTINCT a.opportunity_id
  FROM public.outbound_actions a
  WHERE public.opos_is_founder()
    AND a.candidate_id='founder'
    AND a.adapter_name='founder_attested'
    AND a.action_status='submitted'
)
SELECT f.id, f.opportunity_id, f.opportunity_content_hash, f.truth_pack_hash,
  f.projection_version, f.title, f.organization, f.source_id, f.source_url,
  f.posted_date, f.track, f.opportunity_type, f.title_family,
  f.seniority_level, f.work_mode, f.location_country, f.location_city,
  f.location_region, f.remote_scope, f.remote_scope_regions,
  f.employment_type, f.qualification_decision, f.fit_score, f.priority_score,
  f.reasons_json, f.red_line_match, f.excluded_industry_match, f.visible,
  f.visibility_reason, f.evaluated_at, f.projected_at, f.is_stale,
  f.reverified_at, f.opportunity_created_at, f.source_family,
  CASE
    WHEN le.action_type='snooze' AND le.snoozed_until IS NOT NULL
      AND le.snoozed_until > CURRENT_DATE THEN 'snoozed'
    WHEN le.action_type IN ('save','mark_applied','reject','dismiss')
      THEN le.resulting_state
    WHEN le.action_type='restore' THEN le.resulting_state
    WHEN le.action_type IN ('snooze','clear') THEN NULL
    ELSE NULL
  END::varchar AS action_state,
  CASE WHEN le.action_type='snooze' AND le.snoozed_until > CURRENT_DATE
    THEN le.snoozed_until::timestamp without time zone ELSE NULL
  END AS snoozed_until,
  le.created_at AS action_updated_at,
  lf.feedback_label,
  coalesce(fc.feedback_count,0) AS feedback_count,
  lf.feedback_updated_at,
  le.opportunity_id IS NOT NULL OR la.opportunity_id IS NOT NULL
    OR coalesce(fc.feedback_count,0) > 0 AS has_activity,
  CASE WHEN f.work_mode='remote' THEN 0 ELSE 1 END AS remote_rank,
  f.role_relevance_class, f.role_relevance_reason, f.founder_geo_state,
  f.founder_geo_reason, f.application_url, f.application_route,
  f.application_access, f.application_access_reason,
  f.recommendation_state, f.recommendation_reasons_json,
  f.recommendation_priority, f.learned_affinity
FROM public.founder_feed f
LEFT JOIN latest_event le ON le.opportunity_id=f.opportunity_id
LEFT JOIN latest_feedback lf ON lf.opportunity_id=f.opportunity_id
LEFT JOIN feedback_counts fc ON fc.opportunity_id=f.opportunity_id
LEFT JOIN legacy_applied la ON la.opportunity_id=f.opportunity_id
WHERE public.opos_is_founder();

CREATE OR REPLACE FUNCTION public.founder_dashboard_daily(
  p_days integer DEFAULT 7,
  p_high_fit_threshold double precision DEFAULT 80
)
RETURNS TABLE(
  date date, fetched integer, unique_new integer, qualified integer,
  high_fit integer, opened integer, labelled integer, applied integer,
  hidden_by_filters integer
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  IF NOT public.opos_is_founder() THEN
    RAISE EXCEPTION 'authorized founder required';
  END IF;
  IF p_days IS NULL OR p_days < 0 OR p_days > 3650 THEN
    RAISE EXCEPTION 'days must be between 0 and 3650 (0 means all time)';
  END IF;
  IF p_high_fit_threshold IS NULL
     OR p_high_fit_threshold <> p_high_fit_threshold
     OR p_high_fit_threshold < 0 OR p_high_fit_threshold > 100 THEN
    RAISE EXCEPTION 'high fit threshold must be between 0 and 100';
  END IF;
  RETURN QUERY
  WITH first_day AS (
    SELECT CASE WHEN p_days = 0 THEN coalesce(
      (SELECT min(day) FROM (
        SELECT min(r.started_at::date) AS day FROM source_poll_runs r
        UNION ALL SELECT min(o.created_at::date) FROM opportunities o
        UNION ALL SELECT min(e.evaluated_at::date) FROM match_evaluations e
        UNION ALL SELECT min(v.viewed_at::date) FROM founder_opportunity_views v
        UNION ALL SELECT min(f.created_at::date) FROM founder_feedback f
        UNION ALL SELECT min(a.created_at::date) FROM outbound_actions a
      ) AS first_dates), current_date)
    ELSE current_date - (p_days - 1) END AS day
  ), calendar AS (
    SELECT generate_series(first_day.day, current_date, interval '1 day')::date AS day
    FROM first_day
  ), polls AS (
    SELECT r.started_at::date AS day, sum(r.raw_ingested)::integer AS fetched
    FROM source_poll_runs r CROSS JOIN first_day b
    WHERE r.started_at >= b.day AND r.started_at < current_date + 1
    GROUP BY 1
  ), new_opportunities AS (
    SELECT o.created_at::date AS day, count(*)::integer AS unique_new
    FROM opportunities o CROSS JOIN first_day b
    WHERE o.created_at >= b.day AND o.created_at < current_date + 1
    GROUP BY 1
  ), evaluations AS (
    SELECT e.evaluated_at::date AS day,
      count(*) FILTER (WHERE e.qualification_decision = 'qualified')::integer AS qualified,
      count(*) FILTER (WHERE e.fit_score >= p_high_fit_threshold)::integer AS high_fit
    FROM match_evaluations e CROSS JOIN first_day b
    WHERE e.evaluated_at >= b.day AND e.evaluated_at < current_date + 1
    GROUP BY 1
  ), opened AS (
    SELECT v.viewed_at::date AS day, count(*)::integer AS opened
    FROM founder_opportunity_views v CROSS JOIN first_day b
    WHERE v.viewed_at >= b.day AND v.viewed_at < current_date + 1
    GROUP BY 1
  ), labelled AS (
    SELECT f.created_at::date AS day, count(*)::integer AS labelled
    FROM founder_feedback f CROSS JOIN first_day b
    WHERE f.created_at >= b.day AND f.created_at < current_date + 1
    GROUP BY 1
  ), applied AS (
    SELECT a.created_at::date AS day, count(*)::integer AS applied
    FROM outbound_actions a CROSS JOIN first_day b
    WHERE a.created_at >= b.day AND a.created_at < current_date + 1
      AND a.action_status = 'submitted'
    GROUP BY 1
  ), hidden AS (
    SELECT f.opportunity_created_at::date AS day,
      count(DISTINCT f.opportunity_id)::integer AS hidden_by_filters
    FROM founder_feed f CROSS JOIN first_day b
    WHERE f.opportunity_created_at >= b.day
      AND f.opportunity_created_at < current_date + 1
      AND f.is_stale IS FALSE
      AND f.visibility_reason IS NOT NULL
      AND f.visibility_reason <> ''
      AND EXISTS (
        SELECT 1 FROM regexp_split_to_table(
          replace(replace(replace(replace(replace(f.visibility_reason, '[', ''), ']', ''), '"', ''), '{', ''), '}', ''), ','
        ) AS reason
        WHERE reason <> '' AND reason NOT LIKE 'facet:%'
      )
    GROUP BY 1
  )
  SELECT c.day, coalesce(p.fetched,0), coalesce(n.unique_new,0),
    coalesce(e.qualified,0), coalesce(e.high_fit,0), coalesce(o.opened,0),
    coalesce(l.labelled,0), coalesce(a.applied,0), coalesce(h.hidden_by_filters,0)
  FROM calendar c
  LEFT JOIN polls p ON p.day=c.day
  LEFT JOIN new_opportunities n ON n.day=c.day
  LEFT JOIN evaluations e ON e.day=c.day
  LEFT JOIN opened o ON o.day=c.day
  LEFT JOIN labelled l ON l.day=c.day
  LEFT JOIN applied a ON a.day=c.day
  LEFT JOIN hidden h ON h.day=c.day
  ORDER BY c.day DESC;
END;
$$;

UPDATE alembic_version SET version_num='0029_fr008_query_fast_paths' WHERE alembic_version.version_num = '0028_bc2_recommendation';

COMMIT;

