"""OpportunityOS Matching, Qualification, and Tailoring Data Models and Protocol Contracts.

Provides immutable types for hard-constraint qualification, explainable multidimensional
scoring, requirement-to-evidence mappings, and truth-locked tailoring artifacts.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from opportunity.models import Opportunity, Track
from truth.models import AtomicAssertion, EvidenceRecord, MetricAssertion


class QualificationDecision(str, Enum):
    QUALIFIED = "qualified"
    INELIGIBLE = "ineligible"
    UNCERTAIN = "uncertain"


class RequirementSupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    GAP = "gap"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ArtifactType(str, Enum):
    TAILORED_CV = "tailored_cv"
    APPLICATION_NARRATIVE = "application_narrative"
    COVER_LETTER = "cover_letter"
    FREELANCE_PROPOSAL = "freelance_proposal"
    CAPABILITY_STATEMENT = "capability_statement"
    EOI_RESPONSE = "eoi_response"
    RFP_RESPONSE_SCAFFOLD = "rfp_response_scaffold"


class CommitmentStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class HardConstraintResult:
    """Evaluation result for an individual mandatory requirement."""
    constraint_name: str
    passed: bool | None  # True: passed, False: failed, None: unknown/uncertain
    reason: str
    required_field: str
    founder_fact: str
    is_hard_failure: bool = False
    provenance_pointer: str = ""

    def __post_init__(self) -> None:
        if not self.constraint_name:
            raise ValueError("constraint_name cannot be empty")


@dataclass(frozen=True, slots=True)
class MatchDimensionScore:
    """Scored evaluation along an explainable matching dimension."""
    dimension_name: str
    raw_score: float  # Normalized 0.0 - 1.0
    weight: float     # Weight 0.0 - 1.0
    weighted_score: float
    explanation: str
    strengths: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    opportunity_field_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (0.0 <= self.raw_score <= 1.0):
            raise ValueError(f"raw_score must be in [0.0, 1.0], got {self.raw_score}")
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"weight must be in [0.0, 1.0], got {self.weight}")


@dataclass(frozen=True, slots=True)
class MatchEvaluation:
    """Comprehensive, explainable opportunity match evaluation."""
    opportunity_id: str
    track: Track
    qualification_decision: QualificationDecision
    overall_fit_score: float  # 0.0 - 100.0
    hard_constraints: tuple[HardConstraintResult, ...]
    dimension_scores: tuple[MatchDimensionScore, ...]
    strengths: tuple[str, ...]
    gaps: tuple[str, ...]
    unknowns: tuple[str, ...]
    uncertainty_penalty: float
    explanation: str
    policy_version: str
    evaluated_at: str
    score_breakdown: tuple[tuple[str, float], ...] = ()

    @property
    def is_qualified(self) -> bool:
        return self.qualification_decision == QualificationDecision.QUALIFIED

    @property
    def is_ineligible(self) -> bool:
        return self.qualification_decision == QualificationDecision.INELIGIBLE

    @property
    def is_review_required(self) -> bool:
        return self.qualification_decision == QualificationDecision.UNCERTAIN


@dataclass(frozen=True, slots=True)
class RequirementMapping:
    """Mapping from a specific opportunity requirement to supporting truth evidence."""
    requirement_text: str
    requirement_type: str  # "skill", "responsibility", "experience", "education", "certification", "other"
    status: RequirementSupportStatus
    supporting_assertion_ids: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.requirement_text:
            raise ValueError("requirement_text cannot be empty")


@dataclass(frozen=True, slots=True)
class RequirementEvidenceMap:
    """Complete requirement-to-evidence graph for an opportunity."""
    opportunity_id: str
    mappings: tuple[RequirementMapping, ...]
    coverage_score: float = 0.0  # 0.0 - 1.0

    def get_status_counts(self) -> dict[RequirementSupportStatus, int]:
        counts = {status: 0 for status in RequirementSupportStatus}
        for m in self.mappings:
            counts[m.status] += 1
        return counts


@dataclass(frozen=True, slots=True)
class GeneratedClaim:
    """Atomic claim within a generated artifact tied to supporting truth."""
    claim_id: str
    text: str
    section_id: str
    assertion_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    is_forward_commitment: bool = False
    commitment_status: CommitmentStatus = CommitmentStatus.RESOLVED
    policy_source: str = ""


@dataclass(frozen=True, slots=True)
class ForwardCommitment:
    """Forward-looking commitment (e.g. rate, availability, staffing, guarantees)."""
    commitment_type: str  # "rate", "availability", "delivery_date", "staffing", "travel", "legal_status", "guarantee"
    description: str
    status: CommitmentStatus
    value: str
    policy_source: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactSection:
    """Structured section within a compiled artifact."""
    section_id: str
    heading: str
    content: str
    items: tuple[str, ...] = ()
    assertion_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def compute_artifact_hash(
    opportunity_id: str,
    opportunity_content_hash: str,
    artifact_type: str,
    sections: tuple[ArtifactSection, ...],
    claims: tuple[GeneratedClaim, ...],
) -> str:
    payload = {
        "opp_id": opportunity_id,
        "opp_hash": opportunity_content_hash,
        "type": artifact_type,
        "sections": [(s.section_id, s.heading, s.content, s.items) for s in sections],
        "claims": [(c.claim_id, c.text, c.assertion_ids, c.evidence_ids) for c in claims],
    }
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(dumped).hexdigest()


@dataclass(frozen=True, slots=True)
class TailoredArtifact:
    """Immutable, versioned artifact tailored to a specific opportunity."""
    artifact_id: str
    artifact_type: ArtifactType
    opportunity_id: str
    opportunity_content_hash: str
    template_version: str
    policy_version: str
    title: str
    sections: tuple[ArtifactSection, ...]
    generated_claims: tuple[GeneratedClaim, ...]
    commitment_checklist: tuple[ForwardCommitment, ...]
    compiled_at: str
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        if not self.artifact_hash:
            computed = compute_artifact_hash(
                self.opportunity_id,
                self.opportunity_content_hash,
                self.artifact_type.value,
                self.sections,
                self.generated_claims,
            )
            object.__setattr__(self, "artifact_hash", computed)


@dataclass(frozen=True, slots=True)
class ArtifactValidationResult:
    """Validation outcome for a tailored artifact against truth constraints."""
    is_valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    total_claims: int = 0
    verified_claims: int = 0
    unverified_claims: int = 0
    unresolved_commitments: int = 0


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    """Versioned scoring weights, thresholds, and execution configuration."""
    version: str = "1.0.0"
    auto_rejection_enabled: bool = False  # Disabled by default until >=95% founder precision demonstrated
    uncertainty_penalty_weight: float = 0.15
    employment_weights: dict[str, float] = field(default_factory=lambda: {
        "skills": 0.35,
        "experience": 0.20,
        "responsibilities": 0.15,
        "domain": 0.10,
        "geography": 0.10,
        "compensation": 0.05,
        "trajectory": 0.05,
    })
    independent_weights: dict[str, float] = field(default_factory=lambda: {
        "services": 0.35,
        "scope": 0.20,
        "portfolio": 0.20,
        "budget": 0.10,
        "delivery": 0.10,
        "evidence_sufficiency": 0.05,
    })


@dataclass(frozen=True, slots=True)
class TailoringPolicy:
    """Versioned tailoring and forward commitment policy."""
    version: str = "1.0.0"
    max_skills_highlighted: int = 10
    max_experience_bullets_per_role: int = 5
    default_hourly_rate: float | None = None
    default_daily_rate: float | None = None
    default_currency: str = "USD"
    default_availability_hours_per_week: int | None = None
    default_notice_period_days: int | None = None
    business_legal_name: str | None = None
    business_registration_country: str | None = None
    tax_identifier_available: bool = False
    guarantees_policy: str = "standard_professional_warranty"
