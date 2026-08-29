"""Deterministic in-memory graph for truth, capability, and provenance nodes."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
import re
from types import MappingProxyType
from typing import Any, TypeAlias

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
    EvidenceRecord,
    LanguageRecord,
    MetricAssertion,
    MetricVerification,
    Modality,
    Polarity,
    PortfolioItem,
    RelationType,
    ServiceRecord,
    SkillRecord,
    TypedRelation,
    VerificationStatus,
    WorkAuthorization,
)


Profile: TypeAlias = CareerProfile | CapabilityProfile

_WORD_PATTERN = re.compile(r"[\w+#]+", re.UNICODE)
_STOP_WORDS = frozenset({
    "a", "an", "and", "or", "of", "in", "at", "to", "for", "with", "on", "by", "from",
    "the", "is", "was", "were", "as", "into", "onto", "via", "using",
})
_NEGATIVE_MARKERS = re.compile(
    r"\b(?:not|no|never|neither|nor|without|cannot|unauthorized|non-|ineligible|lacks?|lacking)\b",
    re.I,
)
_BOUND_AT_MOST = re.compile(r"\b(?:at\s*most|up\s*to|less\s*than|under|maximum\s*of|no\s*more\s*than)\b", re.I)
_BOUND_AT_LEAST = re.compile(r"\b(?:at\s*least|more\s*than|over|minimum\s*of|no\s*less\s*than)\b", re.I)
_CONDITIONAL = re.compile(r"\b(?:subject\s*to|conditional\s*(?:on|upon)|depending\s*on|if\s*approved|contingent\s*on)\b", re.I)


def _extract_tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _WORD_PATTERN.finditer(text.replace("_", " "))}


def _single_record_supports_value(
    value: Any,
    record: EvidenceRecord,
    predicate: str | None = None,
    subject_id: str | None = None,
) -> bool:
    if value is None:
        return True

    if record.verification_status is VerificationStatus.EXPLICIT_NULL:
        return value is None

    if record.content is None or not record.content.strip():
        return False

    content = record.content
    content_lower = content.casefold()

    # Explicit locator/metadata scope checks if present
    if record.metadata:
        rec_subj = record.metadata.get("subject_id") or record.metadata.get("subject")
        if rec_subj and subject_id and rec_subj != subject_id:
            return False
        rec_pred = record.metadata.get("predicate") or record.metadata.get("field")
        if rec_pred and predicate and rec_pred != predicate:
            return False

    if isinstance(value, str):
        val_str = value.strip()
        val_lower = val_str.casefold()
        if not val_lower:
            return True

        # Check for negation in evidence modifying or associated with this value
        if _NEGATIVE_MARKERS.search(content_lower):
            # If the value is "authorized" and record has "not authorized" / "unauthorized"
            if val_lower in {"authorized", "valid", "eligible", "allowed"}:
                if re.search(r"\b(?:not\s+authorized|unauthorized|not\s+eligible|ineligible|no\s+authorization)\b", content_lower):
                    return False
            # Check if negative prefix/phrase directly modifies this value
            neg_pattern = re.compile(rf"\b(?:not|no|never|without|unauthorized|non-|ineligible|lacks?|lacking)\s+(?:\w+\s+)?{re.escape(val_lower)}\b")
            if neg_pattern.search(content_lower):
                return False

        # Subject / Predicate Safety checks:
        if predicate in {"employment.title", "employment.market_facing_title"}:
            # If title is in a supervisory/relational phrase (e.g. "reports to Chief Data Officer"),
            # then that title belongs to the manager/supervisor, NOT the employment subject!
            if re.search(
                rf"\b(?:reports?\s+to|reporting\s+to|reported\s+to|managed\s+by|supervised\s+by|assisting|under\s+(?:the\s+(?:direction|supervision)\s+of\s+)?|directed\s+by|advised\s+by)\s+{re.escape(val_lower)}\b",
                content_lower,
            ):
                return False

        if predicate == "employment.organization":
            # If organization name is marked as a client/vendor/partner, it is not the employer
            if re.search(
                rf"\b(?:client\s+was|client\s*:\s*|partnered\s+with|vendor\s+was|vendor\s*:\s*)\s+{re.escape(val_lower)}\b",
                content_lower,
            ):
                return False

        if predicate == "certification.name":
            # If certification is a prerequisite / requirement for others, it is not held
            if re.search(
                rf"\b(?:prerequisites?\s*(?:is|are|:)?|requires?|recommended\s*(?:is|:)?|client\s+mandated|supervised\s+holders?\s+of)\s+{re.escape(val_lower)}\b",
                content_lower,
            ):
                return False

        if val_lower in content_lower:
            return True

        val_tokens = _extract_tokens(val_str) - _STOP_WORDS
        if val_tokens:
            rec_tokens = _extract_tokens(content)
            if val_tokens.issubset(rec_tokens):
                return True

        # Check canonical skill aliases
        from .ingest import CANONICAL_SKILL_ALIASES
        canonical = CANONICAL_SKILL_ALIASES.get(val_lower)
        if canonical:
            can_tokens = _extract_tokens(canonical) - _STOP_WORDS
            if can_tokens.issubset(_extract_tokens(content)):
                return True
            if canonical.casefold() in content_lower:
                return True

        return False

    if isinstance(value, (int, float)):
        val_num = int(value) if isinstance(value, float) and value.is_integer() else value
        num_str = str(val_num)
        # Search for exact whole number match in this single record
        pattern = re.compile(rf"(?<![\d.]){re.escape(num_str)}(?![\d.])")
        return bool(pattern.search(content))

    if isinstance(value, date):
        # Exact date match required! Year-only string does NOT match exact date.
        date_iso = value.isoformat()
        if date_iso in content:
            return True
        month_names = [
            "", "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december"
        ]
        month_abbr = [
            "", "jan", "feb", "mar", "apr", "may", "jun",
            "jul", "aug", "sep", "oct", "nov", "dec"
        ]
        m_name = month_names[value.month]
        m_abbr = month_abbr[value.month]
        d_str = str(value.day)
        y_str = str(value.year)

        if f"{value.day:02d}/{value.month:02d}/{value.year}" in content or f"{value.month:02d}/{value.day:02d}/{value.year}" in content:
            return True
        if y_str in content_lower and (m_name in content_lower or m_abbr in content_lower) and d_str in content_lower:
            return True
        return False

    if isinstance(value, (tuple, list, set, frozenset)):
        return all(_single_record_supports_value(item, record, predicate=predicate, subject_id=subject_id) for item in value)

    return False


def _is_value_supported_by_evidence(
    value: Any,
    evidence_records: tuple[EvidenceRecord, ...],
    predicate: str | None = None,
    subject_id: str | None = None,
) -> bool:
    if value is None:
        return True
    if not evidence_records:
        return False

    # Check for EXPLICIT_NULL
    if all(r.verification_status is VerificationStatus.EXPLICIT_NULL for r in evidence_records):
        return value is None

    # For collections: every item must be supported by at least one single evidence record
    if isinstance(value, (tuple, list, set, frozenset)):
        return all(
            any(_single_record_supports_value(item, r, predicate=predicate, subject_id=subject_id) for r in evidence_records)
            for item in value
        )

    # For scalar values: at least one single evidence record must support the whole scalar value
    return any(_single_record_supports_value(value, r, predicate=predicate, subject_id=subject_id) for r in evidence_records)


class TruthGraph:
    """Owns atomic evidence, assertions, typed relations, and immutable profiles.

    Mutation is explicit and transactional: profile validation finishes before any
    graph index is changed. Returned mappings and records are immutable.
    """

    def __init__(
        self,
        evidence: Iterable[EvidenceRecord] = (),
        assertions: Iterable[AtomicAssertion] = (),
        relations: Iterable[TypedRelation] = (),
        metrics: Iterable[MetricAssertion] = (),
    ) -> None:
        self._evidence: dict[str, EvidenceRecord] = {}
        self._assertions: dict[str, AtomicAssertion] = {}
        self._relations: dict[str, TypedRelation] = {}
        self._metrics: dict[str, MetricAssertion] = {}
        self._profiles: dict[str, Profile] = {}
        self._entities: dict[str, object] = {}
        self._entity_evidence: dict[str, tuple[str, ...]] = {}
        self._evidence_entities: dict[str, list[str]] = {}

        for record in evidence:
            self.add_evidence(record)
        for assertion in assertions:
            self.add_assertion(assertion)
        for metric in metrics:
            self.add_metric_assertion(metric)
        for relation in relations:
            self.add_relation(relation)

    @property
    def evidence_records(self):
        return MappingProxyType(self._evidence)

    @property
    def assertions(self):
        return MappingProxyType(self._assertions)

    @property
    def relations(self):
        return MappingProxyType(self._relations)

    @property
    def metrics(self):
        return MappingProxyType(self._metrics)

    @property
    def profiles(self):
        return MappingProxyType(self._profiles)

    def _check_id_collision(self, node_id: str) -> None:
        if (
            node_id in self._evidence
            or node_id in self._entities
            or node_id in self._assertions
            or node_id in self._relations
            or node_id in self._metrics
        ):
            raise ValueError(f"duplicate graph node id: {node_id}")

    def add_evidence(self, record: EvidenceRecord) -> None:
        self._check_id_collision(record.id)
        self._evidence[record.id] = record
        self._evidence_entities.setdefault(record.id, [])

    def add_assertion(self, assertion: AtomicAssertion) -> None:
        if assertion.id in self._assertions:
            raise ValueError(f"duplicate assertion id: {assertion.id}")
        self._check_id_collision(assertion.id)

        for ev_id in assertion.evidence_ids:
            if ev_id not in self._evidence:
                raise ValueError(f"assertion {assertion.id} references unknown evidence: {ev_id}")

        evidence_records = tuple(self._evidence[ev_id] for ev_id in assertion.evidence_ids)

        # Epistemic propagation check
        if assertion.verification_status is VerificationStatus.VERIFIED:
            if not evidence_records:
                raise ValueError(f"assertion {assertion.id} is VERIFIED but has no evidence")
            if any(r.verification_status is VerificationStatus.UNVERIFIED for r in evidence_records):
                raise ValueError(f"assertion {assertion.id} cannot be VERIFIED when supported by UNVERIFIED evidence")
            if any(r.verification_status is VerificationStatus.EXPLICIT_NULL for r in evidence_records):
                raise ValueError(f"assertion {assertion.id} cannot be VERIFIED when supported by EXPLICIT_NULL evidence")
            if any(r.verification_status is VerificationStatus.APPROXIMATE for r in evidence_records):
                if assertion.modality is Modality.DEFINITE:
                    raise ValueError(f"assertion {assertion.id} cannot have DEFINITE modality when evidence is APPROXIMATE")

        if assertion.assertion_type is AssertionType.DIRECT_FACT:
            if not evidence_records:
                raise ValueError(f"assertion {assertion.id} is DIRECT_FACT but has no evidence")
            if any(r.assertion_type in {AssertionType.USER_ASSERTION, AssertionType.DERIVED_CAPABILITY} for r in evidence_records):
                raise ValueError(f"assertion {assertion.id} cannot be DIRECT_FACT when supported by user assertion or derived capability")

        # Value support verification
        if assertion.value is not None and evidence_records:
            if not _is_value_supported_by_evidence(assertion.value, evidence_records):
                raise ValueError(f"assertion {assertion.id} value {assertion.value!r} is not supported by evidence {assertion.evidence_ids}")

        self._assertions[assertion.id] = assertion

    def add_relation(self, relation: TypedRelation) -> None:
        if relation.id in self._relations:
            raise ValueError(f"duplicate relation id: {relation.id}")
        self._check_id_collision(relation.id)

        if not isinstance(relation.relation_type, RelationType):
            raise ValueError(f"relation {relation.id} relation_type must be a RelationType enum")

        for ev_id in relation.evidence_ids:
            if ev_id not in self._evidence:
                raise ValueError(f"relation {relation.id} references unknown evidence: {ev_id}")

        valid_nodes = (
            set(self._entities)
            | set(self._evidence)
            | set(self._assertions)
            | set(self._profiles)
            | set(self._metrics)
            | {a.subject_id for a in self._assertions.values()}
            | {m.subject_id for m in self._metrics.values()}
        )
        if relation.source_id not in valid_nodes or relation.target_id not in valid_nodes:
            raise ValueError(
                f"relation {relation.id} references nonexistent source '{relation.source_id}' or target '{relation.target_id}'"
            )

        evidence_records = tuple(self._evidence[ev_id] for ev_id in relation.evidence_ids)
        if relation.verification_status is VerificationStatus.VERIFIED:
            if not evidence_records:
                raise ValueError(f"relation {relation.id} is VERIFIED but has no evidence")
            if any(r.verification_status is VerificationStatus.UNVERIFIED for r in evidence_records):
                raise ValueError(f"relation {relation.id} cannot be VERIFIED when supported by UNVERIFIED evidence")

        self._relations[relation.id] = relation

    def add_metric_assertion(self, metric: MetricAssertion) -> None:
        if metric.id in self._metrics:
            raise ValueError(f"duplicate metric assertion id: {metric.id}")
        self._check_id_collision(metric.id)

        for ev_id in metric.evidence_ids:
            if ev_id not in self._evidence:
                raise ValueError(f"metric assertion {metric.id} references unknown evidence: {ev_id}")

        evidence_records = tuple(self._evidence[ev_id] for ev_id in metric.evidence_ids)
        if metric.verification_status is MetricVerification.VERIFIED:
            if not evidence_records:
                raise ValueError(f"metric assertion {metric.id} is VERIFIED but has no evidence")
            # Verify numeric value is in evidence
            if not _is_value_supported_by_evidence(metric.numeric_value, evidence_records):
                raise ValueError(f"metric assertion {metric.id} numeric value {metric.numeric_value} not in evidence {metric.evidence_ids}")

        self._metrics[metric.id] = metric

    def add_career_profile(self, profile: CareerProfile) -> None:
        self._add_profile(profile)

    def add_capability_profile(self, profile: CapabilityProfile) -> None:
        self._add_profile(profile)

    def _add_profile(self, profile: Profile) -> None:
        nodes = tuple(self._walk_profile(profile))
        node_ids = [node.id for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("profile contains duplicate entity ids")
        collisions = set(node_ids) & (
            set(self._entities) | set(self._evidence) | set(self._assertions) | set(self._relations) | set(self._metrics)
        )
        if collisions:
            raise ValueError(f"duplicate graph node id: {sorted(collisions)[0]}")

        links: dict[str, tuple[str, ...]] = {}
        for node in nodes:
            evidence_ids = self._direct_evidence_ids(node)
            missing = sorted(set(evidence_ids) - set(self._evidence))
            if missing:
                raise ValueError(f"node {node.id} references unknown evidence: {', '.join(missing)}")
            links[node.id] = evidence_ids

        # Validate that all material fields on all entities are supported by their evidence
        self._validate_profile_field_provenance(profile, links)

        # Commit nodes and links
        self._profiles[profile.id] = profile
        for node in nodes:
            self._entities[node.id] = node
            self._entity_evidence[node.id] = links[node.id]
            for ev_id in links[node.id]:
                self._evidence_entities.setdefault(ev_id, []).append(node.id)

        # Project field assertions and typed relations for profile entities
        self._project_profile_assertions(profile)

    def _validate_profile_field_provenance(self, profile: Profile, links: dict[str, tuple[str, ...]]) -> None:
        if isinstance(profile, CareerProfile):
            if profile.approved_summaries:
                evs = tuple(self._evidence[ev_id] for ev_id in links.get(profile.id, ()))
                if not evs:
                    evs = tuple(self._evidence.values())
                for summary in profile.approved_summaries:
                    if not _is_value_supported_by_evidence(summary, evs, predicate="profile.approved_summary", subject_id=profile.id):
                        raise ValueError(f"field profile.approved_summary '{summary}' is not supported by evidence")

            for emp in profile.employment:
                evs = tuple(self._evidence[ev_id] for ev_id in links[emp.id])
                if not _is_value_supported_by_evidence(emp.organization, evs, predicate="employment.organization", subject_id=emp.id):
                    raise ValueError(f"field employment.organization '{emp.organization}' is not supported by evidence: {', '.join(links[emp.id])}")
                if not _is_value_supported_by_evidence(emp.title, evs, predicate="employment.title", subject_id=emp.id):
                    raise ValueError(f"field employment.title '{emp.title}' is not supported by evidence: {', '.join(links[emp.id])}")
                if emp.market_facing_title and not _is_value_supported_by_evidence(emp.market_facing_title, evs, predicate="employment.market_facing_title", subject_id=emp.id):
                    raise ValueError(f"field employment.market_facing_title '{emp.market_facing_title}' is not supported by evidence: {', '.join(links[emp.id])}")
                if not _is_value_supported_by_evidence(emp.start_date, evs, predicate="employment.start_date", subject_id=emp.id):
                    raise ValueError(f"field employment.start_date '{emp.start_date}' is not supported by evidence: {', '.join(links[emp.id])}")
                if emp.end_date and not _is_value_supported_by_evidence(emp.end_date, evs, predicate="employment.end_date", subject_id=emp.id):
                    raise ValueError(f"field employment.end_date '{emp.end_date}' is not supported by evidence: {', '.join(links[emp.id])}")
                for resp in emp.responsibilities:
                    if not _is_value_supported_by_evidence(resp, evs, predicate="employment.responsibility", subject_id=emp.id):
                        raise ValueError(f"field employment.responsibility '{resp}' is not supported by evidence: {', '.join(links[emp.id])}")
                for ach in emp.achievements:
                    ach_evs = tuple(self._evidence[ev_id] for ev_id in links[ach.id])
                    if not _is_value_supported_by_evidence(ach.statement, ach_evs, predicate="achievement.statement", subject_id=ach.id):
                        raise ValueError(f"field achievement.statement '{ach.statement}' is not supported by evidence: {', '.join(links[ach.id])}")
            for edu in profile.education:
                evs = tuple(self._evidence[ev_id] for ev_id in links[edu.id])
                if not _is_value_supported_by_evidence(edu.institution, evs, predicate="education.institution", subject_id=edu.id):
                    raise ValueError(f"field education.institution '{edu.institution}' is not supported by evidence: {', '.join(links[edu.id])}")
                if not _is_value_supported_by_evidence(edu.qualification, evs, predicate="education.qualification", subject_id=edu.id):
                    raise ValueError(f"field education.qualification '{edu.qualification}' is not supported by evidence: {', '.join(links[edu.id])}")
                if edu.start_date and not _is_value_supported_by_evidence(edu.start_date, evs, predicate="education.start_date", subject_id=edu.id):
                    raise ValueError(f"field education.start_date '{edu.start_date}' is not supported by evidence: {', '.join(links[edu.id])}")
                if edu.end_date and not _is_value_supported_by_evidence(edu.end_date, evs, predicate="education.end_date", subject_id=edu.id):
                    raise ValueError(f"field education.end_date '{edu.end_date}' is not supported by evidence: {', '.join(links[edu.id])}")
            for cert in profile.certifications:
                evs = tuple(self._evidence[ev_id] for ev_id in links[cert.id])
                if not _is_value_supported_by_evidence(cert.name, evs, predicate="certification.name", subject_id=cert.id):
                    raise ValueError(f"field certification.name '{cert.name}' is not supported by evidence: {', '.join(links[cert.id])}")
                if not _is_value_supported_by_evidence(cert.issuer, evs, predicate="certification.issuer", subject_id=cert.id):
                    raise ValueError(f"field certification.issuer '{cert.issuer}' is not supported by evidence: {', '.join(links[cert.id])}")
                if cert.issued_date and not _is_value_supported_by_evidence(cert.issued_date, evs, predicate="certification.issued_date", subject_id=cert.id):
                    raise ValueError(f"field certification.issued_date '{cert.issued_date}' is not supported by evidence: {', '.join(links[cert.id])}")
                if cert.expiry_date and not _is_value_supported_by_evidence(cert.expiry_date, evs, predicate="certification.expiry_date", subject_id=cert.id):
                    raise ValueError(f"field certification.expiry_date '{cert.expiry_date}' is not supported by evidence: {', '.join(links[cert.id])}")
                if cert.credential_id and not _is_value_supported_by_evidence(cert.credential_id, evs, predicate="certification.credential_id", subject_id=cert.id):
                    raise ValueError(f"field certification.credential_id '{cert.credential_id}' is not supported by evidence: {', '.join(links[cert.id])}")
                if cert.credential_url and not _is_value_supported_by_evidence(cert.credential_url, evs, predicate="certification.credential_url", subject_id=cert.id):
                    raise ValueError(f"field certification.credential_url '{cert.credential_url}' is not supported by evidence: {', '.join(links[cert.id])}")
            for skill in profile.skills:
                evs = tuple(self._evidence[ev_id] for ev_id in links[skill.id])
                if not _is_value_supported_by_evidence(skill.name, evs, predicate="skill.name", subject_id=skill.id):
                    raise ValueError(f"field skill.name '{skill.name}' is not supported by evidence: {', '.join(links[skill.id])}")
                if skill.proficiency and not _is_value_supported_by_evidence(skill.proficiency, evs, predicate="skill.proficiency", subject_id=skill.id):
                    raise ValueError(f"field skill.proficiency '{skill.proficiency}' is not supported by evidence: {', '.join(links[skill.id])}")
            for lang in profile.languages:
                evs = tuple(self._evidence[ev_id] for ev_id in links[lang.id])
                if not _is_value_supported_by_evidence(lang.language, evs, predicate="language.language", subject_id=lang.id):
                    raise ValueError(f"field language.language '{lang.language}' is not supported by evidence: {', '.join(links[lang.id])}")
                if not _is_value_supported_by_evidence(lang.proficiency, evs, predicate="language.proficiency", subject_id=lang.id):
                    raise ValueError(f"field language.proficiency '{lang.proficiency}' is not supported by evidence: {', '.join(links[lang.id])}")
            for auth in profile.work_authorizations:
                evs = tuple(self._evidence[ev_id] for ev_id in links[auth.id])
                if not _is_value_supported_by_evidence(auth.jurisdiction, evs, predicate="work_authorization.jurisdiction", subject_id=auth.id):
                    raise ValueError(f"field work_authorization.jurisdiction '{auth.jurisdiction}' is not supported by evidence: {', '.join(links[auth.id])}")
                if not _is_value_supported_by_evidence(auth.status, evs, predicate="work_authorization.status", subject_id=auth.id):
                    raise ValueError(f"field work_authorization.status '{auth.status}' is not supported by evidence: {', '.join(links[auth.id])}")
                if auth.expiry_date and not _is_value_supported_by_evidence(auth.expiry_date, evs, predicate="work_authorization.expiry_date", subject_id=auth.id):
                    raise ValueError(f"field work_authorization.expiry_date '{auth.expiry_date}' is not supported by evidence: {', '.join(links[auth.id])}")
        else:
            cap_evs = tuple(self._evidence[ev_id] for ev_id in links.get(profile.id, ()))
            if not cap_evs:
                cap_evs = tuple(self._evidence.values())
            if profile.target_industries:
                for ind in profile.target_industries:
                    if not _is_value_supported_by_evidence(ind, cap_evs, predicate="capability.target_industry", subject_id=profile.id):
                        raise ValueError(f"field capability.target_industry '{ind}' is not supported by evidence")
            if profile.excluded_industries:
                for ind in profile.excluded_industries:
                    if not _is_value_supported_by_evidence(ind, cap_evs, predicate="capability.excluded_industry", subject_id=profile.id):
                        raise ValueError(f"field capability.excluded_industry '{ind}' is not supported by evidence")
            if profile.delivery_languages:
                for dlang in profile.delivery_languages:
                    if not _is_value_supported_by_evidence(dlang, cap_evs, predicate="capability.delivery_language", subject_id=profile.id):
                        raise ValueError(f"field capability.delivery_language '{dlang}' is not supported by evidence")

            for srv in profile.services:
                evs = tuple(self._evidence[ev_id] for ev_id in links[srv.id])
                if not _is_value_supported_by_evidence(srv.name, evs, predicate="service.name", subject_id=srv.id):
                    raise ValueError(f"field service.name '{srv.name}' is not supported by evidence: {', '.join(links[srv.id])}")
                if not _is_value_supported_by_evidence(srv.description, evs, predicate="service.description", subject_id=srv.id):
                    raise ValueError(f"field service.description '{srv.description}' is not supported by evidence: {', '.join(links[srv.id])}")
                if srv.engagement_types and not _is_value_supported_by_evidence([et.value for et in srv.engagement_types], evs, predicate="service.engagement_type", subject_id=srv.id):
                    raise ValueError(f"field service.engagement_types is not supported by evidence: {', '.join(links[srv.id])}")
                if srv.deliverables and not _is_value_supported_by_evidence(srv.deliverables, evs, predicate="service.deliverable", subject_id=srv.id):
                    raise ValueError(f"field service.deliverables '{srv.deliverables}' is not supported by evidence: {', '.join(links[srv.id])}")
            for port in profile.portfolio:
                evs = tuple(self._evidence[ev_id] for ev_id in links[port.id])
                if not _is_value_supported_by_evidence(port.title, evs, predicate="portfolio.title", subject_id=port.id):
                    raise ValueError(f"field portfolio.title '{port.title}' is not supported by evidence: {', '.join(links[port.id])}")
                if not _is_value_supported_by_evidence(port.summary, evs, predicate="portfolio.summary", subject_id=port.id):
                    raise ValueError(f"field portfolio.summary '{port.summary}' is not supported by evidence: {', '.join(links[port.id])}")
                if port.outcome and not _is_value_supported_by_evidence(port.outcome, evs, predicate="portfolio.outcome", subject_id=port.id):
                    raise ValueError(f"field portfolio.outcome '{port.outcome}' is not supported by evidence: {', '.join(links[port.id])}")
                if port.url and not _is_value_supported_by_evidence(port.url, evs, predicate="portfolio.url", subject_id=port.id):
                    raise ValueError(f"field portfolio.url '{port.url}' is not supported by evidence: {', '.join(links[port.id])}")
            if profile.capacity:
                cap = profile.capacity
                evs = tuple(self._evidence[ev_id] for ev_id in links[cap.id])
                if cap.available_from and not _is_value_supported_by_evidence(cap.available_from, evs, predicate="capacity.available_from", subject_id=cap.id):
                    raise ValueError(f"field capacity.available_from '{cap.available_from}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.hours_per_week is not None and not _is_value_supported_by_evidence(cap.hours_per_week, evs, predicate="capacity.hours_per_week", subject_id=cap.id):
                    raise ValueError(f"field capacity.hours_per_week '{cap.hours_per_week}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.min_project_value is not None and not _is_value_supported_by_evidence(cap.min_project_value, evs, predicate="capacity.min_project_value", subject_id=cap.id):
                    raise ValueError(f"field capacity.min_project_value '{cap.min_project_value}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.max_project_value is not None and not _is_value_supported_by_evidence(cap.max_project_value, evs, predicate="capacity.max_project_value", subject_id=cap.id):
                    raise ValueError(f"field capacity.max_project_value '{cap.max_project_value}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.annual_turnover_usd is not None and not _is_value_supported_by_evidence(cap.annual_turnover_usd, evs, predicate="capacity.annual_turnover_usd", subject_id=cap.id):
                    raise ValueError(f"field capacity.annual_turnover_usd '{cap.annual_turnover_usd}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.bid_bond_capacity_usd is not None and not _is_value_supported_by_evidence(cap.bid_bond_capacity_usd, evs, predicate="capacity.bid_bond_capacity_usd", subject_id=cap.id):
                    raise ValueError(f"field capacity.bid_bond_capacity_usd '{cap.bid_bond_capacity_usd}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.legal_capacity is not None and not _is_value_supported_by_evidence(cap.legal_capacity, evs, predicate="capacity.legal_capacity", subject_id=cap.id):
                    raise ValueError(f"field capacity.legal_capacity '{cap.legal_capacity}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.currencies and not _is_value_supported_by_evidence(cap.currencies, evs, predicate="capacity.currency", subject_id=cap.id):
                    raise ValueError(f"field capacity.currencies '{cap.currencies}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.service_regions and not _is_value_supported_by_evidence(cap.service_regions, evs, predicate="capacity.service_region", subject_id=cap.id):
                    raise ValueError(f"field capacity.service_regions '{cap.service_regions}' is not supported by evidence: {', '.join(links[cap.id])}")
                if cap.onsite_willingness and not _is_value_supported_by_evidence(cap.onsite_willingness, evs, predicate="capacity.onsite_willingness", subject_id=cap.id):
                    raise ValueError(f"field capacity.onsite_willingness '{cap.onsite_willingness}' is not supported by evidence: {', '.join(links[cap.id])}")
            for tool in profile.tools:
                tool_evs = tuple(self._evidence[ev_id] for ev_id in links[tool.id])
                if not _is_value_supported_by_evidence(tool.name, tool_evs, predicate="tool.name", subject_id=tool.id):
                    raise ValueError(f"field tool.name '{tool.name}' is not supported by evidence: {', '.join(links[tool.id])}")
                if tool.proficiency and not _is_value_supported_by_evidence(tool.proficiency, tool_evs, predicate="tool.proficiency", subject_id=tool.id):
                    raise ValueError(f"field tool.proficiency '{tool.proficiency}' is not supported by evidence: {', '.join(links[tool.id])}")

    def _derive_epistemic_status(
        self,
        evidence_ids: tuple[str, ...],
        *,
        default_assertion_type: AssertionType = AssertionType.DIRECT_FACT,
    ) -> tuple[AssertionType, VerificationStatus, Polarity, Modality]:
        if not evidence_ids:
            return (AssertionType.UNSUPPORTED_CLAIM, VerificationStatus.UNVERIFIED, Polarity.POSITIVE, Modality.DEFINITE)

        records = [self._evidence[ev_id] for ev_id in evidence_ids if ev_id in self._evidence]
        if not records:
            return (AssertionType.UNSUPPORTED_CLAIM, VerificationStatus.UNVERIFIED, Polarity.POSITIVE, Modality.DEFINITE)

        # Verification Status: weakest link
        if any(r.verification_status is VerificationStatus.EXPLICIT_NULL for r in records):
            status = VerificationStatus.EXPLICIT_NULL
        elif any(r.verification_status is VerificationStatus.UNVERIFIED for r in records):
            status = VerificationStatus.UNVERIFIED
        elif any(r.verification_status is VerificationStatus.APPROXIMATE for r in records):
            status = VerificationStatus.APPROXIMATE
        else:
            status = VerificationStatus.VERIFIED

        # Assertion Type: weakest link
        priority = {
            AssertionType.PROHIBITED_CLAIM: 0,
            AssertionType.UNSUPPORTED_CLAIM: 1,
            AssertionType.USER_ASSERTION: 2,
            AssertionType.DERIVED_CAPABILITY: 3,
            AssertionType.NORMALIZED_FACT: 4,
            AssertionType.DIRECT_FACT: 5,
        }
        min_type = default_assertion_type
        for r in records:
            if priority.get(r.assertion_type, 0) < priority.get(min_type, 5):
                min_type = r.assertion_type

        # Polarity & Modality
        combined_text = " ".join(r.content or "" for r in records)
        polarity = Polarity.NEGATIVE if _NEGATIVE_MARKERS.search(combined_text) else Polarity.POSITIVE
        if _BOUND_AT_MOST.search(combined_text):
            modality = Modality.AT_MOST
        elif _BOUND_AT_LEAST.search(combined_text):
            modality = Modality.AT_LEAST
        elif _CONDITIONAL.search(combined_text):
            modality = Modality.CONDITIONAL
        elif status is VerificationStatus.APPROXIMATE:
            modality = Modality.APPROXIMATE
        else:
            modality = Modality.DEFINITE

        return (min_type, status, polarity, modality)

    def _project_profile_assertions(self, profile: Profile) -> None:
        if isinstance(profile, CareerProfile):
            for idx, summary in enumerate(profile.approved_summaries):
                self._project_field_assertion(f"{profile.id}.summary.{idx}", "profile.approved_summary", summary, profile.evidence_ids)

            for emp in profile.employment:
                self._project_field_assertion(emp.id, "employment.organization", emp.organization, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                self._project_field_assertion(emp.id, "employment.title", emp.title, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                if emp.market_facing_title:
                    self._project_field_assertion(emp.id, "employment.market_facing_title", emp.market_facing_title, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                self._project_field_assertion(emp.id, "employment.start_date", emp.start_date, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                if emp.end_date:
                    self._project_field_assertion(emp.id, "employment.end_date", emp.end_date, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                for idx, resp in enumerate(emp.responsibilities):
                    self._project_field_assertion(f"{emp.id}.resp.{idx}", "employment.responsibility", resp, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)

                for ach in emp.achievements:
                    self._project_field_assertion(ach.id, "achievement.statement", ach.statement, ach.evidence_ids)
                    rel_id = f"rel_{emp.id}_{ach.id}"
                    if rel_id not in self._relations:
                        # An Achievement nested under Employment becomes a VERIFIED relation ONLY if evidence
                        # establishes the employer or role relationship itself (e.g. mentions employer or shares evidence).
                        ach_evs = tuple(self._evidence[ev_id] for ev_id in ach.evidence_ids if ev_id in self._evidence)
                        establishes_rel = any(
                            _single_record_supports_value(emp.organization, r) for r in ach_evs
                        ) or bool(set(ach.evidence_ids) & set(emp.evidence_ids))

                        if establishes_rel:
                            rel_type, rel_status, _, _ = self._derive_epistemic_status(ach.evidence_ids)
                        else:
                            rel_type = AssertionType.USER_ASSERTION
                            rel_status = VerificationStatus.UNVERIFIED

                        self._relations[rel_id] = TypedRelation(
                            id=rel_id,
                            source_id=emp.id,
                            relation_type=RelationType.ACHIEVED_DURING,
                            target_id=ach.id,
                            evidence_ids=ach.evidence_ids,
                            assertion_type=rel_type,
                            verification_status=rel_status,
                            effective_from=emp.start_date,
                            effective_to=emp.end_date,
                        )
                    # Extract candidate numeric metric assertions from achievement (default UNAVAILABLE)
                    self._extract_metrics_from_text(ach.id, ach.statement, ach.evidence_ids, ach.metric_verification)

            for edu in profile.education:
                self._project_field_assertion(edu.id, "education.institution", edu.institution, edu.evidence_ids, effective_from=edu.start_date, effective_to=edu.end_date)
                self._project_field_assertion(edu.id, "education.qualification", edu.qualification, edu.evidence_ids, effective_from=edu.start_date, effective_to=edu.end_date)
                if edu.start_date:
                    self._project_field_assertion(edu.id, "education.start_date", edu.start_date, edu.evidence_ids, effective_from=edu.start_date, effective_to=edu.end_date)
                if edu.end_date:
                    self._project_field_assertion(edu.id, "education.end_date", edu.end_date, edu.evidence_ids, effective_from=edu.start_date, effective_to=edu.end_date)

            for cert in profile.certifications:
                modality = Modality.PLANNED if cert.state is CertificationState.PLANNED else Modality.DEFINITE
                self._project_field_assertion(cert.id, "certification.name", cert.name, cert.evidence_ids, force_modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)
                self._project_field_assertion(cert.id, "certification.issuer", cert.issuer, cert.evidence_ids, force_modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)
                self._project_field_assertion(cert.id, "certification.state", cert.state.value, cert.evidence_ids, force_modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)
                if cert.issued_date:
                    self._project_field_assertion(cert.id, "certification.issued_date", cert.issued_date, cert.evidence_ids, force_modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)
                if cert.expiry_date:
                    self._project_field_assertion(cert.id, "certification.expiry_date", cert.expiry_date, cert.evidence_ids, force_modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)
                if cert.credential_id:
                    self._project_field_assertion(cert.id, "certification.credential_id", cert.credential_id, cert.evidence_ids, force_modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)
                if cert.credential_url:
                    self._project_field_assertion(cert.id, "certification.credential_url", cert.credential_url, cert.evidence_ids, force_modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)

            for skill in profile.skills:
                self._project_field_assertion(skill.id, "skill.name", skill.name, skill.evidence_ids)
                if skill.proficiency:
                    self._project_field_assertion(skill.id, "skill.proficiency", skill.proficiency, skill.evidence_ids)

            for lang in profile.languages:
                self._project_field_assertion(lang.id, "language.language", lang.language, lang.evidence_ids)
                self._project_field_assertion(lang.id, "language.proficiency", lang.proficiency, lang.evidence_ids)

            for auth in profile.work_authorizations:
                self._project_field_assertion(auth.id, "work_authorization.jurisdiction", auth.jurisdiction, auth.evidence_ids, effective_to=auth.expiry_date)
                self._project_field_assertion(auth.id, "work_authorization.status", auth.status, auth.evidence_ids, effective_to=auth.expiry_date)
                if auth.expiry_date:
                    self._project_field_assertion(auth.id, "work_authorization.expiry_date", auth.expiry_date, auth.evidence_ids, effective_to=auth.expiry_date)
        else:
            for idx, ind in enumerate(profile.target_industries):
                self._project_field_assertion(f"{profile.id}.target_ind.{idx}", "capability.target_industry", ind, profile.evidence_ids, default_assertion_type=AssertionType.DERIVED_CAPABILITY)
            for idx, ind in enumerate(profile.excluded_industries):
                self._project_field_assertion(f"{profile.id}.excluded_ind.{idx}", "capability.excluded_industry", ind, profile.evidence_ids, default_assertion_type=AssertionType.DERIVED_CAPABILITY)
            for idx, dlang in enumerate(profile.delivery_languages):
                self._project_field_assertion(f"{profile.id}.delivery_lang.{idx}", "capability.delivery_language", dlang, profile.evidence_ids, default_assertion_type=AssertionType.DERIVED_CAPABILITY)

            for srv in profile.services:
                self._project_field_assertion(srv.id, "service.name", srv.name, srv.evidence_ids, default_assertion_type=AssertionType.DERIVED_CAPABILITY)
                self._project_field_assertion(srv.id, "service.description", srv.description, srv.evidence_ids, default_assertion_type=AssertionType.DERIVED_CAPABILITY)
                for idx, eng in enumerate(srv.engagement_types):
                    self._project_field_assertion(f"{srv.id}.eng.{idx}", "service.engagement_type", eng.value, srv.evidence_ids, default_assertion_type=AssertionType.DERIVED_CAPABILITY)
                for idx, deliv in enumerate(srv.deliverables):
                    self._project_field_assertion(f"{srv.id}.deliv.{idx}", "service.deliverable", deliv, srv.evidence_ids, default_assertion_type=AssertionType.DERIVED_CAPABILITY)

            for port in profile.portfolio:
                self._project_field_assertion(port.id, "portfolio.title", port.title, port.evidence_ids)
                self._project_field_assertion(port.id, "portfolio.summary", port.summary, port.evidence_ids)
                if port.outcome:
                    self._project_field_assertion(port.id, "portfolio.outcome", port.outcome, port.evidence_ids)
                    self._extract_metrics_from_text(port.id, port.outcome, port.evidence_ids, port.metric_verification)
                if port.url:
                    self._project_field_assertion(port.id, "portfolio.url", port.url, port.evidence_ids)

            if profile.capacity:
                cap = profile.capacity
                if cap.available_from:
                    self._project_field_assertion(cap.id, "capacity.available_from", cap.available_from, cap.evidence_ids, effective_from=cap.available_from)
                if cap.hours_per_week is not None:
                    self._project_field_assertion(cap.id, "capacity.hours_per_week", cap.hours_per_week, cap.evidence_ids, effective_from=cap.available_from)
                if cap.min_project_value is not None:
                    self._project_field_assertion(cap.id, "capacity.min_project_value", cap.min_project_value, cap.evidence_ids, effective_from=cap.available_from)
                if cap.max_project_value is not None:
                    self._project_field_assertion(cap.id, "capacity.max_project_value", cap.max_project_value, cap.evidence_ids, effective_from=cap.available_from)
                if cap.annual_turnover_usd is not None:
                    self._project_field_assertion(cap.id, "capacity.annual_turnover_usd", cap.annual_turnover_usd, cap.evidence_ids, effective_from=cap.available_from)
                if cap.bid_bond_capacity_usd is not None:
                    self._project_field_assertion(cap.id, "capacity.bid_bond_capacity_usd", cap.bid_bond_capacity_usd, cap.evidence_ids, effective_from=cap.available_from)
                for idx, curr in enumerate(cap.currencies):
                    self._project_field_assertion(f"{cap.id}.curr.{idx}", "capacity.currency", curr, cap.evidence_ids, effective_from=cap.available_from)
                for idx, reg in enumerate(cap.service_regions):
                    self._project_field_assertion(f"{cap.id}.region.{idx}", "capacity.service_region", reg, cap.evidence_ids, effective_from=cap.available_from)
                if cap.onsite_willingness:
                    self._project_field_assertion(cap.id, "capacity.onsite_willingness", cap.onsite_willingness, cap.evidence_ids, effective_from=cap.available_from)
                self._project_field_assertion(cap.id, "capacity.legal_capacity", cap.legal_capacity, cap.evidence_ids, effective_from=cap.available_from)

            for tool in profile.tools:
                self._project_field_assertion(tool.id, "tool.name", tool.name, tool.evidence_ids)
                if tool.proficiency:
                    self._project_field_assertion(tool.id, "tool.proficiency", tool.proficiency, tool.evidence_ids)

    def _project_field_assertion(
        self,
        subject_id: str,
        predicate: str,
        value: Any,
        evidence_ids: tuple[str, ...],
        *,
        default_assertion_type: AssertionType = AssertionType.DIRECT_FACT,
        force_modality: Modality | None = None,
        effective_from: date | None = None,
        effective_to: date | None = None,
    ) -> None:
        assertion_id = f"as_{subject_id}_{predicate.replace('.', '_')}"
        if assertion_id in self._assertions:
            return

        # Filter evidence_ids to those that specifically support this field value
        if value is None:
            field_ev_ids = tuple(
                ev_id for ev_id in evidence_ids
                if self._evidence.get(ev_id) and self._evidence[ev_id].verification_status is VerificationStatus.EXPLICIT_NULL
            )
        else:
            field_ev_ids = tuple(
                ev_id for ev_id in evidence_ids
                if self._evidence.get(ev_id) and _single_record_supports_value(value, self._evidence[ev_id], predicate=predicate, subject_id=subject_id)
            )
        if not field_ev_ids:
            field_ev_ids = evidence_ids

        as_type, status, polarity, modality = self._derive_epistemic_status(field_ev_ids, default_assertion_type=default_assertion_type)
        if force_modality is not None:
            modality = force_modality

        self._assertions[assertion_id] = AtomicAssertion(
            id=assertion_id,
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            assertion_type=as_type,
            verification_status=status,
            evidence_ids=field_ev_ids,
            polarity=polarity,
            modality=modality,
            effective_from=effective_from,
            effective_to=effective_to,
        )

    def _extract_metrics_from_text(
        self,
        subject_id: str,
        text: str,
        evidence_ids: tuple[str, ...],
        verification: MetricVerification,
    ) -> None:
        metric_pattern = re.compile(
            r"(?<![\w-])(?:(?P<curr>[$€£])\s*)?(?P<val>\d+(?:[.,]\d+)?)(?:\s*(?P<unit>%|[xX]\b|hours?|days?|weeks?|months?|users?|clients?|projects?|requests?|seconds?|minutes?|USD|EUR|GBP))?",
            re.IGNORECASE,
        )
        matches = list(metric_pattern.finditer(text))
        supporting_records = tuple(self._evidence[ev_id] for ev_id in evidence_ids if ev_id in self._evidence)

        for idx, match in enumerate(matches):
            curr = match.group("curr") or ""
            val_str = match.group("val").replace(",", "")
            unit = (match.group("unit") or curr or "count").strip()
            try:
                num_val = float(val_str) if "." in val_str else int(val_str)
            except ValueError:
                continue

            # Position-independent check:
            # Metric is VERIFIED only if:
            # 1. Subject/entity has verification == MetricVerification.VERIFIED
            # 2. At least one supporting evidence record explicitly contains this exact number and unit
            is_verified = False
            if verification is MetricVerification.VERIFIED and supporting_records:
                for rec in supporting_records:
                    if not rec.content:
                        continue
                    num_pattern = re.compile(rf"(?<![\d.]){re.escape(str(num_val))}(?![\d.])")
                    if num_pattern.search(rec.content):
                        if unit == "%":
                            if "%" in rec.content or "percent" in rec.content.casefold():
                                is_verified = True
                                break
                        elif unit in {"$", "USD", "EUR", "GBP", "€", "£"}:
                            if any(u in rec.content for u in {"$", "USD", "EUR", "GBP", "€", "£", "dollar", "euro"}):
                                is_verified = True
                                break
                        elif unit not in {"%", "$", "USD", "EUR", "GBP", "€", "£"}:
                            is_verified = True
                            break

            metric_status = MetricVerification.VERIFIED if is_verified else (
                verification if verification is MetricVerification.APPROXIMATE else MetricVerification.UNAVAILABLE
            )

            metric_id = f"metric_{subject_id}_{idx}"
            if metric_id not in self._metrics:
                self._metrics[metric_id] = MetricAssertion(
                    id=metric_id,
                    subject_id=subject_id,
                    numeric_value=num_val,
                    unit=unit,
                    context=text[:100],
                    verification_status=metric_status,
                    evidence_ids=evidence_ids,
                )

    def entities_for_evidence(self, evidence_id: str) -> tuple[object, ...]:
        """Return all entity nodes supported by a given evidence record."""
        if evidence_id not in self._evidence:
            raise KeyError(f"unknown evidence id: {evidence_id}")
        entity_ids = tuple(dict.fromkeys(self._evidence_entities.get(evidence_id, [])))
        return tuple(self._entities[entity_id] for entity_id in entity_ids if entity_id in self._entities)

    def entity_ids_for_evidence(self, evidence_id: str) -> tuple[str, ...]:
        """Return all entity node IDs supported by a given evidence record."""
        if evidence_id not in self._evidence:
            raise KeyError(f"unknown evidence id: {evidence_id}")
        return tuple(dict.fromkeys(self._evidence_entities.get(evidence_id, [])))

    def are_relationally_linked(self, evidence_ids: tuple[str, ...] | list[str] | set[str]) -> bool:
        """Determine whether multiple evidence IDs share an explicit relational edge or common entity in the graph.

        Cross-evidence relationship laundering is prevented by requiring that any conjunction of
        distinct evidence records must be explicitly grounded in the exact same entity or connected
        via an explicit, verified TypedRelation in the TruthGraph.
        """
        unique_ids = tuple(dict.fromkeys(evidence_ids))
        if len(unique_ids) <= 1:
            return True

        # Check if all evidence IDs belong to the exact same sub-entity
        entities_per_ev = [set(self._evidence_entities.get(ev_id, [])) for ev_id in unique_ids]
        common_entities = set.intersection(*entities_per_ev) if entities_per_ev else set()
        common_non_root = [e_id for e_id in common_entities if not isinstance(self._entities.get(e_id), (CareerProfile, CapabilityProfile))]
        if common_non_root:
            return True

        # Check if an explicit verified TypedRelation connects the entities of the distinct evidence records
        for i, ev1 in enumerate(unique_ids):
            for ev2 in unique_ids[i + 1 :]:
                ents1 = set(self._evidence_entities.get(ev1, []))
                ents2 = set(self._evidence_entities.get(ev2, []))
                connected = False
                for r in self._relations.values():
                    if r.verification_status is not VerificationStatus.VERIFIED:
                        continue
                    if (r.source_id in ents1 and r.target_id in ents2) or (r.source_id in ents2 and r.target_id in ents1):
                        connected = True
                        break
                if not connected:
                    return False

        return True

    def active_assertions(self, as_of: date | None = None) -> tuple[AtomicAssertion, ...]:
        """Return currently active, non-superseded, non-conflicting, temporally valid assertions."""
        all_assertions = list(self._assertions.values())
        superseded_ids: set[str] = set()
        conflicting_ids: set[str] = set()

        for a in all_assertions:
            # Assertion a only supersedes or conflicts if a is itself active as_of
            if as_of is not None:
                if a.effective_from and as_of < a.effective_from:
                    continue
                if a.effective_to and as_of > a.effective_to:
                    continue
            for s_id in a.supersedes:
                superseded_ids.add(s_id)
            for c_id in a.conflicts_with:
                conflicting_ids.add(c_id)
                conflicting_ids.add(a.id)

        active = []
        for a in all_assertions:
            if a.id in superseded_ids:
                continue
            if a.id in conflicting_ids:
                continue
            if as_of is not None:
                if a.effective_from and as_of < a.effective_from:
                    continue
                if a.effective_to and as_of > a.effective_to:
                    continue
            active.append(a)

        return tuple(active)

    @staticmethod
    def _direct_evidence_ids(node: object) -> tuple[str, ...]:
        value = getattr(node, "evidence_ids", ())
        return tuple(value)

    @staticmethod
    def _walk_profile(profile: Profile):
        yield profile
        if isinstance(profile, CareerProfile):
            for employment in profile.employment:
                yield employment
                yield from employment.achievements
            yield from profile.education
            yield from profile.certifications
            yield from profile.skills
            yield from profile.languages
            yield from profile.work_authorizations
            yield from profile.red_lines
            yield from profile.never_claims
        else:
            yield from profile.services
            yield from profile.portfolio
            if profile.capacity is not None:
                yield profile.capacity
            yield from profile.tools
            yield from profile.red_lines
            yield from profile.never_claims

    def evidence(self, evidence_id: str) -> EvidenceRecord:
        try:
            return self._evidence[evidence_id]
        except KeyError as error:
            raise KeyError(f"unknown evidence id: {evidence_id}") from error

    def entity(self, entity_id: str) -> object:
        try:
            return self._entities[entity_id]
        except KeyError as error:
            raise KeyError(f"unknown entity id: {entity_id}") from error

    def evidence_for(self, entity_id: str, *, recursive: bool = False) -> tuple[EvidenceRecord, ...]:
        """Return direct, or stable recursively collected, provenance records."""
        entity = self.entity(entity_id)
        evidence_ids = list(self._entity_evidence[entity_id])
        if recursive and isinstance(entity, (CareerProfile, CapabilityProfile)):
            for node in self._walk_profile(entity):
                evidence_ids.extend(self._entity_evidence[node.id])
        unique_ids = tuple(dict.fromkeys(evidence_ids))
        return tuple(self._evidence[evidence_id] for evidence_id in unique_ids)

    def provenance(self, entity_id: str) -> tuple[tuple[str, EvidenceRecord], ...]:
        """Return a stable edge list from a profile/entity to its recursive evidence."""
        entity = self.entity(entity_id)
        nodes = (
            tuple(self._walk_profile(entity))
            if isinstance(entity, (CareerProfile, CapabilityProfile))
            else (entity,)
        )
        return tuple(
            (node.id, self._evidence[evidence_id])
            for node in nodes
            for evidence_id in self._entity_evidence[node.id]
        )

    def records_by_assertion(self, assertion_type: AssertionType) -> tuple[EvidenceRecord, ...]:
        return tuple(
            record
            for record in self._evidence.values()
            if record.assertion_type is assertion_type
        )

    def facts(self) -> tuple[EvidenceRecord, ...]:
        fact_types = {AssertionType.DIRECT_FACT, AssertionType.NORMALIZED_FACT}
        return tuple(record for record in self._evidence.values() if record.assertion_type in fact_types)

    def inferences(self) -> tuple[EvidenceRecord, ...]:
        inference_types = {AssertionType.DERIVED_CAPABILITY, AssertionType.USER_ASSERTION}
        return tuple(
            record for record in self._evidence.values() if record.assertion_type in inference_types
        )

    def assertions_for_subject(self, subject_id: str) -> tuple[AtomicAssertion, ...]:
        return tuple(a for a in self._assertions.values() if a.subject_id == subject_id)

    def assertion_for_field(self, subject_id: str, predicate: str) -> AtomicAssertion | None:
        for a in self._assertions.values():
            if a.subject_id == subject_id and a.predicate == predicate:
                return a
        return None

    def relations_for_source(self, source_id: str) -> tuple[TypedRelation, ...]:
        return tuple(r for r in self._relations.values() if r.source_id == source_id)

    def relations_between(self, source_id: str, target_id: str) -> tuple[TypedRelation, ...]:
        return tuple(r for r in self._relations.values() if r.source_id == source_id and r.target_id == target_id)

    def has_relation(
        self,
        source_id: str,
        relation_type: RelationType | str,
        target_id: str,
        *,
        as_of: date | None = None,
    ) -> bool:
        for r in self._relations.values():
            if r.source_id == source_id and r.target_id == target_id:
                if isinstance(relation_type, RelationType) and r.relation_type is not relation_type:
                    continue
                if isinstance(relation_type, str) and str(r.relation_type) != str(relation_type):
                    continue
                if r.verification_status is VerificationStatus.UNVERIFIED:
                    continue
                if as_of is not None:
                    if r.effective_from and as_of < r.effective_from:
                        continue
                    if r.effective_to and as_of > r.effective_to:
                        continue
                return True
        return False

    def metric_assertions_for_evidence(self, evidence_id: str) -> tuple[MetricAssertion, ...]:
        return tuple(m for m in self._metrics.values() if evidence_id in m.evidence_ids)

    def metric_assertions_for_subject(self, subject_id: str) -> tuple[MetricAssertion, ...]:
        return tuple(m for m in self._metrics.values() if m.subject_id == subject_id)

    def metric_status_for_evidence(self, evidence_id: str):
        """Find metric statuses of achievements/portfolio items linked to evidence."""
        statuses = []
        for node_id, evidence_ids in self._entity_evidence.items():
            if evidence_id in evidence_ids:
                node = self._entities[node_id]
                status = getattr(node, "metric_verification", None)
                if status is not None:
                    statuses.append(status)
        return tuple(statuses)

    def certification_records(self):
        return tuple(
            certification
            for profile in self._profiles.values()
            if isinstance(profile, CareerProfile)
            for certification in profile.certifications
        )

    def rules(self):
        red_lines = []
        never_claims = []
        for profile in self._profiles.values():
            red_lines.extend(profile.red_lines)
            never_claims.extend(profile.never_claims)
        return tuple(red_lines), tuple(never_claims)

