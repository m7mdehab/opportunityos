BEGIN;

-- Running upgrade 0022_storage_v2_direct_tiering -> 0023_alembic_access

REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM authenticated';
          END IF;
        END $$;

ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='0023_alembic_access' WHERE alembic_version.version_num = '0022_storage_v2_direct_tiering';

COMMIT;

