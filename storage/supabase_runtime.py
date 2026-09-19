"""Deterministic hosted Supabase runtime contract used by tests and tooling.

Alembic migration 0010_hosted_runtime is schema authority. This module mirrors
its narrow browser surface without connecting to a provider or reading secrets.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

RUNTIME_CONTRACT_VERSION = "w17-r1-runtime-v2"


@dataclass(frozen=True)
class SupabaseRuntimeContract:
    feed_view: str = "founder_feed"
    enqueue_function: str = "enqueue_poll_now"
    job_status_function: str = "poll_job_status"
    cv_bucket: str = "founder-cv-portfolio"
    artifact_bucket: str = "opportunity-artifacts"


def render_runtime_sql(contract: SupabaseRuntimeContract | None = None) -> str:
    c = contract or SupabaseRuntimeContract()
    for value in (c.feed_view, c.enqueue_function, c.job_status_function):
        if not value.replace("_", "").isalnum() or not value.islower():
            raise ValueError("runtime SQL identifiers must be lowercase names")
    return f"""-- OpportunityOS {RUNTIME_CONTRACT_VERSION}; generated, no secrets
CREATE OR REPLACE VIEW public.{c.feed_view}
WITH (security_invoker = true)
AS
SELECT DISTINCT ON (opportunity_id)
    id, opportunity_id, opportunity_content_hash, truth_pack_hash,
    projection_version, title, organization, source_id, source_url,
    posted_date, deadline, is_stale, reverified_at, description, track,
    opportunity_type, title_family, seniority_level, work_mode,
    location_country, location_city, location_region, remote_scope,
    remote_scope_regions, employment_type, qualification_decision, fit_score,
    priority_score, reasons_json, dimension_scores_json, evaluation_detail_json,
    policy_version, selected_cv_variant, selected_cv_object_path,
    selected_cv_sha256, red_line_match, excluded_industry_match, visible,
    visibility_reason, evaluated_at, projected_at
FROM public.feed_projection
ORDER BY opportunity_id, projected_at DESC, evaluated_at DESC;

GRANT SELECT ON public.{c.feed_view} TO authenticated;
REVOKE ALL ON public.{c.feed_view} FROM anon;

CREATE OR REPLACE FUNCTION public.{c.enqueue_function}(p_source_id text DEFAULT NULL)
RETURNS TABLE(job_id text, job_type text, status text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE sched public.source_schedules%ROWTYPE; new_id text; payload text;
BEGIN
    IF NOT public.opos_is_founder() THEN RAISE EXCEPTION 'authorized founder required'; END IF;
    FOR sched IN
        SELECT s.* FROM public.source_schedules AS s
        WHERE (p_source_id IS NULL OR s.source_id = p_source_id)
          AND s.read_allowed = true
          AND s.next_due_at <= now()
          AND (s.cooldown_until IS NULL OR s.cooldown_until <= now())
        ORDER BY s.next_due_at, s.source_id
        LIMIT 16
        FOR UPDATE SKIP LOCKED
    LOOP
        IF EXISTS (
            SELECT 1 FROM public.worker_jobs AS w
            WHERE w.job_type = 'poll_source'
              AND w.status IN ('PENDING', 'RETRY', 'RUNNING')
              AND (w.payload_json::jsonb ->> 'source_id') = sched.source_id
        ) THEN CONTINUE; END IF;
        new_id := md5(clock_timestamp()::text || random()::text || sched.source_id);
        payload := json_build_object('source_id', sched.source_id)::text;
        INSERT INTO public.worker_jobs
            (id, job_type, payload_json, status, run_after, retry_count,
             max_retries, created_at, updated_at)
        VALUES (new_id, 'poll_source', payload, 'PENDING', now(), 0, 3, now(), now());
        UPDATE public.source_schedules
           SET last_attempt_at = now(),
               next_due_at = now() + make_interval(hours => sched.cadence_hours),
               updated_at = now()
         WHERE source_id = sched.source_id;
        job_id := new_id; job_type := 'poll_source'; status := 'PENDING';
        RETURN NEXT;
    END LOOP;
END;
$$;
REVOKE ALL ON FUNCTION public.{c.enqueue_function}(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.{c.enqueue_function}(text) TO authenticated;

CREATE OR REPLACE FUNCTION public.{c.job_status_function}(p_job_id text)
RETURNS TABLE(job_id text, job_type text, status text, run_after timestamptz,
              retry_count integer, error_present boolean)
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
AS $$
    SELECT id, job_type, status, run_after AT TIME ZONE 'UTC', retry_count,
           (error_message IS NOT NULL)
      FROM public.worker_jobs
     WHERE id = p_job_id AND public.opos_is_founder()
$$;
REVOKE ALL ON FUNCTION public.{c.job_status_function}(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.{c.job_status_function}(text) TO authenticated;
"""


def runtime_sql_sha256(contract: SupabaseRuntimeContract | None = None) -> str:
    return hashlib.sha256(render_runtime_sql(contract).encode("utf-8")).hexdigest()


def assert_runtime_schema_capabilities(connection) -> None:
    required = {"feed_projection", "worker_jobs", "source_schedules"}
    rows = connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' "
        "AND table_name IN ('feed_projection', 'worker_jobs', 'source_schedules')"
    )
    present = {str(row[0]) for row in rows}
    missing = sorted(required - present)
    if missing:
        raise RuntimeError("Supabase runtime schema is missing: " + ", ".join(missing))
