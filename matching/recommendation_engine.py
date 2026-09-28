"""Deterministic recommendation gates, behavior profile, and feed composition.

This module consumes compact FR-008/BC-1 facts and caller-supplied Founder
interaction summaries. It has no persistence or network dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


_NEGATIVE_LABELS = frozenset({"bad_match", "irrelevant_role"})
_EXCLUDED_ACTIONS = frozenset({
    "applied", "submitted", "rejected", "rejected_by_founder", "dismissed",
})
_ACTIONABLE_ACCESS = frozenset({"direct_free", "free_intermediary", "free_account_required"})


@dataclass(frozen=True, slots=True)
class BehaviorSignal:
    """Privacy-safe categorical interaction used to derive learned affinity."""

    role_family: str | None = None
    source_family: str | None = None
    feedback_label: str | None = None
    action_type: str | None = None
    opportunity_id: str | None = None


@dataclass(frozen=True, slots=True)
class BehaviorProfile:
    role_family_affinity: tuple[tuple[str, float], ...]
    source_family_affinity: tuple[tuple[str, float], ...]

    def score(self, *, role_family: str | None, source_family: str | None) -> float:
        roles = dict(self.role_family_affinity)
        sources = dict(self.source_family_affinity)
        # Role preference is the stronger signal; source-level evidence is
        # intentionally smaller and saved-only history contributes nothing.
        role = roles.get((role_family or "").casefold(), 0.0)
        source = sources.get((source_family or "").casefold(), 0.0)
        return max(0.0, min(100.0, 50.0 + role + source))


def build_behavior_profile(
    signals: Iterable[BehaviorSignal], *, exclude_opportunity_id: str | None = None,
) -> BehaviorProfile:
    """Build bounded categorical affinity; unknown labels and saves are neutral.

    Explicit role feedback changes role-family affinity. Applied/submitted
    actions are a medium positive signal. Eligibility corrections, duplicate
    reports, source-quality reports, and review requests do not become role
    preference evidence.
    """
    role_totals: dict[str, float] = {}
    source_totals: dict[str, float] = {}
    role_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for signal in signals:
        if exclude_opportunity_id and signal.opportunity_id == exclude_opportunity_id:
            continue
        label = (signal.feedback_label or "").casefold()
        action = (signal.action_type or "").casefold()
        role = (signal.role_family or "").strip().casefold()
        source = (signal.source_family or "").strip().casefold()
        value = 0.0
        if label == "good_match":
            value = 20.0
        elif label in _NEGATIVE_LABELS:
            value = -24.0
        elif action in {"applied", "submitted"}:
            value = 12.0
        if value == 0.0:
            continue
        if role:
            role_totals[role] = role_totals.get(role, 0.0) + value
            role_counts[role] = role_counts.get(role, 0) + 1
        if source:
            source_totals[source] = source_totals.get(source, 0.0) + value * 0.25
            source_counts[source] = source_counts.get(source, 0) + 1

    def normalized(totals: dict[str, float], counts: dict[str, int]) -> tuple[tuple[str, float], ...]:
        # Shrink sparse observations toward neutral and cap their influence.
        return tuple(sorted(
            (key, max(-35.0, min(35.0, total / (counts[key] + 1))))
            for key, total in totals.items()
        ))

    return BehaviorProfile(
        role_family_affinity=normalized(role_totals, role_counts),
        source_family_affinity=normalized(source_totals, source_counts),
    )


@dataclass(frozen=True, slots=True)
class RecommendationCandidate:
    opportunity_id: str
    role_relevance: str
    geography: str
    application_access: str
    application_url: str | None
    decision: str | None
    fit_score: float | None
    confidence_score: float | None
    role_family: str | None = None
    source_family: str | None = None
    is_stale: bool = False
    feedback_label: str | None = None
    action_state: str | None = None
    family_key: str | None = None
    organization: str | None = None
    freshness_score: float | None = None
    source_application_confidence: float | None = None
    evidence_completeness: float | None = None


@dataclass(frozen=True, slots=True)
class Recommendation:
    opportunity_id: str
    state: str  # for_you | review | excluded
    reasons: tuple[str, ...]
    role_tier: int
    fit_score: float
    affinity_score: float
    geography_score: float
    freshness_score: float
    source_application_confidence: float
    evidence_quality_score: float = 0.0

    @property
    def rank_key(self) -> tuple[float, ...]:
        return (
            self.role_tier, self.fit_score, self.evidence_quality_score,
            self.affinity_score, self.geography_score, self.freshness_score,
            self.source_application_confidence,
        )


def recommend(
    candidate: RecommendationCandidate,
    *,
    behavior: BehaviorProfile | None = None,
) -> Recommendation:
    """Apply recommendation hard gates before deterministic ranking.

    Recommendation gates represent disqualifying or un-actionable facts.
    Capability evidence and confidence affect ranking and are surfaced as
    uncertainty reasons, but never act as universal eligibility gates.
    """
    role = candidate.role_relevance.casefold()
    geo = candidate.geography.casefold()
    access = candidate.application_access.casefold()
    decision = (candidate.decision or "").casefold()
    feedback = (candidate.feedback_label or "").casefold()
    action = (candidate.action_state or "").casefold()
    reasons: list[str] = []

    if candidate.is_stale:
        state, reasons = "excluded", ["stale"]
    elif role == "non_target":
        state, reasons = "excluded", ["non_target_role"]
    elif geo == "ineligible":
        state, reasons = "excluded", ["geography_incompatible"]
    elif feedback in _NEGATIVE_LABELS:
        state, reasons = "excluded", ["founder_negative_role_feedback"]
    elif action in _EXCLUDED_ACTIONS:
        state, reasons = "excluded", [f"already_{action}"]
    elif decision == "ineligible":
        state, reasons = "excluded", ["qualification_ineligible"]
    elif feedback == "eligibility_wrong":
        state, reasons = "review", ["founder_eligibility_correction"]
    elif feedback in {
        "seniority_wrong", "review_required", "duplicate_issue", "source_quality_issue",
    }:
        state, reasons = "review", [f"founder_{feedback}"]
    elif role not in {"core", "adjacent"}:
        state, reasons = "review", ["role_relevance_unknown"]
    elif geo not in {"eligible", "likely_eligible"}:
        state, reasons = "review", ["geography_needs_review"]
    elif access not in _ACTIONABLE_ACCESS or not (candidate.application_url or "").strip():
        state, reasons = "review", ["application_route_needs_review"]
    else:
        state, reasons = "for_you", ["recommendation_gates_passed"]
        if decision not in {"qualified", "eligible"}:
            reasons.append("check_eligibility")
        if candidate.fit_score is None:
            reasons.append("capability_fit_unscored")
        if candidate.evidence_completeness is None or (candidate.evidence_completeness or 0.0) < 65.0:
            reasons.append("founder_evidence_limited")
        if (candidate.confidence_score or 0.0) < 40.0:
            reasons.append("match_confidence_low")

    profile = behavior or BehaviorProfile((), ())
    affinity = profile.score(role_family=candidate.role_family, source_family=candidate.source_family)
    role_tier = 2 if role == "core" else 1 if role == "adjacent" else 0
    geo_score = 100.0 if geo == "eligible" else 85.0 if geo == "likely_eligible" else 0.0
    return Recommendation(
        opportunity_id=candidate.opportunity_id,
        state=state,
        reasons=tuple(reasons),
        role_tier=role_tier,
        fit_score=max(0.0, min(100.0, candidate.fit_score or 0.0)),
        affinity_score=affinity,
        geography_score=geo_score,
        freshness_score=max(0.0, min(100.0, candidate.freshness_score or 0.0)),
        source_application_confidence=max(0.0, min(100.0, candidate.source_application_confidence or 0.0)),
        evidence_quality_score=max(0.0, min(100.0, (
            (candidate.evidence_completeness if candidate.evidence_completeness is not None else 0.0)
            + (candidate.confidence_score if candidate.confidence_score is not None else 0.0)
        ) / (int(candidate.evidence_completeness is not None) + int(candidate.confidence_score is not None) or 1))),
    )


def compose_for_you(
    recommendations: Iterable[Recommendation],
    candidates: Iterable[RecommendationCandidate],
    *,
    limit: int | None = None,
) -> tuple[str, ...]:
    """Deduplicate role families and interleave employers deterministically.

    The per-employer cap starts at four of the first 20 and six of the first
    50, relaxing only when remaining inventory cannot fill a position.
    """
    by_id = {candidate.opportunity_id: candidate for candidate in candidates}
    best_by_family: dict[str, Recommendation] = {}
    ungrouped: list[Recommendation] = []
    for item in recommendations:
        if item.state != "for_you":
            continue
        candidate = by_id.get(item.opportunity_id)
        family = (candidate.family_key or "").strip() if candidate else ""
        if not family:
            ungrouped.append(item)
            continue
        previous = best_by_family.get(family)
        if previous is None or item.rank_key > previous.rank_key or (
            item.rank_key == previous.rank_key and item.opportunity_id < previous.opportunity_id
        ):
            best_by_family[family] = item
    ranked = sorted(
        [*ungrouped, *best_by_family.values()],
        key=lambda item: (tuple(-part for part in item.rank_key), item.opportunity_id),
    )
    selected: list[Recommendation] = []
    deferred: list[Recommendation] = []
    employer_counts: dict[str, int] = {}
    for item in ranked:
        candidate = by_id.get(item.opportunity_id)
        employer = (candidate.organization or "").strip().casefold() if candidate else ""
        rank = len(selected) + 1
        cap = 4 if rank <= 20 else 6 if rank <= 50 else None
        if employer and cap is not None and employer_counts.get(employer, 0) >= cap:
            deferred.append(item)
            continue
        selected.append(item)
        if employer:
            employer_counts[employer] = employer_counts.get(employer, 0) + 1
    # Relax caps only as needed to fill the requested portion of the inventory.
    for item in deferred:
        if limit is not None and len(selected) >= limit:
            break
        selected.append(item)
    if limit is not None:
        selected = selected[:max(0, limit)]
    return tuple(item.opportunity_id for item in selected)
