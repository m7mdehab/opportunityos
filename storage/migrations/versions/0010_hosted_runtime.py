"""0010_hosted_runtime

Repository-owned Supabase-native runtime boundary for the Founder Alpha.

The migration deliberately keeps the durable Founder binding in PostgreSQL and
uses the JWT subject claim supplied by Supabase/PostgREST.  It does not rely on
an operator-set session GUC, and it does not expose the canonical application
relations directly to browser roles.  Browser reads use narrow views and the
only browser write is the due-only, idempotent Poll Now RPC.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_hosted_runtime"
down_revision: Union[str, None] = "0009_hosted_founder_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# This revision does not change the canonical Founder filter seed defaults.
_D3_FILTER_SEED_OVERRIDES: dict[str, dict[str, object]] = {}


# This revision is intentionally SQL-first for PostgreSQL: Supabase policies,
# security-invoker views and RPCs have no portable SQLAlchemy equivalent.
_BROWSER_POLICY_TABLES = (
    "feed_projection",
    "source_schedules",
    "source_poll_runs",
    "artifact_cache",
)


def _postgres_upgrade() -> None:
    # The helper reads the JWT subject claim that PostgREST installs for every
    # request.  It is durable across requests and process restarts because the
    # authoritative subject is bound in founder_identity, rather than in a
    # mutable session GUC.  NULL/empty claims fail closed.
    op.execute(
        """
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
        $$
        """
    )

    # Browser-facing reads are narrow and intentionally omit descriptions,
    # raw payloads, provenance text, and other private columns.
    op.execute(
        """
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
        FROM public.feed_projection
        """
    )
    op.execute(
        """
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
        ) AS r ON true
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW public.founder_artifact_metadata
        WITH (security_invoker = true)
        AS
        SELECT
            cache_key, opportunity_id, truth_pack_hash, template_id,
            artifact_kind, content_type, storage_backend, object_key,
            payload_sha256, size_bytes, generation_version, created_at
        FROM public.artifact_cache
        """
    )

    # 0009 intentionally denies browser access to every ORM relation.  Replace
    # only the read policies required by the hosted UI; all other relations
    # remain denied by their 0009 policy.
    for table in _BROWSER_POLICY_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON public.{table}")
        # Plain PostgreSQL disposable fixtures do not necessarily define the
        # Supabase browser roles. Keep the migration executable there while
        # creating the policy whenever the provider does expose the role.
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'CREATE POLICY {table}_founder_authenticated_read '
                     || 'ON public.{table} FOR SELECT TO authenticated '
                     || 'USING (public.opos_is_founder())';
              END IF;
            END $$
            """
        )

    # Views need no public/table grants beyond the deliberate SELECT surface.
    for view in ("founder_feed", "founder_source_health", "founder_artifact_metadata"):
        op.execute(f"REVOKE ALL ON public.{view} FROM PUBLIC")
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON public.{view} FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.{view} FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.{view} TO authenticated';
              END IF;
            END $$
            """
        )

    # The identity table and queue are never directly writable/readable from a
    # browser.  SECURITY DEFINER functions below are the only exposed actions.
    op.execute("REVOKE ALL ON public.founder_identity FROM PUBLIC")
    op.execute("REVOKE ALL ON public.worker_jobs FROM PUBLIC")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL ON public.founder_identity FROM anon';
            EXECUTE 'REVOKE ALL ON public.worker_jobs FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'REVOKE ALL ON public.founder_identity FROM authenticated';
            EXECUTE 'REVOKE ALL ON public.worker_jobs FROM authenticated';
          END IF;
        END $$
        """
    )

    # Supabase Storage remains private; browser downloads are allowed only for
    # the bound Founder subject. The metadata tables are provider-owned and are
    # touched only when this migration is executed against Supabase.
    op.execute(
        """
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
        END $$
        """
    )

    # A status read is deliberately constrained to the authenticated founder and
    # exposes no payload or error text.
    op.execute(
        """
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
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.poll_job_status(text) FROM PUBLIC")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL ON FUNCTION public.poll_job_status(text) FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'GRANT EXECUTE ON FUNCTION public.poll_job_status(text) TO authenticated';
          END IF;
        END $$
        """
    )

    # Poll Now uses only durable source_schedules rows.  Therefore the hosted
    # boundary cannot invent source IDs or bypass the repository read policy,
    # which remains authoritative in the Python scheduler/registry.  It is
    # due-only (no force flag), cooldown-aware, active-job deduplicated and
    # advances next_due_at in the same transaction as the queue insert.
    op.execute(
        """
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
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM PUBLIC")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated';
          END IF;
        END $$
        """
    )


def _postgres_downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF to_regclass('storage.objects') IS NOT NULL THEN
            EXECUTE 'DROP POLICY IF EXISTS founder_private_cv_select ON storage.objects';
            EXECUTE 'DROP POLICY IF EXISTS founder_private_artifact_select ON storage.objects';
          END IF;
        END $$
        """
    )
    op.execute("DROP FUNCTION IF EXISTS public.enqueue_poll_now(text)")
    op.execute("DROP FUNCTION IF EXISTS public.poll_job_status(text)")
    op.execute("DROP VIEW IF EXISTS public.founder_artifact_metadata")
    op.execute("DROP VIEW IF EXISTS public.founder_source_health")
    op.execute("DROP VIEW IF EXISTS public.founder_feed")
    for table in reversed(_BROWSER_POLICY_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_founder_authenticated_read ON public.{table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON public.{table}")
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'CREATE POLICY {table}_browser_deny_authenticated ON public.{table} '
                     || 'FOR ALL TO authenticated USING (false) WITH CHECK (false)';
              END IF;
            END $$
            """
        )
    op.execute("DROP FUNCTION IF EXISTS public.opos_is_founder()")


def upgrade() -> None:
    op.create_table(
        "founder_identity",
        sa.Column("id", sa.String(length=16), primary_key=True, nullable=False),
        sa.Column("supabase_user_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("id = 'singleton'", name="ck_founder_identity_singleton"),
    )
    op.create_index("ix_founder_identity_supabase_user_id", "founder_identity", ["supabase_user_id"], unique=True)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.founder_identity ENABLE ROW LEVEL SECURITY")
        _postgres_upgrade()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _postgres_downgrade()
        op.execute("ALTER TABLE public.founder_identity DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_founder_identity_supabase_user_id", table_name="founder_identity")
    op.drop_table("founder_identity")
