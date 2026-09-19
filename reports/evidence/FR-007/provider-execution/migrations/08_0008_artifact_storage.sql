BEGIN;

-- Running upgrade 0007_source_schedules -> 0008_artifact_storage

ALTER TABLE artifact_cache ADD COLUMN storage_backend VARCHAR(32) DEFAULT 'postgres_payload' NOT NULL;

ALTER TABLE artifact_cache ADD COLUMN object_key VARCHAR(256);

ALTER TABLE artifact_cache ADD COLUMN payload_sha256 VARCHAR(64);

ALTER TABLE artifact_cache ADD COLUMN size_bytes INTEGER;

ALTER TABLE artifact_cache ADD COLUMN generation_version VARCHAR(64);

UPDATE artifact_cache SET size_bytes = octet_length(payload) WHERE payload IS NOT NULL;

ALTER TABLE artifact_cache ALTER COLUMN storage_backend DROP DEFAULT;

UPDATE alembic_version SET version_num='0008_artifact_storage' WHERE alembic_version.version_num = '0007_source_schedules';

COMMIT;

