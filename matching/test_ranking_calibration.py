from __future__ import annotations

import json
import unittest

from matching.gold_review import (
    ActionabilityChoice,
    CapabilityFitBand,
    GoldReviewLabel,
    TargetFamilyTier,
)
from matching.ranking_calibration import (
    MINIMUM_GOLD_SET_SIZE,
    RankingPrediction,
    evaluate_gold_review,
)


class RankingCalibrationTest(unittest.TestCase):
    def _label(
        self,
        opportunity_id: str,
        *,
        action: ActionabilityChoice = ActionabilityChoice.MAYBE_REVIEW,
        fit: CapabilityFitBand = CapabilityFitBand.GOOD_REALISTIC,
        geo: bool | None = True,
        seniority: bool | None = True,
        skills: bool | None = True,
        tier: TargetFamilyTier | None = TargetFamilyTier.PRIMARY,
        rationale: str = "Synthetic contract fixture.",
    ) -> GoldReviewLabel:
        return GoldReviewLabel(
            opportunity_id=opportunity_id,
            actionability=action,
            capability_fit=fit,
            geography_correctness=geo,
            seniority_correctness=seniority,
            required_skill_correctness=skills,
            expected_target_family_tier=tier,
            reviewer_rationale=rationale,
        )

    def test_metrics_cover_ineligibility_review_order_tier_and_fit_correlation(self):
        labels = [
            self._label("syn-a", action=ActionabilityChoice.DEFINITELY_APPLY, fit=CapabilityFitBand.EXCEPTIONAL_DIRECT),
            self._label("syn-b", action=ActionabilityChoice.LIKELY_APPLY, fit=CapabilityFitBand.STRONG, tier=TargetFamilyTier.ADJACENT),
            self._label("syn-c", action=ActionabilityChoice.PROBABLY_SKIP, fit=CapabilityFitBand.WEAK, tier=TargetFamilyTier.NOT_TARGET, geo=False),
            self._label("syn-d", action=ActionabilityChoice.DEFINITELY_INELIGIBLE, fit=CapabilityFitBand.STRETCH, tier=TargetFamilyTier.STRETCH, geo=None),
            self._label("syn-e", action=ActionabilityChoice.DEFINITELY_APPLY, fit=CapabilityFitBand.GOOD_REALISTIC, tier=TargetFamilyTier.ADJACENT, seniority=False),
        ]
        predictions = [
            RankingPrediction("syn-a", "qualified", 96, 1000, "primary"),
            RankingPrediction("syn-b", "qualified", 85, 900, "adjacent"),
            RankingPrediction("syn-c", "uncertain", 25, 500, "not_target"),
            RankingPrediction("syn-d", "uncertain", 45, 200, None),
            RankingPrediction("syn-e", "ineligible", 72, 100, "adjacent"),
        ]

        report = evaluate_gold_review(labels, predictions)

        self.assertFalse(report.minimum_sample_met)
        self.assertEqual(report.total_items, 5)
        self.assertEqual(report.hard_ineligible_precision, 0.0)
        self.assertEqual(report.hard_ineligible_true_positives, 0)
        self.assertEqual(report.hard_ineligible_false_positives, 1)
        self.assertEqual(report.hard_ineligible_false_negatives, 1)
        self.assertEqual(len(report.false_positive_tokens), 1)
        self.assertEqual(len(report.false_negative_tokens), 1)
        self.assertEqual(report.geography_correctness_rate, 0.75)
        self.assertEqual(report.geography_labeled_items, 4)
        self.assertEqual(report.seniority_correctness_rate, 0.8)
        self.assertEqual(report.required_skill_correctness_rate, 1.0)
        self.assertEqual(report.target_tier_accuracy, 0.8)
        self.assertEqual(report.recommended_comparison_pairs, 3)
        self.assertEqual(report.recommended_apply_over_skip_accuracy, round(2 / 3, 6))
        self.assertGreater(report.fit_score_spearman_rho, 0.0)
        self.assertEqual(report.fit_score_mean_by_band["weak"], 25.0)
        target_results = report.to_dict()["targets"]
        self.assertFalse(target_results["hard_ineligible_precision"]["met"])
        self.assertFalse(target_results["geography_correctness"]["met"])
        self.assertFalse(target_results["target_tier_accuracy"]["met"])
        self.assertFalse(target_results["recommended_apply_over_skip_accuracy"]["met"])

    def test_tie_uses_the_feed_opportunity_id_tie_break(self):
        labels = [
            self._label("syn-a", action=ActionabilityChoice.DEFINITELY_APPLY),
            self._label("syn-b", action=ActionabilityChoice.PROBABLY_SKIP),
        ]
        predictions = [
            RankingPrediction("syn-a", "qualified", 70, 100, "primary"),
            RankingPrediction("syn-b", "qualified", 60, 100, "primary"),
        ]
        report = evaluate_gold_review(labels, predictions)
        self.assertEqual(report.recommended_apply_over_skip_accuracy, 1.0)

    def test_report_contains_only_aggregates_and_hashed_review_tokens(self):
        labels = [
            self._label(
                "private-real-job-id",
                action=ActionabilityChoice.DEFINITELY_APPLY,
                rationale="Private rationale that must not enter a report.",
            ),
            self._label("syn-skip", action=ActionabilityChoice.PROBABLY_SKIP),
        ]
        predictions = [
            RankingPrediction("private-real-job-id", "ineligible", 10, 1, "stretch"),
            RankingPrediction("syn-skip", "qualified", 20, 2, "primary"),
        ]
        serialized = json.dumps(evaluate_gold_review(labels, predictions).to_dict())
        self.assertIn("false_positive_tokens", serialized)
        self.assertNotIn("private-real-job-id", serialized)
        self.assertNotIn("Private rationale", serialized)

    def test_unavailable_metrics_are_null_and_explained(self):
        report = evaluate_gold_review(
            [self._label("syn-only", action=ActionabilityChoice.MAYBE_REVIEW, geo=None, seniority=None, skills=None, tier=None)],
            [RankingPrediction("syn-only", "uncertain", 50, 10, None)],
        )
        self.assertIsNone(report.hard_ineligible_precision)
        self.assertIsNone(report.geography_correctness_rate)
        self.assertIsNone(report.seniority_correctness_rate)
        self.assertIsNone(report.required_skill_correctness_rate)
        self.assertIsNone(report.target_tier_accuracy)
        self.assertIsNone(report.recommended_apply_over_skip_accuracy)
        self.assertIsNone(report.fit_score_spearman_rho)
        self.assertIsNone(report.to_dict()["targets"]["hard_ineligible_precision"]["met"])
        self.assertGreaterEqual(len(report.limitations), 7)

    def test_only_matching_unique_ids_are_accepted(self):
        label = self._label("syn-a")
        prediction = RankingPrediction("syn-a", "qualified", 75, 100)
        with self.assertRaisesRegex(ValueError, "same IDs"):
            evaluate_gold_review([label], [RankingPrediction("syn-b", "qualified", 75, 100)])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluate_gold_review([label, label], [prediction, prediction])

    def test_predictions_reject_invalid_scores_and_decisions(self):
        with self.assertRaisesRegex(ValueError, "fit_score must be at most"):
            RankingPrediction("syn-a", "qualified", 101, 100)
        with self.assertRaisesRegex(ValueError, "finite number"):
            RankingPrediction("syn-a", "qualified", 50, float("nan"))
        with self.assertRaisesRegex(ValueError, "recognized FR-008 decision"):
            RankingPrediction("syn-a", "skip", 50, 100)

    def test_sample_count_does_not_attest_real_founder_review(self):
        self.assertEqual(MINIMUM_GOLD_SET_SIZE, 150)
        labels = [
            self._label(f"synthetic-{index:03d}")
            for index in range(MINIMUM_GOLD_SET_SIZE)
        ]
        predictions = [
            RankingPrediction(f"synthetic-{index:03d}", "qualified", 50, float(index))
            for index in range(MINIMUM_GOLD_SET_SIZE)
        ]
        report = evaluate_gold_review(labels, predictions)
        self.assertEqual(report.total_items, MINIMUM_GOLD_SET_SIZE)
        self.assertFalse(report.minimum_sample_met)
        self.assertTrue(any("Founder review" in item for item in report.limitations))


if __name__ == "__main__":
    unittest.main()
