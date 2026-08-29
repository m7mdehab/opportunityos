import random
import re
import unittest

from truth.fixtures import PROHIBITED_CLAIMS, UNBACKED_CLAIMS, VERIFIED_CLAIMS, synthetic_graph
from truth.ingest import IngestionError, graph_from_dict, load_yaml
from truth.models import AssertionType
from truth.validator import ClaimValidator


class AdversarialTruthTests(unittest.TestCase):
    def setUp(self):
        self.validator = ClaimValidator(synthetic_graph())

    def test_metric_substitution_never_inherits_original_provenance(self):
        original = VERIFIED_CLAIMS[0]
        for injected_value in (0, 1, 39, 41, 90, 400, 999999):
            claim = original.replace("40%", f"{injected_value}%")
            with self.subTest(claim=claim):
                result = self.validator.validate_claim(claim, ("ev-achievement",))
                self.assertFalse(result.allowed)
                self.assertEqual(AssertionType.UNSUPPORTED_CLAIM, result.assertion_type)

    def test_evidence_laundering_cannot_append_an_unbacked_skill(self):
        result = self.validator.validate_claim(
            "Uses Python for data engineering and Kubernetes.", ("ev-python",)
        )
        self.assertFalse(result.allowed)
        self.assertIn("no evidence record supports", result.reasons[0])

    def test_many_evidence_ids_do_not_make_an_unrelated_claim_true(self):
        all_ids = tuple(synthetic_graph().evidence_records)
        result = self.validator.validate_claim("Managed 50 engineers.", all_ids)
        self.assertFalse(result.allowed)

    def test_forbidden_phrases_survive_case_and_whitespace_obfuscation(self):
        variants = (
            "FORTUNE 500 CLIENTS",
            "fortune   500\nclients",
            "We GuArAnTeE the result",
            "This GUARANTEES success",
        )
        for claim in variants:
            with self.subTest(claim=claim):
                self.assertFalse(self.validator.validate_claim(claim).allowed)

    def test_planned_certification_held_verbs_are_all_rejected(self):
        for verb in ("holds", "earned", "obtained", "completed", "was awarded"):
            claim = f"The professional {verb} the Example Cloud Architect certification."
            with self.subTest(verb=verb):
                self.assertFalse(self.validator.validate_claim(claim).allowed)

    def test_explicit_null_cannot_be_coerced_into_a_fact(self):
        claims = (
            "Legal capacity is confirmed.",
            "Legal capacity is individual contractor.",
            "The founder may bid as a registered entity.",
        )
        for claim in claims:
            with self.subTest(claim=claim):
                self.assertFalse(
                    self.validator.validate_claim(claim, ("ev-legal-null",)).allowed
                )

    def test_seeded_case_and_space_mutations_are_deterministic(self):
        rng = random.Random(2002)
        base = VERIFIED_CLAIMS[1]
        outcomes = []
        for _ in range(100):
            characters = [character.upper() if rng.randrange(2) else character.lower() for character in base]
            mutated = "".join(characters)
            mutated = re.sub(r" ", lambda _: " " * rng.randint(1, 4), mutated)
            result = self.validator.validate_claim(mutated)
            outcomes.append((result.allowed, result.evidence_ids))
        self.assertEqual(1, len(set(outcomes)))
        allowed, ev_ids = outcomes[0]
        self.assertTrue(allowed)
        self.assertIn("ev-python", ev_ids)

    def test_all_seeded_bad_claims_reject_in_batch(self):
        results = self.validator.validate_claims(PROHIBITED_CLAIMS + UNBACKED_CLAIMS)
        self.assertEqual(len(PROHIBITED_CLAIMS + UNBACKED_CLAIMS), len(results))
        self.assertTrue(all(not result.allowed for result in results))

    def test_yaml_tags_aliases_and_block_payloads_are_not_interpreted(self):
        payloads = (
            "evidence: !!python/object/apply:os.system ['echo unsafe']",
            "evidence: &anchor []\ncareer_profile: *anchor",
            "evidence: |\n  injected",
            "evidence: >\n  folded",
        )
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(IngestionError):
                load_yaml(payload)

    def test_mapping_types_and_booleans_cannot_pass_integer_fields(self):
        base = {
            "evidence": [
                {"id": "ev", "content": "capacity", "source": "fixture", "locator": "capacity"}
            ],
            "capability_profile": {
                "id": "cap", "capacity": {
                    "id": "capacity", "evidence_ids": ["ev"], "hours_per_week": True,
                },
            },
        }
        with self.assertRaises(IngestionError):
            graph_from_dict(base)

    def test_repeated_validation_has_no_stateful_drift(self):
        claim = VERIFIED_CLAIMS[0]
        baseline = self.validator.validate_claim(claim)
        for _ in range(100):
            self.assertEqual(baseline, self.validator.validate_claim(claim))


if __name__ == "__main__":
    unittest.main()
