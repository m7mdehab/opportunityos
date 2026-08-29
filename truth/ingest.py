"""Strict deterministic ingestion for JSON, YAML, and Python mappings."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

from .graph import TruthGraph
from .models import (
    Achievement,
    AssertionType,
    AtomicAssertion,
    BusinessCapacity,
    CapabilityProfile,
    CareerProfile,
    CertificationRecord,
    CertificationState,
    EducationRecord,
    EmploymentRecord,
    EngagementType,
    EvidenceRecord,
    LanguageRecord,
    MetricAssertion,
    MetricVerification,
    Modality,
    NeverClaimRule,
    Polarity,
    PortfolioItem,
    ProhibitedConceptCategory,
    RedLineRule,
    RelationType,
    ServiceRecord,
    SkillRecord,
    TypedRelation,
    VerificationStatus,
    WorkAuthorization,
)


class IngestionError(ValueError):
    """Raised when input is ambiguous, malformed, or outside the schema."""


CANONICAL_SKILL_ALIASES = {
    "amazon web services": "AWS",
    "aws": "AWS",
    "c sharp": "C#",
    "c#": "C#",
    "docker": "Docker",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "google cloud platform": "Google Cloud Platform",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "node": "Node.js",
    "node.js": "Node.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "power bi": "Power BI",
    "python": "Python",
    "react": "React",
    "sql": "SQL",
    "typescript": "TypeScript",
    "ts": "TypeScript",
}


def canonicalize_skill(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestionError("skill name must be a non-empty string")
    normalized = re.sub(r"[\s_-]+", " ", value.strip()).casefold()
    return CANONICAL_SKILL_ALIASES.get(normalized, " ".join(part.capitalize() for part in normalized.split()))


def parse_date(value: Any, field_name: str, *, allow_none: bool = True) -> date | None:
    if value is None and allow_none:
        return None
    if isinstance(value, datetime):
        raise IngestionError(f"{field_name} must be an ISO-8601 date, not a datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise IngestionError(f"{field_name} must use ISO-8601 YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise IngestionError(f"invalid {field_name}: {value}") from error


def parse_datetime(value: Any, field_name: str) -> date | datetime | None:
    if value is None or isinstance(value, (date, datetime)):
        return value
    if not isinstance(value, str):
        raise IngestionError(f"{field_name} must be an ISO-8601 date or datetime")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return parse_date(value, field_name)
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise IngestionError(f"invalid {field_name}: {value}") from error
    if parsed.tzinfo is None:
        raise IngestionError(f"{field_name} datetime must include a timezone")
    return parsed


T = TypeVar("T")


def _enum(enum_type: type[T], value: Any, field_name: str) -> T:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise IngestionError(f"{field_name} must be a string")
    try:
        return enum_type(value.casefold())  # type: ignore[call-arg]
    except ValueError as error:
        allowed = ", ".join(item.value for item in enum_type)  # type: ignore[attr-defined]
        raise IngestionError(f"{field_name} must be one of: {allowed}") from error


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise IngestionError(f"{context} must be a mapping with string keys")
    return value


def _validate_keys(
    value: Mapping[str, Any], context: str, *, required: set[str], optional: set[str] = frozenset()
) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise IngestionError(f"{context} missing required fields: {', '.join(sorted(missing))}")
    if unknown:
        raise IngestionError(f"{context} contains unknown fields: {', '.join(sorted(unknown))}")


def _tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise IngestionError(f"{field_name} must be a list")
    return tuple(value)


def _strings(value: Any, field_name: str) -> tuple[str, ...]:
    result = _tuple(value, field_name)
    if not all(isinstance(item, str) for item in result):
        raise IngestionError(f"{field_name} must contain only strings")
    return result


def _finite_non_negative_float_or_none(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise IngestionError(f"{field_name} cannot be a boolean")
    if isinstance(value, (int, float)):
        val = float(value)
    elif isinstance(value, str):
        if value.strip().lower() in {"nan", "inf", "-inf", "+inf", "infinity", "-infinity"}:
            raise IngestionError(f"{field_name} cannot be NaN or Infinity")
        try:
            val = float(value.strip())
        except ValueError as error:
            raise IngestionError(f"{field_name} must be a valid numeric value") from error
    else:
        raise IngestionError(f"{field_name} must be a number or null")

    if math.isnan(val) or math.isinf(val):
        raise IngestionError(f"{field_name} must be a finite number (NaN and Infinity are forbidden)")
    if val < 0:
        raise IngestionError(f"{field_name} cannot be negative")
    return val


def _strict_non_negative_int_or_none(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise IngestionError(f"{field_name} cannot be a boolean")
    if isinstance(value, int):
        val = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise IngestionError(f"{field_name} must be an integer (fractional float is forbidden)")
        val = int(value)
    elif isinstance(value, str):
        cleaned = value.strip()
        if not re.fullmatch(r"[+-]?\d+", cleaned):
            raise IngestionError(f"{field_name} must be a valid integer string (fractional and non-decimal values forbidden)")
        try:
            val = int(cleaned)
        except ValueError as error:
            raise IngestionError(f"{field_name} must be a valid integer") from error
    else:
        raise IngestionError(f"{field_name} must be an integer or null")

    if val < 0:
        raise IngestionError(f"{field_name} cannot be negative")
    if val > 10**14:
        raise IngestionError(f"{field_name} exceeds maximum allowable integer limit")
    return val


def _positive_int_or_none(value: Any, field_name: str) -> int | None:
    return _strict_non_negative_int_or_none(value, field_name)


def parse_evidence(value: Any) -> EvidenceRecord:
    data = _mapping(value, "evidence")
    required = {"id", "content", "source", "locator"}
    optional = {"assertion_type", "verification_status", "observed_at", "metadata"}
    _validate_keys(data, "evidence", required=required, optional=optional)
    metadata = data.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise IngestionError("evidence.metadata must be a mapping")
    return EvidenceRecord(
        id=data["id"],
        content=data["content"],
        source=data["source"],
        locator=data["locator"],
        assertion_type=_enum(
            AssertionType, data.get("assertion_type", "direct_fact"), "evidence.assertion_type"
        ),
        verification_status=_enum(
            VerificationStatus,
            data.get("verification_status", "verified"),
            "evidence.verification_status",
        ),
        observed_at=parse_datetime(data.get("observed_at"), "evidence.observed_at"),
        metadata=metadata,
    )


def parse_achievement(value: Any) -> Achievement:
    data = _mapping(value, "achievement")
    _validate_keys(
        data,
        "achievement",
        required={"id", "statement", "evidence_ids"},
        optional={"metric_verification"},
    )
    return Achievement(
        id=data["id"], statement=data["statement"],
        evidence_ids=_strings(data["evidence_ids"], "achievement.evidence_ids"),
        metric_verification=_enum(
            MetricVerification,
            data.get("metric_verification", "unavailable"),
            "achievement.metric_verification",
        ),
    )


def parse_employment(value: Any) -> EmploymentRecord:
    data = _mapping(value, "employment")
    _validate_keys(
        data, "employment",
        required={"id", "organization", "title", "start_date", "evidence_ids"},
        optional={"end_date", "achievements", "responsibilities", "market_facing_title"},
    )
    return EmploymentRecord(
        id=data["id"], organization=data["organization"], title=data["title"],
        start_date=parse_date(data["start_date"], "employment.start_date", allow_none=False),
        end_date=parse_date(data.get("end_date"), "employment.end_date"),
        evidence_ids=_strings(data["evidence_ids"], "employment.evidence_ids"),
        achievements=tuple(parse_achievement(item) for item in _tuple(data.get("achievements"), "employment.achievements")),
        responsibilities=_strings(data.get("responsibilities"), "employment.responsibilities"),
        market_facing_title=data.get("market_facing_title"),
    )


def parse_education(value: Any) -> EducationRecord:
    data = _mapping(value, "education")
    _validate_keys(
        data, "education", required={"id", "institution", "qualification", "evidence_ids"},
        optional={"start_date", "end_date"},
    )
    return EducationRecord(
        id=data["id"], institution=data["institution"], qualification=data["qualification"],
        start_date=parse_date(data.get("start_date"), "education.start_date"),
        end_date=parse_date(data.get("end_date"), "education.end_date"),
        evidence_ids=_strings(data["evidence_ids"], "education.evidence_ids"),
    )


def parse_certification(value: Any) -> CertificationRecord:
    data = _mapping(value, "certification")
    _validate_keys(
        data, "certification", required={"id", "name", "issuer", "state", "evidence_ids"},
        optional={"issued_date", "expiry_date", "credential_id", "credential_url"},
    )
    return CertificationRecord(
        id=data["id"], name=data["name"], issuer=data["issuer"],
        state=_enum(CertificationState, data["state"], "certification.state"),
        evidence_ids=_strings(data["evidence_ids"], "certification.evidence_ids"),
        issued_date=parse_date(data.get("issued_date"), "certification.issued_date"),
        expiry_date=parse_date(data.get("expiry_date"), "certification.expiry_date"),
        credential_id=data.get("credential_id"), credential_url=data.get("credential_url"),
    )


def parse_skill(value: Any, context: str = "skill") -> SkillRecord:
    data = _mapping(value, context)
    _validate_keys(data, context, required={"id", "name", "evidence_ids"}, optional={"proficiency"})
    return SkillRecord(
        id=data["id"], name=canonicalize_skill(data["name"]),
        evidence_ids=_strings(data["evidence_ids"], f"{context}.evidence_ids"),
        proficiency=data.get("proficiency"),
    )


def parse_language(value: Any) -> LanguageRecord:
    data = _mapping(value, "language")
    _validate_keys(data, "language", required={"id", "language", "proficiency", "evidence_ids"})
    return LanguageRecord(
        id=data["id"], language=data["language"], proficiency=data["proficiency"],
        evidence_ids=_strings(data["evidence_ids"], "language.evidence_ids"),
    )


def parse_work_authorization(value: Any) -> WorkAuthorization:
    data = _mapping(value, "work_authorization")
    _validate_keys(
        data, "work_authorization", required={"id", "jurisdiction", "status", "evidence_ids"},
        optional={"expiry_date"},
    )
    return WorkAuthorization(
        id=data["id"], jurisdiction=data["jurisdiction"], status=data["status"],
        evidence_ids=_strings(data["evidence_ids"], "work_authorization.evidence_ids"),
        expiry_date=parse_date(data.get("expiry_date"), "work_authorization.expiry_date"),
    )


def parse_red_line(value: Any) -> RedLineRule:
    data = _mapping(value, "red_line")
    _validate_keys(data, "red_line", required={"id", "pattern", "reason"})
    try:
        re.compile(data["pattern"])
    except (TypeError, re.error) as error:
        raise IngestionError(f"invalid red_line.pattern: {error}") from error
    return RedLineRule(id=data["id"], pattern=data["pattern"], reason=data["reason"])


def parse_never_claim(value: Any) -> NeverClaimRule:
    data = _mapping(value, "never_claim")
    _validate_keys(
        data, "never_claim",
        required={"id"},
        optional={"concept", "description", "reason", "pattern", "phrase", "forbidden_phrases"},
    )
    if "concept" in data:
        concept = _enum(
            ProhibitedConceptCategory,
            data["concept"],
            "never_claim.concept",
        )
    else:
        # Require explicit concept or derive predictably from id if valid enum value
        concept_val = data["id"].replace("-", "_").lower()
        try:
            concept = ProhibitedConceptCategory(concept_val)
        except ValueError:
            raise IngestionError(
                f"never_claim {data['id']} requires a valid concept from: {', '.join(sorted(item.value for item in ProhibitedConceptCategory))}"
            )

    pattern = data.get("pattern") or ""
    phrase = data.get("phrase")
    forbidden_phrases = _strings(data.get("forbidden_phrases"), "never_claim.forbidden_phrases")
    if phrase and not forbidden_phrases:
        forbidden_phrases = (phrase,)
    if not pattern and phrase:
        pattern = r"\b" + re.escape(phrase) + r"\b"
    if not pattern:
        pattern = r"\b" + re.escape(data["id"]) + r"\b"

    description = data.get("description") or data.get("reason") or "prohibited concept"
    return NeverClaimRule(
        id=data["id"],
        concept=concept,
        description=description,
        pattern=pattern,
        forbidden_phrases=forbidden_phrases,
    )


def parse_assertion(value: Any) -> AtomicAssertion:
    data = _mapping(value, "assertion")
    _validate_keys(
        data, "assertion",
        required={"id", "subject_id", "predicate", "value"},
        optional={"assertion_type", "verification_status", "evidence_ids", "polarity", "modality", "qualifiers", "effective_from", "effective_to", "supersedes", "conflicts_with"},
    )
    return AtomicAssertion(
        id=data["id"],
        subject_id=data["subject_id"],
        predicate=data["predicate"],
        value=data["value"],
        assertion_type=_enum(AssertionType, data.get("assertion_type", "direct_fact"), "assertion.assertion_type"),
        verification_status=_enum(VerificationStatus, data.get("verification_status", "verified"), "assertion.verification_status"),
        evidence_ids=_strings(data.get("evidence_ids"), "assertion.evidence_ids"),
        polarity=_enum(Polarity, data.get("polarity", "positive"), "assertion.polarity"),
        modality=_enum(Modality, data.get("modality", "definite"), "assertion.modality"),
        qualifiers=_strings(data.get("qualifiers"), "assertion.qualifiers"),
        effective_from=parse_date(data.get("effective_from"), "assertion.effective_from"),
        effective_to=parse_date(data.get("effective_to"), "assertion.effective_to"),
        supersedes=_strings(data.get("supersedes"), "assertion.supersedes"),
        conflicts_with=_strings(data.get("conflicts_with"), "assertion.conflicts_with"),
    )


def parse_relation(value: Any) -> TypedRelation:
    data = _mapping(value, "relation")
    _validate_keys(
        data, "relation",
        required={"id", "source_id", "relation_type", "target_id"},
        optional={"evidence_ids", "assertion_type", "verification_status", "effective_from", "effective_to"},
    )
    return TypedRelation(
        id=data["id"],
        source_id=data["source_id"],
        relation_type=_enum(RelationType, data["relation_type"], "relation.relation_type"),
        target_id=data["target_id"],
        evidence_ids=_strings(data.get("evidence_ids"), "relation.evidence_ids"),
        assertion_type=_enum(AssertionType, data.get("assertion_type", "direct_fact"), "relation.assertion_type"),
        verification_status=_enum(VerificationStatus, data.get("verification_status", "verified"), "relation.verification_status"),
        effective_from=parse_date(data.get("effective_from"), "relation.effective_from"),
        effective_to=parse_date(data.get("effective_to"), "relation.effective_to"),
    )


def parse_metric_assertion(value: Any) -> MetricAssertion:
    data = _mapping(value, "metric")
    _validate_keys(
        data, "metric",
        required={"id", "subject_id", "numeric_value", "unit", "context"},
        optional={"modality", "verification_status", "evidence_ids"},
    )
    return MetricAssertion(
        id=data["id"],
        subject_id=data["subject_id"],
        numeric_value=_finite_non_negative_float_or_none(data["numeric_value"], "metric.numeric_value"),
        unit=data["unit"],
        context=data["context"],
        modality=_enum(Modality, data.get("modality", "definite"), "metric.modality"),
        verification_status=_enum(MetricVerification, data.get("verification_status", "verified"), "metric.verification_status"),
        evidence_ids=_strings(data.get("evidence_ids"), "metric.evidence_ids"),
    )


def parse_career_profile(value: Any) -> CareerProfile:
    data = _mapping(value, "career_profile")
    optional = {
        "evidence_ids", "employment", "education", "certifications", "skills", "languages",
        "work_authorizations", "approved_summaries", "red_lines", "never_claims",
    }
    _validate_keys(data, "career_profile", required={"id"}, optional=optional)
    return CareerProfile(
        id=data["id"], evidence_ids=_strings(data.get("evidence_ids"), "career_profile.evidence_ids"),
        employment=tuple(parse_employment(item) for item in _tuple(data.get("employment"), "career_profile.employment")),
        education=tuple(parse_education(item) for item in _tuple(data.get("education"), "career_profile.education")),
        certifications=tuple(parse_certification(item) for item in _tuple(data.get("certifications"), "career_profile.certifications")),
        skills=tuple(parse_skill(item) for item in _tuple(data.get("skills"), "career_profile.skills")),
        languages=tuple(parse_language(item) for item in _tuple(data.get("languages"), "career_profile.languages")),
        work_authorizations=tuple(parse_work_authorization(item) for item in _tuple(data.get("work_authorizations"), "career_profile.work_authorizations")),
        approved_summaries=_strings(data.get("approved_summaries"), "career_profile.approved_summaries"),
        red_lines=tuple(parse_red_line(item) for item in _tuple(data.get("red_lines"), "career_profile.red_lines")),
        never_claims=tuple(parse_never_claim(item) for item in _tuple(data.get("never_claims"), "career_profile.never_claims")),
    )


def parse_service(value: Any) -> ServiceRecord:
    data = _mapping(value, "service")
    _validate_keys(
        data, "service", required={"id", "name", "description", "evidence_ids"},
        optional={"engagement_types", "deliverables"},
    )
    return ServiceRecord(
        id=data["id"], name=data["name"], description=data["description"],
        evidence_ids=_strings(data["evidence_ids"], "service.evidence_ids"),
        engagement_types=tuple(
            _enum(EngagementType, item, "service.engagement_types")
            for item in _tuple(data.get("engagement_types"), "service.engagement_types")
        ),
        deliverables=_strings(data.get("deliverables"), "service.deliverables"),
    )


def parse_portfolio_item(value: Any) -> PortfolioItem:
    data = _mapping(value, "portfolio_item")
    _validate_keys(
        data, "portfolio_item", required={"id", "title", "summary", "evidence_ids"},
        optional={"outcome", "metric_verification", "url"},
    )
    return PortfolioItem(
        id=data["id"], title=data["title"], summary=data["summary"],
        evidence_ids=_strings(data["evidence_ids"], "portfolio_item.evidence_ids"),
        outcome=data.get("outcome"),
        metric_verification=_enum(
            MetricVerification, data.get("metric_verification", "unavailable"),
            "portfolio_item.metric_verification",
        ),
        url=data.get("url"),
    )


def parse_capacity(value: Any) -> BusinessCapacity:
    data = _mapping(value, "capacity")
    _validate_keys(
        data, "capacity", required={"id", "evidence_ids"},
        optional={"available_from", "hours_per_week", "min_project_value", "max_project_value",
                  "annual_turnover_usd", "bid_bond_capacity_usd",
                  "currencies", "service_regions", "onsite_willingness", "legal_capacity"},
    )
    return BusinessCapacity(
        id=data["id"], evidence_ids=_strings(data["evidence_ids"], "capacity.evidence_ids"),
        available_from=parse_date(data.get("available_from"), "capacity.available_from"),
        hours_per_week=_strict_non_negative_int_or_none(data.get("hours_per_week"), "capacity.hours_per_week"),
        min_project_value=_strict_non_negative_int_or_none(data.get("min_project_value"), "capacity.min_project_value"),
        max_project_value=_strict_non_negative_int_or_none(data.get("max_project_value"), "capacity.max_project_value"),
        annual_turnover_usd=_finite_non_negative_float_or_none(data.get("annual_turnover_usd"), "capacity.annual_turnover_usd"),
        bid_bond_capacity_usd=_finite_non_negative_float_or_none(data.get("bid_bond_capacity_usd"), "capacity.bid_bond_capacity_usd"),
        currencies=_strings(data.get("currencies"), "capacity.currencies"),
        service_regions=_strings(data.get("service_regions"), "capacity.service_regions"),
        onsite_willingness=data.get("onsite_willingness"), legal_capacity=data.get("legal_capacity"),
    )


def parse_capability_profile(value: Any) -> CapabilityProfile:
    data = _mapping(value, "capability_profile")
    optional = {
        "evidence_ids", "services", "portfolio", "capacity", "target_industries",
        "excluded_industries", "delivery_languages", "tools", "red_lines", "never_claims",
    }
    _validate_keys(data, "capability_profile", required={"id"}, optional=optional)
    return CapabilityProfile(
        id=data["id"], evidence_ids=_strings(data.get("evidence_ids"), "capability_profile.evidence_ids"),
        services=tuple(parse_service(item) for item in _tuple(data.get("services"), "capability_profile.services")),
        portfolio=tuple(parse_portfolio_item(item) for item in _tuple(data.get("portfolio"), "capability_profile.portfolio")),
        capacity=parse_capacity(data["capacity"]) if data.get("capacity") is not None else None,
        target_industries=_strings(data.get("target_industries"), "capability_profile.target_industries"),
        excluded_industries=_strings(data.get("excluded_industries"), "capability_profile.excluded_industries"),
        delivery_languages=_strings(data.get("delivery_languages"), "capability_profile.delivery_languages"),
        tools=tuple(parse_skill(item, "tool") for item in _tuple(data.get("tools"), "capability_profile.tools")),
        red_lines=tuple(parse_red_line(item) for item in _tuple(data.get("red_lines"), "capability_profile.red_lines")),
        never_claims=tuple(parse_never_claim(item) for item in _tuple(data.get("never_claims"), "capability_profile.never_claims")),
    )


def graph_from_dict(value: Any) -> TruthGraph:
    data = _mapping(value, "document")
    _validate_keys(
        data, "document",
        required={"evidence"},
        optional={"career_profile", "capability_profile", "assertions", "relations", "metrics"},
    )
    evidence_nodes = tuple(parse_evidence(item) for item in _tuple(data["evidence"], "evidence"))
    assertions = tuple(parse_assertion(item) for item in _tuple(data.get("assertions"), "assertions"))
    relations = tuple(parse_relation(item) for item in _tuple(data.get("relations"), "relations"))
    metrics = tuple(parse_metric_assertion(item) for item in _tuple(data.get("metrics"), "metrics"))

    graph = TruthGraph(evidence=evidence_nodes, assertions=assertions, relations=relations, metrics=metrics)
    if data.get("career_profile") is not None:
        graph.add_career_profile(parse_career_profile(data["career_profile"]))
    if data.get("capability_profile") is not None:
        graph.add_capability_profile(parse_capability_profile(data["capability_profile"]))
    return graph


def load_json(text: str) -> TruthGraph:
    try:
        value = json.loads(text, object_pairs_hook=_unique_json_object)
    except json.JSONDecodeError as error:
        raise IngestionError(f"invalid JSON: {error.msg}") from error
    return graph_from_dict(value)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IngestionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_yaml(text: str) -> TruthGraph:
    return graph_from_dict(_parse_yaml(text))


def load_document(text: str, format: str) -> TruthGraph:
    normalized = format.casefold().lstrip(".")
    if normalized == "json":
        return load_json(text)
    if normalized in {"yaml", "yml"}:
        return load_yaml(text)
    raise IngestionError(f"unsupported document format: {format}")


def load_path(path: str | Path) -> TruthGraph:
    document_path = Path(path)
    return load_document(document_path.read_text(encoding="utf-8"), document_path.suffix)


def _parse_yaml(text: str) -> Any:
    """Parse the safe YAML subset used by truth packs (no tags, anchors, or block scalars)."""
    if not isinstance(text, str) or not text.strip():
        raise IngestionError("YAML document is empty")
    if "\t" in text:
        raise IngestionError("YAML indentation must use spaces")
    lines: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = _strip_yaml_comment(raw).rstrip()
        if not stripped.strip() or stripped.lstrip() in {"---", "..."}:
            continue
        content = stripped.lstrip(" ")
        if (
            re.search(r"(?:^|[\s:])(?:!![^\s]+|[&*][A-Za-z0-9_-]+)(?=\s|$)", content)
            or re.search(r":\s*[|>][+-]?\s*$", content)
        ):
            raise IngestionError(f"unsupported YAML feature on line {number}")
        lines.append((len(stripped) - len(content), content))
    if not lines:
        raise IngestionError("YAML document is empty")

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(lines) or lines[index][0] != indent:
            raise IngestionError("invalid YAML indentation")
        is_list = lines[index][1].startswith("- ") or lines[index][1] == "-"
        container: Any = [] if is_list else {}
        while index < len(lines) and lines[index][0] == indent:
            content = lines[index][1]
            if is_list:
                if not (content.startswith("- ") or content == "-"):
                    raise IngestionError("cannot mix YAML lists and mappings at one indentation")
                item_text = content[1:].strip()
                index += 1
                if not item_text:
                    if index >= len(lines) or lines[index][0] <= indent:
                        raise IngestionError("empty YAML list item")
                    item, index = parse_block(index, lines[index][0])
                elif _yaml_mapping_entry(item_text):
                    key, raw_value = _split_yaml_mapping(item_text)
                    item = {}
                    if raw_value:
                        item[key] = _yaml_scalar(raw_value)
                    elif index < len(lines) and lines[index][0] > indent:
                        item[key], index = parse_block(index, lines[index][0])
                    else:
                        item[key] = None
                    if index < len(lines) and lines[index][0] > indent:
                        extra_indent = lines[index][0]
                        extra, index = parse_block(index, extra_indent)
                        if not isinstance(extra, dict):
                            raise IngestionError("list mapping continuation must be a mapping")
                        duplicate = set(item) & set(extra)
                        if duplicate:
                            raise IngestionError(f"duplicate YAML key: {sorted(duplicate)[0]}")
                        item.update(extra)
                else:
                    item = _yaml_scalar(item_text)
                container.append(item)
            else:
                if content.startswith("-"):
                    raise IngestionError("cannot mix YAML mappings and lists at one indentation")
                key, raw_value = _split_yaml_mapping(content)
                if key in container:
                    raise IngestionError(f"duplicate YAML key: {key}")
                index += 1
                if raw_value:
                    container[key] = _yaml_scalar(raw_value)
                elif index < len(lines) and lines[index][0] > indent:
                    container[key], index = parse_block(index, lines[index][0])
                else:
                    container[key] = None
        if index < len(lines) and lines[index][0] > indent:
            raise IngestionError("invalid YAML indentation")
        return container, index

    result, final_index = parse_block(0, lines[0][0])
    if final_index != len(lines) or lines[0][0] != 0:
        raise IngestionError("invalid YAML document indentation")
    return result


def _strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
        elif character == "\\" and quote == '"':
            escaped = True
        elif character in {"'", '"'}:
            quote = None if quote == character else character if quote is None else quote
        elif character == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index]
    if quote is not None:
        raise IngestionError("unterminated YAML string")
    return value


def _yaml_mapping_entry(value: str) -> bool:
    try:
        _split_yaml_mapping(value)
        return True
    except IngestionError:
        return False


def _split_yaml_mapping(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?", value)
    if not match:
        raise IngestionError(f"invalid YAML mapping entry: {value}")
    return match.group(1), (match.group(2) or "").strip()


def _yaml_scalar(value: str) -> Any:
    lowered = value.casefold()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if value.startswith(("[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise IngestionError("inline YAML collections must use JSON syntax") from error
    if value.startswith(('"', "'")):
        if len(value) < 2 or value[-1] != value[0]:
            raise IngestionError("unterminated YAML string")
        if value[0] == '"':
            try:
                return json.loads(value)
            except json.JSONDecodeError as error:
                raise IngestionError("invalid YAML quoted string") from error
        return value[1:-1].replace("''", "'")
    if re.fullmatch(r"-?(0|[1-9]\d*)", value):
        return int(value)
    if re.fullmatch(r"-?(0|[1-9]\d*)\.\d+", value):
        return float(value)
    return value
