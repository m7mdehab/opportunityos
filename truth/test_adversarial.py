from datetime import date
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
        self.assertTrue(any("absent from evidence" in r or "no evidence record supports" in r for r in result.reasons))

    def test_many_evidence_ids_do_not_make_an_unrelated_claim_true(self):
        all_ids = tuple(synthetic_graph().evidence_records)
        result = self.validator.validate_claim("Managed 50 engineers.", all_ids)
        self.assertFalse(result.allowed)

    def test_forbidden_phrases_survive_case_and_whitespace_obfuscation(self):
        variants = (
            "FORTUNE 500 CLIENTS",
            "fortune   500\nclients",
            "Fortune-500 Clients",
            "Fortune.500.Clients",
            "We GuArAnTeE the result",
            "This GUARANTEES success",
            "We Guarantee!",
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

    def test_cross_evidence_relationship_laundering_is_rejected(self):
        counterexamples = (
            # 1. Employer + unrelated skill
            ("Uses Python for data engineering at Synthetic Analytics Ltd.", ("ev-org", "ev-python")),
            # 2. Client/Institution + unrelated achievement
            ("Built a synthetic reporting pipeline that reduced processing time by 40% at Example Institute.", ("ev-degree", "ev-achievement")),
            # 3. Project + unrelated tool
            ("Delivered a synthetic data quality assessment using Python.", ("ev-portfolio", "ev-python")),
            # 4. Timeframe + unrelated capability
            ("From 2022-01-01 to 2024-06-30, offered analytics pipeline assessments.", ("ev-dates", "ev-service")),
            # 5. Role + unrelated service
            ("Data Engineer offers analytics pipeline assessments.", ("ev-title", "ev-service")),
            # 6. Two individually supported facts joined into unsupported relational statement
            ("Pursuing Example Cloud Architect certification at Synthetic Analytics Ltd.", ("ev-org", "ev-cert-plan")),
        )
        for claim, ev_ids in counterexamples:
            with self.subTest(claim=claim):
                result = self.validator.validate_claim(claim, ev_ids)
                self.assertFalse(result.allowed, f"Claim should have been rejected: {claim}")
                self.assertEqual(AssertionType.UNSUPPORTED_CLAIM, result.assertion_type)
                self.assertTrue(
                    any("composite claim combines independent evidence records" in r or "absent from evidence" in r or "no evidence record supports" in r for r in result.reasons),
                    f"Unexpected reasons: {result.reasons}",
                )

    def test_epistemic_assertion_type_laundering_is_prevented(self):
        from truth.models import EvidenceRecord, VerificationStatus, EmploymentRecord, SkillRecord, CareerProfile
        from truth.graph import TruthGraph

        ev_fact = EvidenceRecord("ev-f", "Direct employer fact.", "src", "loc", assertion_type=AssertionType.DIRECT_FACT)
        ev_derived = EvidenceRecord("ev-d", "Derived consulting capability.", "src", "loc", assertion_type=AssertionType.DERIVED_CAPABILITY)
        ev_user = EvidenceRecord("ev-u", "Self-declared user assertion.", "src", "loc", assertion_type=AssertionType.USER_ASSERTION)

        # 1. Direct fact alone is direct fact
        g1 = TruthGraph((ev_fact,))
        v1 = ClaimValidator(g1)
        r1 = v1.validate_claim("Direct employer fact.", ("ev-f",))
        self.assertTrue(r1.allowed)
        self.assertEqual(AssertionType.DIRECT_FACT, r1.assertion_type)

        # 2. Derived capability alone is derived capability
        g2 = TruthGraph((ev_derived,))
        v2 = ClaimValidator(g2)
        r2 = v2.validate_claim("Derived consulting capability.", ("ev-d",))
        self.assertTrue(r2.allowed)
        self.assertEqual(AssertionType.DERIVED_CAPABILITY, r2.assertion_type)

        # 3. User assertion alone is user assertion
        g3 = TruthGraph((ev_user,))
        v3 = ClaimValidator(g3)
        r3 = v3.validate_claim("Self-declared user assertion.", ("ev-u",))
        self.assertTrue(r3.allowed)
        self.assertEqual(AssertionType.USER_ASSERTION, r3.assertion_type)

        # 4. Mixed DERIVED_CAPABILITY + DIRECT_FACT under common parent cannot upgrade to DIRECT_FACT
        emp = EmploymentRecord("emp-mix", "Org", "Title", date(2020, 1, 1), None, evidence_ids=("ev-f", "ev-d"))
        profile = CareerProfile("prof-mix", employment=(emp,))
        g4 = TruthGraph((ev_fact, ev_derived))
        g4.add_career_profile(profile)
        v4 = ClaimValidator(g4)
        r4 = v4.validate_claim("Direct employer fact. Derived consulting capability.", ("ev-f", "ev-d"))
        if r4.allowed:
            self.assertEqual(AssertionType.DERIVED_CAPABILITY, r4.assertion_type)

        # 5. Mixed USER_ASSERTION + DIRECT_FACT under common parent must resolve to USER_ASSERTION
        emp_u = EmploymentRecord("emp-u", "Org", "Title", date(2020, 1, 1), None, evidence_ids=("ev-f", "ev-u"))
        profile_u = CareerProfile("prof-u", employment=(emp_u,))
        g5 = TruthGraph((ev_fact, ev_user))
        g5.add_career_profile(profile_u)
        v5 = ClaimValidator(g5)
        r5 = v5.validate_claim("Direct employer fact. Self-declared user assertion.", ("ev-f", "ev-u"))
        if r5.allowed:
            self.assertEqual(AssertionType.USER_ASSERTION, r5.assertion_type)

    def test_metric_provenance_laundering_is_rejected(self):
        from truth.models import EvidenceRecord, Achievement, MetricVerification, EmploymentRecord, CareerProfile
        from truth.graph import TruthGraph

        ev_verified = EvidenceRecord("ev-v", "Reduced latency by 40%.", "src", "loc")
        ev_unverified = EvidenceRecord("ev-u", "Increased revenue by 500%.", "src", "loc")
        ev_diff_num = EvidenceRecord("ev-num", "Managed 40 projects.", "src", "loc")

        ach_v = Achievement("ach-v", "Reduced latency by 40%.", ("ev-v",), MetricVerification.VERIFIED)
        ach_u = Achievement("ach-u", "Increased revenue by 500%.", ("ev-u",), MetricVerification.UNAVAILABLE)
        ach_num = Achievement("ach-num", "Managed 40 projects.", ("ev-num",), MetricVerification.UNAVAILABLE)

        emp = EmploymentRecord("emp-metrics", "Org", "Title", date(2020, 1, 1), None, ("ev-v", "ev-u", "ev-num"), achievements=(ach_v, ach_u, ach_num))
        profile = CareerProfile("prof-metrics", employment=(emp,))
        graph = TruthGraph((ev_verified, ev_unverified, ev_diff_num))
        graph.add_career_profile(profile)
        validator = ClaimValidator(graph)

        # 1. Unverified metric alone fails
        r1 = validator.validate_claim("Increased revenue by 500%.", ("ev-u",))
        self.assertFalse(r1.allowed)
        self.assertTrue(any("verified metric" in reason for reason in r1.reasons))

        # 2. Verified metric + unverified metric in same claim fails
        r2 = validator.validate_claim("Reduced latency by 40% and increased revenue by 500%.", ("ev-v", "ev-u"))
        self.assertFalse(r2.allowed)
        self.assertTrue(any("verified metric" in reason for reason in r2.reasons))

        # 3. Metric value tampering (40% vs 40 projects)
        r3 = validator.validate_claim("Managed 40 projects.", ("ev-num",))
        self.assertFalse(r3.allowed)

    def test_never_claim_semantic_paraphrase_protection(self):
        from truth.models import EvidenceRecord, NeverClaimRule, ProhibitedConceptCategory, CareerProfile
        from truth.graph import TruthGraph

        # Paraphrases with synonyms, reordered words, and alternate syntax
        forbidden_paraphrases = (
            "We guarantee 100% success on all deliverables.",
            "Results are guaranteed unconditionally.",
            "Zero risk and assured positive ROI.",
            "Guaranteeing satisfaction for all clients.",
            "Worked with top Fortune 500 enterprise clients.",
            "Fortune 500 experience in data platforms.",
            "Providing formal legal representation and binding counsel.",
        )
        for claim in forbidden_paraphrases:
            with self.subTest(claim=claim):
                result = self.validator.validate_claim(claim)
                self.assertFalse(result.allowed)
                self.assertEqual(AssertionType.PROHIBITED_CLAIM, result.assertion_type)

        # Never-Claim overrides even if supporting evidence exists
        ev_fake = EvidenceRecord("ev-fake", "We guarantee results for Fortune 500 clients.", "fake_cv", "loc")
        g_fake = TruthGraph((ev_fake,))
        rule1 = NeverClaimRule("nc-guar", ProhibitedConceptCategory.GUARANTEED_OUTCOME, "no guarantees", r"\bguarantee\b")
        rule2 = NeverClaimRule("nc-f500", ProhibitedConceptCategory.FORTUNE_500_PRESTIGE, "no f500", r"\bfortune\s*500\b")
        g_fake.add_career_profile(CareerProfile("p-fake", red_lines=(), never_claims=(rule1, rule2)))
        v_fake = ClaimValidator(g_fake)
        r_fake = v_fake.validate_claim("We guarantee results for Fortune 500 clients.", ("ev-fake",))
        self.assertFalse(r_fake.allowed)
        self.assertEqual(AssertionType.PROHIBITED_CLAIM, r_fake.assertion_type)

    def test_business_capacity_strict_numeric_validation(self):
        from truth.models import BusinessCapacity
        import math

        invalid_values = (
            True, False, float("nan"), float("inf"), float("-inf"), -1, -0.001, -1000,
        )
        for val in invalid_values:
            with self.subTest(val=val), self.assertRaises(ValueError):
                BusinessCapacity("cap-test", ("ev-capacity",), annual_turnover_usd=val)

            with self.subTest(val=val), self.assertRaises(ValueError):
                BusinessCapacity("cap-test", ("ev-capacity",), bid_bond_capacity_usd=val)

            with self.subTest(val=val), self.assertRaises(ValueError):
                BusinessCapacity("cap-test", ("ev-capacity",), hours_per_week=val)

            with self.subTest(val=val), self.assertRaises(ValueError):
                BusinessCapacity("cap-test", ("ev-capacity",), min_project_value=val)


if __name__ == "__main__":
    unittest.main()
