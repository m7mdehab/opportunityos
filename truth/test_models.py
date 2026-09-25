import unittest
from dataclasses import FrozenInstanceError
from datetime import date

from truth.models import (
    Achievement,
    AssertionType,
    BusinessCapacity,
    CapabilityProfile,
    CertificationRecord,
    CertificationState,
    EvidenceRecord,
    MetricVerification,
    ServiceRecord,
    TargetRoleRecord,
    TargetRoleTier,
    VerificationStatus,
)


class ModelTests(unittest.TestCase):
    def test_enums_have_stable_wire_values(self):
        self.assertEqual("verified", VerificationStatus.VERIFIED.value)
        self.assertEqual("derived_capability", AssertionType.DERIVED_CAPABILITY.value)
        self.assertEqual("planned", CertificationState.PLANNED.value)
        self.assertEqual("approximate", MetricVerification.APPROXIMATE.value)
        self.assertEqual(("primary", "adjacent", "stretch"), tuple(tier.value for tier in TargetRoleTier))

    def test_target_role_tier_is_optional_and_typed(self):
        role = TargetRoleRecord("target-data-engineer", "Data Engineer", ("ev-target",))
        self.assertIsNone(role.tier)
        self.assertEqual(
            TargetRoleTier.PRIMARY,
            TargetRoleRecord(
                "target-llm-engineer", "LLM Engineer", ("ev-target",), TargetRoleTier.PRIMARY
            ).tier,
        )
        with self.assertRaisesRegex(ValueError, "TargetRoleTier"):
            TargetRoleRecord("target-invalid", "Data Engineer", ("ev-target",), "primary")

    def test_models_are_immutable(self):
        evidence = EvidenceRecord(
            "ev-1", "Python", "fixture", "skills.0", metadata={"nested": ["fixed"]}
        )
        with self.assertRaises(FrozenInstanceError):
            evidence.content = "Rust"
        with self.assertRaises(TypeError):
            evidence.metadata["changed"] = True
        self.assertIsInstance(evidence.metadata["nested"], tuple)

    def test_explicit_null_is_structural_not_an_empty_string(self):
        record = EvidenceRecord(
            "ev-null", None, "fixture", "unknown.value",
            verification_status=VerificationStatus.EXPLICIT_NULL,
        )
        self.assertIsNone(record.content)
        with self.assertRaises(ValueError):
            EvidenceRecord(
                "ev-bad", "", "fixture", "unknown.value",
                verification_status=VerificationStatus.EXPLICIT_NULL,
            )
        with self.assertRaises(ValueError):
            EvidenceRecord("ev-bad", None, "fixture", "unknown.value")

    def test_evidence_cannot_encode_a_prohibited_claim_as_support(self):
        with self.assertRaises(ValueError):
            EvidenceRecord(
                "ev-1", "impossible claim", "fixture", "claim",
                assertion_type=AssertionType.PROHIBITED_CLAIM,
            )

    def test_achievement_requires_unique_atomic_evidence(self):
        with self.assertRaises(ValueError):
            Achievement("a-1", "Did a thing", ("ev-1", "ev-1"))
        with self.assertRaises(ValueError):
            Achievement("a-1", "Did a thing", ())

    def test_planned_certification_cannot_have_issued_date(self):
        with self.assertRaises(ValueError):
            CertificationRecord(
                "cert-1", "Example Certificate", "Example Issuer",
                CertificationState.PLANNED, ("ev-1",), issued_date=date(2026, 1, 1),
            )

    def test_business_capacity_validates_ranges(self):
        with self.assertRaises(ValueError):
            BusinessCapacity(
                "capacity-1", ("ev-1",), min_project_value=5000, max_project_value=1000
            )
        with self.assertRaises(ValueError):
            BusinessCapacity("capacity-1", ("ev-1",), hours_per_week=-1)
        with self.assertRaises(ValueError):
            BusinessCapacity("capacity-1", ("ev-1",), annual_turnover_usd=-500.0)

    def test_business_capacity_qualification_fields(self):
        capacity = BusinessCapacity(
            "capacity-1", ("ev-1",),
            annual_turnover_usd=150000.0,
            bid_bond_capacity_usd=50000.0,
            legal_capacity="registered_entity",
        )
        self.assertEqual(150000.0, capacity.annual_turnover_usd)
        self.assertEqual(50000.0, capacity.bid_bond_capacity_usd)
        self.assertEqual("registered_entity", capacity.legal_capacity)

    def test_capability_industry_sets_cannot_contradict(self):
        with self.assertRaises(ValueError):
            CapabilityProfile(
                "cap-1", target_industries=("Finance",), excluded_industries=("finance",)
            )

    def test_service_requires_evidence(self):
        with self.assertRaises(ValueError):
            ServiceRecord("service-1", "Assessment", "Performs assessments", ())

    def test_atomic_assertion_model_invariants(self):
        from truth.models import AtomicAssertion, Polarity, Modality
        assertion = AtomicAssertion(
            id="as-1",
            subject_id="job-1",
            predicate="employment.title",
            value="Data Engineer",
            assertion_type=AssertionType.DIRECT_FACT,
            verification_status=VerificationStatus.VERIFIED,
            evidence_ids=("ev-1",),
            polarity=Polarity.POSITIVE,
            modality=Modality.DEFINITE,
        )
        self.assertEqual("employment.title", assertion.predicate)
        self.assertEqual("Data Engineer", assertion.value)
        self.assertEqual(Polarity.POSITIVE, assertion.polarity)

        with self.assertRaises(ValueError):
            AtomicAssertion("as-bad", "job-1", "", "Val")
        with self.assertRaises(ValueError):
            AtomicAssertion("as-bad", "job-1", "pred", "Val", effective_from=date(2025, 1, 1), effective_to=date(2024, 1, 1))

    def test_typed_relation_model_invariants(self):
        from truth.models import TypedRelation, RelationType
        relation = TypedRelation(
            id="rel-1",
            source_id="job-1",
            relation_type=RelationType.ACHIEVED_DURING,
            target_id="ach-1",
            evidence_ids=("ev-1",),
        )
        self.assertEqual(RelationType.ACHIEVED_DURING, relation.relation_type)
        with self.assertRaises(ValueError):
            TypedRelation("rel-bad", "job-1", "type", "ach-1", effective_from=date(2025, 1, 1), effective_to=date(2024, 1, 1))

    def test_metric_assertion_model_invariants(self):
        from truth.models import MetricAssertion, Modality
        metric = MetricAssertion(
            id="met-1",
            subject_id="ach-1",
            numeric_value=40.0,
            unit="%",
            context="latency reduction",
            modality=Modality.DEFINITE,
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=("ev-1",),
        )
        self.assertEqual(40.0, metric.numeric_value)
        self.assertEqual("%", metric.unit)

        with self.assertRaises(ValueError):
            MetricAssertion("met-bad", "ach-1", -5, "%", "bad")
        with self.assertRaises(ValueError):
            MetricAssertion("met-bad", "ach-1", float("nan"), "%", "bad")

    def test_claim_candidate_model_invariants(self):
        from truth.models import ClaimCandidate, ProhibitedConceptCategory
        candidate = ClaimCandidate(
            text="Candidate text",
            material_assertion_ids=("as-1",),
            concepts=frozenset({ProhibitedConceptCategory.GUARANTEED_OUTCOME}),
            requested_evidence_ids=("ev-1",),
        )
        self.assertIn(ProhibitedConceptCategory.GUARANTEED_OUTCOME, candidate.concepts)
        with self.assertRaises(ValueError):
            ClaimCandidate(text="", material_assertion_ids=())

    def test_business_capacity_rejects_non_integer_for_int_fields(self):
        with self.assertRaises(ValueError):
            BusinessCapacity("cap-1", ("ev-1",), hours_per_week=1.5)
        with self.assertRaises(ValueError):
            BusinessCapacity("cap-1", ("ev-1",), min_project_value=1000.5)


if __name__ == "__main__":
    unittest.main()
