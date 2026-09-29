"""BC-2 recommendation gates and compact feed ordering."""
from typing import Any

from matching.recommendation_engine import BehaviorProfile, Recommendation, RecommendationCandidate, recommend
from storage.ranking import posting_freshness_score, source_confidence_score


def _confidence_factor(detail: dict[str, Any], name: str) -> float | None:
    factors = detail.get("confidence_factors")
    if not isinstance(factors, list):
        return None
    for factor in factors:
        if isinstance(factor, dict) and factor.get("name") == name:
            try:
                return float(factor.get("score"))
            except (TypeError, ValueError):
                return None
    return None


def build_recommendation(
    *,
    opportunity_id: str,
    role_relevance: str,
    geography: str,
    application_access: str,
    application_url: str | None,
    decision: str | None,
    fit_score: float | None,
    evaluation_detail: dict[str, Any] | None,
    posted_date: str | None,
    is_stale: bool,
    feedback_label: str | None = None,
    action_state: str | None = None,
    role_family: str | None = None,
    source_family: str | None = None,
    family_key: str | None = None,
    organization: str | None = None,
    as_of=None,
    behavior: BehaviorProfile | None = None,
    eligibility_state: str | None = None,
    eligibility_reason: str | None = None,
) -> Recommendation:
    from datetime import date

    detail = evaluation_detail or {}
    confidence = detail.get("confidence_score")
    evidence_completeness = _confidence_factor(detail, "founder_evidence_completeness")
    freshness = posting_freshness_score(
        posted_date, is_stale=is_stale, as_of=as_of or date.today(),
    )
    return recommend(RecommendationCandidate(
        opportunity_id=opportunity_id,
        role_relevance=role_relevance,
        geography=geography,
        application_access=application_access,
        application_url=application_url,
        decision=decision,
        fit_score=fit_score,
        confidence_score=confidence,
        role_family=role_family,
        source_family=source_family,
        is_stale=is_stale,
        feedback_label=feedback_label,
        action_state=action_state,
        family_key=family_key,
        organization=organization,
        freshness_score=freshness,
        source_application_confidence=source_confidence_score(detail),
        evidence_completeness=evidence_completeness,
        eligibility_state=eligibility_state,
        eligibility_reason=eligibility_reason,
    ), behavior=behavior)
