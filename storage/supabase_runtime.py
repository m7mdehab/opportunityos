"""Provider-neutral Supabase runtime SQL contract.

Repository migrations remain schema authority. This module contains the small
SQL surface enabling authenticated feed reads and asynchronous Poll Now.
Importing it never connects to a database or reads credentials.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass

RUNTIME_CONTRACT_VERSION = "w17-runtime-v1"

@dataclass(frozen=True)
class SupabaseRuntimeContract:
    feed_view: str = "founder_feed"
    enqueue_function: str = "enqueue_poll_now"
    job_status_function: str = "poll_job_status"
    truth_pack_bucket: str = "founder-truth-pack"
    artifact_bucket: str = "opportunity-artifacts"

def render_runtime_sql(contract: SupabaseRuntimeContract | None = None) -> str:
    """Return deterministic PostgreSQL SQL for the hosted runtime boundary."""
    c = contract or SupabaseRuntimeContract()
    for value in (c.feed_view, c.enqueue_function, c.job_status_function):
        if not value.replace("_", "").isalnum() or not value.islower():
            raise ValueError("runtime SQL identifiers must be lowercase names")
    return f"""-- OpportunityOS {RUNTIME_CONTRACT_VERSION}; generated, no secrets
-- Apply after Alembic head. This file contains no psql meta-commands.

CREATE OR REPLACE VIEW public.{c.feed_view}
WITH (security_invoker = true)
AS
SELECT
    id, opportunity_id, opportunity_content_hash, truth_pack_hash,
    projection_version, title, organization, source_id, source_url, posted_date,
    track, opportunity_type, title_family, seniority_level, work_mode,
    location_country, location_city, location_region, remote_scope,
    remote_scope_regions, employment_type, qualification_decision, fit_score,
    priority_score, reasons_json, red_line_match, excluded_industry_match,
    visible, visibility_reason, evaluated_at, projected_at
FROM public.feed_projection;

GRANT SELECT ON public.{c.feed_view} TO authenticated;
REVOKE ALL ON public.{c.feed_view} FROM anon;

DROP POLICY IF EXISTS feed_projection_authenticated_read ON public.feed_projection;
CREATE POLICY feed_projection_authenticated_read
    ON public.feed_projection FOR SELECT TO authenticated
    USING (public.opos_is_founder());

CREATE OR REPLACE FUNCTION public.{c.enqueue_function}(p_source_id text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    selected public.source_schedules%ROWTYPE;
    enqueued jsonb := '[]'::jsonb;
    skipped jsonb := '[]'::jsonb;
    new_id text;
BEGIN
    IF NOT public.opos_is_founder() THEN RAISE EXCEPTION 'authorized founder required'; END IF;
    FOR selected IN SELECT * FROM public.source_schedules
      WHERE p_source_id IS NULL OR source_id = p_source_id
      ORDER BY source_id FOR UPDATE SKIP LOCKED
    LOOP
      IF EXISTS (SELECT 1 FROM public.worker_jobs w WHERE w.job_type='poll_source'
                 AND w.status IN ('PENDING','RETRY','RUNNING')
                 AND (w.payload_json::jsonb ->> 'source_id')=selected.source_id) THEN
        skipped := skipped || jsonb_build_array(jsonb_build_object('source_id', selected.source_id, 'reason', 'already_queued'));
      ELSIF selected.cooldown_until IS NOT NULL AND selected.cooldown_until > now() THEN
        skipped := skipped || jsonb_build_array(jsonb_build_object('source_id', selected.source_id, 'reason', 'cooldown'));
      ELSIF selected.next_due_at > now() THEN
        skipped := skipped || jsonb_build_array(jsonb_build_object('source_id', selected.source_id, 'reason', 'not_due'));
      ELSE
        new_id := md5(clock_timestamp()::text || random()::text || selected.source_id);
        INSERT INTO public.worker_jobs (id, job_type, payload_json, status, run_after, retry_count, max_retries, created_at, updated_at)
        VALUES (new_id, 'poll_source', json_build_object('source_id', selected.source_id)::text, 'PENDING', now(), 0, 3, now(), now());
        UPDATE public.source_schedules SET last_attempt_at=now(), next_due_at=now()+make_interval(hours=>selected.cadence_hours), updated_at=now() WHERE source_id=selected.source_id;
        enqueued := enqueued || jsonb_build_array(jsonb_build_object('source_id', selected.source_id, 'job_id', new_id));
      END IF;
    END LOOP;
    RETURN jsonb_build_object('enqueued', enqueued, 'skipped', skipped);
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
    """Read-only check for the canonical tables required by the SQL."""
    required = {"feed_projection", "worker_jobs"}
    rows = connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name IN ('feed_projection', 'worker_jobs')"
    )
    present = {str(row[0]) for row in rows}
    missing = sorted(required - present)
    if missing:
        raise RuntimeError("Supabase runtime schema is missing: " + ", ".join(missing))
