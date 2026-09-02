from datetime import date
from pathlib import Path
import re
from collections.abc import Iterable

from .graph import TruthGraph, _units_compatible, _metric_contexts_compatible
from .models import (
    AssertionType,
    AtomicAssertion,
    CertificationState,
    ClaimCandidate,
    ClaimVerificationResult,
    MetricVerification,
    Modality,
    NeverClaimRule,
    Polarity,
    ProhibitedConceptCategory,
    RedLineRule,
    VerificationStatus,
)


_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[\w+#]+", re.UNICODE)
_METRIC = re.compile(
    r"(?<![\w-])(?:[$€£]\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*[xX]\b|\s*(?:hours?|days?|weeks?|months?|users?|clients?|projects?|requests?|seconds?|minutes?))?",
    re.IGNORECASE,
)
_APPROXIMATION = re.compile(r"\b(?:about|approximately|approx\.?|around|roughly|nearly|circa)\b", re.I)
_PLANNING = re.compile(r"\b(?:plan(?:ned|ning)?|pursu(?:e|ing)|intend(?:ed|ing)?|prepar(?:e|ing)|aspir(?:e|ing)|candidate)\b", re.I)
_HELD = re.compile(r"\b(?:certified|credentialed|hold(?:s|ing)?|earned|obtained|completed|awarded)\b", re.I)
_NON_MATERIAL_WORDS = {
    "a", "an", "and", "or", "the", "is", "was", "were", "are", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "as", "at", "by", "for", "from", "in",
    "into", "of", "on", "onto", "to", "with", "uses", "used", "using", "that", "this",
    "these", "those", "approximately", "about", "around", "nearly", "roughly", "such",
    "over", "under", "more", "less", "than", "per", "we", "i", "he", "she", "they", "our",
    "served", "serves", "serving", "works", "worked", "working", "offers", "offered", "offering",
}


_CONNECTIVE_TERMS_PATH = Path(__file__).with_name("connective_terms.txt")


def _load_connective_terms(path: Path) -> frozenset[str]:
    """Load the committed class-(c) connective-boilerplate stop-list.

    Blank lines and lines starting with ``#`` are comments/documentation
    (see the file itself for why each entry is factually weightless). Every
    other line is exactly one lower-case word. Loaded once at import.
    """
    terms: set[str] = set()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        terms.add(stripped.casefold())
    return frozenset(terms)


CONNECTIVE_TERMS: frozenset[str] = _load_connective_terms(_CONNECTIVE_TERMS_PATH)


def opportunity_terms_from_values(*values: str | None) -> set[str]:
    """Build the class-(b) opportunity-provenanced term set from real field values.

    The CALLER (e.g. `api/routes_api.py::_compile_and_export`) is responsible
    for passing only actual `Opportunity` field values that carry their own
    field provenance (employer name, role title, ...) -- this function only
    tokenizes whatever it is given. It never inspects a claim or an
    opportunity object itself, so it cannot be used to launder an arbitrary
    word into admissibility: the validator only ever excuses a token that is
    literally present in a value the caller asserts is real opportunity data.
    """
    terms: set[str] = set()
    for value in values:
        if not value:
            continue
        terms.update(_tokens(_normalize(str(value))))
    return terms - _NON_MATERIAL_WORDS


_NEGATIVE_MARKERS = re.compile(
    r"\b(?:not|no|never|neither|nor|without|cannot|unauthorized|non-|ineligible|lacks?|lacking)\b",
    re.I,
)
_BOUND_AT_MOST = re.compile(r"\b(?:at\s*most|up\s*to|less\s*than|under|maximum\s*of|no\s*more\s*than)\b", re.I)
_BOUND_AT_LEAST = re.compile(r"\b(?:at\s*least|more\s*than|over|minimum\s*of|no\s*less\s*than)\b", re.I)
_CONDITIONAL = re.compile(r"\b(?:subject\s*to|conditional\s*(?:on|upon)|depending\s*on|if\s*approved|contingent\s*on)\b", re.I)
_EXACT = re.compile(r"\b(?:exactly|strictly|precisely)\b", re.I)


def _normalize(value: str) -> str:
    return _SPACE.sub(" ", value.strip().casefold())


def _tokens(value: str) -> set[str]:
    return {match.group(0).casefold() for match in _WORD.finditer(value)}


def _parse_structured_metrics(text: str) -> list[tuple[float | int, str]]:
    return [(num, unit) for num, unit, _ in _parse_structured_metrics_with_context(text)]


_CLAUSE_SPLIT = re.compile(r"[,;.\n]|\b(?:and|while|whereas|but|although)\b", re.IGNORECASE)


def _get_clause_context(text: str, match_start: int, match_end: int) -> str:
    prev_delims = [m.end() for m in _CLAUSE_SPLIT.finditer(text[:match_start])]
    clause_start = prev_delims[-1] if prev_delims else 0
    next_delim = _CLAUSE_SPLIT.search(text[match_end:])
    clause_end = match_end + next_delim.start() if next_delim else len(text)
    return text[clause_start:clause_end]


def _parse_structured_metrics_with_context(text: str) -> list[tuple[float | int, str, str]]:
    results = []
    metric_pattern = re.compile(
        r"(?<![\w-])(?:(?P<curr>[$€£])\s*)?(?P<val>\d+(?:[.,]\d+)?)(?:\s*(?P<unit>%|[xX]\b|hours?|days?|weeks?|months?|users?|clients?|projects?|engagements?|requests?|seconds?|minutes?|USD|EUR|GBP))?",
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
            ctx = _get_clause_context(text, match.start(), match.end()).strip()
            results.append((val_num, unit, ctx))
        except ValueError:
            continue
    return results


def _material_metrics(value: str) -> tuple[str, ...]:
    metrics = []
    for num, unit in _parse_structured_metrics(value):
        metrics.append(f"{num}{unit}")
    return tuple(metrics)


def _clean_text_for_matching(value: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return _SPACE.sub(" ", cleaned.strip().casefold())


class ClaimValidator:
    """Enforce evidence, metric, credential, red-line, and never-claim rules."""

    def __init__(self, graph: TruthGraph) -> None:
        self.graph = graph

    def validate_candidate(self, candidate: ClaimCandidate) -> ClaimVerificationResult:
        """Validate a structured ClaimCandidate before or during free-text generation."""
        if not isinstance(candidate, ClaimCandidate):
            raise ValueError("candidate must be a ClaimCandidate")

        # 1. Structured Never-Claim policy evaluation: intersect candidate concepts with prohibited categories
        red_lines, never_claims = self.graph.rules()
        prohibited_categories = {rule.concept for rule in never_claims if isinstance(rule, NeverClaimRule)}
        prohibited_intersection = candidate.concepts & prohibited_categories
        if prohibited_intersection:
            prohibited_names = ", ".join(sorted(c.value for c in prohibited_intersection))
            return self._result(
                candidate.text, False, AssertionType.PROHIBITED_CLAIM,
                VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                (f"candidate asserts prohibited concept category: {prohibited_names}",),
            )

        # 2. Structural Policy Check: Autonomous factual candidates MUST specify material_assertion_ids
        if not candidate.material_assertion_ids:
            return self._result(
                candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                ("autonomous claim candidate must specify material_assertion_ids",),
            )

        # 3. Field-level atomic assertion verification & active state resolution
        supporting_assertion_evidence = []
        assertion_values = []
        active_set = set(self.graph.active_assertions(candidate.as_of))

        for as_id in candidate.material_assertion_ids:
            if as_id not in self.graph.assertions:
                return self._result(
                    candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                    VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                    (f"unknown atomic assertion: {as_id}",),
                )
            assertion = self.graph.assertions[as_id]

            # Check if active in graph as of candidate.as_of
            if assertion not in active_set:
                if assertion.conflicts_with:
                    return self._result(
                        candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                        (f"assertion {as_id} has unresolved conflicts: {', '.join(assertion.conflicts_with)}",),
                    )
                if candidate.as_of is not None and assertion.effective_to and candidate.as_of > assertion.effective_to:
                    return self._result(
                        candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                        (f"assertion {as_id} expired on {assertion.effective_to} as of {candidate.as_of}",),
                    )
                return self._result(
                    candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                    VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                    (f"assertion {as_id} is inactive / superseded as of {candidate.as_of}",),
                )

            supporting_assertion_evidence.extend(assertion.evidence_ids)
            if assertion.value is not None:
                assertion_values.append(str(assertion.value))

            # Polarity check
            if assertion.polarity is Polarity.NEGATIVE and not _NEGATIVE_MARKERS.search(candidate.text):
                return self._result(
                    candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                    VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                    (f"assertion {as_id} has negative polarity but candidate text is positive",),
                )

            # Modality checks
            if assertion.modality is Modality.AT_MOST:
                if not _BOUND_AT_MOST.search(candidate.text) or _EXACT.search(candidate.text) or _BOUND_AT_LEAST.search(candidate.text):
                    return self._result(
                        candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                        (f"assertion {as_id} has AT_MOST modality and candidate text cannot strengthen it to exact or lower bound",),
                    )

            if assertion.modality is Modality.APPROXIMATE:
                if _EXACT.search(candidate.text) or not _APPROXIMATION.search(candidate.text):
                    return self._result(
                        candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                        (f"assertion {as_id} has APPROXIMATE modality and candidate text cannot claim exact value",),
                    )

            if assertion.modality is Modality.CONDITIONAL:
                if not _CONDITIONAL.search(candidate.text):
                    return self._result(
                        candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                        (f"assertion {as_id} has CONDITIONAL modality and candidate text cannot claim unconditional fact",),
                    )

            if assertion.modality is Modality.PLANNED:
                if _HELD.search(candidate.text) or not _PLANNING.search(candidate.text):
                    return self._result(
                        candidate.text, False, AssertionType.PROHIBITED_CLAIM,
                        VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                        (f"assertion {as_id} has planned modality and cannot be represented as held",),
                    )

        authorized_evidence = set(supporting_assertion_evidence)

        # 4. Check requested_evidence_ids is strictly authorized by selected material assertions
        if candidate.requested_evidence_ids:
            unauthorized = set(candidate.requested_evidence_ids) - authorized_evidence
            if unauthorized:
                return self._result(
                    candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                    VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                    (f"requested evidence '{', '.join(sorted(unauthorized))}' is not authorized by the selected material assertions",),
                )

        evidence_ids = candidate.requested_evidence_ids or tuple(dict.fromkeys(supporting_assertion_evidence))

        # 5. Check that candidate text is authorized by the selected assertions (NOT arbitrary unasserted evidence text)
        candidate_material_tokens = _tokens(_normalize(candidate.text)) - _NON_MATERIAL_WORDS
        authorized_assertion_tokens = set()
        for as_id in candidate.material_assertion_ids:
            assertion = self.graph.assertions[as_id]
            if assertion.value is not None:
                authorized_assertion_tokens.update(_tokens(_normalize(str(assertion.value))) - _NON_MATERIAL_WORDS)
            authorized_assertion_tokens.update(_tokens(_normalize(assertion.predicate)) - _NON_MATERIAL_WORDS)
            authorized_assertion_tokens.update(_tokens(_normalize(assertion.subject_id)) - _NON_MATERIAL_WORDS)
            for qual in assertion.qualifiers:
                authorized_assertion_tokens.update(_tokens(_normalize(qual)) - _NON_MATERIAL_WORDS)
            if assertion.predicate.startswith("skill.") or assertion.predicate.startswith("tool."):
                from .ingest import CANONICAL_SKILL_ALIASES
                val_key = str(assertion.value).casefold()
                if val_key in CANONICAL_SKILL_ALIASES:
                    authorized_assertion_tokens.update(_tokens(_normalize(CANONICAL_SKILL_ALIASES[val_key])) - _NON_MATERIAL_WORDS)

        unauthorized_tokens = candidate_material_tokens - authorized_assertion_tokens
        if unauthorized_tokens:
            return self._result(
                candidate.text, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED, candidate.requested_evidence_ids,
                (f"candidate text contains facts not authorized by the selected material assertions: {', '.join(sorted(unauthorized_tokens))}",),
            )

        selected_subjects = {
            self.graph.assertions[as_id].subject_id
            for as_id in candidate.material_assertion_ids
            if as_id in self.graph.assertions
        }
        return self.validate_claim(candidate.text, evidence_ids, as_of=candidate.as_of, allowed_subject_ids=selected_subjects)

    def validate_claim(
        self,
        claim: str,
        evidence_ids: Iterable[str] | None = None,
        *,
        as_of: date | None = None,
        allowed_subject_ids: set[str] | None = None,
        opportunity_terms: set[str] | None = None,
    ) -> ClaimVerificationResult:
        if not isinstance(claim, str) or not claim.strip():
            raise ValueError("claim must be a non-empty string")
        claim = _SPACE.sub(" ", claim.strip())

        # 1. Never-Claim policy and Red Lines evaluate FIRST and override evidence eligibility.
        prohibited_reasons = self._prohibited_reasons(claim)
        if prohibited_reasons:
            return self._result(
                claim, False, AssertionType.PROHIBITED_CLAIM,
                VerificationStatus.UNVERIFIED, (), prohibited_reasons,
            )

        # 2. Planned credentials cannot be represented as held.
        credential_reasons = self._planned_credential_reasons(claim)
        if credential_reasons:
            return self._result(
                claim, False, AssertionType.PROHIBITED_CLAIM,
                VerificationStatus.UNVERIFIED, (), credential_reasons,
            )

        # 3. Resolve requested evidence.
        requested = tuple(dict.fromkeys(evidence_ids or ()))
        unknown = tuple(item for item in requested if item not in self.graph.evidence_records)
        if unknown:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED, (),
                (f"unknown evidence: {', '.join(unknown)}",),
            )

        candidates = (
            tuple(self.graph.evidence(item) for item in requested)
            if requested
            else tuple(self.graph.evidence_records.values())
        )

        # 4. Polarity and Modality bounds safety on candidate/requested evidence
        for record in candidates:
            if record.content:
                if _NEGATIVE_MARKERS.search(record.content) and not _NEGATIVE_MARKERS.search(claim):
                    return self._result(
                        claim, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, requested or (record.id,),
                        ("claim inverts negative evidence polarity into a positive assertion",),
                    )
                if _BOUND_AT_MOST.search(record.content) and (_BOUND_AT_LEAST.search(claim) or _EXACT.search(claim)):
                    return self._result(
                        claim, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, requested or (record.id,),
                        ("claim strengthens upper-bound modality to exact or lower-bound",),
                    )
                if _CONDITIONAL.search(record.content) and not _CONDITIONAL.search(claim):
                    return self._result(
                        claim, False, AssertionType.UNSUPPORTED_CLAIM,
                        VerificationStatus.UNVERIFIED, requested or (record.id,),
                        ("claim strengthens conditional evidence to unconditional assertion",),
                    )

        # 5. Find supporting evidence records.
        # Prefer single records that cover all material terms of the claim.
        full_matches = []
        claim_material_tokens = _tokens(claim) - _NON_MATERIAL_WORDS
        for record in candidates:
            if record.content:
                rec_tokens = _tokens(record.content)
                if claim_material_tokens and claim_material_tokens <= rec_tokens:
                    full_matches.append(record)

        if full_matches:
            supporting = tuple(full_matches)
        else:
            supporting = tuple(record for record in candidates if self._supports(record.content, claim))

        if not supporting:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED, (),
                ("no evidence record supports the material claim",),
            )

        supporting_ids = tuple(record.id for record in supporting)

        # 6. Temporal validity as-of evaluation
        if as_of is not None:
            temporal_reason = self._validate_temporal_validity(claim, supporting, as_of)
            if temporal_reason:
                return self._result(
                    claim, False, AssertionType.UNSUPPORTED_CLAIM,
                    VerificationStatus.UNVERIFIED, supporting_ids,
                    (temporal_reason,),
                )

        # 8. Relational composition guard:
        # Cross-evidence relationship laundering is prevented.
        # If multiple evidence records are required to cover the claim, they MUST be relationally linked
        # by an explicit common entity node or TypedRelation in the TruthGraph.
        if len(supporting) > 1 and not self.graph.are_relationally_linked(supporting_ids):
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED, supporting_ids,
                ("composite claim combines independent evidence records without an establishing graph relation",),
            )

        # 9. Material lexical coverage check.
        #
        # Three term classes are recognised (ADR-0014). Only class (a) --
        # founder-claim terms, i.e. anything not covered below -- can ever
        # cause a rejection here:
        #   (a) founder-claim terms: must be covered by `evidence_tokens`
        #       (the cited, relationally-linked supporting evidence). This is
        #       unchanged from before ADR-0014.
        #   (b) opportunity-provenanced terms: `opportunity_terms`, supplied
        #       explicitly by the CALLER from real `Opportunity` field values
        #       (see `opportunity_terms_from_values`). The validator never
        #       guesses these; it only ever subtracts exactly the tokens the
        #       caller asserts are real opportunity data.
        #   (c) connective boilerplate: `CONNECTIVE_TERMS`, the committed,
        #       fixed stop-list loaded from `truth/connective_terms.txt`.
        # Because (b) and (c) are pure set subtractions applied on top of (a),
        # neither can ever cause a term to be excused unless it is literally
        # a member of that class's fixed vocabulary -- there is no code path
        # by which an arbitrary unsupported founder-specific word can be
        # marked class (b) or (c) to pass; the sets are closed and supplied
        # from a fixed file or from the caller's real field values, never
        # from the claim text itself.
        evidence_tokens = set().union(*(_tokens(record.content or "") for record in supporting))
        admissible_non_founder_terms = CONNECTIVE_TERMS | (opportunity_terms or set())
        uncovered = sorted(_tokens(claim) - evidence_tokens - _NON_MATERIAL_WORDS - admissible_non_founder_terms)
        if uncovered:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                supporting_ids,
                (f"claim contains material terms absent from evidence: {', '.join(uncovered)}",),
            )

        # 10. Verification status resolution: conservative weakest-link rule.
        status = self._resolve_verification_status(supporting, claim)
        if status is None:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                supporting_ids,
                ("supporting evidence is unverified, explicit-null, or approximate without qualification",),
            )

        # 11. Exact metric provenance validation.
        metric_reason = self._validate_metric_provenance(claim, supporting, allowed_subject_ids=allowed_subject_ids)
        if metric_reason:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                supporting_ids, (metric_reason,),
            )

        # 12. Conservative epistemic assertion-type resolution.
        assertion_type = self._resolve_assertion_type(supporting)
        if assertion_type in {AssertionType.UNSUPPORTED_CLAIM, AssertionType.PROHIBITED_CLAIM}:
            return self._result(
                claim, False, assertion_type,
                VerificationStatus.UNVERIFIED,
                supporting_ids, ("claim resolves to unsupported or prohibited assertion type",),
            )

        return self._result(
            claim, True, assertion_type, status,
            supporting_ids, ("claim is traceable to supporting evidence",),
        )

    def validate_narrative(self, text: str) -> ClaimVerificationResult:
        """Validate a NARRATIVE segment (ADR-0014): connective prose that
        asserts no founder-specific fact and therefore cites no evidence.

        Only the guards that do not depend on evidence apply: Never-Claim /
        red-line prohibition and the planned-credential guard, run on the
        FULL narrative text exactly as they run on claim text in
        `validate_claim`. The evidence-coverage, relational-composition, and
        metric-provenance guards (`validate_claim` steps 3-12) are not
        meaningful for text that makes no evidentiary claim about the
        founder, so they do not run here -- this method never grants an
        exemption from any of those guards for text that *does* contain a
        founder-specific assertion; the compiler is responsible for only
        ever routing genuinely connective, fact-free text through this path
        (see `matching/compiler_employment.py` and
        `matching/compiler_independent.py`).
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("narrative text must be a non-empty string")
        text = _SPACE.sub(" ", text.strip())

        prohibited_reasons = self._prohibited_reasons(text)
        if prohibited_reasons:
            return self._result(
                text, False, AssertionType.PROHIBITED_CLAIM,
                VerificationStatus.UNVERIFIED, (), prohibited_reasons,
            )

        credential_reasons = self._planned_credential_reasons(text)
        if credential_reasons:
            return self._result(
                text, False, AssertionType.PROHIBITED_CLAIM,
                VerificationStatus.UNVERIFIED, (), credential_reasons,
            )

        return self._result(
            text, True, AssertionType.USER_ASSERTION,
            VerificationStatus.UNVERIFIED, (),
            ("narrative segment: connective text only, not an evidence-checked founder claim",),
        )

    def _validate_temporal_validity(self, claim: str, supporting: tuple, as_of: date) -> str | None:
        """Evaluate whether certifications, work authorizations, or assertions are expired as of as_of."""
        for cert in self.graph.certification_records():
            if cert.expiry_date and as_of > cert.expiry_date:
                if _normalize(cert.name) in _normalize(claim) and _HELD.search(claim):
                    return f"certification {cert.id} expired on {cert.expiry_date} as of {as_of}"
        return None

    def validate_claims(
        self, claims: Iterable[str | tuple[str, Iterable[str]]]
    ) -> tuple[ClaimVerificationResult, ...]:
        results = []
        for item in claims:
            if isinstance(item, str):
                results.append(self.validate_claim(item))
            else:
                claim, evidence_ids = item
                results.append(self.validate_claim(claim, evidence_ids))
        return tuple(results)

    def require_valid(
        self, claims: Iterable[str | tuple[str, Iterable[str]]]
    ) -> tuple[ClaimVerificationResult, ...]:
        results = self.validate_claims(claims)
        rejected = tuple(result.claim for result in results if not result.allowed)
        if rejected:
            raise ValueError(f"rejected claims: {'; '.join(rejected)}")
        return results

    def _prohibited_reasons(self, claim: str) -> tuple[str, ...]:
        red_lines, never_claims = self.graph.rules()
        reasons = []
        for rule in red_lines:
            try:
                matched = re.search(rule.pattern, claim, flags=re.IGNORECASE)
            except re.error as error:
                raise ValueError(f"invalid red-line pattern {rule.id}: {error}") from error
            if matched:
                reasons.append(f"red line {rule.id}: {rule.reason}")

        cleaned_claim = _clean_text_for_matching(claim)
        for rule in never_claims:
            # Check concept pattern (semantic pattern)
            matched_pattern = False
            if rule.pattern:
                try:
                    matched_pattern = bool(re.search(rule.pattern, claim, flags=re.IGNORECASE))
                except re.error as error:
                    raise ValueError(f"invalid never-claim pattern {rule.id}: {error}") from error

            # Check exact forbidden phrases as defense-in-depth
            matched_phrase = False
            for phrase in rule.forbidden_phrases:
                cleaned_phrase = _clean_text_for_matching(phrase)
                if cleaned_phrase and cleaned_phrase in cleaned_claim:
                    matched_phrase = True
                    break

            if matched_pattern or matched_phrase:
                reasons.append(f"never-claim {rule.id} [{rule.concept}]: {rule.description}")

        return tuple(reasons)

    def _planned_credential_reasons(self, claim: str) -> tuple[str, ...]:
        normalized_claim = _normalize(claim)
        reasons = []
        for certification in self.graph.certification_records():
            if certification.state is not CertificationState.PLANNED:
                continue
            if _normalize(certification.name) not in normalized_claim:
                continue
            if _HELD.search(claim) or not _PLANNING.search(claim):
                reasons.append(
                    f"planned certification {certification.id} cannot be represented as held"
                )
        return tuple(reasons)

    @staticmethod
    def _supports(content: str | None, claim: str) -> bool:
        if content is None:
            return False
        normalized_content = _normalize(content)
        normalized_claim = _normalize(claim)
        if normalized_content == normalized_claim:
            return True
        if len(normalized_content) >= 4 and normalized_content in normalized_claim:
            return True
        claim_tokens = _tokens(normalized_claim) - _NON_MATERIAL_WORDS
        content_tokens = _tokens(normalized_content) - _NON_MATERIAL_WORDS
        if bool(content_tokens) and content_tokens <= claim_tokens:
            return True
        if bool(content_tokens & claim_tokens):
            return True
        return False

    def _validate_metric_provenance(
        self,
        claim: str,
        supporting: tuple,
        allowed_subject_ids: set[str] | None = None,
    ) -> str | None:
        """Verify that every numeric metric in the claim maps to an exact verified MetricAssertion."""
        structured_metrics = _parse_structured_metrics_with_context(claim)
        if not structured_metrics:
            return None

        for num_val, unit, claim_metric_ctx in structured_metrics:
            metric_verified = False
            for record in supporting:
                if not record.content:
                    continue

                # Check atomic MetricAssertions for this record
                metric_assertions = self.graph.metric_assertions_for_evidence(record.id)
                for ma in metric_assertions:
                    if ma.verification_status is not MetricVerification.VERIFIED:
                        continue
                    if allowed_subject_ids is not None and ma.subject_id not in allowed_subject_ids:
                        continue
                    if ma.numeric_value != num_val:
                        continue

                    if not _units_compatible(unit, ma.unit):
                        continue

                    if not _metric_contexts_compatible(ma.context, claim_metric_ctx, num_val):
                        continue

                    metric_verified = True
                    break

                if metric_verified:
                    break

            if not metric_verified:
                return f"claim metric '{num_val} {unit}' lacks an exact verified metric provenance node"

        return None

    @staticmethod
    def _resolve_verification_status(supporting: tuple, claim: str) -> VerificationStatus | None:
        """Resolve verification status across supporting evidence using conservative weakest-link rule."""
        statuses = {record.verification_status for record in supporting}
        if VerificationStatus.EXPLICIT_NULL in statuses or VerificationStatus.UNVERIFIED in statuses:
            return None
        if VerificationStatus.APPROXIMATE in statuses:
            if not _APPROXIMATION.search(claim):
                return None
            return VerificationStatus.APPROXIMATE
        return VerificationStatus.VERIFIED

    @staticmethod
    def _resolve_assertion_type(supporting: tuple) -> AssertionType:
        """Propagate epistemic status using the conservative weakest-link rule.

        Epistemic hierarchy from strongest to weakest:
        DIRECT_FACT > NORMALIZED_FACT > DERIVED_CAPABILITY > USER_ASSERTION.

        A composite claim takes the weakest/most inferential status among all supporting evidence.
        """
        if not supporting:
            return AssertionType.UNSUPPORTED_CLAIM

        present = {record.assertion_type for record in supporting}
        if AssertionType.PROHIBITED_CLAIM in present:
            return AssertionType.PROHIBITED_CLAIM
        if AssertionType.UNSUPPORTED_CLAIM in present:
            return AssertionType.UNSUPPORTED_CLAIM
        if AssertionType.USER_ASSERTION in present:
            return AssertionType.USER_ASSERTION
        if AssertionType.DERIVED_CAPABILITY in present:
            return AssertionType.DERIVED_CAPABILITY
        if AssertionType.NORMALIZED_FACT in present:
            return AssertionType.NORMALIZED_FACT
        return AssertionType.DIRECT_FACT

    @staticmethod
    def _result(
        claim: str,
        allowed: bool,
        assertion_type: AssertionType,
        verification_status: VerificationStatus,
        evidence_ids: tuple[str, ...],
        reasons: tuple[str, ...],
    ) -> ClaimVerificationResult:
        return ClaimVerificationResult(
            claim=claim, allowed=allowed, assertion_type=assertion_type,
            verification_status=verification_status,
            evidence_ids=evidence_ids, reasons=reasons,
        )
