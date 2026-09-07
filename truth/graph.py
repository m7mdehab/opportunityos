"""Deterministic in-memory graph for truth, capability, and provenance nodes."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
import re
from types import MappingProxyType
from typing import Any, TypeAlias

from .models import (
    CANONICAL_MATERIAL_MANIFEST,
    Achievement,
    ApprovedPhrase,
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
    Identity,
    LanguageRecord,
    MaterialFieldSpec,
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


_IDENTITY_SENSITIVE_PREDICATES = frozenset({
    "employment.title",
    "employment.market_facing_title",
    "employment.organization",
    "certification.name",
    "certification.issuer",
    "work_authorization.status",
    "work_authorization.jurisdiction",
})


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
        if rec_pred and predicate and rec_pred != predicate and not (predicate and predicate.endswith(f".{rec_pred}")):
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

        # Structural / Scoped Admission for Identity-Sensitive Predicates
        if predicate in _IDENTITY_SENSITIVE_PREDICATES:
            field_suffix = predicate.split(".")[-1]

            # 1. Exact scalar match: the entire record content IS the exact value
            if content.strip().casefold() == val_lower:
                return True

            # 2. Explicit metadata scope:
            if record.metadata:
                meta_val = (
                    record.metadata.get(field_suffix)
                    or (record.metadata.get("value") if record.metadata.get("predicate") == predicate else None)
                    or (record.metadata.get("value") if record.metadata.get("field") == field_suffix else None)
                )
                if meta_val is not None:
                    return str(meta_val).strip().casefold() == val_lower

            # 3. Explicit locator scope:
            if record.locator:
                loc = record.locator.casefold()
                loc_matches = (
                    loc == field_suffix
                    or loc.endswith(f".{field_suffix}")
                    or loc.endswith(predicate.casefold())
                    or (field_suffix == "organization" and (loc in {"org", "organization"} or loc.endswith(".org") or loc.endswith(".organization")))
                    or (field_suffix in {"title", "market_facing_title"} and (loc in {"title", "market_facing_title"} or loc.endswith(".title") or loc.endswith(".market_facing_title")))
                    or (predicate.startswith("work_authorization") and (loc in {"auth", "status", "jurisdiction", "work_authorization.status", "work_authorization.jurisdiction"} or loc.endswith(".status") or loc.endswith(".jurisdiction")))
                    or (predicate.startswith("certification") and (loc in {"cert", "name", "issuer", "certification.name", "certification.issuer"} or loc.endswith(".name") or loc.endswith(".issuer")))
                )
                if loc_matches:
                    if val_lower in content_lower:
                        return True
                    val_tokens = _extract_tokens(val_str) - _STOP_WORDS
                    if val_tokens and val_tokens.issubset(_extract_tokens(content)):
                        return True

            # Unscoped prose cannot establish identity-sensitive fields!
            return False

        # For non-identity-sensitive fields
        if predicate == "certification.state":
            if val_lower == "planned":
                if re.search(r"\b(?:plan|planning|planned|pursuing|pursue|candidate|in\s*progress)\b", content_lower):
                    return True
            elif val_lower == "active":
                if re.search(r"\b(?:active|current|certified|completed|passed|licensed|holds?|holder|valid)\b", content_lower):
                    return True
            elif val_lower == "expired":
                if re.search(r"\b(?:expired|inactive|past|former|lapsed)\b", content_lower):
                    return True

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
        full_pat = re.compile(rf"\b{m_name}\s+{value.day},?\s+{value.year}\b|\b{value.day}\s+{m_name}\s+{value.year}\b", re.I)
        if full_pat.search(content):
            return True
        abbr_pat = re.compile(rf"\b{m_abbr}\.?\s+{value.day},?\s+{value.year}\b|\b{value.day}\s+{m_abbr}\.?\s+{value.year}\b", re.I)
        if abbr_pat.search(content):
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


_CLAUSE_SPLIT = re.compile(r"[,;.\n]|\b(?:and|while|whereas|but|although)\b", re.IGNORECASE)


def _get_clause_context(text: str, match_start: int, match_end: int) -> str:
    prev_delims = [m.end() for m in _CLAUSE_SPLIT.finditer(text[:match_start])]
    clause_start = prev_delims[-1] if prev_delims else 0
    next_delim = _CLAUSE_SPLIT.search(text[match_end:])
    clause_end = match_end + next_delim.start() if next_delim else len(text)
    return text[clause_start:clause_end]


def _parse_metrics_with_context(text: str) -> list[tuple[float | int, str, str]]:
    results = []
    metric_pattern = re.compile(
        r"(?<![\w-])(?:(?P<curr>[$€£])\s*)?(?P<val>\d+(?:[.,]\d+)?)(?:[-\s]*(?P<unit>%|[xX]\b|hours?|days?|weeks?|months?|users?|clients?|projects?|tickets?|engagements?|requests?|seconds?|minutes?|USD|EUR|GBP))?",
        re.IGNORECASE,
    )
    for match in metric_pattern.finditer(text):
        curr = match.group("curr") or ""
        val_str = match.group("val").replace(",", "")
        unit = (match.group("unit") or curr or "count").strip().casefold()
        digits = re.sub(r"\D", "", val_str)
        if re.fullmatch(r"(?:19|20)\d{2}", digits) and unit == "count":
            continue
        try:
            val_num = float(val_str) if "." in val_str else int(val_str)
            ctx = _get_clause_context(text, match.start(), match.end())
            results.append((val_num, unit, ctx))
        except ValueError:
            continue
    return results


_UNIT_EQUIVALENCE_CLASSES: tuple[frozenset[str], ...] = (
    frozenset({"%", "percent", "percentage", "pct"}),
    frozenset({"$", "usd", "dollar", "dollars"}),
    frozenset({"€", "eur", "euro", "euros"}),
    frozenset({"£", "gbp", "pound", "pounds"}),
    frozenset({"h", "hr", "hrs", "hour", "hours"}),
    frozenset({"d", "day", "days"}),
    frozenset({"wk", "wks", "week", "weeks"}),
    frozenset({"mo", "mos", "month", "months"}),
    frozenset({"yr", "yrs", "year", "years"}),
    frozenset({"min", "mins", "minute", "minutes"}),
    frozenset({"s", "sec", "secs", "second", "seconds"}),
    frozenset({"user", "users"}),
    frozenset({"client", "clients"}),
    frozenset({"project", "projects"}),
    frozenset({"ticket", "tickets"}),
    frozenset({"request", "requests"}),
    frozenset({"engagement", "engagements"}),
    frozenset({"engineer", "engineers"}),
    frozenset({"member", "members"}),
    frozenset({"team", "teams"}),
    frozenset({"count", "item", "items", "unit", "units"}),
    frozenset({"x", "times", "fold"}),
)


def _canonical_unit_class(unit: str) -> frozenset[str] | None:
    u = unit.strip().casefold()
    for eq_class in _UNIT_EQUIVALENCE_CLASSES:
        if u in eq_class:
            return eq_class
    if u.endswith("s") and len(u) > 3:
        singular = u[:-1]
        for eq_class in _UNIT_EQUIVALENCE_CLASSES:
            if singular in eq_class:
                return eq_class
        return frozenset({u, singular})
    return frozenset({u, f"{u}s"})


def _units_compatible(unit_a: str, unit_b: str, ev_ctx: str = "") -> bool:
    ua = unit_a.strip().casefold()
    ub = unit_b.strip().casefold()
    if ua == ub:
        return True
    class_a = _canonical_unit_class(ua)
    class_b = _canonical_unit_class(ub)
    if class_a is not None and class_b is not None:
        return class_a == class_b
    return False


_INCREASE_WORDS = frozenset({"increased", "increase", "increasing", "growth", "grew", "boosted", "boost", "rose", "rise", "rising"})
_DECREASE_WORDS = frozenset({"decreased", "decrease", "decreasing", "fell", "fall", "fallen", "falling", "dropped", "drop", "dropping", "reduced", "reduce", "reducing", "reduction", "cut", "saved", "savings"})

_GENERIC_METRIC_FILLER = frozenset({
    "a", "an", "and", "or", "of", "in", "at", "to", "for", "with", "on", "by", "from",
    "the", "is", "was", "were", "as", "into", "onto", "via", "using", "that", "this",
    "these", "those", "over", "under", "than", "per", "about", "approximately", "nearly",
    "roughly", "around", "least", "most", "up", "such",
    "increased", "increase", "increasing", "decreased", "decrease", "decreasing",
    "fell", "fall", "fallen", "falling", "dropped", "drop", "dropping",
    "reduced", "reduce", "reducing", "reduction", "improved", "improve", "improving", "improvement",
    "grew", "grow", "growing", "growth", "cut", "cutting", "boosted", "boost", "boosting",
    "rose", "rise", "rising", "saved", "save", "saving", "savings",
    "built", "delivered", "processed", "managed", "generated", "achieved", "attained",
    "scaled", "handled", "led", "served", "earned", "made", "spent",
    "%", "percent", "percentage", "pct", "usd", "eur", "gbp", "count", "hour", "hours",
    "day", "days", "week", "weeks", "month", "months", "year", "years",
})


def _metric_contexts_compatible(metric_ctx: str, ev_ctx: str, num_val: float | int) -> bool:
    if not metric_ctx or not metric_ctx.strip():
        return False
    if not ev_ctx or not ev_ctx.strip():
        return False

    metric_tokens_all = _extract_tokens(metric_ctx)
    ev_tokens_all = _extract_tokens(ev_ctx)

    metric_has_inc = bool(metric_tokens_all & _INCREASE_WORDS)
    metric_has_dec = bool(metric_tokens_all & _DECREASE_WORDS)
    ev_has_inc = bool(ev_tokens_all & _INCREASE_WORDS)
    ev_has_dec = bool(ev_tokens_all & _DECREASE_WORDS)

    if metric_has_inc and ev_has_dec and not (metric_has_dec or ev_has_inc):
        return False
    if metric_has_dec and ev_has_inc and not (metric_has_inc or ev_has_dec):
        return False

    num_str = str(int(num_val) if isinstance(num_val, (int, float)) and float(num_val).is_integer() else num_val).casefold()
    metric_substantive = metric_tokens_all - _GENERIC_METRIC_FILLER - {num_str}
    ev_substantive = ev_tokens_all - _GENERIC_METRIC_FILLER - {num_str}

    if metric_substantive:
        for tok in metric_substantive:
            if tok not in ev_tokens_all and not any(tok in ev_tok or ev_tok in tok for ev_tok in ev_tokens_all):
                return False
        return True

    if ev_substantive and not metric_substantive:
        return False

    metric_non_stop = metric_tokens_all - _STOP_WORDS - {num_str}
    ev_non_stop = ev_tokens_all - _STOP_WORDS - {num_str}
    return bool(metric_non_stop & ev_non_stop)


def _is_subject_proven_for_metric(metric: MetricAssertion, record: EvidenceRecord, graph: TruthGraph | None = None) -> bool:
    if not metric.subject_id:
        return True

    # A. Evidence metadata explicitly naming subject_id
    if record.metadata:
        rec_subj = record.metadata.get("subject_id") or record.metadata.get("subject")
        if rec_subj and str(rec_subj) == str(metric.subject_id):
            return True
        if metric.subject_id in record.metadata:
            return True

    # B. Locator explicitly naming that exact subject/entity
    if record.locator:
        loc = record.locator.strip()
        if loc == metric.subject_id:
            return True
        if loc.startswith(f"{metric.subject_id}.") or loc.endswith(f".{metric.subject_id}"):
            return True
        parts = loc.split(".")
        if metric.subject_id in parts:
            return True

    # C. Graph entity -> evidence binding
    if graph is not None:
        if metric.subject_id in graph._entity_evidence:
            if record.id in graph._entity_evidence[metric.subject_id]:
                return True
        if metric.subject_id in graph._entities:
            entity = graph._entities[metric.subject_id]
            if hasattr(entity, "evidence_ids") and record.id in entity.evidence_ids:
                return True

    # D. An existing graph assertion/relation that explicitly binds that exact subject to the evidence
    if graph is not None:
        for as_node in graph._assertions.values():
            if as_node.subject_id == metric.subject_id and record.id in as_node.evidence_ids:
                return True
        for rel in graph._relations.values():
            if (rel.source_id == metric.subject_id or rel.target_id == metric.subject_id) and record.id in rel.evidence_ids:
                return True
        if hasattr(graph, "_pending_relations"):
            for rel in graph._pending_relations:
                if (rel.source_id == metric.subject_id or rel.target_id == metric.subject_id) and record.id in rel.evidence_ids:
                    return True

    return False


def _single_record_supports_metric(metric: MetricAssertion, record: EvidenceRecord, graph: TruthGraph | None = None) -> bool:
    if record.verification_status is VerificationStatus.UNVERIFIED or record.verification_status is VerificationStatus.EXPLICIT_NULL:
        return False
    if record.verification_status is VerificationStatus.APPROXIMATE and metric.modality is Modality.DEFINITE:
        return False
    if not record.content or not record.content.strip():
        return False

    if not _is_subject_proven_for_metric(metric, record, graph):
        return False

    if record.metadata:
        rec_subj = record.metadata.get("subject_id") or record.metadata.get("subject")
        if rec_subj and metric.subject_id and rec_subj != metric.subject_id:
            return False
        rec_val = record.metadata.get("numeric_value") or record.metadata.get("value")
        if rec_val is not None:
            try:
                if float(rec_val) != float(metric.numeric_value):
                    return False
            except (ValueError, TypeError):
                return False
        rec_unit = record.metadata.get("unit")
        if rec_unit is not None and not _units_compatible(metric.unit, str(rec_unit), record.content):
            return False
        rec_ctx = record.metadata.get("context")
        if rec_ctx is not None and not _metric_contexts_compatible(metric.context, str(rec_ctx), metric.numeric_value):
            return False

    parsed = _parse_metrics_with_context(record.content)
    for ev_val, ev_unit, ev_ctx in parsed:
        val_match = False
        try:
            val_match = float(ev_val) == float(metric.numeric_value)
        except (ValueError, TypeError):
            pass
        if not val_match:
            continue
        if not _units_compatible(metric.unit, ev_unit, ev_ctx):
            continue
        if not _metric_contexts_compatible(metric.context, ev_ctx, metric.numeric_value):
            continue
        if _BOUND_AT_MOST.search(ev_ctx) and metric.modality in {Modality.DEFINITE, Modality.AT_LEAST}:
            continue
        if _CONDITIONAL.search(ev_ctx) and metric.modality is Modality.DEFINITE:
            continue
        return True

    return False


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
        self._identity: Identity | None = None
        self._approved_phrases: dict[str, ApprovedPhrase] = {}

        self._pending_relations = tuple(relations)
        for record in evidence:
            self.add_evidence(record)
        for assertion in assertions:
            self.add_assertion(assertion)
        for metric in metrics:
            self.add_metric_assertion(metric)
        for relation in relations:
            self.add_relation(relation)
        self._pending_relations = ()

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

    @property
    def identity(self):
        """The founder's identity block, or None if the pack carries none."""
        return self._identity

    @property
    def approved_phrases(self):
        return MappingProxyType(self._approved_phrases)

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
            if not _is_value_supported_by_evidence(
                assertion.value,
                evidence_records,
                predicate=assertion.predicate,
                subject_id=assertion.subject_id,
            ):
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
            existing = self._metrics[metric.id]
            if existing.verification_status is not MetricVerification.UNAVAILABLE:
                raise ValueError(f"duplicate metric assertion id: {metric.id}")
        else:
            self._check_id_collision(metric.id)

        for ev_id in metric.evidence_ids:
            if ev_id not in self._evidence:
                raise ValueError(f"metric assertion {metric.id} references unknown evidence: {ev_id}")

        evidence_records = tuple(self._evidence[ev_id] for ev_id in metric.evidence_ids)
        if metric.verification_status is MetricVerification.VERIFIED:
            if not evidence_records:
                raise ValueError(f"metric assertion {metric.id} is VERIFIED but has no evidence")
            if any(r.verification_status is VerificationStatus.UNVERIFIED for r in evidence_records):
                raise ValueError(f"metric assertion {metric.id} cannot be VERIFIED when supported by UNVERIFIED evidence")
            if not any(_single_record_supports_metric(metric, r, graph=self) for r in evidence_records):
                raise ValueError(
                    f"metric assertion {metric.id} (value={metric.numeric_value}, unit={metric.unit}, context={metric.context!r}) "
                    f"is not supported by evidence {metric.evidence_ids}"
                )

        self._metrics[metric.id] = metric

    def add_career_profile(self, profile: CareerProfile) -> None:
        self._add_profile(profile)

    def add_capability_profile(self, profile: CapabilityProfile) -> None:
        self._add_profile(profile)

    def add_identity(self, identity: Identity) -> None:
        """Add the pack's (singleton) identity block, projected like any
        other entity per `CANONICAL_MATERIAL_MANIFEST`."""
        if self._identity is not None:
            raise ValueError("duplicate identity: only one identity section is permitted per pack")
        self._check_id_collision(identity.id)

        missing = sorted(set(identity.evidence_ids) - set(self._evidence))
        if missing:
            raise ValueError(f"identity references unknown evidence: {', '.join(missing)}")

        links = {identity.id: identity.evidence_ids}
        self._validate_entity_manifest(identity, links)

        self._entities[identity.id] = identity
        self._entity_evidence[identity.id] = identity.evidence_ids
        for ev_id in identity.evidence_ids:
            self._evidence_entities.setdefault(ev_id, []).append(identity.id)

        self._project_entity_manifest(identity)
        self._identity = identity

    def add_approved_phrase(self, phrase: ApprovedPhrase) -> None:
        """Add one founder-authored approved phrase, projected like any other
        entity per `CANONICAL_MATERIAL_MANIFEST`."""
        if phrase.id in self._approved_phrases:
            raise ValueError(f"duplicate approved_phrase id: {phrase.id}")
        self._check_id_collision(phrase.id)

        missing = sorted(set(phrase.evidence_ids) - set(self._evidence))
        if missing:
            raise ValueError(f"approved_phrase {phrase.id} references unknown evidence: {', '.join(missing)}")

        links = {phrase.id: phrase.evidence_ids}
        self._validate_entity_manifest(phrase, links)

        self._entities[phrase.id] = phrase
        self._entity_evidence[phrase.id] = phrase.evidence_ids
        for ev_id in phrase.evidence_ids:
            self._evidence_entities.setdefault(ev_id, []).append(phrase.id)

        self._project_entity_manifest(phrase)
        self._approved_phrases[phrase.id] = phrase

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

    def _validate_profile_field_provenance(
        self,
        profile: Profile,
        links: dict[str, tuple[str, ...]],
        manifest: tuple[MaterialFieldSpec, ...] = CANONICAL_MATERIAL_MANIFEST,
    ) -> None:
        self._validate_entity_manifest(profile, links, manifest=manifest)

    def _validate_entity_manifest(
        self,
        entity: Any,
        links: dict[str, tuple[str, ...]],
        manifest: tuple[MaterialFieldSpec, ...] = CANONICAL_MATERIAL_MANIFEST,
    ) -> None:
        entity_cls = type(entity)
        entity_id = getattr(entity, "id", None)
        entity_ev_ids = links.get(entity_id, ()) if entity_id else ()
        entity_evs = tuple(self._evidence[ev_id] for ev_id in entity_ev_ids if ev_id in self._evidence)

        specs = [s for s in manifest if s.model_cls is entity_cls]
        for spec in specs:
            if not hasattr(entity, spec.field_name):
                continue
            val = getattr(entity, spec.field_name)
            if spec.is_nested_entity:
                if val:
                    children = val if isinstance(val, (tuple, list)) else (val,)
                    for child in children:
                        self._validate_entity_manifest(child, links, manifest=manifest)
                continue

            if val is None or val == () or val == []:
                if not spec.optional:
                    raise ValueError(f"field {spec.predicate} is required on {entity_id}")
                continue

            if spec.is_collection:
                items = val if isinstance(val, (tuple, list, set, frozenset)) else (val,)
                for item in items:
                    item_val = item.value if hasattr(item, "value") else item
                    if not _is_value_supported_by_evidence(item_val, entity_evs, predicate=spec.predicate, subject_id=entity_id):
                        raise ValueError(f"field {spec.predicate} '{item_val}' is not supported by evidence: {', '.join(entity_ev_ids)}")
            else:
                field_val = val.value if hasattr(val, "value") else val
                if not _is_value_supported_by_evidence(field_val, entity_evs, predicate=spec.predicate, subject_id=entity_id):
                    raise ValueError(f"field {spec.predicate} '{field_val}' is not supported by evidence: {', '.join(entity_ev_ids)}")

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

    def _project_profile_assertions(
        self,
        profile: Profile,
        manifest: tuple[MaterialFieldSpec, ...] = CANONICAL_MATERIAL_MANIFEST,
    ) -> None:
        self._project_entity_manifest(profile, manifest=manifest)

    def _project_entity_manifest(
        self,
        entity: Any,
        manifest: tuple[MaterialFieldSpec, ...] = CANONICAL_MATERIAL_MANIFEST,
    ) -> None:
        entity_cls = type(entity)
        entity_id = getattr(entity, "id", None)
        entity_ev_ids = getattr(entity, "evidence_ids", ())

        eff_from = getattr(entity, "start_date", None) or getattr(entity, "issued_date", None) or getattr(entity, "available_from", None)
        eff_to = getattr(entity, "end_date", None) or getattr(entity, "expiry_date", None)

        force_modality = None
        if isinstance(entity, CertificationRecord):
            force_modality = Modality.PLANNED if entity.state is CertificationState.PLANNED else Modality.DEFINITE

        default_as_type = AssertionType.DERIVED_CAPABILITY if isinstance(entity, (CapabilityProfile, ServiceRecord)) else AssertionType.DIRECT_FACT

        specs = [s for s in manifest if s.model_cls is entity_cls]
        for spec in specs:
            if not hasattr(entity, spec.field_name):
                continue
            val = getattr(entity, spec.field_name)
            if spec.is_nested_entity:
                if val:
                    children = val if isinstance(val, (tuple, list)) else (val,)
                    for child in children:
                        self._project_entity_manifest(child, manifest=manifest)
                        if isinstance(entity, EmploymentRecord) and isinstance(child, Achievement):
                            self._wire_employment_achievement_relation(entity, child)
                continue

            if val is None or val == () or val == []:
                # Project explicit null if evidence is EXPLICIT_NULL
                if any(self._evidence.get(ev_id) and self._evidence[ev_id].verification_status is VerificationStatus.EXPLICIT_NULL for ev_id in entity_ev_ids):
                    self._project_field_assertion(
                        subject_id=entity_id or spec.predicate,
                        predicate=spec.predicate,
                        value=None,
                        evidence_ids=entity_ev_ids,
                        default_assertion_type=default_as_type,
                        force_modality=force_modality,
                        effective_from=eff_from,
                        effective_to=eff_to,
                    )
                continue

            predicate = spec.predicate
            if isinstance(entity, SkillRecord) and entity_id and entity_id.startswith("tool"):
                predicate = predicate.replace("skill.", "tool.")

            if spec.is_collection:
                items = val if isinstance(val, (tuple, list, set, frozenset)) else (val,)
                for idx, item in enumerate(items):
                    item_val = item.value if hasattr(item, "value") else item
                    self._project_field_assertion(
                        subject_id=entity_id or predicate,
                        predicate=predicate,
                        value=item_val,
                        evidence_ids=entity_ev_ids,
                        default_assertion_type=default_as_type,
                        force_modality=force_modality,
                        effective_from=eff_from,
                        effective_to=eff_to,
                    )
            else:
                field_val = val.value if hasattr(val, "value") else val
                self._project_field_assertion(
                    subject_id=entity_id or predicate,
                    predicate=predicate,
                    value=field_val,
                    evidence_ids=entity_ev_ids,
                    default_assertion_type=default_as_type,
                    force_modality=force_modality,
                    effective_from=eff_from,
                    effective_to=eff_to,
                )

        if isinstance(entity, Achievement):
            self._extract_metrics_from_text(entity.id, entity.statement, entity.evidence_ids, entity.metric_verification)
        elif isinstance(entity, PortfolioItem):
            self._extract_metrics_from_text(entity.id, entity.summary, entity.evidence_ids, entity.metric_verification)
            if entity.outcome:
                self._extract_metrics_from_text(entity.id, entity.outcome, entity.evidence_ids, entity.metric_verification)

    def _wire_employment_achievement_relation(self, emp: EmploymentRecord, ach: Achievement) -> None:
        rel_id = f"rel_{emp.id}_{ach.id}"
        if rel_id not in self._relations:
            ach_evs = tuple(self._evidence[ev_id] for ev_id in ach.evidence_ids if ev_id in self._evidence)
            establishes_rel = any(
                _single_record_supports_value(emp.organization, r, predicate="employment.organization", subject_id=emp.id) for r in ach_evs
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
        val_str = str(value) if value is not None else "null"
        assertion_id = f"as_{subject_id}_{predicate.replace('.', '_')}_{val_str.replace(' ', '_')[:32]}"
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
        verification: MetricVerification = MetricVerification.UNAVAILABLE,
    ) -> None:
        metric_pattern = re.compile(
            r"(?<![\w-])(?:(?P<curr>[$€£])\s*)?(?P<val>\d+(?:[.,]\d+)?)(?:[-\s]*(?P<unit>%|[xX]\b|hours?|days?|weeks?|months?|users?|clients?|projects?|tickets?|engagements?|requests?|seconds?|minutes?|USD|EUR|GBP))?",
            re.IGNORECASE,
        )
        matches = list(metric_pattern.finditer(text))

        for idx, match in enumerate(matches):
            curr = match.group("curr") or ""
            val_str = match.group("val").replace(",", "")
            unit = (match.group("unit") or curr or "count").strip()
            try:
                num_val = float(val_str) if "." in val_str else int(val_str)
            except ValueError:
                continue

            # Candidate metric assertions created during auto-extraction ALWAYS default to UNAVAILABLE.
            # A metric becomes VERIFIED ONLY via an explicit MetricAssertion added to the graph.
            metric_status = MetricVerification.UNAVAILABLE

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

