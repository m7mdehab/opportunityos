"""Gold Set Benchmarking and Evaluation Harness for OpportunityOS Matching Subsystem.

Provides standardized evaluation fixtures and scoring metrics for regression testing
and future founder-labeled precision tuning without fabricating founder labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from opportunity.models import Opportunity, RemotePolicy, SeniorityLevel, Track
from truth.graph import TruthGraph

from .models import (
    MatchEvaluation,
    QualificationDecision,
    ScoringPolicy,
)
from .qualification import QualificationEngine
from .scorer import OpportunityScorer


@dataclass(frozen=True, slots=True)
class BenchmarkItem:
    """An opportunity benchmark fixture paired with expected evaluation criteria."""
    item_id: str
    opportunity: Opportunity
    expected_qualification: QualificationDecision
    min_expected_fit_score: float
    max_expected_fit_score: float
    must_pass_constraints: tuple[str, ...] = ()
    must_fail_constraints: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Evaluation summary over a benchmark suite."""
    total_items: int
    qualification_matches: int
    qualification_accuracy: float
    score_bound_matches: int
    constraint_matches: int
    is_passing: bool
    item_results: tuple[dict[str, Any], ...] = ()


class GoldSetHarness:
    """Runs evaluation benchmarks against matching and qualification engines."""

    def __init__(self, scorer: OpportunityScorer | None = None) -> None:
        self.scorer = scorer or OpportunityScorer()

    def run_benchmark(self, items: Sequence[BenchmarkItem], truth_graph: TruthGraph) -> BenchmarkReport:
        """Evaluate a sequence of benchmark items and compute accuracy metrics."""
        qual_matches = 0
        score_matches = 0
        constraint_matches = 0
        item_results: list[dict[str, Any]] = []

        for item in items:
            eval_res = self.scorer.evaluate(item.opportunity, truth_graph)
            
            # Check qualification match
            is_qual_ok = (eval_res.qualification_decision == item.expected_qualification)
            if is_qual_ok:
                qual_matches += 1

            # Check score bounds
            is_score_ok = (item.min_expected_fit_score <= eval_res.overall_fit_score <= item.max_expected_fit_score)
            if is_score_ok:
                score_matches += 1

            # Check must-pass / must-fail constraints
            passed_names = {c.constraint_name for c in eval_res.hard_constraints if c.passed is True}
            failed_names = {c.constraint_name for c in eval_res.hard_constraints if c.passed is False}
            
            must_pass_ok = all(name in passed_names for name in item.must_pass_constraints)
            must_fail_ok = all(name in failed_names for name in item.must_fail_constraints)
            is_constraint_ok = must_pass_ok and must_fail_ok
            if is_constraint_ok:
                constraint_matches += 1

            item_results.append({
                "item_id": item.item_id,
                "qualification_actual": eval_res.qualification_decision.value,
                "qualification_expected": item.expected_qualification.value,
                "score_actual": eval_res.overall_fit_score,
                "is_qual_ok": is_qual_ok,
                "is_score_ok": is_score_ok,
                "is_constraint_ok": is_constraint_ok,
            })

        total = len(items)
        qual_acc = (qual_matches / total) if total > 0 else 1.0
        is_passing = (qual_matches == total and score_matches == total and constraint_matches == total)

        return BenchmarkReport(
            total_items=total,
            qualification_matches=qual_matches,
            qualification_accuracy=round(qual_acc, 3),
            score_bound_matches=score_matches,
            constraint_matches=constraint_matches,
            is_passing=is_passing,
            item_results=tuple(item_results),
        )
