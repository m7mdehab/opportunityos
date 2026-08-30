"""Deterministic Replay and Gold Set Benchmarks for Matching Subsystem."""
from __future__ import annotations

import unittest

from opportunity.models import RemotePolicy, SeniorityLevel, Track
from matching.compiler_employment import EmploymentArtifactCompiler
from matching.gold_set import BenchmarkItem, GoldSetHarness
from matching.models import QualificationDecision
from matching.scorer import OpportunityScorer
from matching.test_qualification import create_test_graph, create_test_opportunity


class TestDeterministicReplayAndGoldSet(unittest.TestCase):
    def setUp(self) -> None:
        self.truth_graph = create_test_graph()
        self.scorer = OpportunityScorer()
        self.compiler = EmploymentArtifactCompiler()
        self.harness = GoldSetHarness(scorer=self.scorer)

    def test_deterministic_scoring_replay(self) -> None:
        opp = create_test_opportunity()
        eval1 = self.scorer.evaluate(opp, self.truth_graph)
        eval2 = self.scorer.evaluate(opp, self.truth_graph)
        eval3 = self.scorer.evaluate(opp, self.truth_graph)

        self.assertEqual(eval1.overall_fit_score, eval2.overall_fit_score)
        self.assertEqual(eval2.overall_fit_score, eval3.overall_fit_score)
        self.assertEqual(eval1.qualification_decision, eval2.qualification_decision)
        self.assertEqual(eval1.score_breakdown, eval2.score_breakdown)

    def test_deterministic_artifact_hash_replay(self) -> None:
        opp = create_test_opportunity()
        cv1 = self.compiler.compile_tailored_cv(opp, self.truth_graph)
        cv2 = self.compiler.compile_tailored_cv(opp, self.truth_graph)

        self.assertEqual(cv1.artifact_hash, cv2.artifact_hash)
        self.assertEqual(len(cv1.sections), len(cv2.sections))
        self.assertEqual(len(cv1.generated_claims), len(cv2.generated_claims))

    def test_gold_set_benchmark_execution(self) -> None:
        # Standard benchmark fixtures across employment and procurement
        opp_high = create_test_opportunity(
            opp_id="bench-high-fit",
            title="Senior Distributed Systems Architect",
            skills=("Python", "Go"),
        )
        opp_low = create_test_opportunity(
            opp_id="bench-low-fit",
            title="Junior Frontend React Developer",
            skills=("React", "CSS", "JavaScript"),
        )
        opp_excluded = create_test_opportunity(
            opp_id="bench-excluded",
            geo_status="excluded",
        )

        items = (
            BenchmarkItem(
                item_id="item-high",
                opportunity=opp_high,
                expected_qualification=QualificationDecision.QUALIFIED,
                min_expected_fit_score=75.0,
                max_expected_fit_score=100.0,
                must_pass_constraints=("geographic_eligibility",),
                rationale="High fit backend role matching verified skills.",
            ),
            BenchmarkItem(
                item_id="item-low",
                opportunity=opp_low,
                expected_qualification=QualificationDecision.QUALIFIED,
                min_expected_fit_score=0.0,
                max_expected_fit_score=75.0,
                must_pass_constraints=("geographic_eligibility",),
                rationale="Low fit role with skill gaps.",
            ),
            BenchmarkItem(
                item_id="item-excluded",
                opportunity=opp_excluded,
                expected_qualification=QualificationDecision.INELIGIBLE,
                min_expected_fit_score=0.0,
                max_expected_fit_score=50.0,
                must_fail_constraints=("geographic_eligibility",),
                rationale="Geographically excluded opportunity.",
            ),
        )

        report = self.harness.run_benchmark(items, self.truth_graph)
        self.assertTrue(report.is_passing)
        self.assertEqual(report.qualification_accuracy, 1.0)
        self.assertEqual(report.total_items, 3)


if __name__ == "__main__":
    unittest.main()
