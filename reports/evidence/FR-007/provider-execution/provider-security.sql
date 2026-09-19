-- Supabase-specific browser-role hardening.
-- RLS does not govern TRUNCATE, so remove non-row browser privileges that
-- Supabase grants on public tables by default. Also protect alembic_version,
-- which is outside ORM metadata but is exposed from the public schema.
BEGIN;
ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')
     AND NOT EXISTS (
       SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='alembic_version'
          AND policyname='alembic_version_browser_deny_anon'
     )
  THEN
    EXECUTE 'CREATE POLICY alembic_version_browser_deny_anon ON public.alembic_version FOR ALL TO anon USING (false) WITH CHECK (false)';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated')
     AND NOT EXISTS (
       SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='alembic_version'
          AND policyname='alembic_version_browser_deny_authenticated'
     )
  THEN
    EXECUTE 'CREATE POLICY alembic_version_browser_deny_authenticated ON public.alembic_version FOR ALL TO authenticated USING (false) WITH CHECK (false)';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM authenticated;
  END IF;
END $$;
COMMIT;
SELECT c.relrowsecurity
  FROM pg_class c
 WHERE c.oid=to_regclass('public.alembic_version');
SELECT table_name, grantee, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public'
   AND grantee IN ('anon','authenticated')
   AND privilege_type IN ('TRUNCATE','REFERENCES','TRIGGER')
 ORDER BY table_name, grantee, privilege_type;
