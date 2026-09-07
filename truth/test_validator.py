import unittest

from truth.fixtures import (
    PROHIBITED_CLAIMS,
    UNBACKED_CLAIMS,
    VERIFIED_CLAIMS,
    synthetic_graph,
)
from truth.models import AssertionType, EvidenceRecord, VerificationStatus
from truth.validator import ClaimValidator


class ClaimValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = ClaimValidator(synthetic_graph())

    def test_verified_gold_claims_are_traceable(self):
        for claim in VERIFIED_CLAIMS:
            with self.subTest(claim=claim):
                result = self.validator.validate_claim(claim)
                self.assertTrue(result.allowed, result.reasons)
                self.assertTrue(result.evidence_ids)
                self.assertIn(
                    result.assertion_type,
                    {
                        AssertionType.DIRECT_FACT,
                        AssertionType.NORMALIZED_FACT,
                        AssertionType.DERIVED_CAPABILITY,
                    },
                )

    def test_unbacked_gold_claims_are_rejected(self):
        for claim in UNBACKED_CLAIMS:
            with self.subTest(claim=claim):
                result = self.validator.validate_claim(claim)
                self.assertFalse(result.allowed)
                self.assertEqual(AssertionType.UNSUPPORTED_CLAIM, result.assertion_type)

    def test_prohibited_gold_claims_are_rejected(self):
        for claim in PROHIBITED_CLAIMS:
            with self.subTest(claim=claim):
                result = self.validator.validate_claim(claim)
                self.assertFalse(result.allowed)
                self.assertEqual(AssertionType.PROHIBITED_CLAIM, result.assertion_type)

    def test_metric_requires_exact_value_and_verified_metric_node(self):
        verified = self.validator.validate_claim(
            "Built a synthetic reporting pipeline that reduced processing time by 40%."
        )
        injected = self.validator.validate_claim(
            "Built a synthetic reporting pipeline that reduced processing time by 90%."
        )
        approximate = self.validator.validate_claim(
            "Approximately 25 source systems were assessed."
        )
        self.assertTrue(verified.allowed)
        self.assertFalse(injected.allowed)
        self.assertFalse(approximate.allowed)
        self.assertIn("verified metric", approximate.reasons[0])

    def test_approximate_non_metric_claim_must_be_qualified(self):
        graph = synthetic_graph()
        graph.add_evidence(
            EvidenceRecord(
                "ev-approx-text", "large dataset", "fixture", "summary",
                verification_status=VerificationStatus.APPROXIMATE,
            )
        )
        validator = ClaimValidator(graph)
        self.assertTrue(validator.validate_claim("Approximately a large dataset").allowed)
        self.assertFalse(validator.validate_claim("A large dataset").allowed)

    def test_requested_evidence_must_support_the_claim(self):
        result = self.validator.validate_claim(
            "Offers analytics pipeline assessments.", ("ev-python",)
        )
        self.assertFalse(result.allowed)
        self.assertIn("no evidence", result.reasons[0])

    def test_unknown_and_explicit_null_evidence_fail_closed(self):
        unknown = self.validator.validate_claim("A claim", ("missing",))
        null = self.validator.validate_claim("Legal capacity is confirmed", ("ev-legal-null",))
        self.assertFalse(unknown.allowed)
        self.assertIn("unknown evidence", unknown.reasons[0])
        self.assertFalse(null.allowed)

    def test_red_lines_and_never_claims_are_case_insensitive(self):
        red = self.validator.validate_claim("We GUARANTEE the outcome.")
        never = self.validator.validate_claim("Experience serving FORTUNE 500 CLIENTS worldwide.")
        self.assertFalse(red.allowed)
        self.assertFalse(never.allowed)
        self.assertIn("red line", red.reasons[0])
        self.assertIn("never-claim", never.reasons[0])

    def test_planned_credential_can_only_be_described_as_planned(self):
        planned = self.validator.validate_claim(VERIFIED_CLAIMS[3])
        held = self.validator.validate_claim(
            "Holds the Example Cloud Architect certification."
        )
        ambiguous = self.validator.validate_claim("Example Cloud Architect certified professional.")
        self.assertTrue(planned.allowed)
        self.assertFalse(held.allowed)
        self.assertFalse(ambiguous.allowed)

    def test_batch_and_require_valid_preserve_input_order(self):
        results = self.validator.validate_claims((VERIFIED_CLAIMS[1], UNBACKED_CLAIMS[0]))
        self.assertEqual((VERIFIED_CLAIMS[1], UNBACKED_CLAIMS[0]), tuple(r.claim for r in results))
        with self.assertRaisesRegex(ValueError, "rejected claims"):
            self.validator.require_valid((VERIFIED_CLAIMS[1], UNBACKED_CLAIMS[0]))

    def test_adr_0018_phone_tokens_are_not_parsed_as_metrics(self):
        from truth.validator import _parse_structured_metrics_with_context

        # Phone numbers should NOT be parsed as metrics
        self.assertEqual([], _parse_structured_metrics_with_context("+20-555-0101"))
        self.assertEqual([], _parse_structured_metrics_with_context("+1-555-0199"))
        self.assertEqual([], _parse_structured_metrics_with_context("+20 100 123 4567"))
        self.assertEqual([], _parse_structured_metrics_with_context("Call me at +20-555-0101 today"))

        # Real quantified metrics MUST still be parsed
        team_metric = _parse_structured_metrics_with_context("led a team of 20")
        self.assertEqual(1, len(team_metric))
        self.assertEqual(20, team_metric[0][0])
        self.assertEqual("count", team_metric[0][1])

        percent_metric = _parse_structured_metrics_with_context("increased speed by 25%")
        self.assertEqual(1, len(percent_metric))
        self.assertEqual(25, percent_metric[0][0])
        self.assertEqual("%", percent_metric[0][1])


if __name__ == "__main__":
    unittest.main()

