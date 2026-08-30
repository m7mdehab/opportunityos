"""Unit tests for Application Artifact Selector."""
from __future__ import annotations

import unittest
from matching.models import ArtifactType, TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from outbound.artifact_selector import ApplicationArtifactSelector


def make_test_artifact(
    artifact_id: str = "art-1",
    opportunity_id: str = "opp-1",
    opportunity_content_hash: str = "opp-hash-1",
    artifact_type: ArtifactType = ArtifactType.TAILORED_CV,
) -> TailoredArtifact:
    return TailoredArtifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        opportunity_id=opportunity_id,
        opportunity_content_hash=opportunity_content_hash,
        template_version="1.0",
        policy_version="1.0",
        title="Tailored CV",
        sections=(),
        generated_claims=(),
        commitment_checklist=(),
        compiled_at="2026-08-30T00:00:00Z",
    )


class TestArtifactSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.selector = ApplicationArtifactSelector()
        self.tg = TruthGraph()
        self.opp = Opportunity(
            id="opp-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://example.com",
            source_id="1",
            organization="Acme",
            title="Lead Engineer",
            description="Engineering lead.",
            content_hash="current-hash-123",
        )
        self.valid_artifact = make_test_artifact("art-valid", "opp-1", "current-hash-123")

    def test_select_valid_bound_artifact(self) -> None:
        art, errors = self.selector.select_artifact(
            candidate_id="cand-1",
            opportunity=self.opp,
            artifact_type=ArtifactType.TAILORED_CV,
            available_artifacts=(self.valid_artifact,),
            truth_graph=self.tg,
        )
        self.assertIsNotNone(art)
        self.assertEqual(art.artifact_id, "art-valid")
        self.assertEqual(len(errors), 0)

    def test_reject_stale_opportunity_hash(self) -> None:
        stale_artifact = make_test_artifact("art-stale", "opp-1", "old-stale-hash-000")
        art, errors = self.selector.select_artifact(
            candidate_id="cand-1",
            opportunity=self.opp,
            artifact_type=ArtifactType.TAILORED_CV,
            available_artifacts=(stale_artifact,),
            truth_graph=self.tg,
        )
        self.assertIsNone(art)
        self.assertTrue(any("STALE" in e for e in errors))

    def test_reject_wrong_opportunity_id(self) -> None:
        wrong_opp_art = make_test_artifact("art-wrong", "opp-unrelated-99", "current-hash-123")
        art, errors = self.selector.select_artifact(
            candidate_id="cand-1",
            opportunity=self.opp,
            artifact_type=ArtifactType.TAILORED_CV,
            available_artifacts=(wrong_opp_art,),
            truth_graph=self.tg,
        )
        self.assertIsNone(art)
        self.assertTrue(any("No artifact bound" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
