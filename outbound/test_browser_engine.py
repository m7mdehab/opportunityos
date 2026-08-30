"""Tests for OutboundBrowserEngine."""
import unittest
from matching.models import (
    ArtifactType,
    QualificationDecision,
    TailoredArtifact,
    TailoringPolicy,
    Track,
)
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, Modality, Polarity, VerificationStatus
from outbound.authority import ActionAuthority, GlobalKillSwitch
from outbound.browser_engine import MockBrowserDriver, OutboundBrowserEngine
from outbound.idempotency import IdempotencyLedger
from outbound.mock_harness import MockATSHarness
from outbound.models import (
    ActionStatus,
    BoundArtifact,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    SourceActionPolicy,
)
from outbound.registry import AdapterRegistry, SourceActionRegistry


class OutboundBrowserEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        GlobalKillSwitch.enable()
        self.ledger = IdempotencyLedger(":memory:")
        self.opportunity = Opportunity(
            id="opp-be-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
            source_id="1",
            organization="Acme",
            title="Lead",
            description="Role in Egypt.",
        )
        self.tg = TruthGraph()
        ev = EvidenceRecord(id="ev-1", source="profile", locator="p1", content="Founder Name. Authorized in Egypt.")
        self.tg.add_evidence(ev)
        self.tg.add_assertion(AtomicAssertion(
            id="a-1", subject_id="founder", predicate="identity.name",
            value="Founder Name", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-1",),
        ))

        self.policy = TailoringPolicy()
        raw_art = TailoredArtifact(
            artifact_id="art-1",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            template_version="1.0",
            policy_version="1.0",
            title="CV",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        self.artifact = BoundArtifact(artifact=raw_art, candidate_id="founder", workspace="default")

    def tearDown(self) -> None:
        GlobalKillSwitch.enable()

    def test_dry_run_prepares_without_mutations(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        rec = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.DRY_RUN,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.PREPARED)
        self.assertEqual(len(harness.fields_filled), 0)
        self.assertFalse(harness.submitted)

    def test_assisted_mode_fills_fields_without_submission(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        rec = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.PREPARED)
        self.assertEqual(harness.fields_filled.get("name"), "Founder Name")
        self.assertFalse(harness.submitted)


if __name__ == "__main__":
    unittest.main()
