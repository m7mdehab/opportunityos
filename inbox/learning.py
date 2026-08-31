"""Safe Learning & Experiment Governance Layer with Immutable Truth Authority."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from .analytics import ConversionMetric


@dataclass(frozen=True, slots=True)
class OptimizationRecommendation:
    """Versioned, non-mutating strategy recommendation."""
    recommendation_id: str
    dimension: str
    target_value: str
    suggested_action: str
    confidence: float
    evidence_basis: str
    requires_founder_approval: bool = True


class SafeLearningEngine:
    """Generates bounded optimization recommendations without modifying TruthGraph or permissions."""

    @classmethod
    def evaluate_conversion_insights(
        cls,
        metrics: Sequence[ConversionMetric],
    ) -> tuple[OptimizationRecommendation, ...]:
        """Generate recommendations strictly when sample size is sufficient and evidence is clear."""
        recs: list[OptimizationRecommendation] = []
        for m in metrics:
            if not m.is_sample_sufficient:
                continue  # Never claim causal superiority on tiny samples

            if m.interview_rate is not None and m.interview_rate > 0.30:
                recs.append(OptimizationRecommendation(
                    recommendation_id=f"rec-{m.dimension}-{m.dimension_value}",
                    dimension=m.dimension, target_value=m.dimension_value,
                    suggested_action=f"Increase discovery priority for high-converting {m.dimension} '{m.dimension_value}'",
                    confidence=0.85,
                    evidence_basis=f"Observed {m.interviews_count}/{m.total_applications} interview conversion rate ({m.interview_rate:.1%})",
                    requires_founder_approval=True,
                ))
        return tuple(recs)

    # Invariant checks: Asserting that learning engine CANNOT mutate TruthGraph or action authority
    def attempt_truth_mutation(self, *args, **kwargs) -> None:
        raise PermissionError("Learning loop is strictly forbidden from mutating TruthGraph facts or assertions")

    def attempt_permission_mutation(self, *args, **kwargs) -> None:
        raise PermissionError("Learning loop is strictly forbidden from altering Outbound Source Action permissions")
