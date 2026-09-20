"""0013_hosted_poll_now_cadence

Repair the hosted Poll Now RPC for DOUBLE PRECISION source cadence values.

PostgreSQL make_interval(hours => ...) requires integer hours. The durable
source_schedules.cadence_hours column is DOUBLE PRECISION so fractional
cadences must be converted through the seconds argument instead.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013_hosted_poll_now_cadence"
down_revision: Union[str, None] = "0012_hosted_policy_alignment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D3_FILTER_SEED_OVERRIDES: dict[str, dict[str, object]] = {}


_FIXED_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.enqueue_poll_now(p_source_id text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  sched public.source_schedules%ROWTYPE;
  requested text[];
  enqueued jsonb := '[]'::jsonb;
  skipped jsonb := '[]'::jsonb;
  new_id text;
  reason text;
BEGIN
  IF NOT public.opos_is_founder() THEN
    RAISE EXCEPTION 'authorized founder required';
  END IF;

  IF p_source_id IS NOT NULL THEN
    requested := ARRAY[p_source_id];
  ELSE
    SELECT COALESCE(array_agg(source_id ORDER BY source_id), ARRAY[]::text[])
      INTO requested
      FROM public.source_schedules;
  END IF;

  IF cardinality(requested) = 0 THEN
    RETURN jsonb_build_object('enqueued', enqueued, 'skipped', skipped);
  END IF;

  FOREACH p_source_id IN ARRAY requested LOOP
    SELECT *
      INTO sched
      FROM public.source_schedules
     WHERE source_id = p_source_id
     FOR UPDATE;

    IF NOT FOUND THEN
      skipped := skipped || jsonb_build_array(
        jsonb_build_object('source_id', p_source_id, 'reason', 'not_scheduled')
      );
      CONTINUE;
    END IF;

    IF EXISTS (
      SELECT 1
        FROM public.worker_jobs w
       WHERE w.job_type = 'poll_source'
         AND w.status IN ('PENDING', 'RETRY', 'RUNNING')
         AND (w.payload_json::jsonb ->> 'source_id') = sched.source_id
    ) THEN
      reason := 'already_queued';
    ELSIF sched.cooldown_until IS NOT NULL AND sched.cooldown_until > now() THEN
      reason := 'cooldown';
    ELSIF sched.next_due_at > now() THEN
      reason := 'not_due';
    ELSE
      reason := NULL;
    END IF;

    IF reason IS NOT NULL THEN
      skipped := skipped || jsonb_build_array(
        jsonb_build_object('source_id', sched.source_id, 'reason', reason)
      );
      CONTINUE;
    END IF;

    new_id := md5(clock_timestamp()::text || random()::text || sched.source_id);
    INSERT INTO public.worker_jobs
      (id, job_type, payload_json, status, run_after, retry_count,
       max_retries, created_at, updated_at)
    VALUES
      (new_id, 'poll_source',
       json_build_object('source_id', sched.source_id)::text,
       'PENDING', now(), 0, 3, now(), now());

    UPDATE public.source_schedules
       SET last_attempt_at = now(),
           next_due_at = now() + make_interval(secs => sched.cadence_hours * 3600.0),
           updated_at = now()
     WHERE source_id = sched.source_id;

    enqueued := enqueued || jsonb_build_array(
      jsonb_build_object('source_id', sched.source_id, 'job_id', new_id)
    );
  END LOOP;

  RETURN jsonb_build_object('enqueued', enqueued, 'skipped', skipped);
END;
$$
"""


def _grant() -> None:
    op.execute("REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated';
      END IF;
    END $$""")


def upgrade() -> None:
    op.execute(_FIXED_FUNCTION)
    _grant()


def downgrade() -> None:
    # The repository copy of 0011 has also been repaired to use the valid
    # DOUBLE PRECISION cadence expression, so the same behavioral contract is
    # correct on either side of this drift-repair revision.
    op.execute(_FIXED_FUNCTION)
    _grant()
