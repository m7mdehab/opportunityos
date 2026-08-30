"""Tests for OutboundBrowserEngine orchestration, split registry prevention, and staleness detection."""
import unittest
from matching.models import ArtifactType, TailoredArtifact, TailoringPolicy, Track
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, Modality, Polarity, VerificationStatus
from outbound.authority import ActionAuthority
from outbound.browser_engine import OutboundBrowserEngine
from outbound.models import BoundArtifact, ExecutionMode, SourceActionPolicy
from outbound.registry import AdapterRegistry, SourceActionRegistry


class BrowserEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.opportunity = Opportunity(
            id="opp-be-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/corp/jobs/1",
            source_id="1",
            organization="Corp",
            title="Lead",
            description="Role in Egypt.",
        )
        self.policy = TailoringPolicy(
            default_notice_period_days=30,
            default_sponsorship_required=False,
        )

    def test_split_adapter_registry_strictly_rejected(self) -> None:
        auth_adapter_reg = AdapterRegistry()
        different_adapter_reg = AdapterRegistry()
        auth = ActionAuthority(adapter_registry=auth_adapter_reg)

        with self.assertRaises(ValueError) as ctx:
            OutboundBrowserEngine(authority=auth, adapter_registry=different_adapter_reg)
        self.assertTrue("Split adapter registry rejected" in str(ctx.exception))

    def test_split_source_registry_strictly_rejected(self) -> None:
        auth_src_reg = SourceActionRegistry()
        different_src_reg = SourceActionRegistry()
        auth = ActionAuthority(registry=auth_src_reg)

        with self.assertRaises(ValueError) as ctx:
            OutboundBrowserEngine(authority=auth, source_registry=different_src_reg)
        self.assertTrue("Split source registry rejected" in str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
