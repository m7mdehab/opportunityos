"""Unit and contract tests for matching data models."""
from __future__ import annotations

import unittest

from opportunity.models import Track
from matching.models import (
    ArtifactSection,
    ArtifactType,
    ConfidenceFactor,
    CommitmentStatus,
    ForwardCommitment,
    GeneratedClaim,
    HardConstraintResult,
    MatchDimensionScore,
    MatchEvaluation,
    QualificationDecision,
    RequirementMapping,
    RequirementPriority,
    RequirementSupportStatus,
    ScoringPolicy,
    TailoredArtifact,
    TailoringPolicy,
)


class TestMatchingModels(unittest.TestCase):
    def test_hard_constraint_result(self) -> None:
        hc = HardConstraintResult(
            constraint_name="geo",
            passed=True,
            reason="Eligible",
            required_field="location",
            founder_fact="Egypt",
            provenance_pointer="fixture:job.location",
        )
        self.assertEqual(hc.constraint_name, "geo")
        self.assertTrue(hc.passed)
        self.assertFalse(hc.is_hard_failure)
        self.assertEqual(hc.constraint_type, "geo")
        self.assertEqual(hc.decision, True)
        self.assertEqual(hc.job_evidence_field, "location")
        self.assertEqual(hc.founder_side_evidence, "Egypt")
        self.assertEqual(hc.explanation, "Eligible")
        self.assertGreaterEqual(hc.confidence, 0.0)
        self.assertLessEqual(hc.confidence, 1.0)

    def test_hard_failure_requires_job_source_pointer_and_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "source pointer"):
            HardConstraintResult(
                constraint_name="work_authorization",
                passed=False,
                reason="Not authorized",
                required_field="description",
                founder_fact="Verified negative authorization",
                is_hard_failure=True,
                job_evidence_text="Must have authorization",
            )

    def test_hard_constraint_evidence_aliases_and_bounds(self) -> None:
        hc = HardConstraintResult(
            constraint_name="language_requirement",
            passed=False,
            reason="Missing required language",
            required_field="description",
            founder_fact="Verified lack of proficiency",
            is_hard_failure=True,
            provenance_pointer="fixture:job.description",
            job_evidence_text="Must speak French",
            confidence=0.97,
            requirement_mandatory=True,
        )
        self.assertEqual(hc.constraint_type, "language_requirement")
        self.assertEqual(hc.job_evidence_text, "Must speak French")
        self.assertEqual(hc.job_evidence_field, "description")
        self.assertEqual(hc.source_pointer, "fixture:job.description")
        self.assertEqual(hc.founder_side_evidence, "Verified lack of proficiency")
        self.assertFalse(hc.decision)
        self.assertEqual(hc.confidence, 0.97)
        self.assertIs(hc.requirement_mandatory, True)
        self.assertEqual(hc.explanation, hc.reason)

        with self.assertRaisesRegex(ValueError, "confidence"):
            HardConstraintResult(
                constraint_name="geo",
                passed=None,
                reason="Unresolved",
                required_field="remote_scope",
                founder_fact="Unknown",
                provenance_pointer="fixture:job.remote_scope",
                confidence=1.5,
            )

    def test_match_dimension_score_bounds(self) -> None:
        with self.assertRaises(ValueError):
            MatchDimensionScore(
                dimension_name="test",
                raw_score=1.5,
                weight=0.5,
                weighted_score=0.75,
                explanation="test",
            )

    def test_confidence_factor_is_named_and_bounded(self) -> None:
        factor = ConfidenceFactor(
            name="description_completeness",
            score=72.5,
            explanation="Synthetic description length falls in the middle heuristic band.",
        )
        self.assertEqual(factor.score, 72.5)
        with self.assertRaisesRegex(ValueError, "name"):
            ConfidenceFactor(name=" ", score=50.0, explanation="synthetic")
        with self.assertRaisesRegex(ValueError, "score"):
            ConfidenceFactor(name="invalid", score=100.1, explanation="synthetic")

    def test_requirement_mapping_priority_is_typed_and_compatible(self) -> None:
        legacy = RequirementMapping(
            requirement_text="Python",
            requirement_type="skill",
            status=RequirementSupportStatus.UNKNOWN,
        )
        self.assertIs(legacy.requirement_priority, RequirementPriority.UNKNOWN)

        mandatory = RequirementMapping(
            requirement_text="Must have Python",
            requirement_type="skill",
            status=RequirementSupportStatus.UNKNOWN,
            requirement_priority="mandatory",
        )
        self.assertIs(mandatory.requirement_priority, RequirementPriority.MANDATORY)

        with self.assertRaisesRegex(ValueError, "requirement_priority"):
            RequirementMapping(
                requirement_text="Python",
                requirement_type="skill",
                status=RequirementSupportStatus.UNKNOWN,
                requirement_priority="ambiguous",
            )

    def test_tailored_artifact_hash_generation(self) -> None:
        sec = ArtifactSection(
            section_id="sec1",
            heading="Header",
            content="Some body text",
            items=("Item 1", "Item 2"),
        )
        claim = GeneratedClaim(
            claim_id="c1",
            text="Claim 1",
            section_id="sec1",
            assertion_ids=("a1",),
            evidence_ids=("ev1",),
        )
        art = TailoredArtifact(
            artifact_id="art-1",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id="opp-100",
            opportunity_content_hash="hash123",
            template_version="v1.0",
            policy_version="1.0.0",
            title="CV for Opp",
            sections=(sec,),
            generated_claims=(claim,),
            commitment_checklist=(),
            compiled_at="2026-08-30",
        )
        self.assertTrue(bool(art.artifact_hash))
        self.assertEqual(len(art.artifact_hash), 64)


if __name__ == "__main__":
    unittest.main()
