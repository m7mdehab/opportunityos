BEGIN;

-- Running upgrade 0010_hosted_runtime -> 0011_hosted_api_surface

CREATE TABLE founder_cv_selections (
    opportunity_id VARCHAR(64) NOT NULL, 
    variant VARCHAR(64) NOT NULL, 
    object_path VARCHAR(256) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    selected_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    truth_pack_hash VARCHAR(64), 
    PRIMARY KEY (opportunity_id), 
    FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE INDEX ix_founder_cv_selections_sha256 ON public.founder_cv_selections (sha256);

ALTER TABLE public.founder_cv_selections ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'CREATE POLICY founder_cv_selections_browser_deny_anon ON public.founder_cv_selections FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'CREATE POLICY founder_cv_selections_browser_deny_authenticated ON public.founder_cv_selections FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF;
    END $$;

REVOKE ALL ON public.founder_cv_selections FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selections FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selections FROM authenticated'; END IF;
    END $$;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS source_poll_runs_browser_deny_authenticated ON public.source_poll_runs';
            EXECUTE 'DROP POLICY IF EXISTS source_poll_runs_founder_authenticated_read ON public.source_poll_runs';
            EXECUTE 'CREATE POLICY source_poll_runs_founder_authenticated_read ON public.source_poll_runs FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS opportunities_browser_deny_authenticated ON public.opportunities';
            EXECUTE 'DROP POLICY IF EXISTS opportunities_founder_authenticated_read ON public.opportunities';
            EXECUTE 'CREATE POLICY opportunities_founder_authenticated_read ON public.opportunities FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS match_evaluations_browser_deny_authenticated ON public.match_evaluations';
            EXECUTE 'DROP POLICY IF EXISTS match_evaluations_founder_authenticated_read ON public.match_evaluations';
            EXECUTE 'CREATE POLICY match_evaluations_founder_authenticated_read ON public.match_evaluations FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS founder_cv_selections_browser_deny_authenticated ON public.founder_cv_selections';
            EXECUTE 'DROP POLICY IF EXISTS founder_cv_selections_founder_authenticated_read ON public.founder_cv_selections';
            EXECUTE 'CREATE POLICY founder_cv_selections_founder_authenticated_read ON public.founder_cv_selections FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'GRANT SELECT ON public.founder_cv_selections TO authenticated';
      END IF;
    END $$;

CREATE OR REPLACE VIEW public.founder_opportunity_detail WITH (security_invoker = true) AS
      SELECT o.id, o.title, o.organization, o.source_id, o.source_url, o.track,
        o.description, o.deadline, o.posted_date, o.is_stale, o.reverified_at,
        o.work_mode, o.work_mode_source, o.location_country, o.location_city,
        o.location_region, o.remote_scope, o.remote_scope_regions,
        o.employment_type, o.seniority_level, o.compensation_min, o.compensation_max,
        o.compensation_currency, o.compensation_period, o.title_family, o.title_level,
        o.family_key, e.truth_pack_hash, e.qualification_decision, e.fit_score,
        e.dimension_scores_json, e.reasons_json, e.evaluation_detail_json,
        e.policy_version, e.evaluated_at, c.variant AS cv_variant,
        c.object_path AS cv_object_path, c.sha256 AS cv_sha256
      FROM public.opportunities o
      LEFT JOIN LATERAL (SELECT * FROM public.match_evaluations WHERE opportunity_id=o.id ORDER BY evaluated_at DESC LIMIT 1) e ON true
      LEFT JOIN public.founder_cv_selections c ON c.opportunity_id=o.id;

CREATE OR REPLACE VIEW public.founder_cv_selection WITH (security_invoker = true) AS
      SELECT opportunity_id, variant, object_path, sha256, selected_at, truth_pack_hash
      FROM public.founder_cv_selections;

REVOKE ALL ON public.founder_cv_selection FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS ' || 'founder_filter_settings_browser_deny_authenticated' || ' ON public.founder_filter_settings';
            EXECUTE 'CREATE POLICY founder_filter_settings_founder_authenticated_read ON public.founder_filter_settings FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS ' || 'founder_facets_browser_deny_authenticated' || ' ON public.founder_facets';
            EXECUTE 'CREATE POLICY founder_facets_founder_authenticated_read ON public.founder_facets FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS ' || 'founder_saved_views_browser_deny_authenticated' || ' ON public.founder_saved_views';
            EXECUTE 'CREATE POLICY founder_saved_views_founder_authenticated_read ON public.founder_saved_views FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$;

CREATE OR REPLACE VIEW public.founder_filters WITH (security_invoker = true) AS SELECT * FROM public.founder_filter_settings;

REVOKE ALL ON public.founder_filters FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.founder_filters FROM anon'; END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_filters FROM authenticated'; EXECUTE 'GRANT SELECT ON public.founder_filters TO authenticated'; END IF;
        END $$;

CREATE OR REPLACE VIEW public.founder_facet_settings_view WITH (security_invoker = true) AS SELECT * FROM public.founder_facets;

REVOKE ALL ON public.founder_facet_settings_view FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.founder_facet_settings_view FROM anon'; END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_facet_settings_view FROM authenticated'; EXECUTE 'GRANT SELECT ON public.founder_facet_settings_view TO authenticated'; END IF;
        END $$;

CREATE OR REPLACE VIEW public.founder_saved_view_records WITH (security_invoker = true) AS SELECT * FROM public.founder_saved_views;

REVOKE ALL ON public.founder_saved_view_records FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.founder_saved_view_records FROM anon'; END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_saved_view_records FROM authenticated'; EXECUTE 'GRANT SELECT ON public.founder_saved_view_records TO authenticated'; END IF;
        END $$;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selection FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selection FROM authenticated'; EXECUTE 'GRANT SELECT ON public.founder_cv_selection TO authenticated'; END IF;
    END $$;

REVOKE ALL ON public.founder_opportunity_detail FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON public.founder_opportunity_detail FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_opportunity_detail FROM authenticated'; EXECUTE 'GRANT SELECT ON public.founder_opportunity_detail TO authenticated'; END IF;
    END $$;

DROP FUNCTION IF EXISTS public.enqueue_poll_now(text);

CREATE OR REPLACE FUNCTION public.enqueue_poll_now(p_source_id text DEFAULT NULL)
      RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public AS $$
      DECLARE sched public.source_schedules%ROWTYPE; requested text[]; enqueued jsonb := '[]'::jsonb; skipped jsonb := '[]'::jsonb; new_id text; reason text;
      BEGIN
        IF NOT public.opos_is_founder() THEN RAISE EXCEPTION 'authorized founder required'; END IF;
        IF p_source_id IS NOT NULL THEN requested := ARRAY[p_source_id]; ELSE SELECT COALESCE(array_agg(source_id ORDER BY source_id), ARRAY[]::text[]) INTO requested FROM public.source_schedules; END IF;
        IF cardinality(requested)=0 THEN RETURN jsonb_build_object('enqueued',enqueued,'skipped',skipped); END IF;
        FOREACH p_source_id IN ARRAY requested LOOP
          SELECT * INTO sched FROM public.source_schedules WHERE source_id=p_source_id FOR UPDATE;
          IF NOT FOUND THEN skipped := skipped || jsonb_build_array(jsonb_build_object('source_id',p_source_id,'reason','not_scheduled')); CONTINUE; END IF;
          IF EXISTS (SELECT 1 FROM public.worker_jobs w WHERE w.job_type='poll_source' AND w.status IN ('PENDING','RETRY','RUNNING') AND (w.payload_json::jsonb ->> 'source_id')=sched.source_id) THEN reason:='already_queued';
          ELSIF sched.cooldown_until IS NOT NULL AND sched.cooldown_until>now() THEN reason:='cooldown';
          ELSIF sched.next_due_at>now() THEN reason:='not_due'; ELSE reason:=NULL; END IF;
          IF reason IS NOT NULL THEN skipped := skipped || jsonb_build_array(jsonb_build_object('source_id',sched.source_id,'reason',reason)); CONTINUE; END IF;
          new_id := md5(clock_timestamp()::text || random()::text || sched.source_id);
          INSERT INTO public.worker_jobs (id,job_type,payload_json,status,run_after,retry_count,max_retries,created_at,updated_at) VALUES (new_id,'poll_source',json_build_object('source_id',sched.source_id)::text,'PENDING',now(),0,3,now(),now());
          UPDATE public.source_schedules SET last_attempt_at=now(), next_due_at=now()+make_interval(secs=>sched.cadence_hours * 3600.0), updated_at=now() WHERE source_id=sched.source_id;
          enqueued := enqueued || jsonb_build_array(jsonb_build_object('source_id',sched.source_id,'job_id',new_id));
        END LOOP;
        RETURN jsonb_build_object('enqueued',enqueued,'skipped',skipped);
      END; $$;

REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated'; END IF;
    END $$;

UPDATE alembic_version SET version_num='0011_hosted_api_surface' WHERE alembic_version.version_num = '0010_hosted_runtime';

COMMIT;

