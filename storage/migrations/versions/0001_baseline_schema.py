"""0001_baseline_schema

Revision ID: 0001_baseline_schema
Revises: 
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_baseline_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'opportunities',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('track', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('organization', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('source_id', sa.String(length=128), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('country', sa.String(length=64), nullable=True),
        sa.Column('region', sa.String(length=64), nullable=True),
        sa.Column('geographic_scope', sa.String(length=64), nullable=True),
        sa.Column('posted_date', sa.String(length=64), nullable=True),
        sa.Column('deadline', sa.String(length=64), nullable=True),
        sa.Column('is_stale', sa.Boolean(), nullable=True),
        sa.Column('reverified_at', sa.DateTime(), nullable=True),
        sa.Column('raw_payload_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_opportunities_content_hash'), 'opportunities', ['content_hash'], unique=False)
    op.create_index(op.f('ix_opportunities_organization'), 'opportunities', ['organization'], unique=False)
    op.create_index(op.f('ix_opportunities_source_id'), 'opportunities', ['source_id'], unique=False)
    op.create_index(op.f('ix_opportunities_track'), 'opportunities', ['track'], unique=False)

    op.create_table(
        'field_provenances',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('field_name', sa.String(length=64), nullable=False),
        sa.Column('raw_value', sa.Text(), nullable=True),
        sa.Column('normalized_value', sa.Text(), nullable=True),
        sa.Column('derivation_type', sa.String(length=64), nullable=False),
        sa.Column('raw_pointer', sa.String(length=128), nullable=True),
        sa.Column('record_checksum', sa.String(length=64), nullable=False),
        sa.Column('rule_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_field_provenances_opportunity_id'), 'field_provenances', ['opportunity_id'], unique=False)

    op.create_table(
        'outbound_actions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_content_hash', sa.String(length=64), nullable=False),
        sa.Column('workspace', sa.String(length=64), nullable=False),
        sa.Column('candidate_id', sa.String(length=64), nullable=False),
        sa.Column('track', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=128), nullable=False),
        sa.Column('adapter_name', sa.String(length=64), nullable=False),
        sa.Column('adapter_version', sa.String(length=32), nullable=False),
        sa.Column('execution_mode', sa.String(length=32), nullable=False),
        sa.Column('qualification_decision', sa.String(length=32), nullable=False),
        sa.Column('match_score_snapshot', sa.Float(), nullable=False),
        sa.Column('artifact_ids_json', sa.Text(), nullable=False),
        sa.Column('artifact_hashes_json', sa.Text(), nullable=False),
        sa.Column('manifest_hash', sa.String(length=64), nullable=False),
        sa.Column('action_status', sa.String(length=32), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('receipt_reference', sa.String(length=128), nullable=True),
        sa.Column('confirmation_text', sa.Text(), nullable=True),
        sa.Column('receipt_checksum', sa.String(length=64), nullable=True),
        sa.Column('confirmation_evidence_json', sa.Text(), nullable=True),
        sa.Column('blocker_reason', sa.Text(), nullable=True),
        sa.Column('manual_edits_json', sa.Text(), nullable=True),
        sa.Column('external_reference_id', sa.String(length=128), nullable=True),
        sa.Column('record_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outbound_actions_action_status'), 'outbound_actions', ['action_status'], unique=False)
    op.create_index(op.f('ix_outbound_actions_candidate_id'), 'outbound_actions', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_outbound_actions_idempotency_key'), 'outbound_actions', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_outbound_actions_opportunity_id'), 'outbound_actions', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_outbound_actions_workspace'), 'outbound_actions', ['workspace'], unique=False)

    op.create_table(
        'idempotency_reservations',
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('action_id', sa.String(length=64), nullable=False),
        sa.Column('workspace', sa.String(length=64), nullable=False),
        sa.Column('candidate_id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('action_status', sa.String(length=32), nullable=False),
        sa.Column('record_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('idempotency_key')
    )
    op.create_index(op.f('ix_idempotency_reservations_action_id'), 'idempotency_reservations', ['action_id'], unique=False)
    op.create_index(op.f('ix_idempotency_reservations_opportunity_id'), 'idempotency_reservations', ['opportunity_id'], unique=False)

    op.create_table(
        'inbound_evidence',
        sa.Column('message_content_hash', sa.String(length=64), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('provider_message_id', sa.String(length=128), nullable=False),
        sa.Column('thread_id', sa.String(length=128), nullable=False),
        sa.Column('sender_email', sa.String(length=255), nullable=False),
        sa.Column('sender_name', sa.String(length=255), nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=512), nullable=False),
        sa.Column('snippet', sa.Text(), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('headers_json', sa.Text(), nullable=False),
        sa.Column('attachment_names_json', sa.Text(), nullable=False),
        sa.Column('processing_status', sa.String(length=32), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('message_content_hash')
    )
    op.create_index(op.f('ix_inbound_evidence_processing_status'), 'inbound_evidence', ['processing_status'], unique=False)
    op.create_index(op.f('ix_inbound_evidence_provider_message_id'), 'inbound_evidence', ['provider_message_id'], unique=False)
    op.create_index(op.f('ix_inbound_evidence_thread_id'), 'inbound_evidence', ['thread_id'], unique=False)

    op.create_table(
        'pipeline_events',
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('signal_id', sa.String(length=64), nullable=False),
        sa.Column('previous_stage', sa.String(length=64), nullable=False),
        sa.Column('new_stage', sa.String(length=64), nullable=False),
        sa.Column('track', sa.String(length=32), nullable=False),
        sa.Column('trigger_category', sa.String(length=64), nullable=False),
        sa.Column('message_content_hash', sa.String(length=64), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('actor', sa.String(length=64), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
        sa.UniqueConstraint('signal_id', 'opportunity_id', name='uq_pipeline_signal_opp')
    )
    op.create_index(op.f('ix_pipeline_events_message_content_hash'), 'pipeline_events', ['message_content_hash'], unique=False)
    op.create_index(op.f('ix_pipeline_events_opportunity_id'), 'pipeline_events', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_pipeline_events_signal_id'), 'pipeline_events', ['signal_id'], unique=False)
    op.create_index(op.f('ix_pipeline_events_trigger_category'), 'pipeline_events', ['trigger_category'], unique=False)

    op.create_table(
        'founder_notifications',
        sa.Column('notification_key', sa.String(length=128), nullable=False),
        sa.Column('notification_id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=True),
        sa.Column('signal_id', sa.String(length=64), nullable=False),
        sa.Column('priority', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('action_required', sa.Boolean(), nullable=False),
        sa.Column('deadline', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('acknowledged', sa.Boolean(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('notification_key')
    )
    op.create_index(op.f('ix_founder_notifications_category'), 'founder_notifications', ['category'], unique=False)
    op.create_index(op.f('ix_founder_notifications_notification_id'), 'founder_notifications', ['notification_id'], unique=False)
    op.create_index(op.f('ix_founder_notifications_opportunity_id'), 'founder_notifications', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_founder_notifications_priority'), 'founder_notifications', ['priority'], unique=False)
    op.create_index(op.f('ix_founder_notifications_signal_id'), 'founder_notifications', ['signal_id'], unique=False)

    op.create_table(
        'inbox_checkpoints',
        sa.Column('checkpoint_key', sa.String(length=128), nullable=False),
        sa.Column('cursor_value', sa.String(length=255), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('checkpoint_key')
    )

    op.create_table(
        'reconciliation_records',
        sa.Column('reconciliation_id', sa.String(length=64), nullable=False),
        sa.Column('outbound_action_id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('signal_id', sa.String(length=64), nullable=False),
        sa.Column('inbound_content_hash', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('reconciliation_id')
    )
    op.create_index(op.f('ix_reconciliation_records_inbound_content_hash'), 'reconciliation_records', ['inbound_content_hash'], unique=False)
    op.create_index(op.f('ix_reconciliation_records_opportunity_id'), 'reconciliation_records', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_records_outbound_action_id'), 'reconciliation_records', ['outbound_action_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_records_signal_id'), 'reconciliation_records', ['signal_id'], unique=False)

    op.create_table(
        'worker_jobs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('job_type', sa.String(length=64), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('run_after', sa.DateTime(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('lease_owner', sa.String(length=64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_worker_jobs_job_type'), 'worker_jobs', ['job_type'], unique=False)
    op.create_index(op.f('ix_worker_jobs_run_after'), 'worker_jobs', ['run_after'], unique=False)
    op.create_index(op.f('ix_worker_jobs_status'), 'worker_jobs', ['status'], unique=False)

    op.create_table(
        'founder_feedback',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('feedback_label', sa.String(length=64), nullable=False),
        sa.Column('structured_reason', sa.String(length=128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('dedup_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_founder_feedback_dedup_hash'), 'founder_feedback', ['dedup_hash'], unique=True)
    op.create_index(op.f('ix_founder_feedback_feedback_label'), 'founder_feedback', ['feedback_label'], unique=False)
    op.create_index(op.f('ix_founder_feedback_opportunity_id'), 'founder_feedback', ['opportunity_id'], unique=False)


def downgrade() -> None:
    op.drop_table('founder_feedback')
    op.drop_table('worker_jobs')
    op.drop_table('reconciliation_records')
    op.drop_table('inbox_checkpoints')
    op.drop_table('founder_notifications')
    op.drop_table('pipeline_events')
    op.drop_table('inbound_evidence')
    op.drop_table('idempotency_reservations')
    op.drop_table('outbound_actions')
    op.drop_table('field_provenances')
    op.drop_table('opportunities')
