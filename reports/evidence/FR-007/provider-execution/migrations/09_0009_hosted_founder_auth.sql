BEGIN;

-- Running upgrade 0008_artifact_storage -> 0009_hosted_founder_auth

CREATE TABLE founder_sessions (
    id VARCHAR(64) NOT NULL, 
    token_digest VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    last_seen_at TIMESTAMP WITH TIME ZONE, 
    user_agent_hash VARCHAR(64), 
    auth_version VARCHAR(16) DEFAULT 'v1' NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (token_digest)
);

CREATE UNIQUE INDEX ix_founder_sessions_token_digest ON founder_sessions (token_digest);

CREATE INDEX ix_founder_sessions_expires_at ON founder_sessions (expires_at);

CREATE INDEX ix_founder_sessions_revoked_at ON founder_sessions (revoked_at);

CREATE TABLE founder_auth_rate_limit (
    id VARCHAR(32) NOT NULL, 
    window_started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    attempt_count INTEGER DEFAULT '0' NOT NULL, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE founder_auth_events (
    id VARCHAR(64) NOT NULL, 
    event_type VARCHAR(32) NOT NULL, 
    outcome VARCHAR(32) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    request_id VARCHAR(64), 
    session_id VARCHAR(64), 
    PRIMARY KEY (id)
);

CREATE INDEX ix_founder_auth_events_event_type ON founder_auth_events (event_type);

CREATE INDEX ix_founder_auth_events_created_at ON founder_auth_events (created_at);

CREATE INDEX ix_founder_auth_events_request_id ON founder_auth_events (request_id);

CREATE INDEX ix_founder_auth_events_session_id ON founder_auth_events (session_id);

ALTER TABLE artifact_cache ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY artifact_cache_browser_deny_anon ON artifact_cache FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY artifact_cache_browser_deny_authenticated ON artifact_cache FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE feed_projection ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY feed_projection_browser_deny_anon ON feed_projection FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY feed_projection_browser_deny_authenticated ON feed_projection FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE field_provenances ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY field_provenances_browser_deny_anon ON field_provenances FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY field_provenances_browser_deny_authenticated ON field_provenances FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_auth_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_auth_events_browser_deny_anon ON founder_auth_events FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_auth_events_browser_deny_authenticated ON founder_auth_events FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_auth_rate_limit ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_auth_rate_limit_browser_deny_anon ON founder_auth_rate_limit FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_auth_rate_limit_browser_deny_authenticated ON founder_auth_rate_limit FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_facets ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_facets_browser_deny_anon ON founder_facets FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_facets_browser_deny_authenticated ON founder_facets FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_feedback ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_feedback_browser_deny_anon ON founder_feedback FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_feedback_browser_deny_authenticated ON founder_feedback FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_filter_settings ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_filter_settings_browser_deny_anon ON founder_filter_settings FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_filter_settings_browser_deny_authenticated ON founder_filter_settings FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_notifications ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_notifications_browser_deny_anon ON founder_notifications FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_notifications_browser_deny_authenticated ON founder_notifications FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_opportunity_views ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_opportunity_views_browser_deny_anon ON founder_opportunity_views FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_opportunity_views_browser_deny_authenticated ON founder_opportunity_views FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_saved_views ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_saved_views_browser_deny_anon ON founder_saved_views FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_saved_views_browser_deny_authenticated ON founder_saved_views FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_sessions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_sessions_browser_deny_anon ON founder_sessions FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_sessions_browser_deny_authenticated ON founder_sessions FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE founder_triage_states ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY founder_triage_states_browser_deny_anon ON founder_triage_states FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY founder_triage_states_browser_deny_authenticated ON founder_triage_states FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE idempotency_reservations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY idempotency_reservations_browser_deny_anon ON idempotency_reservations FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY idempotency_reservations_browser_deny_authenticated ON idempotency_reservations FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE inbound_evidence ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY inbound_evidence_browser_deny_anon ON inbound_evidence FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY inbound_evidence_browser_deny_authenticated ON inbound_evidence FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE inbox_checkpoints ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY inbox_checkpoints_browser_deny_anon ON inbox_checkpoints FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY inbox_checkpoints_browser_deny_authenticated ON inbox_checkpoints FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE match_evaluations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY match_evaluations_browser_deny_anon ON match_evaluations FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY match_evaluations_browser_deny_authenticated ON match_evaluations FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY opportunities_browser_deny_anon ON opportunities FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY opportunities_browser_deny_authenticated ON opportunities FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE opportunity_families ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY opportunity_families_browser_deny_anon ON opportunity_families FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY opportunity_families_browser_deny_authenticated ON opportunity_families FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE outbound_actions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY outbound_actions_browser_deny_anon ON outbound_actions FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY outbound_actions_browser_deny_authenticated ON outbound_actions FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE pipeline_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY pipeline_events_browser_deny_anon ON pipeline_events FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY pipeline_events_browser_deny_authenticated ON pipeline_events FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE reconciliation_records ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY reconciliation_records_browser_deny_anon ON reconciliation_records FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY reconciliation_records_browser_deny_authenticated ON reconciliation_records FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE source_poll_runs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY source_poll_runs_browser_deny_anon ON source_poll_runs FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY source_poll_runs_browser_deny_authenticated ON source_poll_runs FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE source_schedules ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY source_schedules_browser_deny_anon ON source_schedules FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY source_schedules_browser_deny_authenticated ON source_schedules FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

ALTER TABLE worker_jobs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'CREATE POLICY worker_jobs_browser_deny_anon ON worker_jobs FOR ALL TO anon USING (false) WITH CHECK (false)'; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'CREATE POLICY worker_jobs_browser_deny_authenticated ON worker_jobs FOR ALL TO authenticated USING (false) WITH CHECK (false)'; END IF; END $$;

UPDATE alembic_version SET version_num='0009_hosted_founder_auth' WHERE alembic_version.version_num = '0008_artifact_storage';

COMMIT;

