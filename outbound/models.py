"""Data models for outbound application and engagement workflows."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from matching.models import (
    ArtifactType,
    QualificationDecision,
    TailoredArtifact,
    Track,
)


class ExecutionMode(str, Enum):
    """Operational mode for outbound workflows."""
    DRY_RUN = "dry_run"
    ASSISTED = "assisted"
    CONTROLLED_SUBMIT = "controlled_submit"


class ActionStatus(str, Enum):
    """Lifecycle status for outbound actions in the idempotency ledger."""
    PLANNED = "planned"
    PREPARED = "prepared"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNKNOWN_OUTCOME = "unknown_outcome"
    BLOCKED = "blocked"


class AdapterLifecycleState(str, Enum):
    """Authoritative graduation lifecycle state for outbound adapters."""
    EXPERIMENTAL = "experimental"
    SHADOW_TESTED = "shadow_tested"
    PROPOSED = "proposed"
    DEVELOPED = "developed"
    TESTED_OFFLINE = "tested_offline"
    SHADOW_RUN_PASSING = "shadow_run_passing"
    ASSISTED_VERIFIED = "assisted_verified"
    SUBMIT_ELIGIBLE = "submit_eligible"
    SUBMIT_ENABLED = "submit_enabled"
    DEPRECATED = "deprecated"


class SourceActionPolicy(str, Enum):
    """Permission level for outbound external interactions on a per-source basis."""
    PROHIBITED = "prohibited"
    MANUAL_ONLY = "manual_only"
    DISCOVERY_ALLOWED = "discovery_allowed"
    PREPARE_ALLOWED = "prepare_allowed"
    BROWSER_FILL_ALLOWED = "browser_fill_allowed"
    SUBMIT_ALLOWED = "submit_allowed"
    API_ACTION_ALLOWED = "api_action_allowed"


class FieldOntologyType(str, Enum):
    """Canonical 19-type interactive form field ontology."""
    IDENTITY = "identity"
    CONTACT = "contact"
    ADDRESS_LOCATION = "address_location"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    LINKS = "links"
    RESUME_CV = "resume_cv"
    COVER_LETTER = "cover_letter"
    ATTACHMENT = "attachment"
    WORK_AUTHORIZATION = "work_authorization"
    SPONSORSHIP = "sponsorship"
    AVAILABILITY = "availability"
    COMPENSATION = "compensation"
    LOCATION_PREFERENCE = "location_preference"
    TRAVEL = "travel"
    RELOCATION = "relocation"
    DEMOGRAPHIC_VOLUNTARY = "demographic_voluntary"
    CUSTOM_NARRATIVE = "custom_narrative"
    LEGAL_DECLARATION = "legal_declaration"
    SECURITY_CLEARANCE = "security_clearance"
    CONFLICT_OF_INTEREST = "conflict_of_interest"
    OTHER_UNKNOWN = "other_unknown"


class AnswerClass(str, Enum):
    """Sensitivity classification for form answers."""
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class ActionAuthorityDecision(str, Enum):
    """Pre-action evaluation decision by ActionAuthority."""
    ALLOW_PREPARE = "allow_prepare"
    ALLOW_FILL = "allow_fill"
    ALLOW_SUBMIT = "allow_submit"
    PAUSE_FOR_REVIEW = "pause_for_review"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class BoundArtifact:
    """A TailoredArtifact bound to an explicit candidate_id and workspace."""
    artifact: TailoredArtifact
    candidate_id: str
    workspace: str

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.candidate_id.strip():
            raise ValueError("BoundArtifact requires explicit non-empty candidate_id")
        if not self.workspace or not self.workspace.strip():
            raise ValueError("BoundArtifact requires explicit non-empty workspace")

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
    """Atomic answer to an application question with verified provenance and confidence."""
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
    generated_claim_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    timestamp: str = ""
    disposition: str = "auto_fill"

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            raise ValueError("opportunity_id is required")
        if not self.action_id:
            raise ValueError("action_id is required")
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc).isoformat())

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
    """Cryptographic pre-submission manifest binding all material authorities."""
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
    graduation_evidence_hash: str = ""
    tailoring_policy_version: str = "1.0.0"
    compiled_at: str = ""
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        if not self.compiled_at:
            object.__setattr__(self, "compiled_at", datetime.now(timezone.utc).isoformat())
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
                "graduation_evidence_hash": self.graduation_evidence_hash,
                "source_policy_version": self.source_policy_version,
                "tailoring_policy_version": self.tailoring_policy_version,
                "artifact_ids": list(self.artifact_ids),
                "artifact_hashes": list(self.artifact_hashes),
                "answers_hash": self.answers_hash,
                "qualification_decision": self.qualification_decision.value,
                "unresolved_mandatory_count": self.unresolved_mandatory_count,
                "red_answers_count": self.red_answers_count,
                "idempotency_key": self.idempotency_key,
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
