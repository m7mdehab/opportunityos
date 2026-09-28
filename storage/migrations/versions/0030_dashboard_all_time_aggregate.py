"""Return dashboard all-time metrics as one aggregate row."""
from typing import Sequence, Union

from alembic import op


revision: str = "0030_dashboard_alltime"
down_revision: Union[str, None] = "0029_fr008_query_fast_paths"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FOUNDER_DASHBOARD_DAILY = r"""
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
    SELECT CASE WHEN p_days = 0 THEN current_date ELSE f.opportunity_created_at::date END AS day,
      count(*)::integer AS hidden_by_filters
    FROM founder_feed f CROSS JOIN first_day b
    WHERE (p_days = 0 OR f.opportunity_created_at >= b.day)
      AND f.opportunity_created_at < current_date + 1
      AND f.is_stale IS FALSE
      AND f.visibility_reason IS NOT NULL
      AND f.visibility_reason <> ''
      AND EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(f.visibility_reason::jsonb) AS reason(value)
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
$$
"""


_FOUNDER_DASHBOARD_DAILY_PREVIOUS = r"""
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
$$
"""


def upgrade() -> None:
    op.execute(_FOUNDER_DASHBOARD_DAILY)


def downgrade() -> None:
    op.execute(_FOUNDER_DASHBOARD_DAILY_PREVIOUS)
