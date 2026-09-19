BEGIN;

-- Running upgrade 0004_founder_control -> 0005_widen_location_region

ALTER TABLE opportunities ALTER COLUMN location_region TYPE TEXT;

UPDATE alembic_version SET version_num='0005_widen_location_region' WHERE alembic_version.version_num = '0004_founder_control';

COMMIT;

