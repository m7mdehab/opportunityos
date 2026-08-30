"""Unit tests for Central Action Authority and Global Kill Switch."""
from __future__ import annotations

import unittest
from matching.models import ArtifactType, QualificationDecision, TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from outbound.authority import ActionAuthority, GlobalKillSwitch
from outbound.models import (
    ActionAuthorityDecision,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    ExecutionMode,
    FieldOntologyType,
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


class TestActionAuthority(unittest.TestCase):
    def setUp(self) -> None:
        GlobalKillSwitch.enable()
        self.registry = SourceActionRegistry()
        self.authority = ActionAuthority(registry=self.registry)
        self.tg = TruthGraph()
        self.opp = Opportunity(
            id="opp-1",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url="https://boards.greenhouse.io/cloudflare/jobs/101",
            source_id="101",
            organization="Cloudflare",
            title="Senior Data Engineer",
            description="Build scalable data systems in Python.",
            content_hash="opp-hash-1",
        )
        self.artifact = make_test_artifact("art-1", "opp-1", "opp-hash-1")

    def test_global_kill_switch_blocks_immediately(self) -> None:
        GlobalKillSwitch.disable()
        decision, reasons = self.authority.evaluate_action(
            opportunity=self.opp,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            adapter_name="greenhouse",
            workspace="ws",
            candidate_id="cand",
            qualification_decision=QualificationDecision.QUALIFIED,
            truth_graph=self.tg,
        )
        self.assertEqual(decision, ActionAuthorityDecision.BLOCK)
        self.assertIn("kill switch", reasons[0].lower())

    def test_dry_run_allows_prepare(self) -> None:
        decision, reasons = self.authority.evaluate_action(
            opportunity=self.opp,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.DRY_RUN,
            adapter_state=AdapterLifecycleState.EXPERIMENTAL,
            adapter_name="greenhouse",
            workspace="ws",
            candidate_id="cand",
            qualification_decision=QualificationDecision.QUALIFIED,
            truth_graph=self.tg,
        )
        self.assertEqual(decision, ActionAuthorityDecision.ALLOW_PREPARE)

    def test_assisted_mode_allows_fill_but_stops_on_unresolved(self) -> None:
        decision, reasons = self.authority.evaluate_action(
            opportunity=self.opp,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.ASSISTED,
            adapter_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            adapter_name="greenhouse",
            workspace="ws",
            candidate_id="cand",
            qualification_decision=QualificationDecision.QUALIFIED,
            truth_graph=self.tg,
            unresolved_mandatory_count=0,
        )
        self.assertEqual(decision, ActionAuthorityDecision.ALLOW_FILL)

        decision2, reasons2 = self.authority.evaluate_action(
            opportunity=self.opp,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.ASSISTED,
            adapter_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            adapter_name="greenhouse",
            workspace="ws",
            candidate_id="cand",
            qualification_decision=QualificationDecision.QUALIFIED,
            truth_graph=self.tg,
            unresolved_mandatory_count=2,
        )
        self.assertEqual(decision2, ActionAuthorityDecision.PAUSE_FOR_REVIEW)


if __name__ == "__main__":
    unittest.main()
