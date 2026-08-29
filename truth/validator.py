"""Fail-closed claim validation against the professional truth graph."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .graph import TruthGraph
from .models import (
    AssertionType,
    CertificationState,
    ClaimVerificationResult,
    MetricVerification,
    NeverClaimRule,
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
    "a", "an", "and", "approximately", "around", "as", "at", "about", "by",
    "for", "from", "in", "is", "nearly", "of", "on", "roughly", "that", "the",
    "to", "was", "were", "with",
}


def _normalize(value: str) -> str:
    return _SPACE.sub(" ", value.strip().casefold())


def _tokens(value: str) -> set[str]:
    return {match.group(0).casefold() for match in _WORD.finditer(value)}


def _material_metrics(value: str) -> tuple[str, ...]:
    metrics = []
    for match in _METRIC.finditer(value):
        token = _SPACE.sub("", match.group(0).casefold()).replace(",", "")
        digits = re.sub(r"\D", "", token)
        # Standalone calendar years are not performance metrics.
        if re.fullmatch(r"(?:19|20)\d{2}", digits) and not re.search(r"[%$€£x]", token):
            continue
        metrics.append(token)
    return tuple(metrics)


def _clean_text_for_matching(value: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return _SPACE.sub(" ", cleaned.strip().casefold())


class ClaimValidator:
    """Enforce evidence, metric, credential, red-line, and never-claim rules."""

    def __init__(self, graph: TruthGraph) -> None:
        self.graph = graph

    def validate_claim(
        self, claim: str, evidence_ids: Iterable[str] | None = None
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

        # 4. Find supporting evidence records.
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

        # 5. Relational composition guard:
        # Cross-evidence relationship laundering is prevented.
        # If multiple evidence records are required to cover the claim, they MUST be relationally linked
        # by an explicit common entity node in the TruthGraph.
        supporting_ids = tuple(record.id for record in supporting)
        if len(supporting) > 1 and not self.graph.are_relationally_linked(supporting_ids):
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED, supporting_ids,
                ("composite claim combines independent evidence records without an establishing graph relation",),
            )

        # 6. Material lexical coverage check.
        evidence_tokens = set().union(*(_tokens(record.content or "") for record in supporting))
        uncovered = sorted(_tokens(claim) - evidence_tokens - _NON_MATERIAL_WORDS)
        if uncovered:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                supporting_ids,
                (f"claim contains material terms absent from evidence: {', '.join(uncovered)}",),
            )

        # 7. Verification status resolution: conservative weakest-link rule.
        status = self._resolve_verification_status(supporting, claim)
        if status is None:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                supporting_ids,
                ("supporting evidence is unverified, explicit-null, or approximate without qualification",),
            )

        # 8. Exact metric provenance validation.
        metric_reason = self._validate_metric_provenance(claim, supporting)
        if metric_reason:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                supporting_ids, (metric_reason,),
            )

        # 9. Conservative epistemic assertion-type resolution.
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
        claim_tokens = _tokens(normalized_claim)
        content_tokens = _tokens(normalized_content)
        return bool(content_tokens) and content_tokens <= claim_tokens

    def _validate_metric_provenance(self, claim: str, supporting: tuple) -> str | None:
        """Verify that every numeric metric in the claim maps to an exact verified metric provenance node."""
        claim_metrics = _material_metrics(claim)
        if not claim_metrics:
            return None

        for metric in claim_metrics:
            matching_records = [
                record for record in supporting
                if record.content and metric in set(_material_metrics(record.content))
            ]
            if not matching_records:
                return f"claim metric '{metric}' is absent from supporting evidence"

            # For each matching record carrying this specific metric, verify if any attached entity has MetricVerification.VERIFIED
            metric_verified = False
            for record in matching_records:
                statuses = self.graph.metric_status_for_evidence(record.id)
                if MetricVerification.VERIFIED in statuses:
                    metric_verified = True
                    break

            if not metric_verified:
                return f"claim metric '{metric}' lacks an exact verified metric provenance node"

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
