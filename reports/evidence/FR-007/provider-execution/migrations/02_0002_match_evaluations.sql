BEGIN;

-- Running upgrade 0001_baseline_schema -> 0002_match_evaluations

CREATE TABLE match_evaluations (
    id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    truth_pack_hash VARCHAR(64) NOT NULL, 
    qualification_decision VARCHAR(32) NOT NULL, 
    fit_score FLOAT NOT NULL, 
    dimension_scores_json TEXT NOT NULL, 
    reasons_json TEXT NOT NULL, 
    policy_version VARCHAR(32) NOT NULL, 
    evaluated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE, 
    CONSTRAINT uq_match_evaluations_opportunity_truth_pack UNIQUE (opportunity_id, truth_pack_hash)
);

CREATE INDEX ix_match_evaluations_opportunity_id ON match_evaluations (opportunity_id);

CREATE INDEX ix_match_evaluations_truth_pack_hash ON match_evaluations (truth_pack_hash);

CREATE INDEX ix_match_evaluations_evaluated_at ON match_evaluations (evaluated_at);

ALTER TABLE match_evaluations ADD COLUMN evaluation_detail_json TEXT;

CREATE TABLE source_poll_runs (
    id VARCHAR(64) NOT NULL, 
    source_id VARCHAR(128) NOT NULL, 
    job_id VARCHAR(64), 
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITHOUT TIME ZONE, 
    status VARCHAR(32) NOT NULL, 
    refusal_reason VARCHAR(128), 
    raw_ingested INTEGER NOT NULL, 
    unique_opportunities INTEGER NOT NULL, 
    inserted INTEGER NOT NULL, 
    unchanged INTEGER NOT NULL, 
    updated INTEGER NOT NULL, 
    error_message TEXT, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_source_poll_runs_source_id ON source_poll_runs (source_id);

CREATE INDEX ix_source_poll_runs_started_at ON source_poll_runs (started_at);

CREATE INDEX ix_source_poll_runs_status ON source_poll_runs (status);

CREATE INDEX ix_source_poll_runs_source_id_started_at ON source_poll_runs (source_id, started_at DESC);

CREATE TABLE founder_opportunity_views (
    id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    viewed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE INDEX ix_founder_opportunity_views_opportunity_id ON founder_opportunity_views (opportunity_id);

CREATE INDEX ix_founder_opportunity_views_viewed_at ON founder_opportunity_views (viewed_at);

CREATE TABLE founder_triage_states (
    opportunity_id VARCHAR(64) NOT NULL, 
    state VARCHAR(32) NOT NULL, 
    snoozed_until TIMESTAMP WITHOUT TIME ZONE, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (opportunity_id), 
    FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE INDEX ix_founder_triage_states_state ON founder_triage_states (state);

UPDATE alembic_version SET version_num='0002_match_evaluations' WHERE alembic_version.version_num = '0001_baseline_schema';

COMMIT;

