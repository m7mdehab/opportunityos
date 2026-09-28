BEGIN;

-- Running upgrade 0017_founder_activity_correction -> 0018_activity_live_fix

CREATE INDEX IF NOT EXISTS founder_activity_events_opportunity_created_idx ON public.founder_activity_events(opportunity_id, created_at DESC, id DESC);

REVOKE ALL ON public.founder_activity_events FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON public.founder_activity_events FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'REVOKE ALL ON public.founder_activity_events FROM authenticated';
        EXECUTE 'GRANT SELECT ON public.founder_activity_events TO authenticated';
        EXECUTE 'DROP POLICY IF EXISTS founder_activity_events_founder_authenticated_read ON public.founder_activity_events';
        EXECUTE 'CREATE POLICY founder_activity_events_founder_authenticated_read ON public.founder_activity_events FOR SELECT TO authenticated USING (public.opos_is_founder())';
      END IF;
    END $$;

DROP VIEW IF EXISTS public.founder_feed_activity;

DROP VIEW IF EXISTS public.founder_activity_state;

CREATE OR REPLACE VIEW public.founder_activity_state AS
      WITH latest_event AS (
        SELECT DISTINCT ON (e.opportunity_id)
          e.opportunity_id, e.action_type, e.resulting_state, e.snoozed_until, e.created_at
        FROM public.founder_activity_events e
        ORDER BY e.opportunity_id, e.created_at DESC, e.id DESC
      ), latest_feedback AS (
        SELECT DISTINCT ON (f.opportunity_id) f.opportunity_id, f.feedback_label, f.created_at AS feedback_updated_at
        FROM public.founder_feedback f
        ORDER BY f.opportunity_id, f.created_at DESC, f.id DESC
      ), feedback_counts AS (
        SELECT opportunity_id, count(*)::integer AS feedback_count FROM public.founder_feedback GROUP BY opportunity_id
      ), legacy_applied AS (
        SELECT DISTINCT opportunity_id FROM public.outbound_actions WHERE candidate_id='founder' AND adapter_name='founder_attested' AND action_status='submitted'
      )
      SELECT o.id AS opportunity_id,
        CASE
          WHEN le.action_type='snooze' AND le.snoozed_until IS NOT NULL AND le.snoozed_until > CURRENT_DATE THEN 'snoozed'
          WHEN le.action_type IN ('mark_applied','dismiss') THEN le.resulting_state
          WHEN le.action_type IN ('snooze','clear') THEN NULL
          ELSE NULL
        END::varchar AS action_state,
        CASE WHEN le.action_type='snooze' AND le.snoozed_until > CURRENT_DATE THEN le.snoozed_until::timestamp ELSE NULL::timestamp END AS snoozed_until,
        le.created_at AS action_updated_at,
        lf.feedback_label, coalesce(fc.feedback_count,0)::integer AS feedback_count,
        lf.feedback_updated_at,
        (le.opportunity_id IS NOT NULL OR la.opportunity_id IS NOT NULL OR coalesce(fc.feedback_count,0) > 0) AS has_activity
      FROM public.opportunities o
      LEFT JOIN latest_event le ON le.opportunity_id=o.id
      LEFT JOIN latest_feedback lf ON lf.opportunity_id=o.id
      LEFT JOIN feedback_counts fc ON fc.opportunity_id=o.id
      LEFT JOIN legacy_applied la ON la.opportunity_id=o.id
      WHERE public.opos_is_founder();

CREATE OR REPLACE VIEW public.founder_feed_activity
      WITH (security_invoker = true) AS
      SELECT f.*, a.action_state, a.snoozed_until, a.action_updated_at, a.feedback_label,
             a.feedback_count, a.feedback_updated_at, a.has_activity
      FROM public.founder_feed f
      LEFT JOIN public.founder_activity_state a ON a.opportunity_id=f.opportunity_id;

REVOKE ALL ON public.founder_activity_state FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.founder_activity_state FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'GRANT SELECT ON public.founder_activity_state TO authenticated'; END IF;
    END $$;

REVOKE ALL ON public.founder_feed_activity FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.founder_feed_activity FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'GRANT SELECT ON public.founder_feed_activity TO authenticated'; END IF;
    END $$;

CREATE OR REPLACE FUNCTION public.founder_set_action(p_opportunity_id text, p_type text, p_until date DEFAULT NULL)
      RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=public AS $$
      DECLARE now_ts timestamp without time zone := clock_timestamp() AT TIME ZONE 'UTC'; next_state text; event_id text; action_id text := NULL; opp public.opportunities%ROWTYPE; eval public.match_evaluations%ROWTYPE; existing_id text;
      BEGIN
        IF NOT public.opos_is_founder() THEN RAISE EXCEPTION 'authorized founder required'; END IF;
        SELECT * INTO opp FROM public.opportunities WHERE id=p_opportunity_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'opportunity not found'; END IF;
        IF p_type='mark_applied' THEN next_state:='submitted';
        ELSIF p_type='dismiss' THEN next_state:='dismissed';
        ELSIF p_type='snooze' THEN IF p_until IS NULL OR p_until<=CURRENT_DATE THEN RAISE EXCEPTION 'snooze requires a future until date'; END IF; next_state:='snoozed';
        ELSIF p_type='clear' THEN next_state:=NULL;
        ELSE RAISE EXCEPTION 'unknown action type'; END IF;
        IF p_type='mark_applied' THEN
          SELECT id INTO existing_id FROM public.outbound_actions WHERE opportunity_id=p_opportunity_id AND candidate_id='founder' AND adapter_name='founder_attested' AND action_status='submitted' ORDER BY created_at ASC, id ASC LIMIT 1;
          IF existing_id IS NULL THEN
            SELECT * INTO eval FROM public.match_evaluations WHERE opportunity_id=p_opportunity_id ORDER BY evaluated_at DESC LIMIT 1;
            action_id:='founder-attested-'||md5(p_opportunity_id);
            INSERT INTO public.outbound_actions(id,opportunity_id,opportunity_content_hash,workspace,candidate_id,track,source,adapter_name,adapter_version,execution_mode,qualification_decision,match_score_snapshot,artifact_ids_json,artifact_hashes_json,manifest_hash,action_status,idempotency_key,created_at,updated_at)
            VALUES(action_id,p_opportunity_id,opp.content_hash,'default','founder',opp.track,opp.source_id,'founder_attested','1.0','dry_run',coalesce(eval.qualification_decision,'uncertain'),coalesce(eval.fit_score,0),'[]','[]',md5(action_id),'submitted','founder-attested:'||p_opportunity_id,now_ts,now_ts);
          ELSE action_id:=existing_id; END IF;
        END IF;
        IF p_type='clear' THEN
          DELETE FROM public.founder_triage_states WHERE opportunity_id=p_opportunity_id;
        ELSE
          INSERT INTO public.founder_triage_states(opportunity_id,state,snoozed_until,created_at,updated_at) VALUES(p_opportunity_id,next_state,CASE WHEN p_type='snooze' THEN p_until ELSE NULL END,now_ts,now_ts)
          ON CONFLICT(opportunity_id) DO UPDATE SET state=excluded.state,snoozed_until=excluded.snoozed_until,updated_at=excluded.updated_at;
        END IF;
        event_id:='activity-'||md5(p_opportunity_id||':'||p_type||':'||clock_timestamp()::text||':'||random()::text);
        INSERT INTO public.founder_activity_events(id,opportunity_id,action_type,resulting_state,snoozed_until,created_at) VALUES(event_id,p_opportunity_id,p_type,next_state,CASE WHEN p_type='snooze' THEN p_until ELSE NULL END,now_ts);
        RETURN jsonb_build_object('opportunity_id',p_opportunity_id,'action_state',next_state,'action_id',action_id,'until',CASE WHEN p_type='snooze' THEN to_char(p_until,'YYYY-MM-DD') ELSE NULL END,'created_at',now_ts);
      END; $$;

REVOKE ALL ON FUNCTION public.founder_set_action(text, text, date) FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION public.founder_set_action(text, text, date) FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.founder_set_action(text, text, date) TO authenticated';
      END IF;
    END $$;

CREATE OR REPLACE FUNCTION public.founder_add_feedback(p_opportunity_id text, p_label text, p_note text DEFAULT NULL)
      RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=public AS $$
      DECLARE now_ts timestamp without time zone := clock_timestamp() AT TIME ZONE 'UTC'; new_id text; prior public.founder_feedback%ROWTYPE; norm_note text:=nullif(btrim(coalesce(p_note,'')),'');
      BEGIN
        IF NOT public.opos_is_founder() THEN RAISE EXCEPTION 'authorized founder required'; END IF;
        IF NOT EXISTS(SELECT 1 FROM public.opportunities WHERE id=p_opportunity_id) THEN RAISE EXCEPTION 'opportunity not found'; END IF;
        IF p_label NOT IN ('good_match','bad_match','eligibility_wrong','seniority_wrong','irrelevant_role','source_quality_issue','duplicate_issue','review_required') THEN RAISE EXCEPTION 'unknown feedback label'; END IF;
        SELECT * INTO prior FROM public.founder_feedback WHERE opportunity_id=p_opportunity_id ORDER BY created_at DESC,id DESC LIMIT 1;
        IF FOUND AND prior.feedback_label=p_label AND coalesce(prior.notes,'')=coalesce(norm_note,'') THEN RETURN jsonb_build_object('id',prior.id,'opportunity_id',prior.opportunity_id,'feedback_label',prior.feedback_label,'structured_reason',prior.structured_reason,'notes',prior.notes,'created_at',prior.created_at); END IF;
        new_id:='feedback-'||substr(md5(clock_timestamp()::text||random()::text||p_opportunity_id),1,16);
        INSERT INTO public.founder_feedback(id,opportunity_id,feedback_label,structured_reason,notes,dedup_hash,created_at) VALUES(new_id,p_opportunity_id,p_label,p_label,norm_note,md5(new_id),now_ts);
        RETURN jsonb_build_object('id',new_id,'opportunity_id',p_opportunity_id,'feedback_label',p_label,'structured_reason',p_label,'notes',norm_note,'created_at',now_ts);
      END; $$;

REVOKE ALL ON FUNCTION public.founder_add_feedback(text, text, text) FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION public.founder_add_feedback(text, text, text) FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.founder_add_feedback(text, text, text) TO authenticated';
      END IF;
    END $$;

CREATE OR REPLACE FUNCTION public.founder_activity_detail(p_opportunity_id text)
      RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
        SELECT CASE WHEN public.opos_is_founder() THEN jsonb_build_object(
          'action_history', coalesce((SELECT jsonb_agg(jsonb_build_object('action_id',e.id,'action_type',e.action_type,'action_status',e.resulting_state,'until',e.snoozed_until,'created_at',e.created_at) ORDER BY e.created_at DESC,e.id DESC) FROM public.founder_activity_events e WHERE e.opportunity_id=p_opportunity_id),'[]'::jsonb),
          'feedback_history', coalesce((SELECT jsonb_agg(jsonb_build_object('id',f.id,'feedback_label',f.feedback_label,'structured_reason',f.structured_reason,'notes',f.notes,'created_at',f.created_at) ORDER BY f.created_at DESC,f.id DESC) FROM public.founder_feedback f WHERE f.opportunity_id=p_opportunity_id),'[]'::jsonb)
        ) ELSE NULL END
      $$;

REVOKE ALL ON FUNCTION public.founder_activity_detail(text) FROM PUBLIC;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION public.founder_activity_detail(text) FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.founder_activity_detail(text) TO authenticated';
      END IF;
    END $$;

UPDATE alembic_version SET version_num='0018_activity_live_fix' WHERE alembic_version.version_num = '0017_founder_activity_correction';

COMMIT;

