"""Adversarial and Claim Validation Tests for Matching Subsystem."""
from __future__ import annotations

import unittest

from matching.compiler_employment import EmploymentArtifactCompiler
from matching.compiler_independent import IndependentArtifactCompiler
from matching.models import (
    ArtifactSection,
    ArtifactType,
    CommitmentStatus,
    ForwardCommitment,
    GeneratedClaim,
    TailoredArtifact,
    TailoringPolicy,
)
from matching.test_qualification import create_test_graph, create_test_opportunity
from matching.validator import ArtifactClaimValidator
from truth.models import AtomicAssertion, Modality, VerificationStatus


class TestArtifactValidatorAndAdversarial(unittest.TestCase):
    def setUp(self) -> None:
        self.truth_graph = create_test_graph()
        self.validator = ArtifactClaimValidator()
        self.emp_compiler = EmploymentArtifactCompiler()

    def test_valid_compiled_cv_passes_validation(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        result = self.validator.validate_artifact(cv, self.truth_graph)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
        self.assertTrue(result.verified_claims > 0)
        self.assertEqual(result.unverified_claims, 0)

    def test_adversarial_unsupported_skill_rejected(self) -> None:
        # Generate valid CV then inject an unsupported material claim
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        fake_claim = GeneratedClaim(
            claim_id="claim-fake-skill",
            text="Kubernetes Expert",
            section_id="skills",
            assertion_ids=("a-nonexistent-k8s",),
            evidence_ids=(),
        )
        tampered_cv = TailoredArtifact(
            artifact_id=cv.artifact_id,
            artifact_type=cv.artifact_type,
            opportunity_id=cv.opportunity_id,
            opportunity_content_hash=cv.opportunity_content_hash,
            template_version=cv.template_version,
            policy_version=cv.policy_version,
            title=cv.title,
            sections=cv.sections,
            generated_claims=cv.generated_claims + (fake_claim,),
            commitment_checklist=cv.commitment_checklist,
            compiled_at=cv.compiled_at,
        )
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("non-existent assertion" in err for err in result.errors))

    def test_adversarial_unverified_status_assertion_rejected(self) -> None:
        # Add unverified assertion to graph and reference it in artifact
        unverified_assertion = AtomicAssertion(
            id="a-unverified-skill",
            subject_id="founder",
            predicate="skill.name",
            value="Solidity",
            evidence_ids=("ev-py",),
            verification_status=VerificationStatus.UNVERIFIED,
        )
        self.truth_graph._assertions["a-unverified-skill"] = unverified_assertion

        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        unverified_claim = GeneratedClaim(
            claim_id="claim-solidity",
            text="Solidity",
            section_id="skills",
            assertion_ids=("a-unverified-skill",),
            evidence_ids=("ev-py",),
        )
        tampered_cv = TailoredArtifact(
            artifact_id=cv.artifact_id,
            artifact_type=cv.artifact_type,
            opportunity_id=cv.opportunity_id,
            opportunity_content_hash=cv.opportunity_content_hash,
            template_version=cv.template_version,
            policy_version=cv.policy_version,
            title=cv.title,
            sections=cv.sections,
            generated_claims=cv.generated_claims + (unverified_claim,),
            commitment_checklist=cv.commitment_checklist,
            compiled_at=cv.compiled_at,
        )
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("unverified assertion" in err for err in result.errors))

    def test_adversarial_planned_credential_upgrade_rejected(self) -> None:
        # Add PLANNED credential assertion
        planned_assertion = AtomicAssertion(
            id="a-planned-cert",
            subject_id="founder",
            predicate="credential.status",
            value="AWS Solutions Architect Professional",
            evidence_ids=("ev-py",),
            verification_status=VerificationStatus.UNVERIFIED,
            modality=Modality.PLANNED,
        )
        self.truth_graph._assertions["a-planned-cert"] = planned_assertion

        # Construct artifact that falsely states completed credential
        sec = ArtifactSection(
            section_id="certs",
            heading="Certifications",
            content="Completed AWS Solutions Architect Professional in 2026.",
            items=("Completed AWS Solutions Architect Professional",),
            assertion_ids=("a-planned-cert",),
            evidence_ids=("ev-py",),
        )
        claim = GeneratedClaim(
            claim_id="claim-cert",
            text="Completed AWS Solutions Architect Professional",
            section_id="certs",
            assertion_ids=("a-planned-cert",),
            evidence_ids=("ev-py",),
        )
        art = TailoredArtifact(
            artifact_id="art-cert",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id="opp-cert",
            opportunity_content_hash="hashcert",
            template_version="v1.0",
            policy_version="1.0.0",
            title="CV with Cert",
            sections=(sec,),
            generated_claims=(claim,),
            commitment_checklist=(),
            compiled_at="2026-08-30",
        )
        result = self.validator.validate_artifact(art, self.truth_graph)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Planned credential" in err or "unverified assertion" in err for err in result.errors))


if __name__ == "__main__":
    unittest.main()
