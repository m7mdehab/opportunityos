"""Tests for Central Action Authority."""
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
from outbound.models import (
    ActionAuthorityDecision,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    BoundArtifact,
    ExecutionMode,
    FieldOntologyType,
    SourceActionPolicy,
)
from outbound.registry import AdapterRegistry, SourceActionRegistry


class ActionAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        GlobalKillSwitch.enable()
        self.opportunity = Opportunity(
            id="opp-auth-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/corp/jobs/1",
            source_id="1",
            organization="Corp",
            title="Lead",
            description="Role in Egypt.",
        )
        self.tg = TruthGraph()
        ev = EvidenceRecord(id="ev-1", source="profile", locator="p1", content="Founder Name.")
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

    def test_kill_switch_blocks_immediately(self) -> None:
        GlobalKillSwitch.disable()
        auth = ActionAuthority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.DRY_RUN,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("kill switch is ACTIVE" in reasons[0])

    def test_dry_run_allows_prepare(self) -> None:
        auth = ActionAuthority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.DRY_RUN,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.ALLOW_PREPARE)

    def test_assisted_mode_allows_fill(self) -> None:
        auth = ActionAuthority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.ASSISTED,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.ALLOW_FILL)

    def test_controlled_submit_requires_submit_enabled(self) -> None:
        adapter_reg = AdapterRegistry()
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("requires SUBMIT_ENABLED" in reasons[0])


if __name__ == "__main__":
    unittest.main()
