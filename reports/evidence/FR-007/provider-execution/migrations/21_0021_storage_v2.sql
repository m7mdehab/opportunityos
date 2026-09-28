BEGIN;

-- Running upgrade 0020_capacity_archive -> 0021_storage_v2

ALTER TABLE opportunities ADD COLUMN archive_object_key VARCHAR(255);

ALTER TABLE opportunities ADD COLUMN archive_sha256 VARCHAR(64);

ALTER TABLE opportunities ADD COLUMN archive_state VARCHAR(16);

ALTER TABLE opportunity_cold_archive ADD COLUMN storage_backend VARCHAR(32) DEFAULT 'postgres_payload' NOT NULL;

ALTER TABLE opportunity_cold_archive ADD COLUMN object_key VARCHAR(255);

ALTER TABLE opportunity_cold_archive ADD COLUMN compressed_size_bytes INTEGER;

ALTER TABLE opportunity_cold_archive ALTER COLUMN payload_zlib DROP NOT NULL;

CREATE INDEX ix_opportunity_cold_archive_object_key ON opportunity_cold_archive (object_key);

DROP INDEX IF EXISTS ix_feed_projection_search_tsv;

UPDATE alembic_version SET version_num='0021_storage_v2' WHERE alembic_version.version_num = '0020_capacity_archive';

COMMIT;

