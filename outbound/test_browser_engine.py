"""Integration and E2E Mock Browser Execution Tests."""
from __future__ import annotations

import unittest
from matching.models import ArtifactType, QualificationDecision, TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, VerificationStatus
from outbound.authority import ActionAuthority, GlobalKillSwitch
from outbound.browser_engine import MockBrowserDriver, OutboundBrowserEngine
from outbound.mock_harness import MockATSHarness
from outbound.models import (
    ActionStatus,
    AdapterLifecycleState,
    ExecutionMode,
    SourceActionPolicy,
)
from outbound.registry import SourceActionRegistry


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


class TestBrowserEngineE2E(unittest.TestCase):
    def setUp(self) -> None:
        GlobalKillSwitch.enable()
        self.registry = SourceActionRegistry()
        self.registry.set_policy("greenhouse:cloudflare", SourceActionPolicy.SUBMIT_ALLOWED)
        self.authority = ActionAuthority(registry=self.registry)
        self.engine = OutboundBrowserEngine(authority=self.authority)

        self.tg = TruthGraph()
        ev = EvidenceRecord(
            id="ev-1", source="doc", locator="cv.pdf",
            content="Mohamed Ehab is a Data Engineer residing in Egypt with email mohamed@example.com."
        )
        self.tg.add_evidence(ev)
        self.tg.add_assertion(AtomicAssertion(
            id="a-1", subject_id="founder", predicate="identity.name", value="Mohamed Ehab",
            evidence_ids=("ev-1",), verification_status=VerificationStatus.VERIFIED,
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-2", subject_id="founder", predicate="identity.email", value="mohamed@example.com",
            evidence_ids=("ev-1",), verification_status=VerificationStatus.VERIFIED,
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-3", subject_id="founder", predicate="authorization.jurisdiction", value="Egypt",
            evidence_ids=("ev-1",), verification_status=VerificationStatus.VERIFIED,
        ))

        self.policy = TailoringPolicy(default_notice_period_days=30)
        self.opp = Opportunity(
            id="opp-1",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url="https://boards.greenhouse.io/cloudflare/jobs/101",
            source_id="101",
            organization="Cloudflare",
            title="Senior Data Engineer",
            description="Engineering role.",
            content_hash="opp-hash-1",
        )
        self.artifact = make_test_artifact("art-1", "opp-1", "opp-hash-1")

    def test_dry_run_executes_safely_without_mutation(self) -> None:
        harness = MockATSHarness(platform="greenhouse")
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.DRY_RUN,
            adapter_state=AdapterLifecycleState.EXPERIMENTAL,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.PREPARED)
        self.assertFalse(harness.submitted)
        self.assertEqual(len(harness.fields_state), 0)

    def test_assisted_mode_fills_fields_and_strictly_never_submits(self) -> None:
        harness = MockATSHarness(platform="greenhouse")
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            adapter_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.PREPARED)
        self.assertFalse(harness.submitted)
        self.assertTrue(len(harness.fields_state) > 0)
        self.assertEqual(harness.fields_state.get("first_name"), "Mohamed")

    def test_controlled_submit_graduated_adapter_confirms_receipt(self) -> None:
        harness = MockATSHarness(platform="greenhouse")
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.CONFIRMED)
        self.assertTrue(harness.submitted)
        self.assertIsNotNone(rec.confirmation_evidence)
        self.assertTrue(rec.confirmation_evidence.confirmed)
        self.assertEqual(rec.external_reference_id, "APP-987654")


if __name__ == "__main__":
    unittest.main()
