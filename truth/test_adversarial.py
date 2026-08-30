from datetime import date
import random
import re
import unittest

from truth.fixtures import PROHIBITED_CLAIMS, UNBACKED_CLAIMS, VERIFIED_CLAIMS, synthetic_graph
from truth.ingest import IngestionError, graph_from_dict, load_yaml
from truth.models import AssertionType, EvidenceRecord, MetricAssertion, MetricVerification
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

        ev_fact = EvidenceRecord("ev-f", "Direct employer fact at Org as Title from 2020-01-01.", "src", "loc", assertion_type=AssertionType.DIRECT_FACT, metadata={"organization": "Org", "title": "Title"})
        ev_derived = EvidenceRecord("ev-d", "Derived consulting capability at Org as Title from 2020-01-01.", "src", "loc", assertion_type=AssertionType.DERIVED_CAPABILITY, metadata={"organization": "Org", "title": "Title"})
        ev_user = EvidenceRecord("ev-u", "Self-declared user assertion at Org as Title from 2020-01-01.", "src", "loc", assertion_type=AssertionType.USER_ASSERTION, metadata={"organization": "Org", "title": "Title"})

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

        ev_verified = EvidenceRecord("ev-v", "Reduced latency by 40% at Org as Title from 2020-01-01.", "src", "loc", metadata={"organization": "Org", "title": "Title", "subject_id": "ach-v"})
        ev_unverified = EvidenceRecord("ev-u", "Increased revenue by 500% at Org as Title from 2020-01-01.", "src", "loc", metadata={"organization": "Org", "title": "Title"})
        ev_diff_num = EvidenceRecord("ev-num", "Managed 40 projects at Org as Title from 2020-01-01.", "src", "loc", metadata={"organization": "Org", "title": "Title"})

        ach_v = Achievement("ach-v", "Reduced latency by 40%.", ("ev-v",), MetricVerification.VERIFIED)
        ach_u = Achievement("ach-u", "Increased revenue by 500%.", ("ev-u",), MetricVerification.UNAVAILABLE)
        ach_num = Achievement("ach-num", "Managed 40 projects.", ("ev-num",), MetricVerification.UNAVAILABLE)

        emp = EmploymentRecord("emp-metrics", "Org", "Title", date(2020, 1, 1), None, ("ev-v", "ev-u", "ev-num"), achievements=(ach_v, ach_u, ach_num))
        profile = CareerProfile("prof-metrics", employment=(emp,))
        m_40 = MetricAssertion("m-40", "ach-v", 40, "%", "Reduced latency by 40%", verification_status=MetricVerification.VERIFIED, evidence_ids=("ev-v",))
        graph = TruthGraph((ev_verified, ev_unverified, ev_diff_num), metrics=(m_40,))
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

    def test_polarity_inversion_attacks(self):
        from truth.models import EvidenceRecord
        from truth.graph import TruthGraph

        ev1 = EvidenceRecord("ev-neg-auth", "Not authorized to work in Exampleland", "cv", "auth")
        ev2 = EvidenceRecord("ev-neg-skill", "No Kubernetes experience", "cv", "skill")
        ev3 = EvidenceRecord("ev-neg-resp", "Not responsible for budget management", "cv", "resp")

        graph = TruthGraph((ev1, ev2, ev3))
        validator = ClaimValidator(graph)

        # 1. Negative auth cannot become positive auth
        r1 = validator.validate_claim("Authorized to work in Exampleland", ("ev-neg-auth",))
        self.assertFalse(r1.allowed)
        self.assertTrue(any("polarity" in reason for reason in r1.reasons))

        # 2. Negative skill cannot become positive skill
        r2 = validator.validate_claim("Kubernetes experience", ("ev-neg-skill",))
        self.assertFalse(r2.allowed)
        self.assertTrue(any("polarity" in reason for reason in r2.reasons))

        # 3. Negative responsibility cannot become positive responsibility
        r3 = validator.validate_claim("Responsible for budget management", ("ev-neg-resp",))
        self.assertFalse(r3.allowed)
        self.assertTrue(any("polarity" in reason for reason in r3.reasons))

    def test_modality_bound_strengthening_attacks(self):
        from truth.models import EvidenceRecord
        from truth.graph import TruthGraph

        ev_bound = EvidenceRecord("ev-bound", "At most 10 hours per week available", "cv", "cap")
        ev_cond = EvidenceRecord("ev-cond", "Conditional on visa grant", "cv", "auth")

        graph = TruthGraph((ev_bound, ev_cond))
        validator = ClaimValidator(graph)

        # 1. At most 10 cannot be claimed as exactly 10 or at least 10
        r1 = validator.validate_claim("Available for at least 10 hours per week", ("ev-bound",))
        self.assertFalse(r1.allowed)
        self.assertTrue(any("upper-bound modality" in reason for reason in r1.reasons))

        r1_exact = validator.validate_claim("Available exactly 10 hours per week", ("ev-bound",))
        self.assertFalse(r1_exact.allowed)
        self.assertTrue(any("upper-bound modality" in reason for reason in r1_exact.reasons))

        # 2. Conditional cannot be claimed as unconditional
        r2 = validator.validate_claim("Authorized unconditionally", ("ev-cond",))
        self.assertFalse(r2.allowed)
        self.assertTrue(any("conditional" in reason for reason in r2.reasons))

    def test_temporal_validity_and_expiration(self):
        from truth.models import EvidenceRecord, CertificationRecord, CertificationState, CareerProfile
        from truth.graph import TruthGraph

        ev_cert = EvidenceRecord("ev-cert-exp", "Completed Example Cloud Architect from Example Issuer on 2023-01-01 expiring on 2025-01-01.", "cv", "cert")
        cert = CertificationRecord(
            "cert-exp", "Example Cloud Architect", "Example Issuer",
            CertificationState.COMPLETED, ("ev-cert-exp",),
            issued_date=date(2023, 1, 1), expiry_date=date(2025, 1, 1),
        )
        profile = CareerProfile("prof-cert", certifications=(cert,))
        graph = TruthGraph((ev_cert,))
        graph.add_career_profile(profile)
        validator = ClaimValidator(graph)

        # 1. Valid before expiration
        r_valid = validator.validate_claim(
            "Completed Example Cloud Architect", ("ev-cert-exp",), as_of=date(2024, 6, 1)
        )
        self.assertTrue(r_valid.allowed)

        # 2. Expired as of 2026 cannot be represented as currently held
        r_expired = validator.validate_claim(
            "Completed Example Cloud Architect", ("ev-cert-exp",), as_of=date(2026, 8, 1)
        )
        self.assertFalse(r_expired.allowed)
        self.assertTrue(any("expired" in reason for reason in r_expired.reasons))

    def test_field_level_atomic_mismatch_attacks(self):
        from truth.models import EvidenceRecord, EmploymentRecord, SkillRecord, LanguageRecord, WorkAuthorization, CareerProfile
        from truth.graph import TruthGraph

        ev_analyst = EvidenceRecord("ev-analyst", "Data Analyst at Example Corp", "cv", "emp")
        ev_python = EvidenceRecord("ev-python", "Uses Python", "cv", "skill")
        ev_english = EvidenceRecord("ev-english", "English professional proficiency", "cv", "lang")
        ev_auth = EvidenceRecord("ev-auth", "Authorized in Exampleland", "cv", "auth")

        graph = TruthGraph((ev_analyst, ev_python, ev_english, ev_auth))
        validator = ClaimValidator(graph)

        # 1. Title CDO backed only by Data Analyst evidence
        r1 = validator.validate_claim("Chief Data Officer at Example Corp", ("ev-analyst",))
        self.assertFalse(r1.allowed)

        # 2. Skill Kubernetes backed only by Python evidence
        r2 = validator.validate_claim("Kubernetes developer", ("ev-python",))
        self.assertFalse(r2.allowed)

        # 3. Language Japanese backed only by English evidence
        r3 = validator.validate_claim("Fluent in Japanese", ("ev-english",))
        self.assertFalse(r3.allowed)

        # 4. Work auth Japan backed only by Exampleland evidence
        r4 = validator.validate_claim("Authorized to work in Japan", ("ev-auth",))
        self.assertFalse(r4.allowed)

    def test_same_parent_false_relationship_composition(self):
        # Even under same parent, unsupported relations cannot be fabricated
        result = self.validator.validate_claim(
            "Reduced processing time by 40% continuously from 2022-01-01 to 2024-06-30.",
            ("ev-dates", "ev-achievement"),
        )
        self.assertFalse(result.allowed)

    def test_single_sentence_multi_metric_isolation(self):
        from truth.models import EvidenceRecord, Achievement, MetricVerification, EmploymentRecord, CareerProfile
        from truth.graph import TruthGraph

        ev_emp = EvidenceRecord("ev-emp", "Title at Org from 2020-01-01.", "cv", "emp", metadata={"organization": "Org", "title": "Title"})
        ev_multi = EvidenceRecord("ev-multi", "Reduced latency by 40% and increased revenue by 200% at Org as Title from 2020-01-01.", "cv", "ach", metadata={"subject_id": "ach-multi"})
        # Only 40% is verified; 200% is unverified
        ach = Achievement("ach-multi", "Reduced latency by 40%.", ("ev-multi",), MetricVerification.VERIFIED)
        emp = EmploymentRecord("emp-m", "Org", "Title", date(2020, 1, 1), None, ("ev-emp",), achievements=(ach,))
        profile = CareerProfile("prof-m", employment=(emp,))
        m_40 = MetricAssertion("m-40-iso", "ach-multi", 40, "%", "Reduced latency by 40%", verification_status=MetricVerification.VERIFIED, evidence_ids=("ev-multi",))
        graph = TruthGraph((ev_emp, ev_multi), metrics=(m_40,))
        graph.add_career_profile(profile)
        validator = ClaimValidator(graph)

        # Verified metric passes
        r_good = validator.validate_claim("Reduced latency by 40%.", ("ev-multi",))
        self.assertTrue(r_good.allowed)

        # Unverified metric in same sentence fails
        r_bad = validator.validate_claim("Increased revenue by 200%.", ("ev-multi",))
        self.assertFalse(r_bad.allowed)

    def test_structured_never_claim_candidate_dominance(self):
        from truth.models import ClaimCandidate, ProhibitedConceptCategory

        candidate = ClaimCandidate(
            text="We provide high quality engineering.",
            concepts=frozenset({ProhibitedConceptCategory.GUARANTEED_OUTCOME}),
        )
        result = self.validator.validate_candidate(candidate)
        self.assertFalse(result.allowed)
        self.assertEqual(AssertionType.PROHIBITED_CLAIM, result.assertion_type)
        self.assertTrue(any("guaranteed_outcome" in reason for reason in result.reasons))

    def test_business_capacity_strict_numeric_validation(self):
        from truth.models import BusinessCapacity

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

    def test_structural_field_mismatch_rejection_cdo_vs_analyst(self):
        from truth.models import EvidenceRecord, EmploymentRecord, CareerProfile
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-analyst", "Data Analyst at Example Corp from 2020-01-01.", "cv", "title", metadata={"organization": "Example Corp", "title": "Data Analyst"})
        # Inconsistent title: Chief Data Officer vs evidence Data Analyst
        emp = EmploymentRecord("emp-cdo", "Example Corp", "Chief Data Officer", date(2020, 1, 1), None, ("ev-analyst",))
        profile = CareerProfile("prof-cdo", employment=(emp,))
        graph = TruthGraph((ev,))
        with self.assertRaises(ValueError) as ctx:
            graph.add_career_profile(profile)
        self.assertIn("employment.title", str(ctx.exception))

    def test_structural_skill_mismatch_rejection(self):
        from truth.models import EvidenceRecord, SkillRecord, CareerProfile
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-py", "Expert in Python programming.", "cv", "skills")
        skill = SkillRecord("sk-rust", "Rust", ("ev-py",))
        profile = CareerProfile("prof-sk", skills=(skill,))
        graph = TruthGraph((ev,))
        with self.assertRaises(ValueError) as ctx:
            graph.add_career_profile(profile)
        self.assertIn("skill.name", str(ctx.exception))

    def test_structural_language_mismatch_rejection(self):
        from truth.models import EvidenceRecord, LanguageRecord, CareerProfile
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-eng", "Fluent in English.", "cv", "lang")
        lang = LanguageRecord("lang-jp", "Japanese", "fluent", ("ev-eng",))
        profile = CareerProfile("prof-lang", languages=(lang,))
        graph = TruthGraph((ev,))
        with self.assertRaises(ValueError) as ctx:
            graph.add_career_profile(profile)
        self.assertIn("language.language", str(ctx.exception))

    def test_structural_work_authorization_mismatch_rejection(self):
        from truth.models import EvidenceRecord, WorkAuthorization, CareerProfile
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-eg", "Authorized to work in Egypt.", "cv", "auth")
        auth = WorkAuthorization("auth-de", "Germany", "citizen", ("ev-eg",))
        profile = CareerProfile("prof-auth", work_authorizations=(auth,))
        graph = TruthGraph((ev,))
        with self.assertRaises(ValueError) as ctx:
            graph.add_career_profile(profile)
        self.assertIn("work_authorization.jurisdiction", str(ctx.exception))

    def test_structural_capacity_mismatch_rejection(self):
        from truth.models import EvidenceRecord, BusinessCapacity, CapabilityProfile
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-cap", "Available 20 hours per week.", "cv", "cap")
        cap = BusinessCapacity("cap-80", ("ev-cap",), hours_per_week=80)
        profile = CapabilityProfile("prof-cap", capacity=cap)
        graph = TruthGraph((ev,))
        with self.assertRaises(ValueError) as ctx:
            graph.add_capability_profile(profile)
        self.assertIn("capacity.hours_per_week", str(ctx.exception))

    def test_verified_assertion_without_evidence_rejected(self):
        from truth.models import AtomicAssertion, VerificationStatus, AssertionType
        from truth.graph import TruthGraph

        # Model level
        with self.assertRaises(ValueError):
            AtomicAssertion("as-noev", "subj", "pred", "val", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, evidence_ids=())

        # Unverified user assertion can exist without evidence
        as_unv = AtomicAssertion("as-noev2", "subj", "pred", "val", AssertionType.USER_ASSERTION, VerificationStatus.UNVERIFIED, evidence_ids=())
        graph = TruthGraph()
        graph.add_assertion(as_unv)
        self.assertIn("as-noev2", graph.assertions)

    def test_dangling_relation_endpoints_and_arbitrary_string_rejected(self):
        from truth.models import TypedRelation, RelationType, VerificationStatus, EvidenceRecord
        from truth.graph import TruthGraph

        # Arbitrary string instead of RelationType enum is rejected at model level
        with self.assertRaises(ValueError):
            TypedRelation("rel-inv", "src", "arbitrary_string", "tgt", evidence_ids=("ev-1",))

        # Dangling evidence reference rejected in graph
        rel = TypedRelation("rel-dang", "src", RelationType.ACHIEVED_DURING, "tgt", evidence_ids=("ev-nonexistent",))
        graph = TruthGraph()
        with self.assertRaises(ValueError) as ctx:
            graph.add_relation(rel)
        self.assertIn("unknown evidence", str(ctx.exception))

    def test_unverified_to_verified_upgrade_rejected(self):
        from truth.models import EvidenceRecord, AtomicAssertion, VerificationStatus, AssertionType
        from truth.graph import TruthGraph

        ev_unv = EvidenceRecord("ev-unv", "Some fact.", "src", "loc", verification_status=VerificationStatus.UNVERIFIED)
        graph = TruthGraph((ev_unv,))

        as_ver = AtomicAssertion("as-up", "subj", "pred", "Some fact.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-unv",))
        with self.assertRaises(ValueError) as ctx:
            graph.add_assertion(as_ver)
        self.assertIn("cannot be VERIFIED when supported by UNVERIFIED evidence", str(ctx.exception))

    def test_approximate_to_definite_upgrade_rejected(self):
        from truth.models import EvidenceRecord, AtomicAssertion, VerificationStatus, AssertionType, Modality
        from truth.graph import TruthGraph

        ev_appr = EvidenceRecord("ev-appr", "Approx 20 items.", "src", "loc", verification_status=VerificationStatus.APPROXIMATE)
        graph = TruthGraph((ev_appr,))

        as_def = AtomicAssertion("as-def", "subj", "pred", "Approx 20 items.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-appr",), modality=Modality.DEFINITE)
        with self.assertRaises(ValueError) as ctx:
            graph.add_assertion(as_def)
        self.assertIn("cannot have DEFINITE modality when evidence is APPROXIMATE", str(ctx.exception))

    def test_active_assertions_supersedes_and_conflicts_resolution(self):
        from truth.models import EvidenceRecord, AtomicAssertion, AssertionType, VerificationStatus
        from truth.graph import TruthGraph

        ev1 = EvidenceRecord("ev-old", "Old role 2020.", "src", "loc")
        ev2 = EvidenceRecord("ev-new", "New role 2024.", "src", "loc")
        ev3 = EvidenceRecord("ev-conf1", "Conflicting 1.", "src", "loc")
        ev4 = EvidenceRecord("ev-conf2", "Conflicting 2.", "src", "loc")

        as_old = AtomicAssertion("as-old", "subj", "role", "Old role 2020.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-old",))
        as_new = AtomicAssertion("as-new", "subj", "role", "New role 2024.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-new",), supersedes=("as-old",))
        as_c1 = AtomicAssertion("as-c1", "subj", "data", "Conflicting 1.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-conf1",), conflicts_with=("as-c2",))
        as_c2 = AtomicAssertion("as-c2", "subj", "data", "Conflicting 2.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-conf2",), conflicts_with=("as-c1",))

        graph = TruthGraph((ev1, ev2, ev3, ev4), (as_old, as_new, as_c1, as_c2))
        active = graph.active_assertions()
        active_ids = {a.id for a in active}

        # as_new is active; as_old is superseded; as_c1 & as_c2 are conflicting (both inactive)
        self.assertIn("as-new", active_ids)
        self.assertNotIn("as-old", active_ids)
        self.assertNotIn("as-c1", active_ids)
        self.assertNotIn("as-c2", active_ids)

    def test_terminal_case_1_cross_record_token_union_rejected(self):
        from truth.models import EvidenceRecord, EmploymentRecord, CareerProfile
        from truth.graph import TruthGraph

        ev1 = EvidenceRecord("ev-ce", "Chief Executive at Example Corp", "cv", "emp", metadata={"organization": "Example Corp", "title": "Chief Executive"})
        ev2 = EvidenceRecord("ev-do", "Data Officer at Example Corp", "cv", "emp", metadata={"organization": "Example Corp", "title": "Data Officer"})
        emp = EmploymentRecord("job-cdo", "Example Corp", "Chief Data Officer", date(2022, 1, 1), None, evidence_ids=("ev-ce", "ev-do"))
        graph = TruthGraph((ev1, ev2))
        with self.assertRaises(ValueError) as ctx:
            graph.add_career_profile(CareerProfile("prof", employment=(emp,)))
        self.assertIn("employment.title", str(ctx.exception))

    def test_terminal_case_2_negated_field_evidence_rejected_at_ingestion(self):
        from truth.models import EvidenceRecord, WorkAuthorization, CareerProfile
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-neg", "Not authorized to work in Germany", "cv", "auth")
        auth = WorkAuthorization("auth-de", "Germany", "authorized", ("ev-neg",))
        graph = TruthGraph((ev,))
        with self.assertRaises(ValueError) as ctx:
            graph.add_career_profile(CareerProfile("prof", work_authorizations=(auth,)))
        self.assertIn("work_authorization.status", str(ctx.exception))

    def test_terminal_case_3_complete_material_field_coverage(self):
        from truth.fixtures import synthetic_graph
        graph = synthetic_graph()
        # Ensure projected assertions exist for all material fields across CareerProfile & CapabilityProfile
        predicates = {a.predicate for a in graph.assertions.values()}
        required_preds = {
            "employment.organization", "employment.title", "employment.start_date", "employment.end_date",
            "employment.responsibility", "achievement.statement", "education.institution", "education.qualification",
            "education.start_date", "education.end_date", "certification.name", "certification.issuer",
            "certification.state", "skill.name", "language.language", "language.proficiency",
            "work_authorization.jurisdiction", "work_authorization.status", "service.name", "service.description",
            "service.deliverable", "portfolio.title", "portfolio.summary", "capacity.available_from",
            "capacity.hours_per_week", "capacity.min_project_value", "capacity.max_project_value",
            "capacity.legal_capacity", "tool.name"
        }
        for pred in required_preds:
            self.assertIn(pred, predicates, f"missing projected assertion for material field: {pred}")

    def test_terminal_case_4_nonexistent_source_target_rejected_in_add_relation(self):
        from truth.models import EvidenceRecord, TypedRelation, RelationType
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-1", "Some relation content", "src", "loc")
        graph = TruthGraph((ev,))
        rel = TypedRelation("rel-nonexistent", "missing-src", RelationType.ACHIEVED_DURING, "missing-tgt", evidence_ids=("ev-1",))
        with self.assertRaises(ValueError) as ctx:
            graph.add_relation(rel)
        self.assertIn("nonexistent source", str(ctx.exception))

    def test_terminal_case_5_nested_achievement_requires_relation_evidence(self):
        from truth.models import EvidenceRecord, EmploymentRecord, Achievement, CareerProfile, VerificationStatus, AssertionType
        from truth.graph import TruthGraph

        ev_emp = EvidenceRecord("ev-emp", "Worked at Synthetic Corp as Data Engineer from 2022-01-01 to 2024-01-01.", "cv", "emp", metadata={"organization": "Synthetic Corp", "title": "Data Engineer"})
        ev_ach = EvidenceRecord("ev-ach", "Built a tool reducing processing time by 40%.", "cv", "ach")
        emp = EmploymentRecord(
            "job-nested", "Synthetic Corp", "Data Engineer", date(2022, 1, 1), date(2024, 1, 1), ("ev-emp",),
            achievements=(Achievement("ach-isolated", "Built a tool reducing processing time by 40%.", ("ev-ach",)),),
        )
        graph = TruthGraph((ev_emp, ev_ach))
        graph.add_career_profile(CareerProfile("prof-nested", employment=(emp,)))

        # Relation must NOT be VERIFIED because ev-ach does not mention Synthetic Corp or link to ev-emp
        rel = graph.relations["rel_job-nested_ach-isolated"]
        self.assertEqual(VerificationStatus.UNVERIFIED, rel.verification_status)
        self.assertEqual(AssertionType.USER_ASSERTION, rel.assertion_type)
        self.assertFalse(graph.are_relationally_linked(("ev-emp", "ev-ach")))

    def test_terminal_case_6_multimetric_verification_order_independence(self):
        from truth.models import EvidenceRecord, MetricAssertion, MetricVerification
        from truth.validator import ClaimValidator
        from truth.graph import TruthGraph

        ev = EvidenceRecord("ev-metrics", "Revenue increased 200% and latency fell 40% at Corp.", "cv", "ach", metadata={"subject_id": "ach-1"})

        # Explicit MetricAssertion: only 40% latency is VERIFIED; 200% is UNAVAILABLE
        ma_lat = MetricAssertion(id="m-lat", subject_id="ach-1", numeric_value=40.0, unit="%", context="latency fell 40%", verification_status=MetricVerification.VERIFIED, evidence_ids=("ev-metrics",))
        ma_rev = MetricAssertion(id="m-rev", subject_id="ach-1", numeric_value=200.0, unit="%", context="revenue increased 200%", verification_status=MetricVerification.UNAVAILABLE, evidence_ids=("ev-metrics",))

        graph = TruthGraph((ev,), metrics=(ma_lat, ma_rev))
        validator = ClaimValidator(graph)

        # Order A: validate latency 40% (allowed)
        res_lat = validator.validate_claim("Latency fell 40%.", ("ev-metrics",))
        self.assertTrue(res_lat.allowed)

        # Order B: validate revenue 200% (rejected because metric assertion is UNAVAILABLE)
        res_rev = validator.validate_claim("Revenue increased 200%.", ("ev-metrics",))
        self.assertFalse(res_rev.allowed)

    def test_terminal_case_7_numeric_substrings_do_not_verify_numbers(self):
        from truth.models import EvidenceRecord, EmploymentRecord, Achievement, CareerProfile, MetricVerification
        from truth.validator import ClaimValidator
        from truth.graph import TruthGraph

        ev_title = EvidenceRecord("ev-title", "Manager at Corp from 2022-01-01 to 2024-01-01.", "cv", "emp", metadata={"organization": "Corp", "title": "Manager"})
        ev_120 = EvidenceRecord("ev-120", "Managed 120 clients at Corp.", "cv", "ach", metadata={"subject_id": "ach-num"})
        emp = EmploymentRecord(
            "job-num", "Corp", "Manager", date(2022, 1, 1), date(2024, 1, 1), ("ev-title",),
            achievements=(Achievement("ach-num", "Managed 120 clients.", ("ev-120",), MetricVerification.VERIFIED),),
        )
        m_120 = MetricAssertion("m-120", "ach-num", 120, "clients", "Managed 120 clients", verification_status=MetricVerification.VERIFIED, evidence_ids=("ev-120",))
        graph = TruthGraph((ev_title, ev_120), metrics=(m_120,))
        graph.add_career_profile(CareerProfile("prof-num", employment=(emp,)))
        val = ClaimValidator(graph)

        # 20 does NOT match 120
        r_20 = val.validate_claim("Managed 20 clients.", ("ev-120",))
        self.assertFalse(r_20.allowed)

        # 4 does NOT match 40%
        ev_40 = EvidenceRecord("ev-40", "Reduced latency by 40% at Corp.", "cv", "ach", metadata={"subject_id": "ach-num2"})
        emp2 = EmploymentRecord(
            "job-num2", "Corp", "Manager", date(2022, 1, 1), date(2024, 1, 1), ("ev-title",),
            achievements=(Achievement("ach-num2", "Reduced latency by 40%.", ("ev-40",), MetricVerification.VERIFIED),),
        )
        m_40 = MetricAssertion("m-40", "ach-num2", 40, "%", "Reduced latency by 40%", verification_status=MetricVerification.VERIFIED, evidence_ids=("ev-40",))
        graph2 = TruthGraph((ev_title, ev_40), metrics=(m_40,))
        graph2.add_career_profile(CareerProfile("prof-num2", employment=(emp2,)))
        val2 = ClaimValidator(graph2)

        r_4 = val2.validate_claim("Reduced latency by 4%.", ("ev-40",))
        self.assertFalse(r_4.allowed)

        # 40 clients does NOT match 40% latency
        r_clients = val2.validate_claim("Served 40 clients.", ("ev-40",))
        self.assertFalse(r_clients.allowed)

    def test_terminal_case_8_year_only_does_not_establish_exact_date(self):
        from truth.models import EvidenceRecord, EmploymentRecord, CareerProfile
        from truth.graph import TruthGraph

        ev_yr = EvidenceRecord("ev-yr", "Worked at Example Corp as Engineer in 2024.", "cv", "emp", metadata={"organization": "Example Corp", "title": "Engineer"})
        emp = EmploymentRecord("job-dt", "Example Corp", "Engineer", date(2024, 12, 31), None, evidence_ids=("ev-yr",))
        graph = TruthGraph((ev_yr,))
        with self.assertRaises(ValueError) as ctx:
            graph.add_career_profile(CareerProfile("prof-dt", employment=(emp,)))
        self.assertIn("employment.start_date", str(ctx.exception))

    def test_terminal_case_9_future_superseder_does_not_invalidate_current_truth(self):
        from truth.models import EvidenceRecord, AtomicAssertion, AssertionType, VerificationStatus
        from truth.graph import TruthGraph

        ev1 = EvidenceRecord("ev-r1", "Staff Engineer in 2024.", "cv", "role")
        ev2 = EvidenceRecord("ev-r2", "Principal Director in 2027.", "cv", "role")
        as_a = AtomicAssertion("as-a", "person", "career.role", "Staff Engineer in 2024.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-r1",), effective_from=date(2024, 1, 1))
        as_b = AtomicAssertion("as-b", "person", "career.role", "Principal Director in 2027.", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-r2",), effective_from=date(2027, 1, 1), supersedes=("as-a",))

        graph = TruthGraph((ev1, ev2), (as_a, as_b))

        # Active in 2026: as_a is active, as_b is NOT active yet and does NOT suppress as_a
        active_2026 = {a.id for a in graph.active_assertions(date(2026, 6, 1))}
        self.assertIn("as-a", active_2026)
        self.assertNotIn("as-b", active_2026)

        # Active in 2027: as_b is active and suppresses as_a
        active_2027 = {a.id for a in graph.active_assertions(date(2027, 6, 1))}
        self.assertIn("as-b", active_2027)
        self.assertNotIn("as-a", active_2027)

    def test_terminal_case_10_candidate_bound_to_material_assertions(self):
        from truth.models import EvidenceRecord, AtomicAssertion, ClaimCandidate, AssertionType, VerificationStatus
        from truth.validator import ClaimValidator
        from truth.graph import TruthGraph

        ev_py = EvidenceRecord("ev-py", "Uses Python for engineering.", "cv", "skill")
        ev_ceo = EvidenceRecord("ev-ceo", "Served as Chief Executive Officer", "cv", "emp")
        as_py = AtomicAssertion("as-py", "skill-py", "skill.name", "Python", AssertionType.DIRECT_FACT, VerificationStatus.VERIFIED, ("ev-py",))

        graph = TruthGraph((ev_py, ev_ceo), (as_py,))
        validator = ClaimValidator(graph)

        cand = ClaimCandidate(
            text="Served as Chief Executive Officer",
            material_assertion_ids=("as-py",),
            requested_evidence_ids=("ev-ceo",),
        )
        res = validator.validate_candidate(cand)
        self.assertFalse(res.allowed)
        self.assertEqual(AssertionType.UNSUPPORTED_CLAIM, res.assertion_type)
        self.assertTrue(any("not authorized" in r for r in res.reasons))

    def test_invariant_1_subject_predicate_safe_field_provenance(self):
        """Invariant 1: Subject/predicate-safe field provenance via explicit scope.
        Proves prose containing supervisor/relational text cannot establish identity-sensitive fields.
        """
        from truth.models import (
            EvidenceRecord, EmploymentRecord, CareerProfile, CertificationRecord,
            CertificationState, WorkAuthorization, AtomicAssertion, AssertionType,
            VerificationStatus,
        )
        from truth.graph import TruthGraph

        # 1. Direct AtomicAssertion admission with supervisor title in prose MUST FAIL
        # Required direct regression:
        # Evidence: "Chief Data Officer manages the Data Engineer at Acme Corp."
        # Attempt: AtomicAssertion(subject_id="employee", predicate="employment.title", value="Chief Data Officer", VERIFIED, DIRECT_FACT)
        ev_direct = EvidenceRecord("ev-direct-mgmt", "Chief Data Officer manages the Data Engineer at Acme Corp.", "cv", "role")
        as_bad_direct = AtomicAssertion(
            id="as-bad-direct",
            subject_id="employee",
            predicate="employment.title",
            value="Chief Data Officer",
            assertion_type=AssertionType.DIRECT_FACT,
            verification_status=VerificationStatus.VERIFIED,
            evidence_ids=("ev-direct-mgmt",),
        )
        graph_direct = TruthGraph((ev_direct,))
        with self.assertRaises(ValueError):
            graph_direct.add_assertion(as_bad_direct)

        # 2. Supervisor title in prose cannot establish employee's title in profile
        # Strengthened regression: organization and start_date are independently valid,
        # and the failure is specifically: employment.title
        ev_rep = EvidenceRecord("ev-rep", "Chief Data Officer manages the Data Engineer at Acme Corp from 2022-01-01.", "cv", "role")
        ev_org = EvidenceRecord("ev-org", "Acme Corp", "cv", "organization", metadata={"organization": "Acme Corp"})
        ev_date = EvidenceRecord("ev-date", "2022-01-01", "cv", "start_date")
        graph1 = TruthGraph((ev_rep, ev_org, ev_date))

        # Attempt supervisor title -> MUST FAIL specifically on employment.title
        bad_emp = EmploymentRecord("emp-bad", "Acme Corp", "Chief Data Officer", date(2022, 1, 1), None, ("ev-rep", "ev-org", "ev-date"))
        bad_prof = CareerProfile("prof-bad", employment=(bad_emp,))
        with self.assertRaises(ValueError) as cm:
            graph1.add_career_profile(bad_prof)
        self.assertIn("employment.title", str(cm.exception))

        # 3. Client vs Employer ownership
        # Concrete bypass 2: "Worked for client BetaCorp while employed by AlphaCorp from 2022-01-01."
        ev_client = EvidenceRecord("ev-cl", "Worked for client BetaCorp while employed by AlphaCorp from 2022-01-01.", "cv", "role")
        graph2 = TruthGraph((ev_client,))
        bad_org_emp = EmploymentRecord("emp-bad-org", "BetaCorp", "Data Engineer", date(2022, 1, 1), None, ("ev-cl",))
        with self.assertRaises(ValueError):
            graph2.add_career_profile(CareerProfile("prof-bad-org", employment=(bad_org_emp,)))

        # 4. Explicit deterministic scope (via metadata or field locator) -> MUST PASS
        ev_good = EvidenceRecord("ev-good", "Data Engineer at Acme Corp from 2022-01-01.", "cv", "title", metadata={"organization": "Acme Corp", "title": "Data Engineer"})
        graph3 = TruthGraph((ev_good,))
        good_emp = EmploymentRecord("emp-good", "Acme Corp", "Data Engineer", date(2022, 1, 1), None, ("ev-good",))
        graph3.add_career_profile(CareerProfile("prof-good", employment=(good_emp,)))
        self.assertIn("emp-good", graph3.entity_ids_for_evidence("ev-good"))

        # 5. Work authorization negative scope
        ev_auth_neg = EvidenceRecord("ev-an", "Not authorized to work in Germany.", "cv", "auth")
        graph4 = TruthGraph((ev_auth_neg,))
        bad_auth = WorkAuthorization("auth-de", "Germany", "authorized", ("ev-an",))
        with self.assertRaises(ValueError):
            graph4.add_career_profile(CareerProfile("prof-bad-auth", work_authorizations=(bad_auth,)))

    def test_invariant_2_canonical_material_field_manifest_reflection(self):
        """Invariant 2: Real complete material-field coverage, reflection, and executable engine.
        Proves CANONICAL_MATERIAL_MANIFEST drives both validation and projection.
        """
        import dataclasses
        from dataclasses import dataclass
        from truth.models import (
            CANONICAL_MATERIAL_MANIFEST, MaterialFieldSpec,
            EmploymentRecord, Achievement, EducationRecord, CertificationRecord,
            SkillRecord, LanguageRecord, WorkAuthorization, ServiceRecord,
            PortfolioItem, BusinessCapacity, CareerProfile, CapabilityProfile,
        )
        from truth.graph import TruthGraph

        # 1. Structural domain model coverage check
        domain_models = (
            EmploymentRecord, Achievement, EducationRecord, CertificationRecord,
            SkillRecord, LanguageRecord, WorkAuthorization, ServiceRecord,
            PortfolioItem, BusinessCapacity, CareerProfile, CapabilityProfile,
        )

        manifest_map = {(spec.model_cls, spec.field_name): spec for spec in CANONICAL_MATERIAL_MANIFEST}
        structural_fields = {"id", "evidence_ids", "metric_verification"}

        for model_cls in domain_models:
            for field in dataclasses.fields(model_cls):
                if field.name in structural_fields:
                    continue
                key = (model_cls, field.name)
                self.assertIn(
                    key,
                    manifest_map,
                    f"Model {model_cls.__name__} field '{field.name}' is not classified in CANONICAL_MATERIAL_MANIFEST",
                )
                spec = manifest_map[key]
                self.assertTrue(len(spec.predicate) > 0, f"Spec for {key} has empty predicate")

        # 2. Synthetic / test-only material field spec mutation test:
        # Proves the common manifest engine performs both validation and projection
        @dataclass(frozen=True, slots=True)
        class CustomEntity:
            id: str
            special_code: str
            evidence_ids: tuple[str, ...]

        custom_spec = MaterialFieldSpec(CustomEntity, "special_code", "custom.special_code")
        custom_manifest = (custom_spec,)

        ev_good = EvidenceRecord("ev-code", "SPEC-999", "src", "loc")
        ev_bad = EvidenceRecord("ev-wrong", "OTHER-000", "src", "loc")

        graph = TruthGraph((ev_good, ev_bad))
        bad_entity = CustomEntity("c1", "SPEC-999", ("ev-wrong",))
        with self.assertRaises(ValueError):
            graph._validate_entity_manifest(bad_entity, {"c1": ("ev-wrong",)}, manifest=custom_manifest)

        good_entity = CustomEntity("c1", "SPEC-999", ("ev-code",))
        graph._validate_entity_manifest(good_entity, {"c1": ("ev-code",)}, manifest=custom_manifest)
        graph._project_entity_manifest(good_entity, manifest=custom_manifest)

        self.assertIn("as_c1_custom_special_code_SPEC-999", graph.assertions)
        as_node = graph.assertions["as_c1_custom_special_code_SPEC-999"]
        self.assertEqual("SPEC-999", as_node.value)
        self.assertEqual("custom.special_code", as_node.predicate)

        # 3. No unrelated graph evidence fallback when profile.evidence_ids is empty
        ev_unrelated = EvidenceRecord("ev-unrelated", "Top data engineer.", "src", "loc")
        prof_empty_ev = CareerProfile("prof-no-ev", approved_summaries=("Top data engineer.",))
        graph_empty = TruthGraph((ev_unrelated,))
        with self.assertRaises(ValueError):
            graph_empty.add_career_profile(prof_empty_ev)

    def test_invariant_3_metric_assertions_are_sole_authority(self):
        """Invariant 3: Real profile auto-extraction produces UNAVAILABLE metrics.
        Metric becomes VERIFIED only via explicit MetricAssertion.
        """
        from truth.models import (
            Achievement,
            CareerProfile,
            EmploymentRecord,
            EvidenceRecord,
            MetricAssertion,
            MetricVerification,
        )
        from truth.validator import ClaimValidator
        from truth.graph import TruthGraph

        # Order A: Statement = 'Revenue increased 40% and latency fell 40%.'
        ev_ach = EvidenceRecord(
            "ev-ach", "Revenue increased 40% and latency fell 40% at Corp as Engineer from 2020-01-01.",
            "cv", "ach", metadata={"organization": "Corp", "title": "Engineer"},
        )
        ach_order_a = Achievement("ach-a", "Revenue increased 40% and latency fell 40%.", ("ev-ach",), MetricVerification.VERIFIED)
        emp_a = EmploymentRecord("emp-a", "Corp", "Engineer", date(2020, 1, 1), None, ("ev-ach",), achievements=(ach_order_a,))
        prof_a = CareerProfile("prof-a", employment=(emp_a,))

        graph_a = TruthGraph((ev_ach,))
        graph_a.add_career_profile(prof_a)

        # After profile ingestion, auto-extracted metrics MUST NOT be VERIFIED (they are UNAVAILABLE)
        for m in graph_a.metrics.values():
            self.assertEqual(MetricVerification.UNAVAILABLE, m.verification_status)

        # Explicitly add ONLY latency reduction 40% -> VERIFIED
        metric_latency = MetricAssertion(
            id="metric-latency-verified",
            subject_id="ach-a",
            numeric_value=40,
            unit="%",
            context="latency fell 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-ach",),
        )
        graph_a.add_metric_assertion(metric_latency)

        validator_a = ClaimValidator(graph_a)
        # Latency claim passes
        res_lat = validator_a.validate_claim("Latency fell 40%.", ("ev-ach",))
        self.assertTrue(res_lat.allowed)
        # Revenue claim fails
        res_rev = validator_a.validate_claim("Revenue increased 40%.", ("ev-ach",))
        self.assertFalse(res_rev.allowed)

        # Order B: Statement with sentence order reversed: 'Latency fell 40% and revenue increased 40%.'
        ev_ach_b = EvidenceRecord(
            "ev-ach-b", "Latency fell 40% and revenue increased 40% at Corp as Engineer from 2020-01-01.",
            "cv", "ach", metadata={"organization": "Corp", "title": "Engineer"},
        )
        ach_order_b = Achievement("ach-b", "Latency fell 40% and revenue increased 40%.", ("ev-ach-b",), MetricVerification.VERIFIED)
        emp_b = EmploymentRecord("emp-b", "Corp", "Engineer", date(2020, 1, 1), None, ("ev-ach-b",), achievements=(ach_order_b,))
        prof_b = CareerProfile("prof-b", employment=(emp_b,))

        graph_b = TruthGraph((ev_ach_b,))
        graph_b.add_career_profile(prof_b)

        # Explicitly add ONLY latency reduction 40% -> VERIFIED
        metric_latency_b = MetricAssertion(
            id="metric-latency-b-verified",
            subject_id="ach-b",
            numeric_value=40,
            unit="%",
            context="latency fell 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-ach-b",),
        )
        graph_b.add_metric_assertion(metric_latency_b)

        validator_b = ClaimValidator(graph_b)
        # Latency claim passes
        self.assertTrue(validator_b.validate_claim("Latency fell 40%.", ("ev-ach-b",)).allowed)
        # Revenue claim fails
        self.assertFalse(validator_b.validate_claim("Revenue increased 40%.", ("ev-ach-b",)).allowed)

        # -------------------------------------------------------------
        # Required Terminal Regression:
        # Evidence: "Revenue increased 40% and latency fell 10%."
        # -------------------------------------------------------------
        from truth.models import ClaimCandidate, AtomicAssertion, AssertionType, VerificationStatus

        ev_mixed = EvidenceRecord(
            "ev-mixed", "Revenue increased 40% and latency fell 10% at Acme Corp from 2022-01-01.",
            "cv", "ach", metadata={"organization": "Acme Corp", "title": "Engineer", "subject_id": "rev-subject"},
        )
        graph_metric = TruthGraph((ev_mixed,))

        # Attempt: MetricAssertion(subject_id="lat-subject", numeric_value=40, unit="%", context="latency fell 40%", VERIFIED)
        # MUST FAIL AT GRAPH ADMISSION
        bad_metric = MetricAssertion(
            id="m-bad-lat40",
            subject_id="lat-subject",
            numeric_value=40,
            unit="%",
            context="latency fell 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-mixed",),
        )
        with self.assertRaises(ValueError):
            graph_metric.add_metric_assertion(bad_metric)

        # These must pass:
        # revenue +40% (ev_mixed metadata has subject_id="rev-subject")
        metric_rev = MetricAssertion(
            id="m-good-rev",
            subject_id="rev-subject",
            numeric_value=40,
            unit="%",
            context="revenue increased 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-mixed",),
        )
        graph_metric.add_metric_assertion(metric_rev)
        self.assertIn("m-good-rev", graph_metric.metrics)

        # latency -10% with subject bound via graph entity
        ev_mixed_lat = EvidenceRecord(
            "ev-mixed-lat", "Revenue increased 40% and latency fell 10% at Acme Corp from 2022-01-01.",
            "cv", "ach", metadata={"organization": "Acme Corp", "title": "Engineer", "subject_id": "lat-subject"},
        )
        graph_metric.add_evidence(ev_mixed_lat)
        metric_lat = MetricAssertion(
            id="m-good-lat",
            subject_id="lat-subject",
            numeric_value=10,
            unit="%",
            context="latency fell 10%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-mixed-lat",),
        )
        graph_metric.add_metric_assertion(metric_lat)
        self.assertIn("m-good-lat", graph_metric.metrics)

        # Also prove:
        # 40 clients cannot establish 40%
        ev_clients = EvidenceRecord("ev-clients", "Managed 40 clients at Acme Corp.", "cv", "ach", metadata={"subject_id": "client-subject"})
        graph_clients = TruthGraph((ev_clients,))
        metric_client_percent = MetricAssertion(
            id="m-client-pct",
            subject_id="client-subject",
            numeric_value=40,
            unit="%",
            context="increased 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-clients",),
        )
        with self.assertRaises(ValueError):
            graph_clients.add_metric_assertion(metric_client_percent)

        # $40 cannot establish 40%
        ev_dollars = EvidenceRecord("ev-dollars", "Earned $40 per hour at Acme Corp.", "cv", "ach", metadata={"subject_id": "dollar-subject"})
        graph_dollars = TruthGraph((ev_dollars,))
        metric_dollar_percent = MetricAssertion(
            id="m-dollar-pct",
            subject_id="dollar-subject",
            numeric_value=40,
            unit="%",
            context="40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-dollars",),
        )
        with self.assertRaises(ValueError):
            graph_dollars.add_metric_assertion(metric_dollar_percent)

        # -------------------------------------------------------------
        # FINAL TWO-LINE AUTHORITY CLOSURE REGRESSIONS
        # -------------------------------------------------------------
        # 1. Subject proof must be structural (no generic locator / word stem / token overlap)
        # Regression 1A: Evidence locator="ach", metric subject_id="achievement-unrelated" -> MUST FAIL
        ev_ach_unrel = EvidenceRecord("ev-ach-unrel", "Revenue decreased 40%.", "cv", "ach")
        graph_ach_unrel = TruthGraph((ev_ach_unrel,))
        metric_ach_unrel = MetricAssertion(
            id="m-ach-unrel",
            subject_id="achievement-unrelated",
            numeric_value=40,
            unit="%",
            context="Revenue decreased 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-ach-unrel",),
        )
        with self.assertRaises(ValueError):
            graph_ach_unrel.add_metric_assertion(metric_ach_unrel)

        # Regression 1B: Evidence id="ev-latency", locator="unscoped", metric subject_id="latency-unrelated" -> MUST FAIL
        ev_lat_unrel = EvidenceRecord("ev-latency", "Latency fell 40%.", "cv", "unscoped")
        graph_lat_unrel = TruthGraph((ev_lat_unrel,))
        metric_lat_unrel = MetricAssertion(
            id="m-lat-unrel",
            subject_id="latency-unrelated",
            numeric_value=40,
            unit="%",
            context="Latency fell 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-latency",),
        )
        with self.assertRaises(ValueError):
            graph_lat_unrel.add_metric_assertion(metric_lat_unrel)

        # Structural Subject Proof Positive Cases:
        # A. metadata.subject_id explicitly equals metric subject -> MUST PASS
        ev_meta_subj = EvidenceRecord(
            "ev-meta-subj", "Revenue decreased 40%.", "cv", "ach",
            metadata={"subject_id": "achievement-unrelated"},
        )
        graph_meta_subj = TruthGraph((ev_meta_subj,))
        graph_meta_subj.add_metric_assertion(
            MetricAssertion(
                id="m-meta-pass",
                subject_id="achievement-unrelated",
                numeric_value=40,
                unit="%",
                context="Revenue decreased 40%",
                verification_status=MetricVerification.VERIFIED,
                evidence_ids=("ev-meta-subj",),
            )
        )
        self.assertIn("m-meta-pass", graph_meta_subj.metrics)

        # B. Real graph entity bound to that evidence -> MUST PASS
        ev_ent_subj = EvidenceRecord(
            "ev-ent-subj", "Latency fell 40% at Corp as Engineer from 2020-01-01.", "cv", "unscoped",
            metadata={"organization": "Corp", "title": "Engineer"},
        )
        ach_ent = Achievement("latency-unrelated", "Latency fell 40%.", ("ev-ent-subj",), MetricVerification.VERIFIED)
        emp_ent = EmploymentRecord("emp-ent", "Corp", "Engineer", date(2020, 1, 1), None, ("ev-ent-subj",), achievements=(ach_ent,))
        prof_ent = CareerProfile("prof-ent", employment=(emp_ent,))
        graph_ent_subj = TruthGraph((ev_ent_subj,))
        graph_ent_subj.add_career_profile(prof_ent)
        graph_ent_subj.add_metric_assertion(
            MetricAssertion(
                id="m-ent-pass",
                subject_id="latency-unrelated",
                numeric_value=40,
                unit="%",
                context="Latency fell 40%",
                verification_status=MetricVerification.VERIFIED,
                evidence_ids=("ev-ent-subj",),
            )
        )
        self.assertIn("m-ent-pass", graph_ent_subj.metrics)

        # 2. Unit equivalence must have NO context fallback
        # Regression 2A: Evidence: "Processed 40 tickets in 5 hours."
        # Attempt: numeric_value=40, unit="hours", context="Processed 40 hours for tickets" -> MUST FAIL
        ev_multi_unit = EvidenceRecord(
            "ev-multi-unit", "Processed 40 tickets in 5 hours.", "cv", "multi-subject",
            metadata={"subject_id": "multi-subject"},
        )
        graph_multi_unit = TruthGraph((ev_multi_unit,))
        metric_bad_unit = MetricAssertion(
            id="m-bad-hours40",
            subject_id="multi-subject",
            numeric_value=40,
            unit="hours",
            context="Processed 40 hours for tickets",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-multi-unit",),
        )
        with self.assertRaises(ValueError):
            graph_multi_unit.add_metric_assertion(metric_bad_unit)

        # Positive independent verification for tickets=40 and hours=5:
        metric_tickets40 = MetricAssertion(
            id="m-good-tickets40",
            subject_id="multi-subject",
            numeric_value=40,
            unit="tickets",
            context="Processed 40 tickets",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-multi-unit",),
        )
        graph_multi_unit.add_metric_assertion(metric_tickets40)
        self.assertIn("m-good-tickets40", graph_multi_unit.metrics)

        metric_hours5 = MetricAssertion(
            id="m-good-hours5",
            subject_id="multi-subject",
            numeric_value=5,
            unit="hours",
            context="Processed tickets in 5 hours",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-multi-unit",),
        )
        graph_multi_unit.add_metric_assertion(metric_hours5)
        self.assertIn("m-good-hours5", graph_multi_unit.metrics)

        # Rejection of crossed unit-value assignments:
        # hours=40 MUST FAIL
        with self.assertRaises(ValueError):
            graph_multi_unit.add_metric_assertion(
                MetricAssertion("m-bad-h40", "multi-subject", 40, "hours", "in 40 hours", MetricVerification.VERIFIED, ("ev-multi-unit",))
            )
        # tickets=5 MUST FAIL
        with self.assertRaises(ValueError):
            graph_multi_unit.add_metric_assertion(
                MetricAssertion("m-bad-t5", "multi-subject", 5, "tickets", "Processed 5 tickets", MetricVerification.VERIFIED, ("ev-multi-unit",))
            )

        # 3. Exact semantic metric identity regressions:
        # Evidence: "Revenue decreased 40%."
        # Attempt: context="Latency decreased 40%" -> MUST FAIL
        ev_rev_dec = EvidenceRecord("ev-rev-dec", "Revenue decreased 40%.", "cv", "ach", metadata={"subject_id": "revenue-subject"})
        graph_rev_dec = TruthGraph((ev_rev_dec,))
        metric_lat_on_rev = MetricAssertion(
            id="m-lat-on-rev",
            subject_id="revenue-subject",
            numeric_value=40,
            unit="%",
            context="Latency decreased 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-rev-dec",),
        )
        with self.assertRaises(ValueError):
            graph_rev_dec.add_metric_assertion(metric_lat_on_rev)

        # Evidence: "Customer churn decreased 40%."
        # Attempt: context="Infrastructure cost decreased 40%" -> MUST FAIL
        ev_churn = EvidenceRecord("ev-churn", "Customer churn decreased 40%.", "cv", "ach", metadata={"subject_id": "churn-subject"})
        graph_churn = TruthGraph((ev_churn,))
        metric_infra_on_churn = MetricAssertion(
            id="m-infra-on-churn",
            subject_id="churn-subject",
            numeric_value=40,
            unit="%",
            context="Infrastructure cost decreased 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-churn",),
        )
        with self.assertRaises(ValueError):
            graph_churn.add_metric_assertion(metric_infra_on_churn)

        # 4. Unit Incompatibilities:
        # 40 users != 40 projects
        ev_users = EvidenceRecord("ev-users", "Onboarded 40 users.", "cv", "ach", metadata={"subject_id": "user-subject"})
        graph_users = TruthGraph((ev_users,))
        metric_projects_on_users = MetricAssertion(
            id="m-proj-on-users",
            subject_id="user-subject",
            numeric_value=40,
            unit="projects",
            context="Onboarded 40 projects",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-users",),
        )
        with self.assertRaises(ValueError):
            graph_users.add_metric_assertion(metric_projects_on_users)

        # 40 hours != 40 requests
        ev_hours = EvidenceRecord("ev-hours", "Delivered 40 hours of consulting.", "cv", "ach", metadata={"subject_id": "hour-subject"})
        graph_hours = TruthGraph((ev_hours,))
        metric_req_on_hours = MetricAssertion(
            id="m-req-on-hours",
            subject_id="hour-subject",
            numeric_value=40,
            unit="requests",
            context="Delivered 40 requests",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-hours",),
        )
        with self.assertRaises(ValueError):
            graph_hours.add_metric_assertion(metric_req_on_hours)

        # USD 40 != EUR 40
        ev_usd = EvidenceRecord("ev-usd", "Earned $40 revenue.", "cv", "ach", metadata={"subject_id": "usd-subject"})
        graph_usd = TruthGraph((ev_usd,))
        metric_eur_on_usd = MetricAssertion(
            id="m-eur-on-usd",
            subject_id="usd-subject",
            numeric_value=40,
            unit="EUR",
            context="Earned EUR 40 revenue",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-usd",),
        )
        with self.assertRaises(ValueError):
            graph_usd.add_metric_assertion(metric_eur_on_usd)

        # 5. Valid positive cases:
        # "Revenue decreased 40%" -> revenue / 40 / %
        metric_rev_pos = MetricAssertion(
            id="m-rev-pos",
            subject_id="revenue-subject",
            numeric_value=40,
            unit="%",
            context="Revenue decreased 40%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-rev-dec",),
        )
        graph_rev_dec.add_metric_assertion(metric_rev_pos)
        self.assertIn("m-rev-pos", graph_rev_dec.metrics)

        # "Latency fell 10%" -> latency / 10 / %
        ev_lat10 = EvidenceRecord("ev-lat10", "Latency fell 10%.", "cv", "ach", metadata={"subject_id": "lat-subject"})
        graph_lat10 = TruthGraph((ev_lat10,))
        metric_lat10_pos = MetricAssertion(
            id="m-lat10-pos",
            subject_id="lat-subject",
            numeric_value=10,
            unit="%",
            context="Latency fell 10%",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-lat10",),
        )
        graph_lat10.add_metric_assertion(metric_lat10_pos)
        self.assertIn("m-lat10-pos", graph_lat10.metrics)

        # "Managed 40 clients" -> clients / 40
        metric_clients_pos = MetricAssertion(
            id="m-clients-pos",
            subject_id="client-subject",
            numeric_value=40,
            unit="clients",
            context="Managed 40 clients",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-clients",),
        )
        graph_clients.add_metric_assertion(metric_clients_pos)
        self.assertIn("m-clients-pos", graph_clients.metrics)

        # "$40 revenue" -> USD/$ 40
        metric_usd_pos = MetricAssertion(
            id="m-usd-pos",
            subject_id="usd-subject",
            numeric_value=40,
            unit="USD",
            context="$40 revenue",
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-usd",),
        )
        graph_usd.add_metric_assertion(metric_usd_pos)
        self.assertIn("m-usd-pos", graph_usd.metrics)

    def test_invariant_4_candidate_authorized_by_assertions_not_extra_text(self):
        """Invariant 4: ClaimCandidate must be authorized by assertions, not their extra text.
        Regression:
          Evidence: 'Uses Python and served as Chief Executive Officer.'
          Selected assertion: skill.name = Python
          Candidate: 'Served as Chief Executive Officer.' -> MUST FAIL
          Candidate: 'Uses Python.' -> MUST PASS
        """
        from truth.models import (
            EvidenceRecord, AtomicAssertion, ClaimCandidate, AssertionType,
            VerificationStatus,
        )
        from truth.validator import ClaimValidator
        from truth.graph import TruthGraph

        ev_extra = EvidenceRecord("ev-extra", "Uses Python and served as Chief Executive Officer.", "cv", "skill")
        as_py = AtomicAssertion(
            id="as-py-skill",
            subject_id="skill-py",
            predicate="skill.name",
            value="Python",
            assertion_type=AssertionType.DIRECT_FACT,
            verification_status=VerificationStatus.VERIFIED,
            evidence_ids=("ev-extra",),
        )
        graph = TruthGraph((ev_extra,), (as_py,))
        validator = ClaimValidator(graph)

        # Candidate asserting unauthorized role -> MUST FAIL
        cand_bad = ClaimCandidate(
            text="Served as Chief Executive Officer.",
            material_assertion_ids=("as-py-skill",),
            requested_evidence_ids=("ev-extra",),
        )
        res_bad = validator.validate_candidate(cand_bad)
        self.assertFalse(res_bad.allowed)
        self.assertEqual(AssertionType.UNSUPPORTED_CLAIM, res_bad.assertion_type)
        self.assertTrue(any("not authorized" in r for r in res_bad.reasons))

        # Candidate asserting authorized skill -> MUST PASS
        cand_good = ClaimCandidate(
            text="Uses Python.",
            material_assertion_ids=("as-py-skill",),
            requested_evidence_ids=("ev-extra",),
        )
        res_good = validator.validate_candidate(cand_good)
        self.assertTrue(res_good.allowed, res_good.reasons)
        self.assertEqual(AssertionType.DIRECT_FACT, res_good.assertion_type)


if __name__ == "__main__":
    unittest.main()


