"""Data Models for OpportunityOS Outbound Application Subsystem."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from matching.models import QualificationDecision
from opportunity.models import Track


class ExecutionMode(str, Enum):
    """Explicit outbound execution modes."""
    DRY_RUN = "dry_run"
    ASSISTED = "assisted"
    CONTROLLED_SUBMIT = "controlled_submit"


class ActionAuthorityDecision(str, Enum):
    """Decision emitted by the central ActionAuthority."""
    ALLOW_PREPARE = "allow_prepare"
    ALLOW_FILL = "allow_fill"
    ALLOW_SUBMIT = "allow_submit"
    PAUSE_FOR_REVIEW = "pause_for_review"
    BLOCK = "block"


class SourceActionPolicy(str, Enum):
    """Platform / source action permissions."""
    DISCOVERY_ALLOWED = "discovery_allowed"
    PREPARE_ALLOWED = "prepare_allowed"
    BROWSER_FILL_ALLOWED = "browser_fill_allowed"
    SUBMIT_ALLOWED = "submit_allowed"
    API_ACTION_ALLOWED = "api_action_allowed"
    MANUAL_ONLY = "manual_only"
    PROHIBITED = "prohibited"


class AdapterLifecycleState(str, Enum):
    """Adapter graduation lifecycle states."""
    EXPERIMENTAL = "experimental"
    DRY_RUN_VERIFIED = "dry_run_verified"
    ASSISTED_VERIFIED = "assisted_verified"
    SUBMIT_ELIGIBLE = "submit_eligible"
    SUBMIT_ENABLED = "submit_enabled"
    SUSPENDED = "suspended"


class FieldOntologyType(str, Enum):
    """19 Canonical application field ontology types."""
    IDENTITY = "identity"
    CONTACT = "contact"
    ADDRESS_LOCATION = "address_location"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    LINKS = "links"
    WORK_AUTHORIZATION = "work_authorization"
    SPONSORSHIP = "sponsorship"
    COMPENSATION = "compensation"
    AVAILABILITY = "availability"
    TRAVEL = "travel"
    RELOCATION = "relocation"
    DEMOGRAPHIC_VOLUNTARY = "demographic_voluntary"
    CUSTOM_NARRATIVE = "custom_narrative"
    LEGAL_DECLARATION = "legal_declaration"
    SECURITY_CLEARANCE = "security_clearance"
    CONFLICT_OF_INTEREST = "conflict_of_interest"
    ATTACHMENT = "attachment"
    OTHER_UNKNOWN = "other_unknown"


class AnswerClass(str, Enum):
    """Deterministic answer safety classes."""
    GREEN = "green"    # TruthGraph backed
    YELLOW = "yellow"  # Policy backed
    RED = "red"        # Sensitive / Legal / Review required


class ActionStatus(str, Enum):
    """Durable submission ledger states."""
    PLANNED = "planned"
    PREPARED = "prepared"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED_SAFE = "failed_safe"
    BLOCKED = "blocked"
    UNKNOWN_OUTCOME = "unknown_outcome"


@dataclass(frozen=True, slots=True)
class ApplicationAnswer:
    """Atomic answered field with full provenance."""
    opportunity_id: str
    opportunity_content_hash: str
    action_id: str
    field_type: FieldOntologyType
    original_label: str
    normalized_question: str
    answer: Any
    answer_class: AnswerClass
    answer_source: str
    assertion_ids: tuple[str, ...] = ()
    policy_source: str = ""
    claim_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    disposition: str = "auto_fill"
    timestamp: str = "2026-08-30T00:00:00Z"

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            raise ValueError("opportunity_id cannot be empty")
        if not self.opportunity_content_hash:
            raise ValueError("opportunity_content_hash cannot be empty")
        if self.answer_class == AnswerClass.GREEN and not self.assertion_ids and not self.answer_source.startswith("truth_graph:"):
            raise ValueError("GREEN answer requires supporting assertion_ids or truth_graph source")
        if self.answer_class == AnswerClass.YELLOW and not self.policy_source:
            raise ValueError("YELLOW answer requires supporting policy_source")


@dataclass(frozen=True, slots=True)
class DetectedFormField:
    """Detected interactive field from form/page inspection."""
    field_id: str
    name: str
    field_type: str  # text, textarea, select, file, radio, checkbox
    label: str
    normalized_label: str
    ontology_type: FieldOntologyType
    required: bool = False
    options: tuple[str, ...] = ()
    step_index: int = 0
    sensitivity_class: AnswerClass = AnswerClass.GREEN


@dataclass(frozen=True, slots=True)
class ConfirmationEvidence:
    """Cryptographic evidence of successful application submission."""
    confirmed: bool
    confirmation_text: str
    application_id: str = ""
    receipt_reference: str = ""
    final_url: str = ""
    detected_at: str = "2026-08-30T00:00:00Z"
    evidence_checksum: str = ""

    def __post_init__(self) -> None:
        if self.confirmed and not self.evidence_checksum:
            digest = hashlib.sha256(
                f"{self.confirmation_text}:{self.application_id}:{self.receipt_reference}:{self.final_url}".encode()
            ).hexdigest()
            object.__setattr__(self, "evidence_checksum", digest)


@dataclass(frozen=True, slots=True)
class PreSubmitManifest:
    """Cryptographic pre-submission manifest binding all authorities."""
    workspace: str
    candidate_id: str
    opportunity_id: str
    opportunity_content_hash: str
    action_type: str
    adapter_name: str
    adapter_version: str
    source_policy_version: str
    artifact_ids: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    answers: tuple[ApplicationAnswer, ...]
    answers_hash: str
    qualification_decision: QualificationDecision
    unresolved_questions_count: int
    red_answers_count: int
    idempotency_key: str
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        if not self.manifest_hash:
            data = {
                "workspace": self.workspace,
                "candidate_id": self.candidate_id,
                "opportunity_id": self.opportunity_id,
                "opportunity_content_hash": self.opportunity_content_hash,
                "action_type": self.action_type,
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
                "source_policy_version": self.source_policy_version,
                "artifact_ids": list(self.artifact_ids),
                "artifact_hashes": list(self.artifact_hashes),
                "answers_hash": self.answers_hash,
                "qualification_decision": self.qualification_decision.value,
                "unresolved_questions_count": self.unresolved_questions_count,
                "red_answers_count": self.red_answers_count,
                "idempotency_key": self.idempotency_key,
            }
            digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()
            object.__setattr__(self, "manifest_hash", digest)


@dataclass(frozen=True, slots=True)
class OutboundActionRecord:
    """Canonical outbound ledger record."""
    action_id: str
    opportunity_id: str
    opportunity_content_hash: str
    track: Track
    source: str
    adapter_name: str
    adapter_version: str
    execution_mode: ExecutionMode
    qualification_decision: QualificationDecision
    match_score_snapshot: float
    artifact_ids: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    answer_manifest_hash: str
    action_status: ActionStatus
    idempotency_key: str
    created_at: str
    updated_at: str
    confirmation_evidence: ConfirmationEvidence | None = None
    blocker_reason: str = ""
    manual_edits: tuple[str, ...] = ()
    external_reference_id: str = ""
