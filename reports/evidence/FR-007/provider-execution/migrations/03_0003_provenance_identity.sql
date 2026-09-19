BEGIN;

-- Running upgrade 0002_match_evaluations -> 0003_provenance_identity

DELETE FROM field_provenances fp
        USING field_provenances fp_keep
        WHERE fp.opportunity_id = fp_keep.opportunity_id
          AND fp.field_name = fp_keep.field_name
          AND fp.record_checksum = fp_keep.record_checksum
          AND fp.id > fp_keep.id;

ALTER TABLE field_provenances ADD CONSTRAINT uq_field_provenances_identity UNIQUE (opportunity_id, field_name, record_checksum);

CREATE TABLE founder_filter_settings (
    filter_id VARCHAR(64) NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    mode VARCHAR(16) NOT NULL, 
    params_json TEXT, 
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (filter_id)
);

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('geo_eligibility', true, 'label_only', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('work_mode_onsite', true, 'label_only', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('red_lines', true, 'hide', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('excluded_industries', true, 'hide', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('track_preference', true, 'rank_only', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('target_roles', true, 'label_only', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('premium_fulltime_onsite', true, 'rank_only', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('stale_postings', true, 'label_only', '{}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('min_fit_score', false, 'hide', '{"min_score": 0}', '2000-01-01 00:00:00');

INSERT INTO founder_filter_settings (filter_id, enabled, mode, params_json, updated_at) VALUES ('compensation_floor', false, 'rank_only', '{"floor": 0, "currency": null}', '2000-01-01 00:00:00');

UPDATE alembic_version SET version_num='0003_provenance_identity' WHERE alembic_version.version_num = '0002_match_evaluations';

COMMIT;

