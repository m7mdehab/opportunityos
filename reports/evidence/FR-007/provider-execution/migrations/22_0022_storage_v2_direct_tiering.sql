BEGIN;

-- Running upgrade 0021_storage_v2 -> 0022_storage_v2_direct_tiering

ALTER TABLE opportunities ADD COLUMN lifecycle_tier VARCHAR(16) DEFAULT 'hot' NOT NULL;

ALTER TABLE opportunities ADD CONSTRAINT ck_opportunities_lifecycle_tier CHECK (lifecycle_tier IN ('hot', 'cold', 'protected'));

CREATE INDEX ix_opportunities_lifecycle_tier ON opportunities (lifecycle_tier);

ALTER TABLE opportunities ALTER COLUMN lifecycle_tier DROP DEFAULT;

ALTER TABLE opportunities ALTER COLUMN description DROP NOT NULL;

ALTER TABLE opportunity_cold_archive ALTER COLUMN storage_backend SET DEFAULT 'supabase_storage';

ALTER TABLE opportunity_cold_archive ALTER COLUMN storage_backend DROP DEFAULT;

TRUNCATE TABLE feed_projection;

ALTER TABLE feed_projection DROP CONSTRAINT uq_feed_projection_opportunity_truth_pack;

ALTER TABLE feed_projection DROP COLUMN search_text;

ALTER TABLE feed_projection DROP COLUMN search_tsv;

ALTER TABLE feed_projection ADD CONSTRAINT uq_feed_projection_current_opportunity UNIQUE (opportunity_id);

DELETE FROM match_evaluations m USING (
             SELECT id, row_number() OVER (
               PARTITION BY opportunity_id
               ORDER BY evaluated_at DESC, created_at DESC, id DESC
             ) AS rn
             FROM match_evaluations
           ) ranked
           WHERE m.id = ranked.id AND ranked.rn > 1;

ALTER TABLE match_evaluations ADD COLUMN content_hash VARCHAR(64);

UPDATE match_evaluations m
           SET content_hash = o.content_hash
           FROM opportunities o
           WHERE o.id = m.opportunity_id AND m.content_hash IS NULL;

ALTER TABLE match_evaluations ALTER COLUMN content_hash SET NOT NULL;

ALTER TABLE match_evaluations ADD COLUMN hard_failure_code VARCHAR(64);

ALTER TABLE match_evaluations ALTER COLUMN dimension_scores_json DROP NOT NULL;

ALTER TABLE match_evaluations DROP CONSTRAINT uq_match_evaluations_opportunity_truth_pack;

ALTER TABLE match_evaluations ADD CONSTRAINT uq_match_evaluations_current_opportunity UNIQUE (opportunity_id);

CREATE TABLE opportunity_archive_orphans (
    object_key VARCHAR(255) NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    compressed_size_bytes INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (object_key)
);

ALTER TABLE public.founder_activity_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE opportunity_archive_orphans ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'DROP POLICY IF EXISTS opportunity_archive_orphans_browser_deny_anon ON opportunity_archive_orphans'; EXECUTE 'CREATE POLICY opportunity_archive_orphans_browser_deny_anon ON opportunity_archive_orphans FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'DROP POLICY IF EXISTS opportunity_archive_orphans_browser_deny_authenticated ON opportunity_archive_orphans'; EXECUTE 'CREATE POLICY opportunity_archive_orphans_browser_deny_authenticated ON opportunity_archive_orphans FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

UPDATE alembic_version SET version_num='0022_storage_v2_direct_tiering' WHERE alembic_version.version_num = '0021_storage_v2';

COMMIT;

