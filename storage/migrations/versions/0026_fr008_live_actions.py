"""FR-008 live review action compatibility over the accepted W23 schema.

Extends the existing Founder triage/activity substrate with Save, Reject, Applied
tracker states and a bounded latest-action restore RPC. This migration is
additive to the accepted Storage V2 runtime; it does not introduce the larger
private tracker schema from the earlier FR-008 development branch.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0026_fr008_live_actions"
down_revision: Union[str, None] = "0025_current_feed_fast_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The W23 activity table intentionally had a narrow enum-like CHECK.
    # FR-008 adds explicit Save/Reject/Applied/Restore events.
    op.execute("ALTER TABLE public.founder_activity_events DROP CONSTRAINT IF EXISTS founder_activity_events_action_type_check")
    op.execute("ALTER TABLE public.founder_activity_events DROP CONSTRAINT IF EXISTS founder_activity_events_resulting_state_check")
    op.execute(
        """ALTER TABLE public.founder_activity_events
           ADD CONSTRAINT founder_activity_events_action_type_check
           CHECK (action_type IN (
             'mark_applied','dismiss','snooze','clear',
             'save','reject','restore'
           ))"""
    )
    op.execute(
        """ALTER TABLE public.founder_activity_events
           ADD CONSTRAINT founder_activity_events_resulting_state_check
           CHECK (
             resulting_state IS NULL OR resulting_state IN (
               'saved','applied','submitted','rejected_by_founder',
               'dismissed','snoozed'
             )
           )"""
    )

    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.founder_set_action(
  p_opportunity_id text,
  p_type text,
  p_until date DEFAULT NULL::date
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  now_ts timestamp without time zone := clock_timestamp() AT TIME ZONE 'UTC';
  next_state text;
  previous_state text;
  event_id text;
  action_id text := NULL;
  opp public.opportunities%ROWTYPE;
  eval public.match_evaluations%ROWTYPE;
  existing_id text;
BEGIN
  IF NOT public.opos_is_founder() THEN
    RAISE EXCEPTION 'authorized founder required';
  END IF;

  SELECT * INTO opp FROM public.opportunities WHERE id = p_opportunity_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'opportunity not found'; END IF;

  SELECT state INTO previous_state
  FROM public.founder_triage_states
  WHERE opportunity_id = p_opportunity_id;

  IF p_type = 'save' THEN
    next_state := 'saved';
  ELSIF p_type = 'mark_applied' THEN
    next_state := 'applied';
  ELSIF p_type = 'reject' THEN
    next_state := 'rejected_by_founder';
  ELSIF p_type = 'dismiss' THEN
    next_state := 'dismissed';
  ELSIF p_type = 'snooze' THEN
    IF p_until IS NULL OR p_until <= CURRENT_DATE THEN
      RAISE EXCEPTION 'snooze requires a future until date';
    END IF;
    next_state := 'snoozed';
  ELSIF p_type = 'clear' THEN
    next_state := NULL;
  ELSE
    RAISE EXCEPTION 'unknown action type';
  END IF;

  IF p_type = 'mark_applied' THEN
    SELECT id INTO existing_id
    FROM public.outbound_actions
    WHERE opportunity_id = p_opportunity_id
      AND candidate_id = 'founder'
      AND adapter_name = 'founder_attested'
    ORDER BY (action_status='submitted') DESC, created_at ASC, id ASC
    LIMIT 1;

    IF existing_id IS NULL THEN
      SELECT * INTO eval
      FROM public.match_evaluations
      WHERE opportunity_id = p_opportunity_id
      ORDER BY evaluated_at DESC
      LIMIT 1;

      action_id := 'founder-attested-' || md5(p_opportunity_id);
      INSERT INTO public.outbound_actions(
        id,opportunity_id,opportunity_content_hash,workspace,candidate_id,
        track,source,adapter_name,adapter_version,execution_mode,
        qualification_decision,match_score_snapshot,artifact_ids_json,
        artifact_hashes_json,manifest_hash,action_status,idempotency_key,
        created_at,updated_at
      )
      VALUES(
        action_id,p_opportunity_id,opp.content_hash,'default','founder',
        opp.track,opp.source_id,'founder_attested','1.0','dry_run',
        coalesce(eval.qualification_decision,'uncertain'),
        coalesce(eval.fit_score,0),'[]','[]',md5(action_id),'submitted',
        'founder-attested:' || p_opportunity_id,now_ts,now_ts
      );
    ELSE
      action_id := existing_id;
      UPDATE public.outbound_actions
      SET action_status='submitted', updated_at=now_ts
      WHERE id=existing_id AND action_status<>'submitted';
    END IF;
  END IF;

  IF p_type = 'clear' THEN
    DELETE FROM public.founder_triage_states
    WHERE opportunity_id = p_opportunity_id;
  ELSE
    INSERT INTO public.founder_triage_states(
      opportunity_id,state,snoozed_until,created_at,updated_at
    )
    VALUES(
      p_opportunity_id,next_state,
      CASE WHEN p_type='snooze' THEN p_until ELSE NULL END,
      now_ts,now_ts
    )
    ON CONFLICT(opportunity_id) DO UPDATE
      SET state=excluded.state,
          snoozed_until=excluded.snoozed_until,
          updated_at=excluded.updated_at;
  END IF;

  event_id := 'activity-' || md5(
    p_opportunity_id || ':' || p_type || ':' ||
    clock_timestamp()::text || ':' || random()::text
  );

  INSERT INTO public.founder_activity_events(
    id,opportunity_id,action_type,resulting_state,snoozed_until,created_at
  )
  VALUES(
    event_id,p_opportunity_id,p_type,next_state,
    CASE WHEN p_type='snooze' THEN p_until ELSE NULL END,now_ts
  );

  RETURN jsonb_build_object(
    'opportunity_id',p_opportunity_id,
    'action_state',next_state,
    'tracker_state',coalesce(next_state,'to_review'),
    'undo_event_id',CASE WHEN p_type IN ('save','mark_applied','reject') THEN event_id ELSE NULL END,
    'action_id',action_id,
    'until',CASE WHEN p_type='snooze' THEN to_char(p_until,'YYYY-MM-DD') ELSE NULL END,
    'created_at',now_ts
  );
END;
$function$;
"""
    )

    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.founder_restore_action(
  p_opportunity_id text,
  p_event_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  original public.founder_activity_events%ROWTYPE;
  latest_id text;
  previous_state text;
  now_ts timestamp without time zone := clock_timestamp() AT TIME ZONE 'UTC';
  restore_id text;
BEGIN
  IF NOT public.opos_is_founder() THEN
    RAISE EXCEPTION 'authorized founder required';
  END IF;

  SELECT * INTO original
  FROM public.founder_activity_events
  WHERE id = p_event_id
    AND opportunity_id = p_opportunity_id;

  IF NOT FOUND OR original.action_type NOT IN ('save','mark_applied','reject') THEN
    RAISE EXCEPTION 'tracker event not found or cannot be undone';
  END IF;

  SELECT id INTO latest_id
  FROM public.founder_activity_events
  WHERE opportunity_id = p_opportunity_id
  ORDER BY created_at DESC, id DESC
  LIMIT 1;

  IF latest_id IS DISTINCT FROM original.id THEN
    RAISE EXCEPTION 'tracker action is no longer the latest activity';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.founder_triage_states
    WHERE opportunity_id = p_opportunity_id
      AND state IS NOT DISTINCT FROM original.resulting_state
  ) THEN
    RAISE EXCEPTION 'current tracker state no longer matches this action';
  END IF;

  SELECT resulting_state INTO previous_state
  FROM public.founder_activity_events
  WHERE opportunity_id = p_opportunity_id
    AND (created_at, id) < (original.created_at, original.id)
  ORDER BY created_at DESC, id DESC
  LIMIT 1;

  IF previous_state IS NULL THEN
    DELETE FROM public.founder_triage_states
    WHERE opportunity_id = p_opportunity_id;
  ELSE
    INSERT INTO public.founder_triage_states(
      opportunity_id,state,snoozed_until,created_at,updated_at
    )
    VALUES(p_opportunity_id,previous_state,NULL,now_ts,now_ts)
    ON CONFLICT(opportunity_id) DO UPDATE
      SET state=excluded.state,
          snoozed_until=NULL,
          updated_at=excluded.updated_at;
  END IF;

  IF original.resulting_state = 'applied' THEN
    UPDATE public.outbound_actions
    SET action_status='undone', updated_at=now_ts
    WHERE id = (
      SELECT id FROM public.outbound_actions
      WHERE opportunity_id=p_opportunity_id
        AND candidate_id='founder'
        AND adapter_name='founder_attested'
        AND action_status='submitted'
      ORDER BY created_at DESC, id DESC
      LIMIT 1
    );
  END IF;

  restore_id := 'activity-' || md5(
    p_opportunity_id || ':restore:' ||
    clock_timestamp()::text || ':' || random()::text
  );

  INSERT INTO public.founder_activity_events(
    id,opportunity_id,action_type,resulting_state,snoozed_until,created_at
  )
  VALUES(restore_id,p_opportunity_id,'restore',previous_state,NULL,now_ts);

  RETURN jsonb_build_object(
    'opportunity_id',p_opportunity_id,
    'action_state',previous_state,
    'tracker_state',coalesce(previous_state,'to_review'),
    'changed',true,
    'event_id',restore_id
  );
END;
$function$;
"""
    )


    op.execute(
        r"""
CREATE OR REPLACE VIEW public.founder_activity_state AS
WITH latest_event AS (
  SELECT DISTINCT ON (e.opportunity_id)
    e.opportunity_id, e.action_type, e.resulting_state, e.snoozed_until, e.created_at
  FROM public.founder_activity_events e
  ORDER BY e.opportunity_id, e.created_at DESC, e.id DESC
), latest_feedback AS (
  SELECT DISTINCT ON (f.opportunity_id)
    f.opportunity_id, f.feedback_label, f.created_at AS feedback_updated_at
  FROM public.founder_feedback f
  ORDER BY f.opportunity_id, f.created_at DESC, f.id DESC
), feedback_counts AS (
  SELECT opportunity_id, count(*)::integer AS feedback_count
  FROM public.founder_feedback
  GROUP BY opportunity_id
), legacy_applied AS (
  SELECT DISTINCT opportunity_id
  FROM public.outbound_actions
  WHERE candidate_id='founder'
    AND adapter_name='founder_attested'
    AND action_status='submitted'
)
SELECT
  o.id AS opportunity_id,
  CASE
    WHEN le.action_type='snooze' AND le.snoozed_until IS NOT NULL
      AND le.snoozed_until > CURRENT_DATE THEN 'snoozed'
    WHEN le.action_type IN ('save','mark_applied','reject','dismiss') THEN le.resulting_state
    WHEN le.action_type='restore' THEN le.resulting_state
    WHEN le.action_type IN ('snooze','clear') THEN NULL
    ELSE NULL
  END::varchar AS action_state,
  CASE
    WHEN le.action_type='snooze' AND le.snoozed_until > CURRENT_DATE
      THEN le.snoozed_until::timestamp without time zone
    ELSE NULL
  END AS snoozed_until,
  le.created_at AS action_updated_at,
  lf.feedback_label,
  coalesce(fc.feedback_count,0) AS feedback_count,
  lf.feedback_updated_at,
  le.opportunity_id IS NOT NULL
    OR la.opportunity_id IS NOT NULL
    OR coalesce(fc.feedback_count,0) > 0 AS has_activity
FROM public.opportunities o
LEFT JOIN latest_event le ON le.opportunity_id=o.id::text
LEFT JOIN latest_feedback lf ON lf.opportunity_id::text=o.id::text
LEFT JOIN feedback_counts fc ON fc.opportunity_id::text=o.id::text
LEFT JOIN legacy_applied la ON la.opportunity_id::text=o.id::text
WHERE public.opos_is_founder();
"""
    )

    op.execute(
        """CREATE OR REPLACE VIEW public.founder_feed_fr008
           WITH (security_invoker = true)
           AS
           SELECT f.*,
                  CASE WHEN f.work_mode='remote' THEN 0 ELSE 1 END AS remote_rank
           FROM public.founder_feed_activity f"""
    )
    op.execute("GRANT SELECT ON public.founder_feed_fr008 TO authenticated")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.founder_restore_action(text,text)")
    # Keep the wider CHECKs on downgrade to avoid making already-written FR-008
    # events invalid. The function is restored to the accepted W23 behavior.
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.founder_set_action(
  p_opportunity_id text,
  p_type text,
  p_until date DEFAULT NULL::date
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
BEGIN
  RAISE EXCEPTION '0026 downgrade requires repository rollback of founder_set_action';
END;
$function$;
"""
    )
