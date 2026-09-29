BEGIN;

-- Running upgrade 0033_hosted_feed_family_key -> 0034_opportunity_created_at

COMMIT;

CREATE INDEX CONCURRENTLY ix_opportunities_created_at ON opportunities (created_at);

BEGIN;

UPDATE alembic_version SET version_num='0034_opportunity_created_at' WHERE alembic_version.version_num = '0033_hosted_feed_family_key';

COMMIT;

