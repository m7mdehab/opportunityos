-- Supabase-specific browser-role hardening.
-- RLS does not govern TRUNCATE, so remove non-row browser privileges that
-- Supabase grants on public tables by default. The Alembic control table is
-- protected by revoking browser grants and enabling deny-by-default RLS.
BEGIN;
REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM PUBLIC;
ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM anon';
    EXECUTE 'REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM authenticated';
    EXECUTE 'REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM authenticated';
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
