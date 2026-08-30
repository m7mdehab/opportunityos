"""Unit and contract tests for matching data models."""
from __future__ import annotations

import unittest

from opportunity.models import Track
from matching.models import (
    ArtifactSection,
    ArtifactType,
    CommitmentStatus,
    ForwardCommitment,
    GeneratedClaim,
    HardConstraintResult,
    MatchDimensionScore,
    MatchEvaluation,
    QualificationDecision,
    RequirementMapping,
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
        )
        self.assertEqual(hc.constraint_name, "geo")
        self.assertTrue(hc.passed)
        self.assertFalse(hc.is_hard_failure)

    def test_match_dimension_score_bounds(self) -> None:
        with self.assertRaises(ValueError):
            MatchDimensionScore(
                dimension_name="test",
                raw_score=1.5,
                weight=0.5,
                weighted_score=0.75,
                explanation="test",
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
