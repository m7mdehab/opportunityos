"""Canonical data models for Inbound Message Ingestion, Signals, and Operational Pipeline."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from matching.models import Track


class SignalCategory(str, Enum):
    """Dual-track signal ontology categories."""
    # Employment Track
    APPLICATION_CONFIRMATION = "application_confirmation"
    REJECTION = "rejection"
    RECRUITER_OUTREACH = "recruiter_outreach"
    ASSESSMENT = "assessment"
    INTERVIEW_REQUEST = "interview_request"
    OFFER = "offer"
    INFORMATION_REQUEST = "information_request"

    # Independent / Client / Procurement Track
    PROPOSAL_CONFIRMATION = "proposal_confirmation"
    CLIENT_OR_BUYER_RESPONSE = "client_or_buyer_response"
    CLARIFICATION_REQUEST = "clarification_request"
    SHORTLIST_OR_INVITATION = "shortlist_or_invitation"
    DISCOVERY_CALL_OR_MEETING_REQUEST = "discovery_call_or_meeting_request"
    PROPOSAL_REJECTION = "proposal_rejection"
    AWARD_OR_WIN = "award_or_win"
    CONTRACT_PROGRESS = "contract_progress"
    PROCUREMENT_AMENDMENT = "procurement_amendment"
    PROCUREMENT_DEADLINE_CHANGE = "procurement_deadline_change"

    # Noise & Ambiguity
    MARKETING = "marketing"
    GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION = "generic_platform_notification"
    UNCLASSIFIED = "unclassified"


class SignalPriority(str, Enum):
    """Urgency / attention tier for inbound signals."""
    URGENT = "urgent"      # Immediate action required (e.g. interview invitation with 24h deadline, offer)
    HIGH = "high"          # Direct recruiter/client reply, assessment, clarification request
    MEDIUM = "medium"      # Proposal clarification, general information request
    LOW = "low"            # Application/proposal confirmation, generic rejection
    NOISE = "noise"        # Platform marketing, newsletter, spam


class CorrelationStatus(str, Enum):
    """Confidence and status of correlating inbound signals to opportunities."""
    EXACT_REFERENCE_MATCH = "exact_reference_match"
    THREAD_LINKED = "thread_linked"
    SOURCE_ID_MATCH = "source_id_match"
    STRONG_MULTI_FIELD_MATCH = "strong_multi_field_match"
    AMBIGUOUS_MULTI_CANDIDATE = "ambiguous_multi_candidate"
    UNLINKED = "unlinked"
    REVIEW_REQUIRED = "review_required"


class OpportunityStage(str, Enum):
    """Operational pipeline stages for dual-track opportunities."""
    DISCOVERED = "discovered"
    QUALIFIED = "qualified"
    APPLIED = "applied"
    IN_REVIEW = "in_review"
    ASSESSMENT_SCHEDULED = "assessment_scheduled"
    INTERVIEWING = "interviewing"
    OFFER_RECEIVED = "offer_received"
    AWARDED = "awarded"
    REJECTED = "rejected"
    CLOSED_UNRESPONSIVE = "closed_unresponsive"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class InboundMessageEvidence:
    """Immutable evidence of an ingested inbound email/message."""
    provider: str
    provider_message_id: str
    thread_id: str
    sender_email: str
    sender_name: str
    recipient_email: str
    subject: str
    snippet: str
    body_text: str
    body_html: str
    received_at: str
    headers: tuple[tuple[str, str], ...] = ()
    attachment_names: tuple[str, ...] = ()
    message_content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.message_content_hash:
            data = {
                "provider": self.provider,
                "provider_message_id": self.provider_message_id,
                "thread_id": self.thread_id,
                "sender_email": self.sender_email,
                "recipient_email": self.recipient_email,
                "subject": self.subject,
                "received_at": self.received_at,
                "body_text": self.body_text,
            }
            digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()
            object.__setattr__(self, "message_content_hash", digest)


@dataclass(frozen=True, slots=True)
class ExtractedDeadline:
    """Explicitly extracted deadline from message text without hallucination."""
    raw_snippet: str
    iso_timestamp: str | None
    is_ambiguous: bool
    requires_human_verification: bool
    deadline_type: str = "general"


@dataclass(frozen=True, slots=True)
class InboundSignal:
    """Atomic classified operational signal derived from inbound message evidence."""
    signal_id: str
    message_content_hash: str
    provider_message_id: str
    category: SignalCategory
    priority: SignalPriority
    track: Track
    confidence: float
    summary: str
    sender_email: str
    detected_at: str
    deadline: ExtractedDeadline | None = None
    extracted_references: tuple[str, ...] = ()
    extracted_organization: str = ""
    extracted_role_title: str = ""
    requires_founder_action: bool = False
    action_description: str = ""


@dataclass(frozen=True, slots=True)
class CorrelationEvidence:
    """Cryptographic and deterministic proof linking a signal to an Opportunity / Outbound Action."""
    signal_id: str
    opportunity_id: str | None
    outbound_action_id: str | None
    status: CorrelationStatus
    matching_criteria: tuple[str, ...]
    confidence: float
    is_authoritative: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    """Immutable lifecycle event committed to the operational pipeline event log."""
    event_id: str
    opportunity_id: str
    signal_id: str
    previous_stage: OpportunityStage
    new_stage: OpportunityStage
    track: Track
    trigger_category: SignalCategory
    message_content_hash: str
    occurred_at: str
    recorded_at: str
    actor: str = "system_inbound_engine"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class DerivedOpportunityState:
    """Current derived operational state for a specific opportunity."""
    opportunity_id: str
    track: Track
    current_stage: OpportunityStage
    latest_event_id: str
    last_signal_category: SignalCategory
    last_signal_at: str
    active_action_required: bool
    action_deadline: str | None = None
    action_summary: str = ""
    event_history_count: int = 0
    reconciliation_required: bool = False
    reconciliation_reason: str = ""


@dataclass(frozen=True, slots=True)
class FounderNotificationRecord:
    """Idempotent actionable notification record for the founder."""
    notification_id: str
    notification_key: str
    opportunity_id: str | None
    signal_id: str
    priority: SignalPriority
    category: SignalCategory
    title: str
    message: str
    action_required: bool
    deadline: str | None
    created_at: str
    acknowledged: bool = False
    acknowledged_at: str | None = None
