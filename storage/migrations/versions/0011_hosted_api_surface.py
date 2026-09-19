"""0011_hosted_api_surface

Hosted API contract additions derived from the canonical PostgreSQL model.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0011_hosted_api_surface"
down_revision: Union[str, None] = "0010_hosted_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# This revision does not change the canonical Founder filter seed defaults.
_D3_FILTER_SEED_OVERRIDES: dict[str, dict[str, object]] = {}


def _postgres_upgrade() -> None:
    op.create_table(
        "founder_cv_selections",
        sa.Column("opportunity_id", sa.String(64), nullable=False),
        sa.Column("variant", sa.String(64), nullable=False),
        sa.Column("object_path", sa.String(256), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("selected_at", sa.DateTime(), nullable=False),
        sa.Column("truth_pack_hash", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("opportunity_id"),
    )
    op.execute("CREATE INDEX ix_founder_cv_selections_sha256 ON public.founder_cv_selections (sha256)")
    op.execute("ALTER TABLE public.founder_cv_selections ENABLE ROW LEVEL SECURITY")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'CREATE POLICY founder_cv_selections_browser_deny_anon ON public.founder_cv_selections FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'CREATE POLICY founder_cv_selections_browser_deny_authenticated ON public.founder_cv_selections FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF;
    END $$""")
    op.execute("REVOKE ALL ON public.founder_cv_selections FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selections FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selections FROM authenticated'; END IF;
    END $$""")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'DROP POLICY IF EXISTS source_poll_runs_browser_deny_authenticated ON public.source_poll_runs';
        EXECUTE 'CREATE POLICY source_poll_runs_founder_authenticated_read ON public.source_poll_runs FOR SELECT TO authenticated USING (public.opos_is_founder())';
      END IF;
    END $$""")
    op.execute("""
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
      LEFT JOIN public.founder_cv_selections c ON c.opportunity_id=o.id
    """)
    op.execute("""
      CREATE OR REPLACE VIEW public.founder_cv_selection WITH (security_invoker = true) AS
      SELECT opportunity_id, variant, object_path, sha256, selected_at, truth_pack_hash
      FROM public.founder_cv_selections
    """)
    op.execute("REVOKE ALL ON public.founder_cv_selection FROM PUBLIC")
    for table in ("founder_filter_settings", "founder_facets", "founder_saved_views"):
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS ' || '{table}_browser_deny_authenticated' || ' ON public.{table}';
            EXECUTE 'CREATE POLICY {table}_founder_authenticated_read ON public.{table} FOR SELECT TO authenticated USING (public.opos_is_founder())';
          END IF;
        END $$""")
    for view, table in (("founder_filters", "founder_filter_settings"), ("founder_facet_settings_view", "founder_facets"), ("founder_saved_view_records", "founder_saved_views")):
        op.execute(f"CREATE OR REPLACE VIEW public.{view} WITH (security_invoker = true) AS SELECT * FROM public.{table}")
        op.execute(f"REVOKE ALL ON public.{view} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.{view} FROM anon'; END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'REVOKE ALL ON public.{view} FROM authenticated'; EXECUTE 'GRANT SELECT ON public.{view} TO authenticated'; END IF;
        END $$""")

    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selection FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_cv_selection FROM authenticated'; EXECUTE 'GRANT SELECT ON public.founder_cv_selection TO authenticated'; END IF;
    END $$""")
    op.execute("REVOKE ALL ON public.founder_opportunity_detail FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON public.founder_opportunity_detail FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON public.founder_opportunity_detail FROM authenticated'; EXECUTE 'GRANT SELECT ON public.founder_opportunity_detail TO authenticated'; END IF;
    END $$""")
    op.execute("DROP FUNCTION IF EXISTS public.enqueue_poll_now(text)")
    op.execute("""
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
          UPDATE public.source_schedules SET last_attempt_at=now(), next_due_at=now()+make_interval(hours=>sched.cadence_hours), updated_at=now() WHERE source_id=sched.source_id;
          enqueued := enqueued || jsonb_build_array(jsonb_build_object('source_id',sched.source_id,'job_id',new_id));
        END LOOP;
        RETURN jsonb_build_object('enqueued',enqueued,'skipped',skipped);
      END; $$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE 'REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM anon'; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE 'GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated'; END IF;
    END $$""")


def _postgres_downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.enqueue_poll_now(text)")
    # Restore the exact 0010 RPC contract when downgrading one revision.
    op.execute("""
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
              IF EXISTS (
                  SELECT 1 FROM public.worker_jobs AS w
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
                  (new_id, 'poll_source', payload, 'PENDING', now(), 0, 3, now(), now());
              UPDATE public.source_schedules
              SET last_attempt_at = now(),
                  next_due_at = now() + make_interval(hours => sched.cadence_hours),
                  updated_at = now()
              WHERE source_id = sched.source_id;
              job_id := new_id;
              job_type := 'poll_source';
              status := 'PENDING';
              RETURN NEXT;
          END LOOP;
      END;
      $$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated';
      END IF;
    END $$""")
    op.execute("DROP VIEW IF EXISTS public.founder_saved_view_records")
    op.execute("DROP VIEW IF EXISTS public.founder_facet_settings_view")
    op.execute("DROP VIEW IF EXISTS public.founder_filters")
    op.execute("DROP VIEW IF EXISTS public.founder_cv_selection")
    op.execute("DROP VIEW IF EXISTS public.founder_opportunity_detail")
    op.execute("DROP INDEX IF EXISTS ix_founder_cv_selections_sha256")
    op.drop_table("founder_cv_selections")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'DROP POLICY IF EXISTS source_poll_runs_founder_authenticated_read ON public.source_poll_runs';
        EXECUTE 'CREATE POLICY source_poll_runs_browser_deny_authenticated ON public.source_poll_runs FOR ALL TO authenticated USING (false) WITH CHECK (false)';
      END IF;
    END $$""")
    for table in ("founder_filter_settings", "founder_facets", "founder_saved_views"):
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS {table}_founder_authenticated_read ON public.{table}';
            EXECUTE 'CREATE POLICY {table}_browser_deny_authenticated ON public.{table} FOR ALL TO authenticated USING (false) WITH CHECK (false)';
          END IF;
        END $$""")


def upgrade() -> None:
    _postgres_upgrade()


def downgrade() -> None:
    _postgres_downgrade()
