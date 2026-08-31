import json
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
    outbound_actions = relationship("OutboundActionRecord", back_populates="opportunity", cascade="all, delete-orphan")
    idempotency_reservations = relationship("IdempotencyReservationRecord", back_populates="opportunity", cascade="all, delete-orphan")
    pipeline_events = relationship("PipelineEventRecord", back_populates="opportunity", cascade="all, delete-orphan")
    notifications = relationship("NotificationRecord", back_populates="opportunity", cascade="all, delete-orphan")


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


class OutboundActionRecord(Base):
    __tablename__ = "outbound_actions"

    id = Column(String(64), primary_key=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_mode = Column(String(32), nullable=False)
    action_status = Column(String(32), nullable=False, index=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    prepared_manifest_hash = Column(String(64), nullable=True)
    receipt_reference = Column(String(128), nullable=True)
    confirmation_text = Column(Text, nullable=True)
    receipt_checksum = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    opportunity = relationship("OpportunityRecord", back_populates="outbound_actions")


class IdempotencyReservationRecord(Base):
    __tablename__ = "idempotency_reservations"

    idempotency_key = Column(String(128), primary_key=True)
    action_id = Column(String(64), nullable=False, index=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String(32), nullable=False)

    opportunity = relationship("OpportunityRecord", back_populates="idempotency_reservations")


class InboundEvidenceRecord(Base):
    __tablename__ = "inbound_evidence"

    id = Column(String(64), primary_key=True)
    message_id = Column(String(128), nullable=False, index=True)
    source_provider = Column(String(64), nullable=False)
    sender = Column(String(255), nullable=False)
    subject = Column(String(512), nullable=False)
    body_hash = Column(String(64), nullable=False)
    received_at = Column(DateTime, nullable=False)
    processing_status = Column(String(32), default="FETCHED", nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    raw_headers_json = Column(Text, nullable=True)


class PipelineEventRecord(Base):
    __tablename__ = "pipeline_events"

    id = Column(String(64), primary_key=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    signal_id = Column(String(64), nullable=False, index=True)
    signal_category = Column(String(64), nullable=False, index=True)
    source_timestamp = Column(DateTime, nullable=False)
    confidence = Column(Float, nullable=False)
    provenance_hash = Column(String(64), nullable=False)
    event_metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    opportunity = relationship("OpportunityRecord", back_populates="pipeline_events")

    __table_args__ = (
        UniqueConstraint("opportunity_id", "signal_id", name="uq_pipeline_opp_signal"),
    )


class NotificationRecord(Base):
    __tablename__ = "notifications"

    id = Column(String(64), primary_key=True)
    notification_key = Column(String(128), unique=True, nullable=False, index=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    priority = Column(String(32), nullable=False, index=True)
    headline = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    action_required = Column(Boolean, default=False)
    deadline = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    opportunity = relationship("OpportunityRecord", back_populates="notifications")


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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    opportunity = relationship("OpportunityRecord", back_populates="feedback")
