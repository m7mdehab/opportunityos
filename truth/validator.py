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
    VerificationStatus,
)


_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[\w+#.%-]+", re.UNICODE)
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

        prohibited_reasons = self._prohibited_reasons(claim)
        if prohibited_reasons:
            return self._result(
                claim, False, AssertionType.PROHIBITED_CLAIM,
                VerificationStatus.UNVERIFIED, (), prohibited_reasons,
            )

        credential_reasons = self._planned_credential_reasons(claim)
        if credential_reasons:
            return self._result(
                claim, False, AssertionType.PROHIBITED_CLAIM,
                VerificationStatus.UNVERIFIED, (), credential_reasons,
            )

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
        supporting = tuple(record for record in candidates if self._supports(record.content, claim))
        if not supporting:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED, (),
                ("no evidence record supports the material claim",),
            )

        evidence_tokens = set().union(*(_tokens(record.content or "") for record in supporting))
        uncovered = sorted(_tokens(claim) - evidence_tokens - _NON_MATERIAL_WORDS)
        if uncovered:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                tuple(record.id for record in supporting),
                (f"claim contains material terms absent from evidence: {', '.join(uncovered)}",),
            )

        verified_support = tuple(
            record for record in supporting
            if record.verification_status is VerificationStatus.VERIFIED
        )
        approximate_support = tuple(
            record for record in supporting
            if record.verification_status is VerificationStatus.APPROXIMATE
        )
        if not verified_support:
            if approximate_support and _APPROXIMATION.search(claim):
                selected = approximate_support
                status = VerificationStatus.APPROXIMATE
            else:
                return self._result(
                    claim, False, AssertionType.UNSUPPORTED_CLAIM,
                    VerificationStatus.UNVERIFIED,
                    tuple(record.id for record in supporting),
                    ("supporting evidence is not verified or explicitly qualified as approximate",),
                )
        else:
            selected = verified_support
            status = VerificationStatus.VERIFIED

        metric_reason = self._metric_rejection(claim, selected)
        if metric_reason:
            return self._result(
                claim, False, AssertionType.UNSUPPORTED_CLAIM,
                VerificationStatus.UNVERIFIED,
                tuple(record.id for record in selected), (metric_reason,),
            )

        assertion_type = self._strongest_assertion_type(selected)
        return self._result(
            claim, True, assertion_type, status,
            tuple(record.id for record in selected), ("claim is traceable to supporting evidence",),
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
            cleaned_phrase = _clean_text_for_matching(rule.phrase)
            if cleaned_phrase and cleaned_phrase in cleaned_claim:
                reasons.append(f"never-claim {rule.id}: {rule.reason}")
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

    def _metric_rejection(self, claim: str, supporting) -> str | None:
        claim_metrics = _material_metrics(claim)
        if not claim_metrics:
            return None
        evidence_text = " ".join(record.content or "" for record in supporting)
        evidence_metrics = set(_material_metrics(evidence_text))
        missing = tuple(metric for metric in claim_metrics if metric not in evidence_metrics)
        if missing:
            return f"claim metrics are absent from evidence: {', '.join(missing)}"
        statuses = tuple(
            status
            for record in supporting
            for status in self.graph.metric_status_for_evidence(record.id)
        )
        if MetricVerification.VERIFIED not in statuses:
            return "numeric metric lacks a verified metric provenance node"
        return None

    @staticmethod
    def _strongest_assertion_type(supporting) -> AssertionType:
        priority = (
            AssertionType.DIRECT_FACT,
            AssertionType.NORMALIZED_FACT,
            AssertionType.DERIVED_CAPABILITY,
            AssertionType.USER_ASSERTION,
        )
        present = {record.assertion_type for record in supporting}
        return next(item for item in priority if item in present)

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
