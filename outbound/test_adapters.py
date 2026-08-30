"""Unit tests for Outbound Platform Adapters."""
from __future__ import annotations

import unittest
from matching.models import ArtifactType, TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from outbound.adapters import (
    AshbyOutboundAdapter,
    FreelanceProposalAdapter,
    GenericFormOutboundAdapter,
    GreenhouseOutboundAdapter,
    LeverOutboundAdapter,
    ProcurementPackageAdapter,
)
from outbound.models import AdapterLifecycleState


def make_test_artifact(
    artifact_id: str = "art-1",
    opportunity_id: str = "opp-1",
    opportunity_content_hash: str = "opp-hash-1",
    artifact_type: ArtifactType = ArtifactType.RFP_RESPONSE_SCAFFOLD,
) -> TailoredArtifact:
    return TailoredArtifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        opportunity_id=opportunity_id,
        opportunity_content_hash=opportunity_content_hash,
        template_version="1.0",
        policy_version="1.0",
        title="RFP Response Scaffold",
        sections=(),
        generated_claims=(),
        commitment_checklist=(),
        compiled_at="2026-08-30T00:00:00Z",
    )


class TestOutboundAdapters(unittest.TestCase):
    def setUp(self) -> None:
        self.tg = TruthGraph()
        self.policy = TailoringPolicy()
        self.opp = Opportunity(
            id="opp-1",
            track=Track.PROCUREMENT,
            source="world_bank",
            source_url="https://worldbank.org/procurement/99",
            source_id="WB-99",
            organization="World Bank",
            title="Consultant",
            description="Procurement consultancy.",
            content_hash="hash-wb",
        )
        self.artifact = make_test_artifact("art-proc", "opp-1", "hash-wb")

    def test_procurement_package_dossier_structure(self) -> None:
        adapter = ProcurementPackageAdapter()
        dossier = adapter.prepare_procurement_dossier(self.opp, self.artifact, self.tg, self.policy)
        self.assertEqual(dossier["notice_id"], "WB-99")
        self.assertEqual(dossier["submission_mode"], "manual_portal_upload_only")
        self.assertTrue(dossier["legal_binding_acceptance_required"])

    def test_adapter_graduation_can_submit(self) -> None:
        gh = GreenhouseOutboundAdapter(lifecycle_state=AdapterLifecycleState.SUBMIT_ELIGIBLE)
        self.assertFalse(gh.can_submit())
        gh.lifecycle_state = AdapterLifecycleState.SUBMIT_ENABLED
        self.assertTrue(gh.can_submit())


if __name__ == "__main__":
    unittest.main()
