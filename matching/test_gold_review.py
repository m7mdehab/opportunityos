"""Contract tests for privacy-safe FR-008 gold-review sampling and labels."""
from __future__ import annotations

import json
import unittest
from dataclasses import fields

from matching.gold_review import (
    ActionabilityChoice,
    CapabilityFitBand,
    GoldReviewLabel,
    InsufficientStratumError,
    SamplingCandidate,
    TargetFamilyTier,
    deserialize_review_label,
    select_stratified,
    serialize_review_label,
)


class TestGoldReviewSampler(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = tuple(
            SamplingCandidate(f"synthetic-opportunity-{group}-{index:02d}", (group,))
            for group in ("employment", "independent")
            for index in range(12)
        )
        self.minimums = {("employment",): 4, ("independent",): 3}

    def test_selection_is_deterministic_and_independent_of_input_order(self) -> None:
        first = select_stratified(self.candidates, seed="fixture-seed-v1", minimums=self.minimums)
        second = select_stratified(
            reversed(self.candidates), seed="fixture-seed-v1", minimums=self.minimums
        )
        self.assertEqual(first, second)

    def test_selection_is_unique_and_meets_every_requested_quota(self) -> None:
        selected = select_stratified(self.candidates, seed="quota-seed", minimums=self.minimums)
        selected_ids = [item.opportunity_id for item in selected]
        self.assertEqual(len(selected_ids), len(set(selected_ids)))
        self.assertEqual(len(selected), 7)
        for stratum, minimum in self.minimums.items():
            self.assertEqual(sum(item.stratum == stratum for item in selected), minimum)

    def test_duplicate_candidate_ids_are_rejected(self) -> None:
        duplicate = SamplingCandidate(self.candidates[0].opportunity_id, ("independent",))
        with self.assertRaisesRegex(ValueError, "IDs must be unique"):
            select_stratified(
                (*self.candidates, duplicate), seed="duplicate-seed", minimums=self.minimums
            )

    def test_insufficient_or_absent_stratum_fails_without_partial_selection(self) -> None:
        short_pool = tuple(item for item in self.candidates if item.stratum == ("employment",))
        with self.assertRaises(InsufficientStratumError) as raised:
            select_stratified(
                short_pool,
                seed="short-seed",
                minimums={("employment",): 4, ("independent",): 1},
            )
        self.assertEqual(
            [(item.stratum, item.available, item.required) for item in raised.exception.deficits],
            [(("independent",), 0, 1)],
        )

    def test_invalid_candidate_and_quota_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SamplingCandidate("synthetic-id", (" ",))
        with self.assertRaises(ValueError):
            select_stratified(self.candidates, seed="seed", minimums={("employment",): True})


class TestGoldReviewLabels(unittest.TestCase):
    def make_label(self, **overrides: object) -> GoldReviewLabel:
        values: dict[str, object] = {
            "opportunity_id": "synthetic-review-id",
            "actionability": ActionabilityChoice.MAYBE_REVIEW,
            "capability_fit": CapabilityFitBand.GOOD_REALISTIC,
            "geography_correctness": True,
            "seniority_correctness": None,
            "required_skill_correctness": False,
            "expected_target_family_tier": TargetFamilyTier.ADJACENT,
            "reviewer_rationale": "Location evidence needs a second look.",
        }
        values.update(overrides)
        return GoldReviewLabel(**values)  # type: ignore[arg-type]

    def test_all_brief_actionability_choices_are_accepted(self) -> None:
        for choice in ActionabilityChoice:
            with self.subTest(choice=choice.value):
                label = self.make_label(actionability=choice.value)
                self.assertEqual(label.actionability, choice)

    def test_all_capability_bands_and_target_tiers_are_accepted(self) -> None:
        for band in CapabilityFitBand:
            with self.subTest(band=band.value):
                self.assertEqual(self.make_label(capability_fit=band.value).capability_fit, band)
        for tier in TargetFamilyTier:
            with self.subTest(tier=tier.value):
                self.assertEqual(
                    self.make_label(expected_target_family_tier=tier.value).expected_target_family_tier,
                    tier,
                )
        self.assertIsNone(self.make_label(expected_target_family_tier=None).expected_target_family_tier)

    def test_invalid_label_values_and_unreviewed_correctness_types_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.make_label(actionability="apply_now")
        with self.assertRaises(ValueError):
            self.make_label(capability_fit="medium")
        with self.assertRaises(ValueError):
            self.make_label(expected_target_family_tier="unknown")
        with self.assertRaises(TypeError):
            self.make_label(geography_correctness=1)
        with self.assertRaises(ValueError):
            self.make_label(schema_version=2)
        with self.assertRaises(ValueError):
            self.make_label(reviewer_rationale="  ")
        with self.assertRaises(ValueError):
            self.make_label(reviewer_rationale="r" * 501)

    def test_versioned_serialization_round_trips_only_allowlisted_fields(self) -> None:
        label = self.make_label()
        serialized = serialize_review_label(label)
        restored = deserialize_review_label(serialized)
        self.assertEqual(restored, label)

        payload = json.loads(serialized)
        self.assertEqual(
            set(payload),
            {
                "schema_version",
                "opportunity_id",
                "actionability",
                "capability_fit",
                "geography_correctness",
                "seniority_correctness",
                "required_skill_correctness",
                "expected_target_family_tier",
                "reviewer_rationale",
            },
        )
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(
            {field.name for field in fields(GoldReviewLabel)},
            set(payload),
        )

    def test_unlisted_source_content_fields_and_duplicate_json_fields_are_rejected(self) -> None:
        payload = json.loads(serialize_review_label(self.make_label()))
        payload["job_description"] = "synthetic source text must not be accepted"
        with self.assertRaisesRegex(ValueError, "unlisted fields"):
            deserialize_review_label(json.dumps(payload))

        base = serialize_review_label(self.make_label())
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            deserialize_review_label(base[:-1] + ',"opportunity_id":"second-id"}')

    def test_missing_fields_wrong_version_and_invalid_json_are_rejected(self) -> None:
        payload = json.loads(serialize_review_label(self.make_label()))
        del payload["reviewer_rationale"]
        with self.assertRaisesRegex(ValueError, "missing or unlisted"):
            deserialize_review_label(json.dumps(payload))

        payload = json.loads(serialize_review_label(self.make_label()))
        payload["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported schema_version"):
            deserialize_review_label(json.dumps(payload))

        with self.assertRaises(json.JSONDecodeError):
            deserialize_review_label("{")

    def test_labels_and_selections_have_no_source_content_fields(self) -> None:
        label = self.make_label()
        label_fields = {field.name for field in fields(label)}
        self.assertNotIn("title", label_fields)
        self.assertNotIn("description", label_fields)
        self.assertNotIn("founder_profile", label_fields)
        self.assertNotIn("job_text", label_fields)

        selection = select_stratified(
            [SamplingCandidate("synthetic-only-id", ("employment",))],
            seed="safe-seed",
            minimums={("employment",): 1},
        )[0]
        self.assertEqual({field.name for field in fields(selection)}, {"opportunity_id", "stratum"})


if __name__ == "__main__":
    unittest.main()
