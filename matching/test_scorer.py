"""Tests for Multidimensional Scorer and Requirement Mapping."""
from __future__ import annotations

import unittest

from opportunity.models import Opportunity, Track
from matching.mapping import RequirementMapper
from matching.models import (
    QualificationDecision,
    RequirementSupportStatus,
    ScoringPolicy,
)
from matching.scorer import OpportunityScorer
from matching.test_qualification import create_test_graph, create_test_opportunity


class TestOpportunityScorerAndMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.truth_graph = create_test_graph()
        self.scorer = OpportunityScorer()
        self.mapper = RequirementMapper()

    def test_high_fit_employment_opportunity(self) -> None:
        opp = create_test_opportunity(
            skills=("Python", "Go"),
            title="Senior Distributed Systems Architect",
        )
        eval_res = self.scorer.evaluate(opp, self.truth_graph)
        self.assertEqual(eval_res.qualification_decision, QualificationDecision.QUALIFIED)
        self.assertTrue(eval_res.overall_fit_score >= 80.0)
        self.assertTrue(len(eval_res.strengths) > 0)
        self.assertTrue(len(eval_res.dimension_scores) >= 5)

    def test_low_fit_different_skills_opportunity(self) -> None:
        opp = create_test_opportunity(
            skills=("Rust", "Haskell", "Scala"),
            title="Junior Frontend Developer",
        )
        eval_res = self.scorer.evaluate(opp, self.truth_graph)
        self.assertTrue(eval_res.overall_fit_score < 70.0)
        self.assertTrue(len(eval_res.gaps) > 0)

    def test_requirement_mapping_classification(self) -> None:
        opp = create_test_opportunity(
            skills=("Python", "Rust"),
        )
        req_map = self.mapper.map_requirements(opp, self.truth_graph)
        self.assertEqual(req_map.opportunity_id, opp.id)
        statuses = [m.status for m in req_map.mappings]
        self.assertIn(RequirementSupportStatus.SUPPORTED, statuses)  # Python
        self.assertIn(RequirementSupportStatus.GAP, statuses)        # Rust


if __name__ == "__main__":
    unittest.main()
