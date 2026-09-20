"""0016_founder_activity

Persistent Founder action/feedback state for the hosted feed.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016_founder_activity"
down_revision: Union[str, None] = "0015_hosted_founder_surface"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D3_FILTER_SEED_OVERRIDES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    # Restore Founder-only SELECT access to the three activity tables. Direct
    # browser writes remain unavailable; mutations go through narrow
    # SECURITY DEFINER RPCs below.
    for table in ("founder_triage_states", "founder_feedback", "outbound_actions"):
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON public.{table}';
            EXECUTE 'DROP POLICY IF EXISTS {table}_founder_authenticated_read ON public.{table}';
            EXECUTE 'CREATE POLICY {table}_founder_authenticated_read ON public.{table} FOR SELECT TO authenticated USING (public.opos_is_founder())';
            EXECUTE 'GRANT SELECT ON public.{table} TO authenticated';
          END IF;
        END $$""")

    op.execute("""
      CREATE OR REPLACE VIEW public.founder_activity_state
      WITH (security_invoker = true)
      AS
      WITH latest_feedback AS (
        SELECT DISTINCT ON (f.opportunity_id)
               f.opportunity_id,
               f.feedback_label,
               f.created_at AS feedback_updated_at
          FROM public.founder_feedback f
         ORDER BY f.opportunity_id, f.created_at DESC, f.id DESC
      ), feedback_counts AS (
        SELECT opportunity_id, count(*)::integer AS feedback_count
          FROM public.founder_feedback
         GROUP BY opportunity_id
      ), latest_applied AS (
        SELECT opportunity_id, max(created_at) AS applied_at
          FROM public.outbound_actions
         WHERE action_status = 'submitted'
         GROUP BY opportunity_id
      )
      SELECT
        o.id AS opportunity_id,
        CASE
          WHEN t.state = 'snoozed'
           AND t.snoozed_until IS NOT NULL
           AND t.snoozed_until <= now()
            THEN CASE WHEN a.applied_at IS NOT NULL THEN 'submitted' ELSE NULL END
          WHEN t.state IS NOT NULL THEN t.state
          WHEN a.applied_at IS NOT NULL THEN 'submitted'
          ELSE NULL
        END::varchar AS action_state,
        CASE
          WHEN t.state = 'snoozed'
           AND t.snoozed_until IS NOT NULL
           AND t.snoozed_until > now()
            THEN t.snoozed_until
          ELSE NULL
        END AS snoozed_until,
        greatest(t.updated_at, a.applied_at) AS action_updated_at,
        lf.feedback_label,
        coalesce(fc.feedback_count, 0)::integer AS feedback_count,
        lf.feedback_updated_at,
        (
          t.state IS NOT NULL
          OR a.applied_at IS NOT NULL
          OR coalesce(fc.feedback_count, 0) > 0
        ) AS has_activity
      FROM public.opportunities o
      LEFT JOIN public.founder_triage_states t ON t.opportunity_id = o.id
      LEFT JOIN latest_applied a ON a.opportunity_id = o.id
      LEFT JOIN latest_feedback lf ON lf.opportunity_id = o.id
      LEFT JOIN feedback_counts fc ON fc.opportunity_id = o.id
    """)

    op.execute("""
      CREATE OR REPLACE VIEW public.founder_feed_activity
      WITH (security_invoker = true)
      AS
      SELECT
        f.*,
        a.action_state,
        a.snoozed_until,
        a.action_updated_at,
        a.feedback_label,
        a.feedback_count,
        a.feedback_updated_at,
        a.has_activity
      FROM public.founder_feed f
      LEFT JOIN public.founder_activity_state a
        ON a.opportunity_id = f.opportunity_id
    """)

    for view in ("founder_activity_state", "founder_feed_activity"):
        op.execute(f"REVOKE ALL ON public.{view} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            EXECUTE 'REVOKE ALL ON public.{view} FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'REVOKE ALL ON public.{view} FROM authenticated';
            EXECUTE 'GRANT SELECT ON public.{view} TO authenticated';
          END IF;
        END $$""")

    op.execute("""
      CREATE OR REPLACE FUNCTION public.founder_set_action(
        p_opportunity_id text,
        p_type text,
        p_until date DEFAULT NULL
      )
      RETURNS jsonb
      LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public
      AS $$
      DECLARE
        now_ts timestamp without time zone := now() AT TIME ZONE 'UTC';
        until_ts timestamp without time zone;
        next_state text;
        action_id text := NULL;
        opp public.opportunities%ROWTYPE;
        eval public.match_evaluations%ROWTYPE;
        current_state text;
      BEGIN
        IF NOT public.opos_is_founder() THEN
          RAISE EXCEPTION 'authorized founder required';
        END IF;

        SELECT * INTO opp
          FROM public.opportunities
         WHERE id = p_opportunity_id;
        IF NOT FOUND THEN
          RAISE EXCEPTION 'opportunity not found';
        END IF;

        SELECT state INTO current_state
          FROM public.founder_triage_states
         WHERE opportunity_id = p_opportunity_id;

        IF p_type = 'mark_applied' THEN
          next_state := 'submitted';
        ELSIF p_type = 'dismiss' THEN
          next_state := 'dismissed';
        ELSIF p_type = 'snooze' THEN
          IF p_until IS NULL OR p_until <= current_date THEN
            RAISE EXCEPTION 'snooze requires a future until date';
          END IF;
          next_state := 'snoozed';
          until_ts := p_until::timestamp;
        ELSE
          RAISE EXCEPTION 'unknown action type';
        END IF;

        INSERT INTO public.founder_triage_states
          (opportunity_id, state, snoozed_until, created_at, updated_at)
        VALUES
          (p_opportunity_id, next_state, until_ts, now_ts, now_ts)
        ON CONFLICT (opportunity_id) DO UPDATE
          SET state = excluded.state,
              snoozed_until = excluded.snoozed_until,
              updated_at = excluded.updated_at;

        IF p_type = 'mark_applied' AND current_state IS DISTINCT FROM 'submitted' THEN
          SELECT * INTO eval
            FROM public.match_evaluations
           WHERE opportunity_id = p_opportunity_id
           ORDER BY evaluated_at DESC
           LIMIT 1;

          action_id := 'action-' || substr(md5(clock_timestamp()::text || random()::text || p_opportunity_id), 1, 16);

          INSERT INTO public.outbound_actions (
            id, opportunity_id, opportunity_content_hash, workspace,
            candidate_id, track, source, adapter_name, adapter_version,
            execution_mode, qualification_decision, match_score_snapshot,
            artifact_ids_json, artifact_hashes_json, manifest_hash,
            action_status, idempotency_key, created_at, updated_at
          ) VALUES (
            action_id,
            p_opportunity_id,
            opp.content_hash,
            'default',
            'founder',
            opp.track,
            opp.source_id,
            'founder_attested',
            '1.0',
            'dry_run',
            coalesce(eval.qualification_decision, 'uncertain'),
            coalesce(eval.fit_score, 0.0),
            '[]',
            '[]',
            md5('founder-attested:' || p_opportunity_id || ':' || now_ts::text) ||
              md5('manifest:' || p_opportunity_id || ':' || now_ts::text),
            'submitted',
            'founder-attested:' || p_opportunity_id || ':' || md5(clock_timestamp()::text || random()::text),
            now_ts,
            now_ts
          );
        END IF;

        IF p_type = 'mark_applied' AND action_id IS NULL THEN
          SELECT id INTO action_id
            FROM public.outbound_actions
           WHERE opportunity_id = p_opportunity_id
             AND action_status = 'submitted'
           ORDER BY created_at DESC
           LIMIT 1;
        END IF;

        RETURN jsonb_build_object(
          'opportunity_id', p_opportunity_id,
          'action_state', next_state,
          'action_id', action_id,
          'until', CASE WHEN until_ts IS NULL THEN NULL ELSE to_char(until_ts, 'YYYY-MM-DD') END,
          'created_at', now_ts
        );
      END;
      $$
    """)

    op.execute("""
      CREATE OR REPLACE FUNCTION public.founder_add_feedback(
        p_opportunity_id text,
        p_label text,
        p_note text DEFAULT NULL
      )
      RETURNS jsonb
      LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public
      AS $$
      DECLARE
        now_ts timestamp without time zone := now() AT TIME ZONE 'UTC';
        new_id text;
        norm_note text := nullif(btrim(coalesce(p_note, '')), '');
        dedup text;
        prior public.founder_feedback%ROWTYPE;
      BEGIN
        IF NOT public.opos_is_founder() THEN
          RAISE EXCEPTION 'authorized founder required';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM public.opportunities WHERE id = p_opportunity_id) THEN
          RAISE EXCEPTION 'opportunity not found';
        END IF;
        IF p_label NOT IN (
          'good_match','bad_match','eligibility_wrong','seniority_wrong',
          'irrelevant_role','source_quality_issue','duplicate_issue','review_required'
        ) THEN
          RAISE EXCEPTION 'unknown feedback label';
        END IF;

        SELECT * INTO prior
          FROM public.founder_feedback
         WHERE opportunity_id = p_opportunity_id
         ORDER BY created_at DESC, id DESC
         LIMIT 1;

        IF FOUND
           AND prior.feedback_label = p_label
           AND coalesce(prior.notes, '') = coalesce(norm_note, '') THEN
          RETURN jsonb_build_object(
            'id', prior.id,
            'opportunity_id', prior.opportunity_id,
            'feedback_label', prior.feedback_label,
            'structured_reason', prior.structured_reason,
            'notes', prior.notes,
            'created_at', prior.created_at
          );
        END IF;

        new_id := 'feedback-' || substr(md5(clock_timestamp()::text || random()::text || p_opportunity_id), 1, 16);
        dedup := md5(p_opportunity_id || ':' || p_label || ':' || coalesce(norm_note, '') || ':' || now_ts::text);

        INSERT INTO public.founder_feedback (
          id, opportunity_id, feedback_label, structured_reason, notes,
          dedup_hash, created_at
        ) VALUES (
          new_id, p_opportunity_id, p_label, p_label, norm_note, dedup, now_ts
        );

        RETURN jsonb_build_object(
          'id', new_id,
          'opportunity_id', p_opportunity_id,
          'feedback_label', p_label,
          'structured_reason', p_label,
          'notes', norm_note,
          'created_at', now_ts
        );
      END;
      $$
    """)

    for signature in (
        "public.founder_set_action(text, text, date)",
        "public.founder_add_feedback(text, text, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            EXECUTE 'REVOKE ALL ON FUNCTION {signature} FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'GRANT EXECUTE ON FUNCTION {signature} TO authenticated';
          END IF;
        END $$""")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.founder_add_feedback(text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS public.founder_set_action(text, text, date)")
    op.execute("DROP VIEW IF EXISTS public.founder_feed_activity")
    op.execute("DROP VIEW IF EXISTS public.founder_activity_state")

    for table in ("founder_triage_states", "founder_feedback", "outbound_actions"):
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS {table}_founder_authenticated_read ON public.{table}';
            EXECUTE 'DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON public.{table}';
            EXECUTE 'CREATE POLICY {table}_browser_deny_authenticated ON public.{table} FOR ALL TO authenticated USING (false) WITH CHECK (false)';
            EXECUTE 'REVOKE ALL ON public.{table} FROM authenticated';
          END IF;
        END $$""")
