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
from .requirements import RequirementPriority


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
    """Evidence-backed evaluation result for an opportunity constraint.

    ``None`` for ``requirement_mandatory`` means available evidence does not
    establish whether the requirement is definitely mandatory.
    """
    constraint_name: str
    passed: bool | None  # True: passed, False: failed, None: unknown/uncertain
    reason: str
    required_field: str
    founder_fact: str
    is_hard_failure: bool = False
    provenance_pointer: str = ""
    # FR-008 evidence contract. The legacy names above remain part of the
    # persisted/API shape; these explicit fields make the decision auditable.
    constraint_type: str = ""
    job_evidence_text: str = ""
    job_evidence_field: str = ""
    source_pointer: str = ""
    founder_side_evidence: str = ""
    decision: bool | None = None
    confidence: float | None = None
    requirement_mandatory: bool | None = None
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.constraint_name:
            raise ValueError("constraint_name cannot be empty")
        if not self.required_field:
            raise ValueError("required_field cannot be empty")
        if self.passed is not None and not isinstance(self.passed, bool):
            raise ValueError("passed must be True, False, or None")
        if self.requirement_mandatory is not None and not isinstance(self.requirement_mandatory, bool):
            raise ValueError("requirement_mandatory must be True, False, or None")

        aliases = (
            ("constraint_type", self.constraint_type, self.constraint_name),
            ("source_pointer", self.source_pointer, self.provenance_pointer),
            ("founder_side_evidence", self.founder_side_evidence, self.founder_fact),
            ("explanation", self.explanation, self.reason),
        )
        for name, canonical, legacy in aliases:
            if canonical and legacy and canonical != legacy:
                raise ValueError(f"{name} conflicts with its compatibility field")
        object.__setattr__(self, "constraint_type", self.constraint_type or self.constraint_name)
        object.__setattr__(self, "source_pointer", self.source_pointer or self.provenance_pointer)
        object.__setattr__(self, "provenance_pointer", self.provenance_pointer or self.source_pointer)
        object.__setattr__(self, "founder_side_evidence", self.founder_side_evidence or self.founder_fact)
        object.__setattr__(self, "explanation", self.explanation or self.reason)
        object.__setattr__(self, "job_evidence_field", self.job_evidence_field or self.required_field)
        if not self.source_pointer.strip():
            raise ValueError("a hard-constraint result requires a valid job-side source pointer")
        if not self.founder_side_evidence.strip():
            raise ValueError("founder-side evidence cannot be empty")
        if not (self.job_evidence_text.strip() or self.job_evidence_field.strip()):
            raise ValueError("job-side evidence text or a structured field is required")

        if self.decision is not None and self.decision is not self.passed:
            raise ValueError("decision must match the compatibility field passed")
        object.__setattr__(self, "decision", self.passed)

        confidence = self.confidence
        if confidence is None:
            # A known pass/fail is supported by resolved evidence; UNKNOWN is
            # intentionally assigned lower confidence without changing its
            # tri-state meaning.
            confidence = 0.9 if self.passed is not None else 0.35
        confidence = float(confidence)
        object.__setattr__(self, "confidence", confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {confidence}")

        if self.is_hard_failure:
            if self.passed is not False:
                raise ValueError("a hard failure must have decision=False")
            pointer = self.source_pointer.strip()
            if not pointer or pointer.startswith("."):
                raise ValueError("a hard failure requires a valid job-side source pointer")
            if not (self.job_evidence_text.strip() or self.job_evidence_field.strip()):
                raise ValueError("a hard failure requires job-side evidence text or a structured field")


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
    #: Stable, code-owned marker tags a rule may attach to this dimension so a
    #: downstream consumer (e.g. api/filters.py's premium_fulltime_onsite
    #: filter) can key off a fixed vocabulary instead of matching prose in
    #: `gaps`/`explanation`, which is free to be reworded. Empty by default;
    #: every existing call site is unaffected. Currently emitted only by the
    #: premium full-time/on-site rule in matching/scorer.py ("premium_shortfall").
    signal_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (0.0 <= self.raw_score <= 1.0):
            raise ValueError(f"raw_score must be in [0.0, 1.0], got {self.raw_score}")
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"weight must be in [0.0, 1.0], got {self.weight}")


@dataclass(frozen=True, slots=True)
class ConfidenceFactor:
    """One inspectable evidence-quality input to the interim confidence score."""
    name: str
    score: float  # Heuristic 0.0 - 100.0; not gold-set calibrated.
    explanation: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("confidence factor name cannot be empty")
        if not (0.0 <= self.score <= 100.0):
            raise ValueError(f"confidence factor score must be in [0.0, 100.0], got {self.score}")


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
    # Preference fit is a separate, nullable ranking signal. None means no
    # stated preference had comparable Founder-side and job-side evidence.
    preference_score: float | None = None
    # Evidence confidence is an independent, heuristic signal. It does not
    # lower capability fit or convert unknown information into a negative.
    confidence_score: float | None = None
    confidence_factors: tuple[ConfidenceFactor, ...] = ()

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
    requirement_priority: RequirementPriority = RequirementPriority.UNKNOWN

    def __post_init__(self) -> None:
        if not self.requirement_text:
            raise ValueError("requirement_text cannot be empty")
        if isinstance(self.requirement_priority, str):
            try:
                object.__setattr__(self, "requirement_priority", RequirementPriority(self.requirement_priority))
            except ValueError as exc:
                raise ValueError(f"invalid requirement_priority: {self.requirement_priority}") from exc
        elif not isinstance(self.requirement_priority, RequirementPriority):
            raise ValueError("requirement_priority must be a RequirementPriority")


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
    predicate: str = ""
    authorized_value: str = ""
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


@dataclass(frozen=True, slots=True)
class OmittedItem:
    """A bullet, skill, summary variant, or entry the compiler considered
    but did not select for this opportunity, with the reason (BRIEF-FR-006
    D1 requirement 4: "what was left out and why"). Part of the artifact's
    API-visible data (`TailoredArtifact.omitted_items`), not only a UI
    nicety -- work order D2/C3 renders it."""
    section_id: str
    text: str
    reason: str
    claim_id: str = ""


def compute_artifact_hash(
    opportunity_id: str,
    opportunity_content_hash: str,
    artifact_type: str,
    sections: tuple[ArtifactSection, ...],
    claims: tuple[GeneratedClaim, ...],
    template_version: str = "",
    policy_version: str = "",
    commitment_checklist: tuple[ForwardCommitment, ...] = (),
) -> str:
    payload = {
        "opp_id": opportunity_id,
        "opp_hash": opportunity_content_hash,
        "type": artifact_type,
        "template_version": template_version,
        "policy_version": policy_version,
        "sections": [(s.section_id, s.heading, s.content, s.items, s.assertion_ids, s.evidence_ids) for s in sections],
        "claims": [
            (
                c.claim_id,
                c.text,
                c.section_id,
                c.assertion_ids,
                c.evidence_ids,
                c.predicate,
                c.authorized_value,
                c.is_forward_commitment,
                c.commitment_status.value,
                c.policy_source,
            )
            for c in claims
        ],
        "commitments": [(fc.commitment_type, fc.description, fc.status.value, fc.value, fc.policy_source) for fc in commitment_checklist],
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
    omitted_items: tuple[OmittedItem, ...] = ()
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        if not self.artifact_hash:
            computed = compute_artifact_hash(
                self.opportunity_id,
                self.opportunity_content_hash,
                self.artifact_type.value,
                self.sections,
                self.generated_claims,
                template_version=self.template_version,
                policy_version=self.policy_version,
                commitment_checklist=self.commitment_checklist,
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
    prohibited_jurisdictions: tuple[str, ...] = ()
    approved_delivery_jurisdictions: tuple[str, ...] = ()
    min_target_compensation: float | None = None
    min_target_yearly_compensation: float | None = None
    min_target_project_budget: float | None = None
    min_target_daily_rate: float | None = None
    min_target_hourly_rate: float | None = None
    employment_weights: dict[str, float] = field(default_factory=lambda: {
        "skills": 0.35,
        "experience": 0.20,
        "responsibilities": 0.15,
        # B3 (BRIEF-FR-006) council review #2 defect fix: this was the
        # policy default actually read by matching/scorer.py's
        # `weights.get("domain", ...)` fallback -- the fallback default
        # alone (previously edited in scorer.py) never fires while this key
        # is present, so it was the only place that mattered. The historical
        # 0.10 -> 0.05 reallocation funded the former target-role-family
        # preference; W3.1 names that contribution explicitly below.
        "domain": 0.05,
        "geography": 0.10,
        "compensation": 0.05,
        "trajectory": 0.05,
        # FR-008 W3.1 adds capability and preference dimensions before the
        # required real-Founder gold-set calibration. Keep new capability
        # dimensions visible but unweighted for now; this is not a calibrated
        # zero-importance judgment. Preserve the prior 0.05 target-role
        # preference contribution under an explicitly named preference key.
        "title_family": 0.0,
        "seniority": 0.0,
        "education_certification": 0.0,
        "target_role_family_preference": 0.05,
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
    default_currency: str | None = None
    default_availability_hours_per_week: int | None = None
    default_notice_period_days: int | None = None
    default_sponsorship_required: bool | None = None
    business_legal_name: str | None = None
    business_registration_country: str | None = None
    tax_identifier_available: bool = False
    guarantees_policy: str | None = None
    prohibited_jurisdictions: tuple[str, ...] = ()
    approved_delivery_jurisdictions: tuple[str, ...] = ()
    min_target_compensation: float | None = None
    min_target_yearly_compensation: float | None = None
    min_target_project_budget: float | None = None
    min_target_daily_rate: float | None = None
    min_target_hourly_rate: float | None = None
