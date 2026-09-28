BEGIN;

-- Running upgrade 0030_dashboard_alltime -> 0031_source_overview_fastpath

CREATE OR REPLACE VIEW public.founder_source_overview
WITH (security_invoker = true)
AS
WITH automated AS (
  SELECT split_part(s.source_id::text, ':', 1) AS source_family,
         s.source_id,
         counts.opportunity_count,
         counts.hidden_count,
         s.last_success_at,
         s.last_status::text AS last_status,
         s.next_due_at,
         false AS manual_only
    FROM public.source_schedules s
    LEFT JOIN LATERAL (
      SELECT count(fp.opportunity_id)
                 FILTER (WHERE o.is_stale IS FALSE AND fp.visible IS TRUE)::integer
                 AS opportunity_count,
             count(fp.opportunity_id)
                 FILTER (WHERE o.is_stale IS FALSE AND fp.visible IS FALSE)::integer
                 AS hidden_count
        FROM public.feed_projection fp
        JOIN public.opportunities o ON o.id = fp.opportunity_id
       WHERE fp.source_id = s.source_id
    ) counts ON true
), manual AS (
  SELECT families.source_family,
         NULL::varchar(128) AS source_id,
         0::integer AS opportunity_count,
         0::integer AS hidden_count,
         NULL::timestamp without time zone AS last_success_at,
         NULL::text AS last_status,
         NULL::timestamp without time zone AS next_due_at,
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

UPDATE alembic_version SET version_num='0031_source_overview_fastpath' WHERE alembic_version.version_num = '0030_dashboard_alltime';

COMMIT;

