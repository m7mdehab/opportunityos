"""Tests for ApplicationArtifactSelector non-bypassable ownership."""
import unittest
from matching.models import ArtifactType, TailoredArtifact
from matching.validator import ArtifactClaimValidator
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, Modality, Polarity, VerificationStatus
from outbound.artifact_selector import ApplicationArtifactSelector
from outbound.models import BoundArtifact


class ApplicationArtifactSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.opportunity = Opportunity(
            id="opp-100",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/corp/jobs/100",
            source_id="100",
            organization="Corp",
            title="Senior Architect",
            description="Senior Architect role.",
        )
        self.tg = TruthGraph()
        ev = EvidenceRecord(id="ev-1", source="contract", locator="p1", content="Senior Architect", metadata={"title": "Senior Architect"})
        self.tg.add_evidence(ev)
        self.tg.add_assertion(AtomicAssertion(
            id="a-1", subject_id="founder", predicate="employment.title",
            value="Senior Architect", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-1",),
        ))
        self.selector = ApplicationArtifactSelector()

    def test_raw_unowned_artifact_is_strictly_rejected(self) -> None:
        raw_art = TailoredArtifact(
            artifact_id="art-raw",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            template_version="1.0",
            policy_version="1.0",
            title="Raw CV",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        selected, errors = self.selector.select_artifact(
            candidate_id="founder",
            opportunity=self.opportunity,
            artifact_type=ArtifactType.TAILORED_CV,
            available_artifacts=(raw_art,),
            truth_graph=self.tg,
            workspace="default",
        )
        self.assertIsNone(selected)
        self.assertTrue(any("Raw unowned TailoredArtifact rejected" in err for err in errors))

    def test_wrong_candidate_artifact_is_strictly_blocked(self) -> None:
        raw_art = TailoredArtifact(
            artifact_id="art-cand-a",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            template_version="1.0",
            policy_version="1.0",
            title="CV for Cand A",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        bound_a = BoundArtifact(artifact=raw_art, candidate_id="candidate_a", workspace="workspace_1")

        selected, errors = self.selector.select_artifact(
            candidate_id="candidate_b",
            opportunity=self.opportunity,
            artifact_type=ArtifactType.TAILORED_CV,
            available_artifacts=(bound_a,),
            truth_graph=self.tg,
            workspace="workspace_1",
        )
        self.assertIsNone(selected)
        self.assertTrue(any("candidate 'candidate_a' does not match requested candidate 'candidate_b'" in err for err in errors))

    def test_wrong_workspace_artifact_is_strictly_blocked(self) -> None:
        raw_art = TailoredArtifact(
            artifact_id="art-ws-1",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            template_version="1.0",
            policy_version="1.0",
            title="CV for WS 1",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        bound_ws1 = BoundArtifact(artifact=raw_art, candidate_id="founder", workspace="workspace_1")

        selected, errors = self.selector.select_artifact(
            candidate_id="founder",
            opportunity=self.opportunity,
            artifact_type=ArtifactType.TAILORED_CV,
            available_artifacts=(bound_ws1,),
            truth_graph=self.tg,
            workspace="workspace_2",
        )
        self.assertIsNone(selected)
        self.assertTrue(any("workspace 'workspace_1' does not match requested workspace 'workspace_2'" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
