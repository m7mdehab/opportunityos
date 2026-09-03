"""Immutable domain models for the OpportunityOS professional truth graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
import math
import re
from types import MappingProxyType
from typing import Any, Mapping


class _StringEnum(str, Enum):
    """Enum whose values serialize predictably as lower-case strings."""

    def __str__(self) -> str:
        return self.value


class VerificationStatus(_StringEnum):
    VERIFIED = "verified"
    APPROXIMATE = "approximate"
    UNVERIFIED = "unverified"
    EXPLICIT_NULL = "explicit_null"


class AssertionType(_StringEnum):
    DIRECT_FACT = "direct_fact"
    NORMALIZED_FACT = "normalized_fact"
    DERIVED_CAPABILITY = "derived_capability"
    USER_ASSERTION = "user_assertion"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    PROHIBITED_CLAIM = "prohibited_claim"


class Polarity(_StringEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Modality(_StringEnum):
    DEFINITE = "definite"
    APPROXIMATE = "approximate"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    CONDITIONAL = "conditional"
    PLANNED = "planned"


class RelationType(_StringEnum):
    ACHIEVED_DURING = "achieved_during"
    UTILIZES_SKILL = "utilizes_skill"
    DELIVERED_SERVICE = "delivered_service"
    APPLIED_TOOL = "applied_tool"
    BELONGS_TO_ENTITY = "belongs_to_entity"
    QUALIFIES_FOR = "qualifies_for"


class ProhibitedConceptCategory(_StringEnum):
    GUARANTEED_OUTCOME = "guaranteed_outcome"
    FORTUNE_500_PRESTIGE = "fortune_500_prestige"
    UNAUTHORIZED_LEGAL_PRACTICE = "unauthorized_legal_practice"
    UNAUTHORIZED_MEDICAL_PRACTICE = "unauthorized_medical_practice"
    SECURITY_CLEARANCE = "security_clearance"
    IP_EXCLUSIVITY_WARRANTY = "ip_exclusivity_warranty"
    FEE_CIRCUMVENTION = "fee_circumvention"
    UNHELD_CREDENTIAL = "unheld_credential"
    UNBACKED_COMMERCIAL_CAPACITY = "unbacked_commercial_capacity"


class CertificationState(_StringEnum):
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    EXPIRED = "expired"
    PLANNED = "planned"


class EngagementType(_StringEnum):
    FIXED_PRICE = "fixed_price"
    TIME_AND_MATERIALS = "time_and_materials"
    RETAINER = "retainer"
    FRACTIONAL = "fractional"
    CONSULTANT_TENDER = "consultant_tender"


class MetricVerification(_StringEnum):
    VERIFIED = "verified"
    APPROXIMATE = "approximate"
    UNAVAILABLE = "unavailable"


def _require_identifier(value: str, field_name: str = "id") -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{field_name} must be a non-empty identifier without whitespace")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _freeze_value(item) for key, item in sorted(value.items())})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _validate_evidence_ids(evidence_ids: tuple[str, ...], *, allow_empty: bool = False) -> None:
    if not isinstance(evidence_ids, tuple):
        raise ValueError("evidence_ids must be an immutable tuple")
    if not evidence_ids and not allow_empty:
        raise ValueError("at least one evidence_id is required")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence_ids must be unique")
    for evidence_id in evidence_ids:
        _require_identifier(evidence_id, "evidence_id")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    id: str
    content: str | None
    source: str
    locator: str
    assertion_type: AssertionType = AssertionType.DIRECT_FACT
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    observed_at: date | datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.source, "source")
        _require_text(self.locator, "locator")
        if not isinstance(self.assertion_type, AssertionType):
            raise ValueError("assertion_type must be an AssertionType")
        if not isinstance(self.verification_status, VerificationStatus):
            raise ValueError("verification_status must be a VerificationStatus")
        if self.verification_status is VerificationStatus.EXPLICIT_NULL:
            if self.content is not None:
                raise ValueError("explicit-null evidence must have content=None")
        elif self.content is None or not self.content.strip():
            raise ValueError("non-null evidence must have non-empty content")
        if self.assertion_type in {
            AssertionType.UNSUPPORTED_CLAIM,
            AssertionType.PROHIBITED_CLAIM,
        }:
            raise ValueError("evidence cannot itself be unsupported or prohibited")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class Achievement:
    id: str
    statement: str
    evidence_ids: tuple[str, ...]
    metric_verification: MetricVerification = MetricVerification.UNAVAILABLE

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.statement, "statement")
        _validate_evidence_ids(self.evidence_ids)
        if not isinstance(self.metric_verification, MetricVerification):
            raise ValueError("metric_verification must be a MetricVerification")


@dataclass(frozen=True, slots=True)
class EmploymentRecord:
    id: str
    organization: str
    title: str
    start_date: date
    end_date: date | None
    evidence_ids: tuple[str, ...]
    achievements: tuple[Achievement, ...] = ()
    responsibilities: tuple[str, ...] = ()
    market_facing_title: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.organization, "organization")
        _require_text(self.title, "title")
        _validate_evidence_ids(self.evidence_ids)
        if not isinstance(self.achievements, tuple) or not isinstance(self.responsibilities, tuple):
            raise ValueError("employment collections must be immutable tuples")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("employment end_date cannot precede start_date")
        if self.market_facing_title is not None:
            _require_text(self.market_facing_title, "market_facing_title")
        for responsibility in self.responsibilities:
            _require_text(responsibility, "responsibility")


@dataclass(frozen=True, slots=True)
class EducationRecord:
    id: str
    institution: str
    qualification: str
    start_date: date | None
    end_date: date | None
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.institution, "institution")
        _require_text(self.qualification, "qualification")
        _validate_evidence_ids(self.evidence_ids)
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("education end_date cannot precede start_date")


@dataclass(frozen=True, slots=True)
class CertificationRecord:
    id: str
    name: str
    issuer: str
    state: CertificationState
    evidence_ids: tuple[str, ...]
    issued_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.name, "name")
        _require_text(self.issuer, "issuer")
        _validate_evidence_ids(self.evidence_ids)
        if not isinstance(self.state, CertificationState):
            raise ValueError("state must be a CertificationState")
        if self.issued_date and self.expiry_date and self.expiry_date < self.issued_date:
            raise ValueError("certification expiry_date cannot precede issued_date")
        if self.state is CertificationState.PLANNED and self.issued_date is not None:
            raise ValueError("a planned certification cannot have an issued_date")


@dataclass(frozen=True, slots=True)
class SkillRecord:
    id: str
    name: str
    evidence_ids: tuple[str, ...]
    proficiency: str | None = None
    category: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.name, "name")
        _validate_evidence_ids(self.evidence_ids)
        if self.proficiency is not None:
            _require_text(self.proficiency, "proficiency")
        if self.category is not None:
            _require_text(self.category, "category")


@dataclass(frozen=True, slots=True)
class LanguageRecord:
    id: str
    language: str
    proficiency: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.language, "language")
        _require_text(self.proficiency, "proficiency")
        _validate_evidence_ids(self.evidence_ids)


@dataclass(frozen=True, slots=True)
class WorkAuthorization:
    id: str
    jurisdiction: str
    status: str
    evidence_ids: tuple[str, ...]
    expiry_date: date | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.jurisdiction, "jurisdiction")
        _require_text(self.status, "status")
        _validate_evidence_ids(self.evidence_ids)


@dataclass(frozen=True, slots=True)
class RedLineRule:
    id: str
    pattern: str
    reason: str

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.pattern, "pattern")
        _require_text(self.reason, "reason")


def _validate_finite_non_negative_number(value: Any, name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be a boolean")
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be a finite number (NaN and Infinity are forbidden)")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _validate_strict_non_negative_integer(value: Any, name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be a boolean")
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class AtomicAssertion:
    id: str
    subject_id: str
    predicate: str
    value: Any
    assertion_type: AssertionType = AssertionType.DIRECT_FACT
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    evidence_ids: tuple[str, ...] = ()
    polarity: Polarity = Polarity.POSITIVE
    modality: Modality = Modality.DEFINITE
    qualifiers: tuple[str, ...] = ()
    effective_from: date | None = None
    effective_to: date | None = None
    supersedes: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "assertion.id")
        _require_identifier(self.subject_id, "assertion.subject_id")
        _require_text(self.predicate, "assertion.predicate")
        if not isinstance(self.assertion_type, AssertionType):
            raise ValueError("assertion_type must be an AssertionType")
        if not isinstance(self.verification_status, VerificationStatus):
            raise ValueError("verification_status must be a VerificationStatus")
        _validate_evidence_ids(self.evidence_ids, allow_empty=True)
        if self.verification_status is VerificationStatus.VERIFIED and not self.evidence_ids:
            raise ValueError("VERIFIED assertion must have at least one evidence ID")
        if self.assertion_type is AssertionType.DIRECT_FACT and not self.evidence_ids:
            raise ValueError("DIRECT_FACT assertion must have at least one evidence ID")
        if self.verification_status is VerificationStatus.EXPLICIT_NULL and self.value is not None:
            raise ValueError("EXPLICIT_NULL assertion must have None value")
        if not isinstance(self.polarity, Polarity):
            raise ValueError("polarity must be a Polarity")
        if not isinstance(self.modality, Modality):
            raise ValueError("modality must be a Modality")
        if not isinstance(self.qualifiers, tuple):
            raise ValueError("qualifiers must be an immutable tuple")
        if not isinstance(self.supersedes, tuple):
            raise ValueError("supersedes must be an immutable tuple")
        if not isinstance(self.conflicts_with, tuple):
            raise ValueError("conflicts_with must be an immutable tuple")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot precede effective_from")


@dataclass(frozen=True, slots=True)
class TypedRelation:
    id: str
    source_id: str
    relation_type: RelationType
    target_id: str
    evidence_ids: tuple[str, ...] = ()
    assertion_type: AssertionType = AssertionType.DIRECT_FACT
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    effective_from: date | None = None
    effective_to: date | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id, "relation.id")
        _require_identifier(self.source_id, "relation.source_id")
        if not isinstance(self.relation_type, RelationType):
            raise ValueError("relation_type must be a RelationType")
        _require_identifier(self.target_id, "relation.target_id")
        _validate_evidence_ids(self.evidence_ids, allow_empty=True)
        if self.verification_status is VerificationStatus.VERIFIED and not self.evidence_ids:
            raise ValueError("VERIFIED relation must have at least one evidence ID")
        if self.assertion_type is AssertionType.DIRECT_FACT and not self.evidence_ids:
            raise ValueError("DIRECT_FACT relation must have at least one evidence ID")
        if not isinstance(self.assertion_type, AssertionType):
            raise ValueError("assertion_type must be an AssertionType")
        if not isinstance(self.verification_status, VerificationStatus):
            raise ValueError("verification_status must be a VerificationStatus")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot precede effective_from")


@dataclass(frozen=True, slots=True)
class MetricAssertion:
    id: str
    subject_id: str
    numeric_value: float | int
    unit: str
    context: str
    modality: Modality = Modality.DEFINITE
    verification_status: MetricVerification = MetricVerification.VERIFIED
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "metric.id")
        _require_identifier(self.subject_id, "metric.subject_id")
        _validate_finite_non_negative_number(self.numeric_value, "metric.numeric_value")
        _require_text(self.unit, "metric.unit")
        _require_text(self.context, "metric.context")
        if not isinstance(self.modality, Modality):
            raise ValueError("modality must be a Modality")
        if not isinstance(self.verification_status, MetricVerification):
            raise ValueError("verification_status must be a MetricVerification")
        _validate_evidence_ids(self.evidence_ids, allow_empty=True)
        if self.verification_status is MetricVerification.VERIFIED and not self.evidence_ids:
            raise ValueError("VERIFIED metric assertion must have at least one evidence ID")


@dataclass(frozen=True, slots=True)
class ClaimCandidate:
    text: str
    material_assertion_ids: tuple[str, ...] = ()
    concepts: frozenset[ProhibitedConceptCategory] = field(default_factory=frozenset)
    requested_evidence_ids: tuple[str, ...] = ()
    as_of: date | None = None

    def __post_init__(self) -> None:
        _require_text(self.text, "text")
        if not isinstance(self.material_assertion_ids, tuple):
            raise ValueError("material_assertion_ids must be an immutable tuple")
        if not isinstance(self.concepts, (frozenset, set)):
            raise ValueError("concepts must be a frozenset")
        if isinstance(self.concepts, set):
            object.__setattr__(self, "concepts", frozenset(self.concepts))
        for concept in self.concepts:
            if not isinstance(concept, ProhibitedConceptCategory):
                raise ValueError("concepts must contain ProhibitedConceptCategory values")
        if not isinstance(self.requested_evidence_ids, tuple):
            raise ValueError("requested_evidence_ids must be an immutable tuple")


@dataclass(frozen=True, slots=True)
class NeverClaimRule:
    id: str
    concept: ProhibitedConceptCategory
    description: str
    pattern: str
    forbidden_phrases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        if not isinstance(self.concept, ProhibitedConceptCategory):
            raise ValueError("concept must be a ProhibitedConceptCategory")
        _require_text(self.description, "description")
        _require_text(self.pattern, "pattern")
        try:
            re.compile(self.pattern, flags=re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"invalid pattern in NeverClaimRule {self.id}: {error}") from error
        if not isinstance(self.forbidden_phrases, tuple):
            raise ValueError("forbidden_phrases must be an immutable tuple")
        for phrase in self.forbidden_phrases:
            _require_text(phrase, "forbidden_phrase")


@dataclass(frozen=True, slots=True)
class CareerProfile:
    id: str
    evidence_ids: tuple[str, ...] = ()
    employment: tuple[EmploymentRecord, ...] = ()
    education: tuple[EducationRecord, ...] = ()
    certifications: tuple[CertificationRecord, ...] = ()
    skills: tuple[SkillRecord, ...] = ()
    languages: tuple[LanguageRecord, ...] = ()
    work_authorizations: tuple[WorkAuthorization, ...] = ()
    approved_summaries: tuple[str, ...] = ()
    red_lines: tuple[RedLineRule, ...] = ()
    never_claims: tuple[NeverClaimRule, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _validate_evidence_ids(self.evidence_ids, allow_empty=True)
        for name in (
            "employment", "education", "certifications", "skills", "languages",
            "work_authorizations", "approved_summaries", "red_lines", "never_claims",
        ):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"{name} must be an immutable tuple")


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    id: str
    name: str
    description: str
    evidence_ids: tuple[str, ...]
    engagement_types: tuple[EngagementType, ...] = ()
    deliverables: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.name, "name")
        _require_text(self.description, "description")
        _validate_evidence_ids(self.evidence_ids)
        if not isinstance(self.engagement_types, tuple) or not isinstance(self.deliverables, tuple):
            raise ValueError("service collections must be immutable tuples")
        if not all(isinstance(item, EngagementType) for item in self.engagement_types):
            raise ValueError("engagement_types must contain EngagementType values")
        if len(self.engagement_types) != len(set(self.engagement_types)):
            raise ValueError("engagement_types must be unique")
        for deliverable in self.deliverables:
            _require_text(deliverable, "deliverable")


@dataclass(frozen=True, slots=True)
class PortfolioItem:
    id: str
    title: str
    summary: str
    evidence_ids: tuple[str, ...]
    outcome: str | None = None
    metric_verification: MetricVerification = MetricVerification.UNAVAILABLE
    url: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.title, "title")
        _require_text(self.summary, "summary")
        _validate_evidence_ids(self.evidence_ids)
        if not isinstance(self.metric_verification, MetricVerification):
            raise ValueError("metric_verification must be a MetricVerification")
        if self.outcome is not None:
            _require_text(self.outcome, "outcome")


@dataclass(frozen=True, slots=True)
class BusinessCapacity:
    id: str
    evidence_ids: tuple[str, ...]
    available_from: date | None = None
    hours_per_week: int | None = None
    min_project_value: int | None = None
    max_project_value: int | None = None
    annual_turnover_usd: float | None = None
    bid_bond_capacity_usd: float | None = None
    currencies: tuple[str, ...] = ()
    service_regions: tuple[str, ...] = ()
    onsite_willingness: str | None = None
    legal_capacity: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _validate_evidence_ids(self.evidence_ids)
        for name in ("currencies", "service_regions"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"{name} must be an immutable tuple")
        _validate_strict_non_negative_integer(self.hours_per_week, "hours_per_week")
        _validate_strict_non_negative_integer(self.min_project_value, "min_project_value")
        _validate_strict_non_negative_integer(self.max_project_value, "max_project_value")
        _validate_finite_non_negative_number(self.annual_turnover_usd, "annual_turnover_usd")
        _validate_finite_non_negative_number(self.bid_bond_capacity_usd, "bid_bond_capacity_usd")
        if (
            self.min_project_value is not None
            and self.max_project_value is not None
            and self.max_project_value < self.min_project_value
        ):
            raise ValueError("max_project_value cannot be below min_project_value")


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    id: str
    evidence_ids: tuple[str, ...] = ()
    services: tuple[ServiceRecord, ...] = ()
    portfolio: tuple[PortfolioItem, ...] = ()
    capacity: BusinessCapacity | None = None
    target_industries: tuple[str, ...] = ()
    excluded_industries: tuple[str, ...] = ()
    delivery_languages: tuple[str, ...] = ()
    tools: tuple[SkillRecord, ...] = ()
    red_lines: tuple[RedLineRule, ...] = ()
    never_claims: tuple[NeverClaimRule, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _validate_evidence_ids(self.evidence_ids, allow_empty=True)
        for name in (
            "services", "portfolio", "target_industries", "excluded_industries",
            "delivery_languages", "tools", "red_lines", "never_claims",
        ):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"{name} must be an immutable tuple")
        overlap = {item.casefold() for item in self.target_industries} & {
            item.casefold() for item in self.excluded_industries
        }
        if overlap:
            raise ValueError("target_industries and excluded_industries cannot overlap")


@dataclass(frozen=True, slots=True)
class Identity:
    """The founder's identity block: name and contact details.

    A singleton per pack (fixed `id`), truth-locked like every other
    material entity: `evidence_ids` back the whole record, and every
    non-null field must be textually supported by that evidence (checked
    by `TruthGraph._validate_entity_manifest` via `CANONICAL_MATERIAL_MANIFEST`,
    same as `EmploymentRecord.organization`/`title`).
    """

    id: str
    name: str
    evidence_ids: tuple[str, ...]
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None
    location_city: str | None = None
    location_country: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.name, "name")
        _validate_evidence_ids(self.evidence_ids)
        for field_name in (
            "headline", "email", "phone", "linkedin", "github", "website",
            "location_city", "location_country",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_text(value, field_name)


@dataclass(frozen=True, slots=True)
class ApprovedPhrase:
    """One founder-authored, evidence-backed sentence a cover letter may use
    verbatim for motivation. Nothing generates or paraphrases these; they are
    the only sentences a cover-letter compiler may draw motivation text from.
    """

    id: str
    text: str
    evidence_ids: tuple[str, ...]
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.text, "text")
        _validate_evidence_ids(self.evidence_ids)
        if not isinstance(self.tags, tuple):
            raise ValueError("tags must be an immutable tuple")
        for tag in self.tags:
            _require_text(tag, "tag")


@dataclass(frozen=True, slots=True)
class ClaimVerificationResult:
    claim: str
    allowed: bool
    assertion_type: AssertionType
    verification_status: VerificationStatus
    evidence_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.claim, "claim")
        _validate_evidence_ids(self.evidence_ids, allow_empty=True)
        if not isinstance(self.assertion_type, AssertionType):
            raise ValueError("assertion_type must be an AssertionType")
        if not isinstance(self.verification_status, VerificationStatus):
            raise ValueError("verification_status must be a VerificationStatus")
        if not isinstance(self.reasons, tuple):
            raise ValueError("reasons must be an immutable tuple")
        if self.allowed and self.assertion_type in {
            AssertionType.UNSUPPORTED_CLAIM,
            AssertionType.PROHIBITED_CLAIM,
        }:
            raise ValueError("unsupported or prohibited claims cannot be allowed")


@dataclass(frozen=True, slots=True)
class MaterialFieldSpec:
    model_cls: type
    field_name: str
    predicate: str
    is_collection: bool = False
    is_nested_entity: bool = False
    optional: bool = False


CANONICAL_MATERIAL_MANIFEST: tuple[MaterialFieldSpec, ...] = (
    # EmploymentRecord
    MaterialFieldSpec(EmploymentRecord, "organization", "employment.organization"),
    MaterialFieldSpec(EmploymentRecord, "title", "employment.title"),
    MaterialFieldSpec(EmploymentRecord, "market_facing_title", "employment.market_facing_title", optional=True),
    MaterialFieldSpec(EmploymentRecord, "start_date", "employment.start_date"),
    MaterialFieldSpec(EmploymentRecord, "end_date", "employment.end_date", optional=True),
    MaterialFieldSpec(EmploymentRecord, "responsibilities", "employment.responsibility", is_collection=True, optional=True),
    MaterialFieldSpec(EmploymentRecord, "achievements", "employment.achievement", is_nested_entity=True, optional=True),

    # Achievement
    MaterialFieldSpec(Achievement, "statement", "achievement.statement"),

    # EducationRecord
    MaterialFieldSpec(EducationRecord, "institution", "education.institution"),
    MaterialFieldSpec(EducationRecord, "qualification", "education.qualification"),
    MaterialFieldSpec(EducationRecord, "start_date", "education.start_date", optional=True),
    MaterialFieldSpec(EducationRecord, "end_date", "education.end_date", optional=True),

    # CertificationRecord
    MaterialFieldSpec(CertificationRecord, "name", "certification.name"),
    MaterialFieldSpec(CertificationRecord, "issuer", "certification.issuer"),
    MaterialFieldSpec(CertificationRecord, "state", "certification.state"),
    MaterialFieldSpec(CertificationRecord, "issued_date", "certification.issued_date", optional=True),
    MaterialFieldSpec(CertificationRecord, "expiry_date", "certification.expiry_date", optional=True),
    MaterialFieldSpec(CertificationRecord, "credential_id", "certification.credential_id", optional=True),
    MaterialFieldSpec(CertificationRecord, "credential_url", "certification.credential_url", optional=True),

    # SkillRecord
    MaterialFieldSpec(SkillRecord, "name", "skill.name"),
    MaterialFieldSpec(SkillRecord, "proficiency", "skill.proficiency", optional=True),
    MaterialFieldSpec(SkillRecord, "category", "skill.category", optional=True),

    # LanguageRecord
    MaterialFieldSpec(LanguageRecord, "language", "language.language"),
    MaterialFieldSpec(LanguageRecord, "proficiency", "language.proficiency"),

    # WorkAuthorization
    MaterialFieldSpec(WorkAuthorization, "jurisdiction", "work_authorization.jurisdiction"),
    MaterialFieldSpec(WorkAuthorization, "status", "work_authorization.status"),
    MaterialFieldSpec(WorkAuthorization, "expiry_date", "work_authorization.expiry_date", optional=True),

    # ServiceRecord
    MaterialFieldSpec(ServiceRecord, "name", "service.name"),
    MaterialFieldSpec(ServiceRecord, "description", "service.description"),
    MaterialFieldSpec(ServiceRecord, "engagement_types", "service.engagement_type", is_collection=True, optional=True),
    MaterialFieldSpec(ServiceRecord, "deliverables", "service.deliverable", is_collection=True, optional=True),

    # PortfolioItem
    MaterialFieldSpec(PortfolioItem, "title", "portfolio.title"),
    MaterialFieldSpec(PortfolioItem, "summary", "portfolio.summary"),
    MaterialFieldSpec(PortfolioItem, "outcome", "portfolio.outcome", optional=True),
    MaterialFieldSpec(PortfolioItem, "url", "portfolio.url", optional=True),

    # BusinessCapacity
    MaterialFieldSpec(BusinessCapacity, "available_from", "capacity.available_from", optional=True),
    MaterialFieldSpec(BusinessCapacity, "hours_per_week", "capacity.hours_per_week", optional=True),
    MaterialFieldSpec(BusinessCapacity, "min_project_value", "capacity.min_project_value", optional=True),
    MaterialFieldSpec(BusinessCapacity, "max_project_value", "capacity.max_project_value", optional=True),
    MaterialFieldSpec(BusinessCapacity, "annual_turnover_usd", "capacity.annual_turnover_usd", optional=True),
    MaterialFieldSpec(BusinessCapacity, "bid_bond_capacity_usd", "capacity.bid_bond_capacity_usd", optional=True),
    MaterialFieldSpec(BusinessCapacity, "currencies", "capacity.currency", is_collection=True, optional=True),
    MaterialFieldSpec(BusinessCapacity, "service_regions", "capacity.service_region", is_collection=True, optional=True),
    MaterialFieldSpec(BusinessCapacity, "onsite_willingness", "capacity.onsite_willingness", optional=True),
    MaterialFieldSpec(BusinessCapacity, "legal_capacity", "capacity.legal_capacity", optional=True),

    # CareerProfile
    MaterialFieldSpec(CareerProfile, "approved_summaries", "profile.approved_summary", is_collection=True, optional=True),
    MaterialFieldSpec(CareerProfile, "employment", "career_profile.employment", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CareerProfile, "education", "career_profile.education", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CareerProfile, "certifications", "career_profile.certifications", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CareerProfile, "skills", "career_profile.skills", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CareerProfile, "languages", "career_profile.languages", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CareerProfile, "work_authorizations", "career_profile.work_authorizations", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CareerProfile, "red_lines", "career_profile.red_lines", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CareerProfile, "never_claims", "career_profile.never_claims", is_nested_entity=True, optional=True),

    # CapabilityProfile
    MaterialFieldSpec(CapabilityProfile, "target_industries", "capability.target_industry", is_collection=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "excluded_industries", "capability.excluded_industry", is_collection=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "delivery_languages", "capability.delivery_language", is_collection=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "services", "capability_profile.services", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "portfolio", "capability_profile.portfolio", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "capacity", "capability_profile.capacity", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "tools", "capability_profile.tools", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "red_lines", "capability_profile.red_lines", is_nested_entity=True, optional=True),
    MaterialFieldSpec(CapabilityProfile, "never_claims", "capability_profile.never_claims", is_nested_entity=True, optional=True),

    # Identity (BRIEF-FR-006 F1): projected top-level identity block.
    MaterialFieldSpec(Identity, "name", "identity.name"),
    MaterialFieldSpec(Identity, "headline", "identity.headline", optional=True),
    MaterialFieldSpec(Identity, "email", "identity.email", optional=True),
    MaterialFieldSpec(Identity, "phone", "identity.phone", optional=True),
    MaterialFieldSpec(Identity, "linkedin", "identity.linkedin", optional=True),
    MaterialFieldSpec(Identity, "github", "identity.github", optional=True),
    MaterialFieldSpec(Identity, "website", "identity.website", optional=True),
    MaterialFieldSpec(Identity, "location_city", "identity.location_city", optional=True),
    MaterialFieldSpec(Identity, "location_country", "identity.location_country", optional=True),

    # ApprovedPhrase (BRIEF-FR-006 F1): founder-authored motivation sentences.
    MaterialFieldSpec(ApprovedPhrase, "text", "approved_phrase.text"),
)
