"""Outbound Application and Action Authority Data Models."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from matching.models import QualificationDecision, TailoredArtifact, Track
from truth.models import VerificationStatus


class ExecutionMode(str, Enum):
    """Governed execution modes for outbound workflows."""
    DRY_RUN = "dry_run"                    # Read-only preparation and planning; zero side effects
    ASSISTED = "assisted"                  # Browser automation to fill forms & upload artifacts; ZERO submit
    CONTROLLED_SUBMIT = "controlled_submit" # Fully automated submission for graduated & enabled adapters


class ActionAuthorityDecision(str, Enum):
    """Decision emitted by the Central Action Authority."""
    ALLOW_PREPARE = "allow_prepare"
    ALLOW_FILL = "allow_fill"
    ALLOW_SUBMIT = "allow_submit"
    PAUSE_FOR_REVIEW = "pause_for_review"
    BLOCK = "block"


class SourceActionPolicy(str, Enum):
    """Action permissions per platform / adapter."""
    PROHIBITED = "prohibited"
    MANUAL_ONLY = "manual_only"
    BROWSER_FILL_ALLOWED = "browser_fill_allowed"
    SUBMIT_ALLOWED = "submit_allowed"
    API_ACTION_ALLOWED = "api_action_allowed"


class AdapterLifecycleState(str, Enum):
    """Formal graduation lifecycle states for outbound adapters."""
    EXPERIMENTAL = "experimental"
    SHADOW_TESTED = "shadow_tested"
    ASSISTED_VERIFIED = "assisted_verified"
    SUBMIT_ELIGIBLE = "submit_eligible"
    SUBMIT_ENABLED = "submit_enabled"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"


class FieldOntologyType(str, Enum):
    """Canonical 19-type field ontology for application form fields."""
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
    """Three-tier answer classification policy."""
    GREEN = "green"   # Sourced strictly from verified TruthGraph assertions
    YELLOW = "yellow" # Sourced strictly from explicit TailoringPolicy preferences
    RED = "red"       # Sensitive, legal, narrative, or ambiguous declarations -> PAUSE


class ActionStatus(str, Enum):
    """Lifecycle state of an outbound application action."""
    PLANNED = "planned"
    PREPARED = "prepared"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    UNKNOWN_OUTCOME = "unknown_outcome"
    BLOCKED = "blocked"
    AWAITING_REVIEW = "awaiting_review"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BoundArtifact:
    """Artifact bound to explicit candidate and workspace ownership."""
    artifact: TailoredArtifact
    candidate_id: str = "founder"
    workspace: str = "default"

    @property
    def artifact_id(self) -> str:
        return self.artifact.artifact_id

    @property
    def artifact_type(self) -> Any:
        return self.artifact.artifact_type

    @property
    def opportunity_id(self) -> str:
        return self.artifact.opportunity_id

    @property
    def opportunity_content_hash(self) -> str:
        return self.artifact.opportunity_content_hash

    @property
    def artifact_hash(self) -> str:
        return self.artifact.artifact_hash

    @property
    def sections(self) -> Any:
        return self.artifact.sections

    @property
    def generated_claims(self) -> Any:
        return self.artifact.generated_claims

    @property
    def commitment_checklist(self) -> Any:
        return self.artifact.commitment_checklist

    @property
    def compiled_at(self) -> str:
        return self.artifact.compiled_at

    @property
    def template_version(self) -> str:
        return self.artifact.template_version

    @property
    def policy_version(self) -> str:
        return self.artifact.policy_version

    @property
    def title(self) -> str:
        return self.artifact.title


@dataclass(frozen=True, slots=True)
class ApplicationAnswer:
    """Atomic answer to an application question with verified provenance."""
    opportunity_id: str
    opportunity_content_hash: str
    action_id: str
    field_type: FieldOntologyType
    original_label: str
    normalized_question: str
    answer: Any | None
    answer_class: AnswerClass
    answer_source: str
    assertion_ids: tuple[str, ...] = ()
    policy_source: str = ""
    disposition: str = "auto_fill"

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            raise ValueError("opportunity_id is required")
        if not self.action_id:
            raise ValueError("action_id is required")
        if self.answer_class == AnswerClass.GREEN:
            if not self.assertion_ids or not self.answer_source.startswith("truth_graph:"):
                raise ValueError("Green answers must have atomic assertion_ids and truth_graph source")
            if self.answer is None:
                raise ValueError("Green answers cannot have answer=None")
        elif self.answer_class == AnswerClass.YELLOW:
            if not self.policy_source:
                raise ValueError("Yellow answers must specify policy_source")
            if self.answer is None:
                raise ValueError("Yellow answers cannot have answer=None")
        elif self.answer_class == AnswerClass.RED:
            if self.answer is not None and self.disposition == "auto_fill":
                raise ValueError("Red answers cannot be auto_filled without explicit review/override")


@dataclass(frozen=True, slots=True)
class DetectedFormField:
    """Detected interactive field from form/page inspection."""
    field_id: str
    name: str
    field_type: str
    label: str
    normalized_label: str
    ontology_type: FieldOntologyType
    required: bool = False
    options: tuple[str, ...] = ()
    step_index: int = 0
    sensitivity_class: AnswerClass = AnswerClass.GREEN


@dataclass(frozen=True, slots=True)
class GraduationRecord:
    """Authoritative graduation record for an outbound adapter."""
    adapter_id: str
    version: str
    lifecycle_state: AdapterLifecycleState
    source_compatibility: tuple[str, ...]
    evidence_hash: str
    verified_at: str
    submit_enabled_by_founder: bool = False


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
    graduation_record_version: str
    source_policy_version: str
    artifact_ids: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    answers: tuple[ApplicationAnswer, ...]
    answers_hash: str
    qualification_decision: QualificationDecision
    unresolved_mandatory_count: int
    red_answers_count: int
    idempotency_key: str
    compiled_at: str
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
                "graduation_record_version": self.graduation_record_version,
                "source_policy_version": self.source_policy_version,
                "artifact_ids": list(self.artifact_ids),
                "artifact_hashes": list(self.artifact_hashes),
                "answers_hash": self.answers_hash,
                "qualification_decision": self.qualification_decision.value,
                "unresolved_mandatory_count": self.unresolved_mandatory_count,
                "red_answers_count": self.red_answers_count,
                "idempotency_key": self.idempotency_key,
                "compiled_at": self.compiled_at,
            }
            digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()
            object.__setattr__(self, "manifest_hash", digest)


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
class OutboundActionRecord:
    """Canonical outbound ledger record."""
    action_id: str
    opportunity_id: str
    opportunity_content_hash: str
    workspace: str
    candidate_id: str
    track: Track
    source: str
    adapter_name: str
    adapter_version: str
    execution_mode: ExecutionMode
    qualification_decision: QualificationDecision
    match_score_snapshot: float
    artifact_ids: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    manifest_hash: str
    action_status: ActionStatus
    idempotency_key: str
    created_at: str
    updated_at: str
    confirmation_evidence: ConfirmationEvidence | None = None
    blocker_reason: str = ""
    manual_edits: tuple[str, ...] = ()
    external_reference_id: str = ""
