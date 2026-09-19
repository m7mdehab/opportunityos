BEGIN;

-- Running upgrade 0005_widen_location_region -> 0006_feed_projection

CREATE TABLE feed_projection (
    id VARCHAR(160) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    opportunity_content_hash VARCHAR(64) NOT NULL, 
    truth_pack_hash VARCHAR(64) NOT NULL, 
    projection_version VARCHAR(32) NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    organization VARCHAR(255) NOT NULL, 
    source_id VARCHAR(128) NOT NULL, 
    source_url TEXT NOT NULL, 
    posted_date VARCHAR(64), 
    track VARCHAR(32) NOT NULL, 
    opportunity_type VARCHAR(32), 
    title_family VARCHAR(64), 
    seniority_level VARCHAR(24) NOT NULL, 
    work_mode VARCHAR(16) NOT NULL, 
    location_country VARCHAR(2), 
    location_city VARCHAR(128), 
    location_region TEXT, 
    remote_scope VARCHAR(24) NOT NULL, 
    remote_scope_regions TEXT, 
    employment_type VARCHAR(24) NOT NULL, 
    qualification_decision VARCHAR(32), 
    fit_score FLOAT, 
    priority_score FLOAT, 
    reasons_json TEXT DEFAULT '[]' NOT NULL, 
    red_line_match BOOLEAN DEFAULT false NOT NULL, 
    excluded_industry_match BOOLEAN DEFAULT false NOT NULL, 
    visible BOOLEAN DEFAULT true NOT NULL, 
    visibility_reason TEXT, 
    search_text TEXT DEFAULT '' NOT NULL, 
    search_tsv TSVECTOR, 
    evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    projected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_feed_projection_opportunity_truth_pack UNIQUE (opportunity_id, truth_pack_hash), 
    FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE INDEX ix_feed_projection_truth_visible_rank ON feed_projection (truth_pack_hash, visible, priority_score);

CREATE INDEX ix_feed_projection_truth_decision_score ON feed_projection (truth_pack_hash, qualification_decision, fit_score);

CREATE INDEX ix_feed_projection_truth_posted ON feed_projection (truth_pack_hash, posted_date);

CREATE INDEX ix_feed_projection_source_id ON feed_projection (source_id);

CREATE INDEX ix_feed_projection_title_family ON feed_projection (title_family);

CREATE INDEX ix_feed_projection_work_mode ON feed_projection (work_mode);

CREATE INDEX ix_feed_projection_location_country ON feed_projection (location_country);

CREATE INDEX ix_feed_projection_search_tsv ON feed_projection USING gin (search_tsv);

UPDATE alembic_version SET version_num='0006_feed_projection' WHERE alembic_version.version_num = '0005_widen_location_region';

COMMIT;

