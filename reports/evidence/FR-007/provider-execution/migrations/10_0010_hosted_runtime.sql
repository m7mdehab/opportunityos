BEGIN;

-- Running upgrade 0009_hosted_founder_auth -> 0010_hosted_runtime

CREATE TABLE founder_identity (
    id VARCHAR(16) NOT NULL, 
    supabase_user_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_founder_identity_singleton CHECK (id = 'singleton'), 
    UNIQUE (supabase_user_id)
);

CREATE UNIQUE INDEX ix_founder_identity_supabase_user_id ON founder_identity (supabase_user_id);

ALTER TABLE public.founder_identity ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.opos_is_founder()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM public.founder_identity
                WHERE id = 'singleton'
                  AND supabase_user_id = NULLIF(
                      current_setting('request.jwt.claim.sub', true), ''
                  )
            )
        $$;

CREATE OR REPLACE VIEW public.founder_feed
        WITH (security_invoker = true)
        AS
        SELECT
            id, opportunity_id, opportunity_content_hash, truth_pack_hash,
            projection_version, title, organization, source_id, source_url,
            posted_date, track, opportunity_type, title_family,
            seniority_level, work_mode, location_country, location_city,
            location_region, remote_scope, remote_scope_regions,
            employment_type, qualification_decision, fit_score, priority_score,
            reasons_json, red_line_match, excluded_industry_match, visible,
            visibility_reason, evaluated_at, projected_at
        FROM public.feed_projection;

CREATE OR REPLACE VIEW public.founder_source_health
        WITH (security_invoker = true)
        AS
        SELECT
            s.source_id, s.next_due_at, s.cooldown_until,
            s.consecutive_failures, s.last_status, s.last_success_at,
            s.updated_at,
            r.started_at AS last_poll_started_at,
            r.finished_at AS last_poll_finished_at,
            r.status AS last_poll_status
        FROM public.source_schedules AS s
        LEFT JOIN LATERAL (
            SELECT started_at, finished_at, status
            FROM public.source_poll_runs
            WHERE source_id = s.source_id
            ORDER BY started_at DESC
            LIMIT 1
        ) AS r ON true;

CREATE OR REPLACE VIEW public.founder_artifact_metadata
        WITH (security_invoker = true)
        AS
        SELECT
            cache_key, opportunity_id, truth_pack_hash, template_id,
            artifact_kind, content_type, storage_backend, object_key,
            payload_sha256, size_bytes, generation_version, created_at
        FROM public.artifact_cache;

DROP POLICY IF EXISTS feed_projection_browser_deny_authenticated ON public.feed_projection;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'CREATE POLICY feed_projection_founder_authenticated_read '
                     || 'ON public.feed_projection FOR SELECT TO authenticated '
                     || 'USING (public.opos_is_founder())';
              END IF;
            END $$;

DROP POLICY IF EXISTS source_schedules_browser_deny_authenticated ON public.source_schedules;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'CREATE POLICY source_schedules_founder_authenticated_read '
                     || 'ON public.source_schedules FOR SELECT TO authenticated '
                     || 'USING (public.opos_is_founder())';
              END IF;
            END $$;

DROP POLICY IF EXISTS source_poll_runs_browser_deny_authenticated ON public.source_poll_runs;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'CREATE POLICY source_poll_runs_founder_authenticated_read '
                     || 'ON public.source_poll_runs FOR SELECT TO authenticated '
                     || 'USING (public.opos_is_founder())';
              END IF;
            END $$;

DROP POLICY IF EXISTS artifact_cache_browser_deny_authenticated ON public.artifact_cache;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'CREATE POLICY artifact_cache_founder_authenticated_read '
                     || 'ON public.artifact_cache FOR SELECT TO authenticated '
                     || 'USING (public.opos_is_founder())';
              END IF;
            END $$;

REVOKE ALL ON public.founder_feed FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_feed FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_feed FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_feed TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_source_health FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_source_health FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_source_health FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_source_health TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_artifact_metadata FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_artifact_metadata FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_artifact_metadata FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_artifact_metadata TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_identity FROM PUBLIC;

REVOKE ALL ON public.worker_jobs FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL ON public.founder_identity FROM anon';
            EXECUTE 'REVOKE ALL ON public.worker_jobs FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'REVOKE ALL ON public.founder_identity FROM authenticated';
            EXECUTE 'REVOKE ALL ON public.worker_jobs FROM authenticated';
          END IF;
        END $$;

DO $$ BEGIN
          IF to_regclass('storage.objects') IS NOT NULL THEN
            EXECUTE 'DROP POLICY IF EXISTS founder_private_cv_select ON storage.objects';
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
              EXECUTE 'CREATE POLICY founder_private_cv_select ON storage.objects '
                   || 'FOR SELECT TO authenticated USING '
                   || '(bucket_id = ''founder-cv-portfolio'' AND public.opos_is_founder())';
            END IF;
            EXECUTE 'DROP POLICY IF EXISTS founder_private_artifact_select ON storage.objects';
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
              EXECUTE 'CREATE POLICY founder_private_artifact_select ON storage.objects '
                   || 'FOR SELECT TO authenticated USING '
                   || '(bucket_id = ''opportunity-artifacts'' AND public.opos_is_founder())';
            END IF;
          END IF;
        END $$;

CREATE OR REPLACE FUNCTION public.poll_job_status(p_job_id text)
        RETURNS TABLE(
            job_id text, job_type text, status text, run_after timestamptz,
            retry_count integer, error_present boolean
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT id, job_type, status, run_after AT TIME ZONE 'UTC',
                   retry_count, (error_message IS NOT NULL)
            FROM public.worker_jobs
            WHERE id = p_job_id AND public.opos_is_founder()
        $$;

REVOKE ALL ON FUNCTION public.poll_job_status(text) FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL ON FUNCTION public.poll_job_status(text) FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'GRANT EXECUTE ON FUNCTION public.poll_job_status(text) TO authenticated';
          END IF;
        END $$;

CREATE OR REPLACE FUNCTION public.enqueue_poll_now(p_source_id text DEFAULT NULL)
        RETURNS TABLE(job_id text, job_type text, status text)
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            sched public.source_schedules%ROWTYPE;
            new_id text;
            payload text;
        BEGIN
            IF NOT public.opos_is_founder() THEN
                RAISE EXCEPTION 'authorized founder required';
            END IF;

            FOR sched IN
                SELECT s.*
                FROM public.source_schedules AS s
                WHERE (p_source_id IS NULL OR s.source_id = p_source_id)
                  AND s.next_due_at <= now()
                  AND (s.cooldown_until IS NULL OR s.cooldown_until <= now())
                ORDER BY s.source_id
                FOR UPDATE SKIP LOCKED
            LOOP
                -- Payload is canonical JSON and is inspected for the same
                -- source-level active-job dedupe used by worker.scheduler.
                IF EXISTS (
                    SELECT 1
                    FROM public.worker_jobs AS w
                    WHERE w.job_type = 'poll_source'
                      AND w.status IN ('PENDING', 'RETRY', 'RUNNING')
                      AND (w.payload_json::jsonb ->> 'source_id') = sched.source_id
                ) THEN
                    CONTINUE;
                END IF;

                new_id := md5(clock_timestamp()::text || random()::text || sched.source_id);
                payload := json_build_object('source_id', sched.source_id)::text;
                INSERT INTO public.worker_jobs
                    (id, job_type, payload_json, status, run_after, retry_count,
                     max_retries, created_at, updated_at)
                VALUES
                    (new_id, 'poll_source', payload, 'PENDING', now(), 0, 3,
                     now(), now());

                UPDATE public.source_schedules
                SET last_attempt_at = now(),
                    next_due_at = now() + make_interval(secs => sched.cadence_hours * 3600.0),
                    updated_at = now()
                WHERE source_id = sched.source_id;

                job_id := new_id;
                job_type := 'poll_source';
                status := 'PENDING';
                RETURN NEXT;
            END LOOP;
        END;
        $$;

REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated';
          END IF;
        END $$;

UPDATE alembic_version SET version_num='0010_hosted_runtime' WHERE alembic_version.version_num = '0009_hosted_founder_auth';

COMMIT;

