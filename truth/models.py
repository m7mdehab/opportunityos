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

    def __post_init__(self) -> None:
        _require_identifier(self.id)
        _require_text(self.name, "name")
        _validate_evidence_ids(self.evidence_ids)
        if self.proficiency is not None:
            _require_text(self.proficiency, "proficiency")


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
    hours_per_week: int | float | None = None
    min_project_value: int | float | None = None
    max_project_value: int | float | None = None
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
        _validate_finite_non_negative_number(self.hours_per_week, "hours_per_week")
        _validate_finite_non_negative_number(self.min_project_value, "min_project_value")
        _validate_finite_non_negative_number(self.max_project_value, "max_project_value")
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
