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
    LargeBinary,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
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

    # A1M (BRIEF-FR-006, migration 0004_founder_control) -- founder-control
    # columns. Field names are the contract shared with the concurrent
    # opportunity/models.py work order; do not rename.
    work_mode = Column(String(16), nullable=False, default="unspecified", index=True)
    work_mode_source = Column(String(16), nullable=True)
    location_country = Column(String(2), nullable=True, index=True)
    location_city = Column(String(128), nullable=True)
    # Source-native remote regions may be a comma-separated list of countries;
    # this must not be truncated because it is retained source truth.
    location_region = Column(Text, nullable=True)
    remote_scope = Column(String(24), nullable=False, default="unspecified")
    remote_scope_regions = Column(Text, nullable=True)
    employment_type = Column(String(24), nullable=False, default="unspecified")
    seniority_level = Column(String(24), nullable=False, default="unspecified")
    compensation_min = Column(Integer, nullable=True)
    compensation_max = Column(Integer, nullable=True)
    compensation_currency = Column(String(8), nullable=True)
    compensation_period = Column(String(16), nullable=True)
    title_family = Column(String(64), nullable=True, index=True)
    title_level = Column(String(24), nullable=True)
    family_key = Column(String(64), nullable=True, index=True)
    # Text().with_variant(...): plain TEXT on every non-PostgreSQL dialect
    # (SQLite, used by several test suites' Base.metadata.create_all(), has no
    # tsvector type and cannot compile a bare TSVECTOR column) and the real
    # ``tsvector`` type on PostgreSQL, where migration 0004_founder_control's
    # GIN index (ix_opportunities_search_tsv) actually lives.
    search_tsv = Column(Text().with_variant(TSVECTOR(), "postgresql"), nullable=True)

    provenances = relationship("FieldProvenanceRecord", back_populates="opportunity", cascade="all, delete-orphan")
    feedback = relationship("FounderFeedbackRecord", back_populates="opportunity", cascade="all, delete-orphan")

    __table_args__ = (
        # Council review #3, finding 7: `storage/models.py` declared none of
        # migration 0004's five indexes, so `compare_metadata` reported five
        # spurious `remove_index` operations at head, `init_db()`'s
        # `create_all` produced a schema missing the GIN index entirely, and
        # `alembic revision --autogenerate` would have proposed dropping all
        # five. This GIN index matches
        # `0004_founder_control.py::upgrade`'s `ix_opportunities_search_tsv`
        # exactly (name and `postgresql_using='gin'`); the other four are
        # `index=True` on the columns above (also name-matching the
        # migration's `ix_opportunities_<column>` indexes).
        Index(
            "ix_opportunities_search_tsv",
            "search_tsv",
            postgresql_using="gin",
        ),
    )


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

    __table_args__ = (
        # Natural identity for a provenance row (see migration
        # 0003_provenance_identity for why this tuple, not the brief's
        # ("opportunity_id", "field_name", "source_locator") -- there is no
        # source_locator column, and raw_pointer, the closest analogue, is
        # nullable and therefore unusable in a PostgreSQL unique constraint).
        # The surrogate ``id`` stays the primary key so ``Session.merge()``
        # (storage/repository.py) has a stable target; this constraint is
        # what gives the row its natural identity and prevents a re-poll
        # from accumulating duplicate provenance rows for the same field.
        UniqueConstraint(
            "opportunity_id", "field_name", "record_checksum", name="uq_field_provenances_identity"
        ),
    )


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


class FounderSessionRecord(Base):
    __tablename__ = "founder_sessions"

    id = Column(String(64), primary_key=True)
    token_digest = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    user_agent_hash = Column(String(64), nullable=True)
    auth_version = Column(String(16), nullable=False, default="v1")


class FounderAuthRateLimitRecord(Base):
    __tablename__ = "founder_auth_rate_limit"

    id = Column(String(32), primary_key=True)
    window_started_at = Column(DateTime(timezone=True), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class FounderAuthEventRecord(Base):
    __tablename__ = "founder_auth_events"

    id = Column(String(64), primary_key=True)
    event_type = Column(String(32), nullable=False, index=True)
    outcome = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    request_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)


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


class MatchEvaluationRecord(Base):
    __tablename__ = "match_evaluations"

    id = Column(String(64), primary_key=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    truth_pack_hash = Column(String(64), nullable=False, index=True)
    qualification_decision = Column(String(32), nullable=False)
    #: 0.0-100.0 (NOT 0.0-1.0). See matching.models.MatchEvaluation.overall_fit_score,
    #: which this column stores verbatim -- any threshold compared against this
    #: column (e.g. a "high_fit" cutoff) must be on the same 0-100 scale.
    fit_score = Column(Float, nullable=False)
    dimension_scores_json = Column(Text, nullable=False)
    reasons_json = Column(Text, nullable=False)
    #: JSON: {"hard_constraints": [{"constraint_name", "passed" (true|false|null,
    #: null=UNKNOWN, never coerced to false), "reason", "required_field",
    #: "founder_fact", "is_hard_failure", "provenance_pointer"}], "strengths": [str],
    #: "gaps": [str], "unknowns": [str], "uncertainty_penalty": float, "explanation": str}.
    #: Nullable: rows written before this column existed (there are none yet --
    #: migration 0002 is unreleased) have no detail payload.
    evaluation_detail_json = Column(Text, nullable=True)
    policy_version = Column(String(32), nullable=False)
    evaluated_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("opportunity_id", "truth_pack_hash", name="uq_match_evaluations_opportunity_truth_pack"),
    )


class SourcePollRunRecord(Base):
    __tablename__ = "source_poll_runs"

    id = Column(String(64), primary_key=True)
    source_id = Column(String(128), nullable=False, index=True)
    job_id = Column(String(64), nullable=True)
    started_at = Column(DateTime, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False, index=True)
    refusal_reason = Column(String(128), nullable=True)
    raw_ingested = Column(Integer, default=0, nullable=False)
    unique_opportunities = Column(Integer, default=0, nullable=False)
    inserted = Column(Integer, default=0, nullable=False)
    unchanged = Column(Integer, default=0, nullable=False)
    updated = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        # Supports "latest run per source" lookups (e.g. /api/sources/health)
        # without a full table scan.
        Index("ix_source_poll_runs_source_id_started_at", "source_id", started_at.desc()),
    )


class FounderOpportunityViewRecord(Base):
    __tablename__ = "founder_opportunity_views"

    id = Column(String(64), primary_key=True)
    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    viewed_at = Column(DateTime, nullable=False, index=True)


class FounderTriageStateRecord(Base):
    __tablename__ = "founder_triage_states"

    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True)
    state = Column(String(32), nullable=False, index=True)
    snoozed_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, nullable=False)


class FounderFilterSettingRecord(Base):
    """D3 (BRIEF-FR-005) -- one row per named founder-controlled filter.

    Table and defaults live in migration ``0003_provenance_identity`` (D3's
    marked block), shared with D5's provenance work in that revision. Every
    fresh database has all ten filters seeded by the migration itself, so the
    API never has to invent a default on first read.

    ``mode`` is one of ``hide`` | ``rank_only`` | ``label_only`` (see
    ``api/filters.py``). ``params_json`` is nullable free-form JSON for the
    handful of filters that take founder-supplied parameters (``min_fit_score``,
    ``compensation_floor``); every other filter's params are ``{}``.

    Timezone convention for ``updated_at``: this column is naive (no
    ``timezone=True``), matching every other ``DateTime`` column in this
    module (e.g. ``MatchEvaluationRecord.evaluated_at``). Writers must strip
    tzinfo from an already-UTC value before writing (see
    ``matching/evaluate_persist.py::_to_naive_utc`` and
    ``api/filters.py::to_naive_utc``) rather than handing psycopg2 a tz-aware
    datetime, which PostgreSQL would silently convert using the session's
    ``timezone`` GUC before storing it naive.
    """

    __tablename__ = "founder_filter_settings"

    filter_id = Column(String(64), primary_key=True)
    enabled = Column(Boolean, nullable=False)
    mode = Column(String(16), nullable=False)
    params_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False)


class OpportunityFamilyRecord(Base):
    """A1M (BRIEF-FR-006, migration 0004_founder_control)."""

    __tablename__ = "opportunity_families"

    family_key = Column(String(64), primary_key=True)
    employer = Column(String(256), nullable=True)
    normalized_title = Column(String(256), nullable=True)
    member_count = Column(Integer, nullable=True)
    best_member_id = Column(String(64), nullable=True)
    split_out = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=True)


class FounderFacetRecord(Base):
    """A1M (BRIEF-FR-006, migration 0004_founder_control)."""

    __tablename__ = "founder_facets"

    facet_id = Column(String(64), primary_key=True)
    mode = Column(String(16), nullable=False, default="off")
    values_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class FounderSavedViewRecord(Base):
    """A1M (BRIEF-FR-006, migration 0004_founder_control)."""

    __tablename__ = "founder_saved_views"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    facets_json = Column(Text, nullable=True)
    search_query = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class ArtifactCacheRecord(Base):
    """A1M (BRIEF-FR-006, migration 0004_founder_control)."""

    __tablename__ = "artifact_cache"

    cache_key = Column(String(128), primary_key=True)
    opportunity_id = Column(String(64), nullable=True)
    truth_pack_hash = Column(String(64), nullable=True)
    template_id = Column(String(32), nullable=True)
    artifact_kind = Column(String(32), nullable=True)
    content_type = Column(String(128), nullable=True)
    payload = Column(LargeBinary, nullable=True)
    storage_backend = Column(String(32), nullable=False, default="postgres_payload", server_default="postgres_payload")
    object_key = Column(String(256), nullable=True)
    payload_sha256 = Column(String(64), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    generation_version = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=True)


class FounderCVSelectionRecord(Base):
    """Durable fixed-CV identity selected by the authoritative Python selector."""

    __tablename__ = "founder_cv_selections"

    opportunity_id = Column(String(64), ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True)
    variant = Column(String(64), nullable=False)
    object_path = Column(String(256), nullable=False)
    sha256 = Column(String(64), nullable=False)
    selected_at = Column(DateTime, nullable=False)
    truth_pack_hash = Column(String(64), nullable=True)

class SourceScheduleRecord(Base):
    """FR-007 W11: Persisted source scheduling, cadence, next-due, and cooldown state.

    Ensures that source cadence and rate-limit cooldowns survive scheduler/worker
    process restarts without warm-up storms.
    """

    __tablename__ = "source_schedules"

    source_id = Column(String(128), primary_key=True)
    cadence_hours = Column(Float, nullable=False)
    last_attempt_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    next_due_at = Column(DateTime, nullable=False, index=True)
    cooldown_until = Column(DateTime, nullable=True, index=True)
    consecutive_failures = Column(Integer, default=0, nullable=False)
    last_status = Column(String(32), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
