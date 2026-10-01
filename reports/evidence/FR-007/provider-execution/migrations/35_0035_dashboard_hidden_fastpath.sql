BEGIN;

-- Running upgrade 0034_opportunity_created_at -> 0035_dashboard_hidden_fastpath

CREATE INDEX ix_feed_projection_hidden_reason ON feed_projection (opportunity_id) INCLUDE (visibility_reason) WHERE visible IS FALSE AND visibility_reason IS NOT NULL AND visibility_reason <> '';

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
    SELECT CASE WHEN p_days = 0 THEN current_date
      ELSE current_date - (p_days - 1) END AS day
  ), calendar AS (
    SELECT current_date AS day WHERE p_days = 0
    UNION ALL
    SELECT generate_series(b.day, current_date, interval '1 day')::date
    FROM first_day b WHERE p_days > 0
  ), polls AS (
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE r.started_at::date END AS day,
      sum(r.raw_ingested)::integer AS fetched
    FROM source_poll_runs r CROSS JOIN first_day b
    WHERE (p_days = 0 OR r.started_at >= b.day)
      AND r.started_at < current_date + 1
    GROUP BY 1
  ), new_opportunities AS (
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE o.created_at::date END AS day,
      count(*)::integer AS unique_new
    FROM opportunities o CROSS JOIN first_day b
    WHERE (p_days = 0 OR o.created_at >= b.day)
      AND o.created_at < current_date + 1
    GROUP BY 1
  ), evaluations AS (
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE e.evaluated_at::date END AS day,
      count(*) FILTER (WHERE e.qualification_decision = 'qualified')::integer AS qualified,
      count(*) FILTER (WHERE e.fit_score >= p_high_fit_threshold)::integer AS high_fit
    FROM match_evaluations e CROSS JOIN first_day b
    WHERE (p_days = 0 OR e.evaluated_at >= b.day)
      AND e.evaluated_at < current_date + 1
    GROUP BY 1
  ), opened AS (
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE v.viewed_at::date END AS day,
      count(*)::integer AS opened
    FROM founder_opportunity_views v CROSS JOIN first_day b
    WHERE (p_days = 0 OR v.viewed_at >= b.day)
      AND v.viewed_at < current_date + 1
    GROUP BY 1
  ), labelled AS (
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE f.created_at::date END AS day,
      count(*)::integer AS labelled
    FROM founder_feedback f CROSS JOIN first_day b
    WHERE (p_days = 0 OR f.created_at >= b.day)
      AND f.created_at < current_date + 1
    GROUP BY 1
  ), applied AS (
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE a.created_at::date END AS day,
      count(*)::integer AS applied
    FROM outbound_actions a CROSS JOIN first_day b
    WHERE (p_days = 0 OR a.created_at >= b.day)
      AND a.created_at < current_date + 1
      AND a.action_status = 'submitted'
    GROUP BY 1
  ), hidden AS (
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE o.created_at::date END AS day,
      count(*)::integer AS hidden_by_filters
    FROM feed_projection fp
    JOIN opportunities o ON o.id = fp.opportunity_id
    CROSS JOIN first_day b
    WHERE (p_days = 0 OR o.created_at >= b.day)
      AND o.created_at < current_date + 1
      AND o.is_stale IS FALSE
      AND fp.visible IS FALSE
      AND fp.visibility_reason IS NOT NULL
      AND fp.visibility_reason <> ''
      AND EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(fp.visibility_reason::jsonb) AS reason(value)
        WHERE reason.value <> '' AND reason.value NOT LIKE 'facet:%'
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

UPDATE alembic_version SET version_num='0035_dashboard_hidden_fastpath' WHERE alembic_version.version_num = '0034_opportunity_created_at';

COMMIT;

