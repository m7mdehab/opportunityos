BEGIN;

-- Running upgrade 0019_activity_view_access -> 0020_capacity_archive

CREATE TABLE opportunity_cold_archive (
    opportunity_id VARCHAR(64) NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    payload_zlib BYTEA NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    original_size_bytes INTEGER NOT NULL, 
    archive_version VARCHAR(16) NOT NULL, 
    archived_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (opportunity_id)
);

CREATE INDEX ix_opportunity_cold_archive_content_hash ON opportunity_cold_archive (content_hash);

ALTER TABLE opportunity_cold_archive ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'DROP POLICY IF EXISTS opportunity_cold_archive_browser_deny_anon ON opportunity_cold_archive'; EXECUTE 'CREATE POLICY opportunity_cold_archive_browser_deny_anon ON opportunity_cold_archive FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'DROP POLICY IF EXISTS opportunity_cold_archive_browser_deny_authenticated ON opportunity_cold_archive'; EXECUTE 'CREATE POLICY opportunity_cold_archive_browser_deny_authenticated ON opportunity_cold_archive FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

UPDATE alembic_version SET version_num='0020_capacity_archive' WHERE alembic_version.version_num = '0019_activity_view_access';

COMMIT;

