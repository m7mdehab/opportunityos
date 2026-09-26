"""Deterministic, inspectable components for the default Recommended feed."""
from __future__ import annotations

import math
from datetime import date
from typing import Any

_RADIX = 101  # Each encoded component is an integer in [0, 100].
_CORE_ORDER_RANGE = 3 * (_RADIX ** 6)
_NEUTRAL_SCORE = 50.0


def _score_bucket(value: Any, *, default: float = _NEUTRAL_SCORE) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    if not math.isfinite(numeric):
        numeric = default
    return max(0, min(100, int(round(numeric))))


def eligibility_tier(decision: str | None) -> tuple[str, int]:
    normalized = str(decision or "").casefold()
    if normalized in {"qualified", "eligible"}:
        return "eligible", 2
    if normalized in {"ineligible"}:
        return "ineligible", 0
    return "review_required", 1


def posting_freshness_score(
    posted_date: str | None,
    *,
    is_stale: bool,
    as_of: date,
) -> float | None:
    """Map posting age to an inspectable 0–100 freshness component.

    Missing or unparseable posted dates remain unknown. A stale flag is direct
    source evidence and therefore resolves to zero freshness.
    """
    if is_stale:
        return 0.0
    if not posted_date:
        return None
    try:
        parsed = date.fromisoformat(str(posted_date)[:10])
    except ValueError:
        return None
    age_days = max(0, (as_of - parsed).days)
    if age_days <= 7:
        return 100.0
    if age_days <= 30:
        return 80.0
    if age_days <= 90:
        return 55.0
    if age_days <= 180:
        return 35.0
    return 15.0


def source_confidence_score(evaluation_detail: dict[str, Any] | None) -> float | None:
    factors = (evaluation_detail or {}).get("confidence_factors")
    if not isinstance(factors, list):
        return None
    for factor in factors:
        if not isinstance(factor, dict) or factor.get("name") != "source_freshness_and_strength":
            continue
        try:
            value = float(factor.get("score"))
        except (TypeError, ValueError):
            return None
        return max(0.0, min(100.0, value)) if math.isfinite(value) else None
    return None


def recommended_priority_score(
    *,
    decision: str | None,
    fit_score: float | None,
    preference_score: float | None,
    confidence_score: float | None,
    freshness_score: float | None,
    source_confidence: float | None,
    rank_penalty: int = 0,
) -> float:
    """Encode the ordered components as a base-101 lexicographic key.

    Founder-configured rank-only filters remain the outer demotion tier. The
    normal order is eligibility, fit, preference, confidence, posting
    freshness, and source confidence. Null scores use 50 for ordering only;
    callers keep the visible values null so missing evidence is not invented.
    """
    _, decision_bucket = eligibility_tier(decision)
    components = (
        decision_bucket,
        _score_bucket(fit_score),
        _score_bucket(preference_score),
        _score_bucket(confidence_score),
        _score_bucket(freshness_score),
        _score_bucket(source_confidence),
    )
    encoded = 0
    for component in components:
        encoded = encoded * _RADIX + component
    penalty = max(0, int(rank_penalty))
    return float(encoded - penalty * _CORE_ORDER_RANGE)


def feed_ranking_components(
    *,
    decision: str | None,
    fit_score: float | None,
    priority_score: float | None,
    evaluation_detail: dict[str, Any] | None,
    posted_date: str | None,
    is_stale: bool,
    as_of: date,
) -> dict[str, Any]:
    detail = evaluation_detail or {}
    preference_score = detail.get("preference_score")
    confidence_score = detail.get("confidence_score")
    freshness_score = posting_freshness_score(posted_date, is_stale=is_stale, as_of=as_of)
    return {
        "priority_score": priority_score,
        "eligibility": eligibility_tier(decision)[0],
        "capability_fit": fit_score,
        "preference_score": preference_score,
        "confidence_score": confidence_score,
        "freshness_score": freshness_score,
        "source_confidence": source_confidence_score(detail),
    }
