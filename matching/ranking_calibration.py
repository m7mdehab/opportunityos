"""Privacy-safe offline metrics for FR-008 gold-set review.

This module only compares caller-supplied review labels with caller-supplied
predictions. It does not load jobs, profiles, databases, or scoring code and it
never emits raw opportunity IDs or reviewer rationales in its report.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable

from matching.gold_review import (
    ActionabilityChoice,
    CapabilityFitBand,
    GoldReviewLabel,
    TargetFamilyTier,
)

MINIMUM_GOLD_SET_SIZE = 150
TARGETS = {
    "hard_ineligible_precision": 1.0,
    "geography_correctness": 0.95,
    "target_tier_accuracy": 0.90,
    "recommended_apply_over_skip_accuracy": 0.90,
}

_INELIGIBLE_DECISIONS = frozenset({"ineligible"})
_APPLY_ACTIONS = frozenset({
    ActionabilityChoice.DEFINITELY_APPLY,
    ActionabilityChoice.LIKELY_APPLY,
})
_SKIP_ACTIONS = frozenset({ActionabilityChoice.PROBABLY_SKIP})
_FIT_BAND_ORDER = {
    CapabilityFitBand.WEAK: 0,
    CapabilityFitBand.STRETCH: 1,
    CapabilityFitBand.PLAUSIBLE_MATERIAL_GAPS: 2,
    CapabilityFitBand.GOOD_REALISTIC: 3,
    CapabilityFitBand.STRONG: 4,
    CapabilityFitBand.EXCEPTIONAL_DIRECT: 5,
}


def _validate_opaque_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("opportunity_id must be a string")
    if not value or value != value.strip() or len(value) > 256:
        raise ValueError("opportunity_id must be a non-empty opaque ID of at most 256 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("opportunity_id must not contain control characters")
    return value


def _finite_number(value: object, *, field_name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be a finite number")
    if minimum is not None and result < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return result


@dataclass(frozen=True, slots=True)
class RankingPrediction:
    """The minimum privacy-safe model output needed for W3.5 metrics."""

    opportunity_id: str
    qualification_decision: str
    fit_score: float
    priority_score: float
    target_family_tier: TargetFamilyTier | str | None = None

    def __post_init__(self) -> None:
        _validate_opaque_id(self.opportunity_id)
        if not isinstance(self.qualification_decision, str):
            raise TypeError("qualification_decision must be a string")
        decision = self.qualification_decision.strip().casefold()
        if decision not in {"qualified", "eligible", "uncertain", "review_required", "ineligible"}:
            raise ValueError("qualification_decision is not a recognized FR-008 decision")
        object.__setattr__(self, "qualification_decision", decision)
        object.__setattr__(self, "fit_score", _finite_number(
            self.fit_score, field_name="fit_score", minimum=0.0, maximum=100.0,
        ))
        object.__setattr__(self, "priority_score", _finite_number(
            self.priority_score, field_name="priority_score",
        ))
        if self.target_family_tier is not None:
            tier = self.target_family_tier
            if not isinstance(tier, TargetFamilyTier):
                try:
                    tier = TargetFamilyTier(tier)
                except (TypeError, ValueError) as exc:
                    raise ValueError("target_family_tier is not a recognized review tier") from exc
            object.__setattr__(self, "target_family_tier", tier)


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Aggregated results with hashed tokens for local FP/FN investigation."""

    total_items: int
    founder_reviewed_real_jobs_confirmed: bool
    minimum_sample_met: bool
    hard_ineligible_precision: float | None
    hard_ineligible_true_positives: int
    hard_ineligible_false_positives: int
    hard_ineligible_false_negatives: int
    false_positive_tokens: tuple[str, ...]
    false_negative_tokens: tuple[str, ...]
    geography_correctness_rate: float | None
    geography_labeled_items: int
    seniority_correctness_rate: float | None
    seniority_labeled_items: int
    required_skill_correctness_rate: float | None
    required_skill_labeled_items: int
    target_tier_accuracy: float | None
    target_tier_labeled_items: int
    recommended_apply_over_skip_accuracy: float | None
    recommended_comparison_pairs: int
    fit_score_spearman_rho: float | None
    fit_score_mean_by_band: dict[str, float]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return aggregates and one-way review tokens, never source labels."""
        return {
            "schema_version": 1,
            "total_items": self.total_items,
            "minimum_sample_size": MINIMUM_GOLD_SET_SIZE,
            "founder_reviewed_real_jobs_confirmed": self.founder_reviewed_real_jobs_confirmed,
            "minimum_sample_met": self.minimum_sample_met,
            "hard_ineligible_precision": self.hard_ineligible_precision,
            "hard_ineligible_true_positives": self.hard_ineligible_true_positives,
            "hard_ineligible_false_positives": self.hard_ineligible_false_positives,
            "hard_ineligible_false_negatives": self.hard_ineligible_false_negatives,
            "false_positive_tokens": list(self.false_positive_tokens),
            "false_negative_tokens": list(self.false_negative_tokens),
            "geography_correctness_rate": self.geography_correctness_rate,
            "geography_labeled_items": self.geography_labeled_items,
            "seniority_correctness_rate": self.seniority_correctness_rate,
            "seniority_labeled_items": self.seniority_labeled_items,
            "required_skill_correctness_rate": self.required_skill_correctness_rate,
            "required_skill_labeled_items": self.required_skill_labeled_items,
            "target_tier_accuracy": self.target_tier_accuracy,
            "target_tier_labeled_items": self.target_tier_labeled_items,
            "recommended_apply_over_skip_accuracy": self.recommended_apply_over_skip_accuracy,
            "recommended_comparison_pairs": self.recommended_comparison_pairs,
            "fit_score_spearman_rho": self.fit_score_spearman_rho,
            "fit_score_mean_by_band": dict(self.fit_score_mean_by_band),
            "targets": {
                "hard_ineligible_precision": {
                    "minimum": TARGETS["hard_ineligible_precision"],
                    "met": _target_met(self.hard_ineligible_precision, TARGETS["hard_ineligible_precision"]),
                },
                "geography_correctness": {
                    "minimum": TARGETS["geography_correctness"],
                    "met": _target_met(self.geography_correctness_rate, TARGETS["geography_correctness"]),
                },
                "target_tier_accuracy": {
                    "minimum": TARGETS["target_tier_accuracy"],
                    "met": _target_met(self.target_tier_accuracy, TARGETS["target_tier_accuracy"]),
                },
                "recommended_apply_over_skip_accuracy": {
                    "minimum": TARGETS["recommended_apply_over_skip_accuracy"],
                    "met": _target_met(
                        self.recommended_apply_over_skip_accuracy,
                        TARGETS["recommended_apply_over_skip_accuracy"],
                    ),
                },
            },
            "limitations": list(self.limitations),
        }


def evaluate_gold_review(
    labels: Iterable[GoldReviewLabel],
    predictions: Iterable[RankingPrediction],
    *,
    founder_reviewed_real_jobs_confirmed: bool = False,
) -> CalibrationReport:
    """Compare a reviewed set with predictions without fitting/tuning weights.

    Labels and predictions must contain exactly the same unique opaque IDs.
    The function returns aggregate rates and stable hashed tokens for hard-
    eligibility false positives/negatives; it does not return rationales.
    """
    if type(founder_reviewed_real_jobs_confirmed) is not bool:
        raise TypeError("founder_reviewed_real_jobs_confirmed must be true or false")
    label_rows = tuple(labels)
    prediction_rows = tuple(predictions)
    if any(not isinstance(row, GoldReviewLabel) for row in label_rows):
        raise TypeError("labels must contain GoldReviewLabel values")
    if any(not isinstance(row, RankingPrediction) for row in prediction_rows):
        raise TypeError("predictions must contain RankingPrediction values")

    label_by_id = _unique_by_id(label_rows, "labels")
    prediction_by_id = _unique_by_id(prediction_rows, "predictions")
    if label_by_id.keys() != prediction_by_id.keys():
        missing_predictions = label_by_id.keys() - prediction_by_id.keys()
        missing_labels = prediction_by_id.keys() - label_by_id.keys()
        raise ValueError(
            f"labels and predictions must cover the same IDs "
            f"(missing predictions={len(missing_predictions)}, missing labels={len(missing_labels)})"
        )

    ids = sorted(label_by_id)
    hard_tp: list[str] = []
    hard_fp: list[str] = []
    hard_fn: list[str] = []
    for opportunity_id in ids:
        label = label_by_id[opportunity_id]
        prediction = prediction_by_id[opportunity_id]
        actual_ineligible = label.actionability is ActionabilityChoice.DEFINITELY_INELIGIBLE
        predicted_ineligible = prediction.qualification_decision in _INELIGIBLE_DECISIONS
        if actual_ineligible and predicted_ineligible:
            hard_tp.append(opportunity_id)
        elif predicted_ineligible:
            hard_fp.append(opportunity_id)
        elif actual_ineligible:
            hard_fn.append(opportunity_id)

    precision = _ratio(len(hard_tp), len(hard_tp) + len(hard_fp))
    geography = _boolean_metric(label_by_id, "geography_correctness")
    seniority = _boolean_metric(label_by_id, "seniority_correctness")
    skills = _boolean_metric(label_by_id, "required_skill_correctness")
    tier_correct, tier_total = _target_tier_metric(label_by_id, prediction_by_id)
    ordering_correct, ordering_total = _apply_skip_metric(label_by_id, prediction_by_id)
    fit_rho, fit_means = _fit_score_metrics(label_by_id, prediction_by_id)

    limitations: list[str] = []
    if len(ids) < MINIMUM_GOLD_SET_SIZE:
        limitations.append(f"reviewed sample has {len(ids)} items; {MINIMUM_GOLD_SET_SIZE} are required")
    if not founder_reviewed_real_jobs_confirmed:
        limitations.append("real-job Founder review is not attested by the caller")
    if precision is None:
        limitations.append("hard-ineligible precision is unavailable because there are no ineligible predictions")
    if geography[1] == 0:
        limitations.append("geography correctness is unavailable because no geography labels are present")
    if seniority[1] == 0:
        limitations.append("seniority correctness is unavailable because no seniority labels are present")
    if skills[1] == 0:
        limitations.append("required-skill correctness is unavailable because no skill labels are present")
    if tier_total == 0:
        limitations.append("target-tier accuracy is unavailable because no expected tiers are present")
    if ordering_total == 0:
        limitations.append("Recommended apply/skip ordering is unavailable because there are no comparable pairs")
    if fit_rho is None:
        limitations.append("fit-score correlation is unavailable because the sample has fewer than two distinct ranks")

    return CalibrationReport(
        total_items=len(ids),
        founder_reviewed_real_jobs_confirmed=founder_reviewed_real_jobs_confirmed,
        minimum_sample_met=(
            founder_reviewed_real_jobs_confirmed
            and len(ids) >= MINIMUM_GOLD_SET_SIZE
        ),
        hard_ineligible_precision=precision,
        hard_ineligible_true_positives=len(hard_tp),
        hard_ineligible_false_positives=len(hard_fp),
        hard_ineligible_false_negatives=len(hard_fn),
        false_positive_tokens=tuple(_review_token(value) for value in sorted(hard_fp)),
        false_negative_tokens=tuple(_review_token(value) for value in sorted(hard_fn)),
        geography_correctness_rate=geography[0],
        geography_labeled_items=geography[1],
        seniority_correctness_rate=seniority[0],
        seniority_labeled_items=seniority[1],
        required_skill_correctness_rate=skills[0],
        required_skill_labeled_items=skills[1],
        target_tier_accuracy=_ratio(tier_correct, tier_total),
        target_tier_labeled_items=tier_total,
        recommended_apply_over_skip_accuracy=_ratio(ordering_correct, ordering_total),
        recommended_comparison_pairs=ordering_total,
        fit_score_spearman_rho=fit_rho,
        fit_score_mean_by_band=fit_means,
        limitations=tuple(limitations),
    )


def _unique_by_id(rows: Iterable[object], field_name: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for row in rows:
        opportunity_id = row.opportunity_id
        if opportunity_id in result:
            raise ValueError(f"{field_name} must not contain duplicate opportunity IDs")
        result[opportunity_id] = row
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _target_met(value: float | None, minimum: float) -> bool | None:
    return value >= minimum if value is not None else None


def _boolean_metric(labels: dict[str, object], field_name: str) -> tuple[float | None, int]:
    values = [getattr(label, field_name) for label in labels.values()]
    known = [value for value in values if value is not None]
    return _ratio(sum(value is True for value in known), len(known)), len(known)


def _target_tier_metric(
    labels: dict[str, object], predictions: dict[str, RankingPrediction],
) -> tuple[int, int]:
    correct = total = 0
    for opportunity_id, label in labels.items():
        expected = label.expected_target_family_tier
        if expected is None:
            continue
        total += 1
        actual = predictions[opportunity_id].target_family_tier
        if actual is expected:
            correct += 1
    return correct, total


def _apply_skip_metric(
    labels: dict[str, object], predictions: dict[str, RankingPrediction],
) -> tuple[int, int]:
    apply_ids = [
        opportunity_id for opportunity_id, label in labels.items()
        if label.actionability in _APPLY_ACTIONS
    ]
    skip_ids = [
        opportunity_id for opportunity_id, label in labels.items()
        if label.actionability in _SKIP_ACTIONS
    ]
    correct = total = 0
    for apply_id in apply_ids:
        for skip_id in skip_ids:
            total += 1
            apply_prediction = predictions[apply_id]
            skip_prediction = predictions[skip_id]
            if (
                apply_prediction.priority_score > skip_prediction.priority_score
                or (
                    apply_prediction.priority_score == skip_prediction.priority_score
                    and apply_id < skip_id
                )
            ):
                correct += 1
    return correct, total


def _fit_score_metrics(
    labels: dict[str, object], predictions: dict[str, RankingPrediction],
) -> tuple[float | None, dict[str, float]]:
    pairs = [
        (predictions[opportunity_id].fit_score, _FIT_BAND_ORDER[label.capability_fit])
        for opportunity_id, label in labels.items()
    ]
    score_by_band: dict[str, list[float]] = {}
    for opportunity_id, label in labels.items():
        score_by_band.setdefault(label.capability_fit.value, []).append(
            predictions[opportunity_id].fit_score
        )
    means = {
        band: round(sum(values) / len(values), 4)
        for band, values in sorted(score_by_band.items())
    }
    if len(pairs) < 2:
        return None, means
    score_ranks = _average_ranks([pair[0] for pair in pairs])
    label_ranks = _average_ranks([pair[1] for pair in pairs])
    return _pearson(score_ranks, label_ranks), means


def _average_ranks(values: list[float | int]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[order[position]] = average_rank
        start = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_sum * right_sum)
    if denominator == 0.0:
        return None
    return round(numerator / denominator, 6)


def _review_token(opportunity_id: str) -> str:
    material = f"fr008-w35-review-token-v1\0{opportunity_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]
