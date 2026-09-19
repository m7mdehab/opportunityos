BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_baseline_schema

CREATE TABLE opportunities (
    id VARCHAR(64) NOT NULL, 
    track VARCHAR(32) NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    organization VARCHAR(255) NOT NULL, 
    description TEXT NOT NULL, 
    source_id VARCHAR(128) NOT NULL, 
    source_url TEXT NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    country VARCHAR(64), 
    region VARCHAR(64), 
    geographic_scope VARCHAR(64), 
    posted_date VARCHAR(64), 
    deadline VARCHAR(64), 
    is_stale BOOLEAN, 
    reverified_at TIMESTAMP WITHOUT TIME ZONE, 
    raw_payload_json TEXT, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_opportunities_content_hash ON opportunities (content_hash);

CREATE INDEX ix_opportunities_organization ON opportunities (organization);

CREATE INDEX ix_opportunities_source_id ON opportunities (source_id);

CREATE INDEX ix_opportunities_track ON opportunities (track);

CREATE TABLE field_provenances (
    id SERIAL NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    field_name VARCHAR(64) NOT NULL, 
    raw_value TEXT, 
    normalized_value TEXT, 
    derivation_type VARCHAR(64) NOT NULL, 
    raw_pointer VARCHAR(128), 
    record_checksum VARCHAR(64) NOT NULL, 
    rule_id VARCHAR(64), 
    PRIMARY KEY (id), 
    FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE INDEX ix_field_provenances_opportunity_id ON field_provenances (opportunity_id);

CREATE TABLE outbound_actions (
    id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    opportunity_content_hash VARCHAR(64) NOT NULL, 
    workspace VARCHAR(64) NOT NULL, 
    candidate_id VARCHAR(64) NOT NULL, 
    track VARCHAR(32) NOT NULL, 
    source VARCHAR(128) NOT NULL, 
    adapter_name VARCHAR(64) NOT NULL, 
    adapter_version VARCHAR(32) NOT NULL, 
    execution_mode VARCHAR(32) NOT NULL, 
    qualification_decision VARCHAR(32) NOT NULL, 
    match_score_snapshot FLOAT NOT NULL, 
    artifact_ids_json TEXT NOT NULL, 
    artifact_hashes_json TEXT NOT NULL, 
    manifest_hash VARCHAR(64) NOT NULL, 
    action_status VARCHAR(32) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    receipt_reference VARCHAR(128), 
    confirmation_text TEXT, 
    receipt_checksum VARCHAR(64), 
    confirmation_evidence_json TEXT, 
    blocker_reason TEXT, 
    manual_edits_json TEXT, 
    external_reference_id VARCHAR(128), 
    record_json TEXT, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_outbound_actions_action_status ON outbound_actions (action_status);

CREATE INDEX ix_outbound_actions_candidate_id ON outbound_actions (candidate_id);

CREATE UNIQUE INDEX ix_outbound_actions_idempotency_key ON outbound_actions (idempotency_key);

CREATE INDEX ix_outbound_actions_opportunity_id ON outbound_actions (opportunity_id);

CREATE INDEX ix_outbound_actions_workspace ON outbound_actions (workspace);

CREATE TABLE idempotency_reservations (
    idempotency_key VARCHAR(128) NOT NULL, 
    action_id VARCHAR(64) NOT NULL, 
    workspace VARCHAR(64) NOT NULL, 
    candidate_id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    action_type VARCHAR(64) NOT NULL, 
    action_status VARCHAR(32) NOT NULL, 
    record_json TEXT NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (idempotency_key)
);

CREATE INDEX ix_idempotency_reservations_action_id ON idempotency_reservations (action_id);

CREATE INDEX ix_idempotency_reservations_opportunity_id ON idempotency_reservations (opportunity_id);

CREATE TABLE inbound_evidence (
    message_content_hash VARCHAR(64) NOT NULL, 
    provider VARCHAR(64) NOT NULL, 
    provider_message_id VARCHAR(128) NOT NULL, 
    thread_id VARCHAR(128) NOT NULL, 
    sender_email VARCHAR(255) NOT NULL, 
    sender_name VARCHAR(255) NOT NULL, 
    recipient_email VARCHAR(255) NOT NULL, 
    subject VARCHAR(512) NOT NULL, 
    snippet TEXT NOT NULL, 
    body_text TEXT NOT NULL, 
    body_html TEXT NOT NULL, 
    received_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    headers_json TEXT NOT NULL, 
    attachment_names_json TEXT NOT NULL, 
    processing_status VARCHAR(32) NOT NULL, 
    processed_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (message_content_hash)
);

CREATE INDEX ix_inbound_evidence_processing_status ON inbound_evidence (processing_status);

CREATE INDEX ix_inbound_evidence_provider_message_id ON inbound_evidence (provider_message_id);

CREATE INDEX ix_inbound_evidence_thread_id ON inbound_evidence (thread_id);

CREATE TABLE pipeline_events (
    event_id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    signal_id VARCHAR(64) NOT NULL, 
    previous_stage VARCHAR(64) NOT NULL, 
    new_stage VARCHAR(64) NOT NULL, 
    track VARCHAR(32) NOT NULL, 
    trigger_category VARCHAR(64) NOT NULL, 
    message_content_hash VARCHAR(64) NOT NULL, 
    occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    recorded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    actor VARCHAR(64) NOT NULL, 
    notes TEXT NOT NULL, 
    PRIMARY KEY (event_id), 
    CONSTRAINT uq_pipeline_signal_opp UNIQUE (signal_id, opportunity_id)
);

CREATE INDEX ix_pipeline_events_message_content_hash ON pipeline_events (message_content_hash);

CREATE INDEX ix_pipeline_events_opportunity_id ON pipeline_events (opportunity_id);

CREATE INDEX ix_pipeline_events_signal_id ON pipeline_events (signal_id);

CREATE INDEX ix_pipeline_events_trigger_category ON pipeline_events (trigger_category);

CREATE TABLE founder_notifications (
    notification_key VARCHAR(128) NOT NULL, 
    notification_id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64), 
    signal_id VARCHAR(64) NOT NULL, 
    priority VARCHAR(32) NOT NULL, 
    category VARCHAR(64) NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    message TEXT NOT NULL, 
    action_required BOOLEAN NOT NULL, 
    deadline VARCHAR(64), 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    acknowledged BOOLEAN NOT NULL, 
    acknowledged_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (notification_key)
);

CREATE INDEX ix_founder_notifications_category ON founder_notifications (category);

CREATE INDEX ix_founder_notifications_notification_id ON founder_notifications (notification_id);

CREATE INDEX ix_founder_notifications_opportunity_id ON founder_notifications (opportunity_id);

CREATE INDEX ix_founder_notifications_priority ON founder_notifications (priority);

CREATE INDEX ix_founder_notifications_signal_id ON founder_notifications (signal_id);

CREATE TABLE inbox_checkpoints (
    checkpoint_key VARCHAR(128) NOT NULL, 
    cursor_value VARCHAR(255) NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (checkpoint_key)
);

CREATE TABLE reconciliation_records (
    reconciliation_id VARCHAR(64) NOT NULL, 
    outbound_action_id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    signal_id VARCHAR(64) NOT NULL, 
    inbound_content_hash VARCHAR(64) NOT NULL, 
    reason TEXT NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    resolved BOOLEAN NOT NULL, 
    resolved_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (reconciliation_id)
);

CREATE INDEX ix_reconciliation_records_inbound_content_hash ON reconciliation_records (inbound_content_hash);

CREATE INDEX ix_reconciliation_records_opportunity_id ON reconciliation_records (opportunity_id);

CREATE INDEX ix_reconciliation_records_outbound_action_id ON reconciliation_records (outbound_action_id);

CREATE INDEX ix_reconciliation_records_signal_id ON reconciliation_records (signal_id);

CREATE TABLE worker_jobs (
    id VARCHAR(64) NOT NULL, 
    job_type VARCHAR(64) NOT NULL, 
    payload_json TEXT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    run_after TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    retry_count INTEGER NOT NULL, 
    max_retries INTEGER NOT NULL, 
    lease_owner VARCHAR(64), 
    lease_expires_at TIMESTAMP WITHOUT TIME ZONE, 
    error_message TEXT, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    updated_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_worker_jobs_job_type ON worker_jobs (job_type);

CREATE INDEX ix_worker_jobs_run_after ON worker_jobs (run_after);

CREATE INDEX ix_worker_jobs_status ON worker_jobs (status);

CREATE TABLE founder_feedback (
    id VARCHAR(64) NOT NULL, 
    opportunity_id VARCHAR(64) NOT NULL, 
    feedback_label VARCHAR(64) NOT NULL, 
    structured_reason VARCHAR(128), 
    notes TEXT, 
    dedup_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_founder_feedback_dedup_hash ON founder_feedback (dedup_hash);

CREATE INDEX ix_founder_feedback_feedback_label ON founder_feedback (feedback_label);

CREATE INDEX ix_founder_feedback_opportunity_id ON founder_feedback (opportunity_id);

INSERT INTO alembic_version (version_num) VALUES ('0001_baseline_schema') RETURNING alembic_version.version_num;

COMMIT;

