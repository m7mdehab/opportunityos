-- Execute as the authenticated provider operator; no writes are performed.
-- The service/backend connection is the owner path. Browser roles are checked
-- through catalog metadata and explicit SET ROLE probes supplied below.
SELECT c.relname AS table_name, c.relrowsecurity,
       COALESCE(array_agg(DISTINCT p.policyname ORDER BY p.policyname)
                FILTER (WHERE p.policyname IS NOT NULL), ARRAY[]::text[]) AS policy_names
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  LEFT JOIN pg_policies p ON p.schemaname=n.nspname AND p.tablename=c.relname
 WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m')
 GROUP BY c.relname, c.relrowsecurity ORDER BY c.relname;
SELECT schemaname, tablename, policyname, roles, cmd, qual, with_check
  FROM pg_policies WHERE schemaname IN ('public','storage')
 ORDER BY schemaname, tablename, policyname;
SELECT table_name, grantee, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public' AND grantee IN ('anon','authenticated')
 ORDER BY table_name, grantee, privilege_type;
SELECT c.relrowsecurity,
       COALESCE(array_agg(p.policyname ORDER BY p.policyname)
                FILTER (WHERE p.policyname IS NOT NULL), ARRAY[]::text[]) AS policy_names
  FROM pg_class c
  LEFT JOIN pg_policies p
    ON p.schemaname='public' AND p.tablename='alembic_version'
 WHERE c.oid=to_regclass('public.alembic_version')
 GROUP BY c.relrowsecurity;
SELECT table_name, grantee, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public'
   AND grantee IN ('anon','authenticated')
   AND privilege_type IN ('TRUNCATE','REFERENCES','TRIGGER')
 ORDER BY table_name, grantee, privilege_type;
-- Browser denial probes. Run each statement in a fresh transaction as the
-- named role; a protected relation must fail or return zero rows.
BEGIN;
SET LOCAL ROLE anon;
SELECT count(*) FROM public.opportunities;
ROLLBACK;
BEGIN;
SET LOCAL ROLE authenticated;
SELECT count(*) FROM public.opportunities;
ROLLBACK;
-- Repeat the two probes for founder_sessions, founder_auth_rate_limit,
-- founder_auth_events, artifact_cache and feed_projection.
