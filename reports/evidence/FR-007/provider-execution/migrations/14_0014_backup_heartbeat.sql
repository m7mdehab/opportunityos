BEGIN;

-- Running upgrade 0013_hosted_poll_now_cadence -> 0014_backup_heartbeat

CREATE TABLE backup_heartbeats (
    id VARCHAR(64) NOT NULL, 
    result VARCHAR(32) NOT NULL, 
    backup_completed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    encryption BOOLEAN NOT NULL, 
    destination_class VARCHAR(64) NOT NULL, 
    database_snapshot_sha VARCHAR(64) NOT NULL, 
    artifact_run_id VARCHAR(64), 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

ALTER TABLE public.backup_heartbeats ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'CREATE POLICY backup_heartbeats_browser_deny_anon ON public.backup_heartbeats FOR ALL TO anon USING (false) WITH CHECK (false)';
        EXECUTE 'REVOKE ALL ON public.backup_heartbeats FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'CREATE POLICY backup_heartbeats_browser_deny_authenticated ON public.backup_heartbeats FOR ALL TO authenticated USING (false) WITH CHECK (false)';
        EXECUTE 'REVOKE ALL ON public.backup_heartbeats FROM authenticated';
      END IF;
    END $$;

REVOKE ALL ON public.backup_heartbeats FROM PUBLIC;

UPDATE alembic_version SET version_num='0014_backup_heartbeat' WHERE alembic_version.version_num = '0013_hosted_poll_now_cadence';

COMMIT;

