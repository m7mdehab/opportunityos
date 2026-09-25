from __future__ import annotations

import unittest
from datetime import date

from storage.ranking import (
    eligibility_tier,
    feed_ranking_components,
    posting_freshness_score,
    recommended_priority_score,
    source_confidence_score,
)


class RecommendedRankingTest(unittest.TestCase):
    def _score(self, **overrides):
        values = {
            "decision": "qualified",
            "fit_score": 70.0,
            "preference_score": 50.0,
            "confidence_score": 50.0,
            "freshness_score": 50.0,
            "source_confidence": 50.0,
            "rank_penalty": 0,
        }
        values.update(overrides)
        return recommended_priority_score(**values)

    def test_eligibility_tiers_are_explicit(self) -> None:
        self.assertEqual(eligibility_tier("qualified"), ("eligible", 2))
        self.assertEqual(eligibility_tier("uncertain"), ("review_required", 1))
        self.assertEqual(eligibility_tier("ineligible"), ("ineligible", 0))

    def test_priority_uses_the_brief_component_order(self) -> None:
        baseline = self._score()
        self.assertGreater(baseline, self._score(decision="uncertain", fit_score=100))
        self.assertGreater(self._score(fit_score=71), baseline)
        self.assertGreater(self._score(preference_score=51), baseline)
        self.assertGreater(self._score(confidence_score=51), baseline)
        self.assertGreater(self._score(freshness_score=51), baseline)
        self.assertGreater(self._score(source_confidence=51), baseline)

        self.assertGreater(
            self._score(fit_score=71, preference_score=0),
            self._score(fit_score=70, preference_score=100),
        )
        self.assertGreater(
            self._score(decision="qualified", fit_score=0),
            self._score(decision="uncertain", fit_score=100),
        )

    def test_null_components_use_neutral_order_buckets_without_fabricating_payload_values(self) -> None:
        self.assertEqual(
            self._score(preference_score=None, confidence_score=None, freshness_score=None, source_confidence=None),
            self._score(preference_score=50, confidence_score=50, freshness_score=50, source_confidence=50),
        )
        payload = feed_ranking_components(
            decision="qualified",
            fit_score=73.25,
            priority_score=123456.0,
            evaluation_detail={"preference_score": None, "confidence_score": None, "confidence_factors": []},
            posted_date=None,
            is_stale=False,
            as_of=date(2026, 9, 25),
        )
        self.assertEqual(payload["priority_score"], 123456.0)
        self.assertEqual(payload["eligibility"], "eligible")
        self.assertEqual(payload["capability_fit"], 73.25)
        self.assertIsNone(payload["preference_score"])
        self.assertIsNone(payload["confidence_score"])
        self.assertIsNone(payload["freshness_score"])
        self.assertIsNone(payload["source_confidence"])

    def test_posting_freshness_and_source_confidence_read_synthetic_evidence(self) -> None:
        as_of = date(2026, 9, 25)
        self.assertEqual(posting_freshness_score("2026-09-24", is_stale=False, as_of=as_of), 100.0)
        self.assertEqual(posting_freshness_score(None, is_stale=True, as_of=as_of), 0.0)
        self.assertIsNone(posting_freshness_score(None, is_stale=False, as_of=as_of))
        detail = {"confidence_factors": [
            {"name": "source_freshness_and_strength", "score": 84.5},
        ]}
        self.assertEqual(source_confidence_score(detail), 84.5)
        self.assertIsNone(source_confidence_score({"confidence_factors": []}))

    def test_rank_only_filter_is_an_explicit_outer_demotion_tier(self) -> None:
        self.assertGreater(
            self._score(decision="uncertain", fit_score=100, rank_penalty=0),
            self._score(decision="qualified", fit_score=100, rank_penalty=1),
        )
        score = self._score(rank_penalty=10)
        self.assertEqual(score, self._score(rank_penalty=10))
        self.assertLess(abs(score), 2**53)


if __name__ == "__main__":
    unittest.main()
