BEGIN;

-- Running upgrade 0006_feed_projection -> 0007_source_schedules

CREATE TABLE source_schedules (
    source_id VARCHAR(128) NOT NULL, 
    cadence_hours FLOAT NOT NULL, 
    last_attempt_at TIMESTAMP WITHOUT TIME ZONE, 
    last_success_at TIMESTAMP WITHOUT TIME ZONE, 
    next_due_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    cooldown_until TIMESTAMP WITHOUT TIME ZONE, 
    consecutive_failures INTEGER DEFAULT '0' NOT NULL, 
    last_status VARCHAR(32), 
    error_message TEXT, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (source_id)
);

CREATE INDEX ix_source_schedules_next_due_at ON source_schedules (next_due_at);

CREATE INDEX ix_source_schedules_cooldown_until ON source_schedules (cooldown_until);

UPDATE alembic_version SET version_num='0007_source_schedules' WHERE alembic_version.version_num = '0006_feed_projection';

COMMIT;

