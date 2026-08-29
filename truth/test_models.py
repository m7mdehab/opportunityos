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
    VerificationStatus,
)


class ModelTests(unittest.TestCase):
    def test_enums_have_stable_wire_values(self):
        self.assertEqual("verified", VerificationStatus.VERIFIED.value)
        self.assertEqual("derived_capability", AssertionType.DERIVED_CAPABILITY.value)
        self.assertEqual("planned", CertificationState.PLANNED.value)
        self.assertEqual("approximate", MetricVerification.APPROXIMATE.value)

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

    def test_capability_industry_sets_cannot_contradict(self):
        with self.assertRaises(ValueError):
            CapabilityProfile(
                "cap-1", target_industries=("Finance",), excluded_industries=("finance",)
            )

    def test_service_requires_evidence(self):
        with self.assertRaises(ValueError):
            ServiceRecord("service-1", "Assessment", "Performs assessments", ())


if __name__ == "__main__":
    unittest.main()
