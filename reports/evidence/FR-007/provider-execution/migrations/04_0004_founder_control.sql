BEGIN;

-- Running upgrade 0003_provenance_identity -> 0004_founder_control

ALTER TABLE opportunities ADD COLUMN work_mode VARCHAR(16) DEFAULT 'unspecified' NOT NULL;

ALTER TABLE opportunities ADD COLUMN work_mode_source VARCHAR(16);

ALTER TABLE opportunities ADD COLUMN location_country VARCHAR(2);

ALTER TABLE opportunities ADD COLUMN location_city VARCHAR(128);

ALTER TABLE opportunities ADD COLUMN location_region VARCHAR(64);

ALTER TABLE opportunities ADD COLUMN remote_scope VARCHAR(24) DEFAULT 'unspecified' NOT NULL;

ALTER TABLE opportunities ADD COLUMN remote_scope_regions TEXT;

ALTER TABLE opportunities ADD COLUMN employment_type VARCHAR(24) DEFAULT 'unspecified' NOT NULL;

ALTER TABLE opportunities ADD COLUMN seniority_level VARCHAR(24) DEFAULT 'unspecified' NOT NULL;

ALTER TABLE opportunities ADD COLUMN compensation_min INTEGER;

ALTER TABLE opportunities ADD COLUMN compensation_max INTEGER;

ALTER TABLE opportunities ADD COLUMN compensation_currency VARCHAR(8);

ALTER TABLE opportunities ADD COLUMN compensation_period VARCHAR(16);

ALTER TABLE opportunities ADD COLUMN title_family VARCHAR(64);

ALTER TABLE opportunities ADD COLUMN title_level VARCHAR(24);

ALTER TABLE opportunities ADD COLUMN family_key VARCHAR(64);

ALTER TABLE opportunities ADD COLUMN search_tsv TSVECTOR;

CREATE INDEX ix_opportunities_work_mode ON opportunities (work_mode);

CREATE INDEX ix_opportunities_location_country ON opportunities (location_country);

CREATE INDEX ix_opportunities_title_family ON opportunities (title_family);

CREATE INDEX ix_opportunities_family_key ON opportunities (family_key);

CREATE INDEX ix_opportunities_search_tsv ON opportunities USING gin (search_tsv);

UPDATE opportunities o
        SET search_tsv = to_tsvector(
            'english',
            concat_ws(
                ' ',
                o.title,
                o.organization,
                o.description,
                o.location_country,
                o.location_city,
                o.location_region,
                (
                    SELECT string_agg(fp.normalized_value, ' ')
                    FROM field_provenances fp
                    WHERE fp.opportunity_id = o.id AND fp.field_name = 'requirements'
                )
            )
        )
        WHERE o.search_tsv IS NULL;

CREATE TABLE opportunity_families (
    family_key VARCHAR(64) NOT NULL, 
    employer VARCHAR(256), 
    normalized_title VARCHAR(256), 
    member_count INTEGER, 
    best_member_id VARCHAR(64), 
    split_out BOOLEAN DEFAULT false NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (family_key)
);

CREATE TABLE founder_facets (
    facet_id VARCHAR(64) NOT NULL, 
    mode VARCHAR(16) DEFAULT 'off' NOT NULL, 
    values_json TEXT, 
    updated_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (facet_id)
);

CREATE TABLE founder_saved_views (
    id VARCHAR(64) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    facets_json TEXT, 
    search_query TEXT, 
    is_default BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    updated_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_founder_saved_views_name UNIQUE (name)
);

CREATE TABLE artifact_cache (
    cache_key VARCHAR(128) NOT NULL, 
    opportunity_id VARCHAR(64), 
    truth_pack_hash VARCHAR(64), 
    template_id VARCHAR(32), 
    artifact_kind VARCHAR(32), 
    content_type VARCHAR(128), 
    payload BYTEA, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (cache_key)
);

UPDATE founder_filter_settings SET mode = 'rank_only' WHERE filter_id = 'target_roles' AND mode = 'label_only';

UPDATE alembic_version SET version_num='0004_founder_control' WHERE alembic_version.version_num = '0003_provenance_identity';

COMMIT;

