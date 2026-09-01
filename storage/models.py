import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class OpportunityRecord(Base):
    __tablename__ = "opportunities"

    id = Column(String(64), primary_key=True)
    track = Column(String(32), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    source_id = Column(String(128), nullable=False, index=True)
    source_url = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    country = Column(String(64), nullable=True)
    region = Column(String(64), nullable=True)
    geographic_scope = Column(String(64), nullable=True)
    posted_date = Column(String(64), nullable=True)
    deadline = Column(String(64), nullable=True)
    is_stale = Column(Boolean, default=False)
    reverified_at = Column(DateTime, nullable=True)
    raw_payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    provenances = relationship("FieldProvenanceRecord", back_populates="opportunity", cascade="all, delete-orphan")
    feedback = relationship("FounderFeedbackRecord", back_populates="opportunity", cascade="all, delete-orphan")


class FieldProvenanceRecord(Base):
    __tablename__ = "field_provenances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(64), nullable=False)
    raw_value = Column(Text, nullable=True)
    normalized_value = Column(Text, nullable=True)
    derivation_type = Column(String(64), nullable=False)
    raw_pointer = Column(String(128), nullable=True)
    record_checksum = Column(String(64), nullable=False)
    rule_id = Column(String(64), nullable=True)

    opportunity = relationship("OpportunityRecord", back_populates="provenances")


class OutboundActionRecordModel(Base):
    __tablename__ = "outbound_actions"

    id = Column(String(64), primary_key=True)
    opportunity_id = Column(String(64), nullable=False, index=True)
    opportunity_content_hash = Column(String(64), nullable=False)
    workspace = Column(String(64), nullable=False, index=True)
    candidate_id = Column(String(64), nullable=False, index=True)
    track = Column(String(32), nullable=False)
    source = Column(String(128), nullable=False)
    adapter_name = Column(String(64), nullable=False)
    adapter_version = Column(String(32), nullable=False)
    execution_mode = Column(String(32), nullable=False)
    qualification_decision = Column(String(32), nullable=False)
    match_score_snapshot = Column(Float, nullable=False)
    artifact_ids_json = Column(Text, nullable=False)
    artifact_hashes_json = Column(Text, nullable=False)
    manifest_hash = Column(String(64), nullable=False)
    action_status = Column(String(32), nullable=False, index=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    receipt_reference = Column(String(128), nullable=True)
    confirmation_text = Column(Text, nullable=True)
    receipt_checksum = Column(String(64), nullable=True)
    confirmation_evidence_json = Column(Text, nullable=True)
    blocker_reason = Column(Text, nullable=True)
    manual_edits_json = Column(Text, nullable=True)
    external_reference_id = Column(String(128), nullable=True)
    record_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class IdempotencyReservationRecord(Base):
    __tablename__ = "idempotency_reservations"

    idempotency_key = Column(String(128), primary_key=True)
    action_id = Column(String(64), nullable=False, index=True)
    workspace = Column(String(64), nullable=False)
    candidate_id = Column(String(64), nullable=False)
    opportunity_id = Column(String(64), nullable=False, index=True)
    action_type = Column(String(64), nullable=False)
    action_status = Column(String(32), nullable=False)
    record_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class InboundEvidenceRecord(Base):
    __tablename__ = "inbound_evidence"

    message_content_hash = Column(String(64), primary_key=True)
    provider = Column(String(64), nullable=False)
    provider_message_id = Column(String(128), nullable=False, index=True)
    thread_id = Column(String(128), nullable=False, index=True)
    sender_email = Column(String(255), nullable=False)
    sender_name = Column(String(255), nullable=False)
    recipient_email = Column(String(255), nullable=False)
    subject = Column(String(512), nullable=False)
    snippet = Column(Text, nullable=False)
    body_text = Column(Text, nullable=False)
    body_html = Column(Text, nullable=False)
    received_at = Column(DateTime, nullable=False)
    headers_json = Column(Text, nullable=False)
    attachment_names_json = Column(Text, nullable=False)
    processing_status = Column(String(32), default="FETCHED", nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)


class PipelineEventRecord(Base):
    __tablename__ = "pipeline_events"

    event_id = Column(String(64), primary_key=True)
    opportunity_id = Column(String(64), nullable=False, index=True)
    signal_id = Column(String(64), nullable=False, index=True)
    previous_stage = Column(String(64), nullable=False)
    new_stage = Column(String(64), nullable=False)
    track = Column(String(32), nullable=False)
    trigger_category = Column(String(64), nullable=False, index=True)
    message_content_hash = Column(String(64), nullable=False, index=True)
    occurred_at = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    actor = Column(String(64), nullable=False)
    notes = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("signal_id", "opportunity_id", name="uq_pipeline_signal_opp"),
    )


class NotificationRecord(Base):
    __tablename__ = "founder_notifications"

    notification_key = Column(String(128), primary_key=True)
    notification_id = Column(String(64), nullable=False, index=True)
    opportunity_id = Column(String(64), nullable=True, index=True)
    signal_id = Column(String(64), nullable=False, index=True)
    priority = Column(String(32), nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    action_required = Column(Boolean, default=False)
    deadline = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)


class InboxCheckpointRecord(Base):
    __tablename__ = "inbox_checkpoints"

    checkpoint_key = Column(String(128), primary_key=True)
    cursor_value = Column(String(255), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class ReconciliationRecordModel(Base):
    __tablename__ = "reconciliation_records"

    reconciliation_id = Column(String(64), primary_key=True)
    outbound_action_id = Column(String(64), nullable=False, index=True)
    opportunity_id = Column(String(64), nullable=False, index=True)
    signal_id = Column(String(64), nullable=False, index=True)
    inbound_content_hash = Column(String(64), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)


class WorkerJobRecord(Base):
    __tablename__ = "worker_jobs"

    id = Column(String(64), primary_key=True)
    job_type = Column(String(64), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    status = Column(String(32), default="PENDING", nullable=False, index=True)
    run_after = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    lease_owner = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class FounderFeedbackRecord(Base):
    __tablename__ = "founder_feedback"

    id = Column(String(64), primary_key=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    feedback_label = Column(String(64), nullable=False, index=True)
    structured_reason = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    dedup_hash = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    opportunity = relationship("OpportunityRecord", back_populates="feedback")
