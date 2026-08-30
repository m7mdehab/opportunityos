"""15 Required Zero-Tolerance Invariant Tests for Outbound Safety Subsystem."""
import json
import os
import tempfile
import unittest
from pathlib import Path
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
    ActionAuthorityDecision,
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    BoundArtifact,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    GraduationRecord,
    SourceActionPolicy,
)
from outbound.ontology import FieldClassifier
from outbound.registry import AdapterRegistry, SourceActionRegistry


class ZeroToleranceOutboundTests(unittest.TestCase):
    def setUp(self) -> None:
        GlobalKillSwitch.enable()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.ledger = IdempotencyLedger(self.db_path)

        self.temp_ev_dir = tempfile.TemporaryDirectory()
        self.ev_dir = Path(self.temp_ev_dir.name)
        gh_ev = self.ev_dir / "greenhouse_graduation_evidence.json"
        gh_ev.write_text(json.dumps({"run_id": "test-gh-run-001", "success": True}), encoding="utf-8")

        self.opportunity = Opportunity(
            id="opp-zt-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
            source_id="1",
            organization="Acme",
            title="Senior Architect",
            description="Role in Egypt.",
        )
        self.tg = TruthGraph()
        ev = EvidenceRecord(id="ev-zt-1", source="passport", locator="p1", content="Founder Name. Authorized in Egypt. Country: Egypt.")
        self.tg.add_evidence(ev)
        self.tg.add_assertion(AtomicAssertion(
            id="a-name", subject_id="founder", predicate="identity.name",
            value="Founder Name", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-zt-1",),
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-auth", subject_id="founder", predicate="authorization.jurisdiction",
            value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-zt-1",),
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-country", subject_id="founder", predicate="identity.country",
            value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-zt-1",),
        ))

        self.policy = TailoringPolicy(
            default_notice_period_days=30,
            default_currency="USD",
            default_hourly_rate=100.0,
            default_sponsorship_required=False,
        )
        raw_artifact = TailoredArtifact(
            artifact_id="art-zt-1",
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
        self.raw_artifact = raw_artifact
        self.artifact = BoundArtifact(artifact=raw_artifact, candidate_id="founder", workspace="default")

    def tearDown(self) -> None:
        GlobalKillSwitch.enable()
        self.temp_ev_dir.cleanup()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_submit_ready_authority(self) -> ActionAuthority:
        adapter_reg = AdapterRegistry(evidence_dir=self.ev_dir)
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        return ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)

    def test_zt_01_global_kill_switch_strictly_blocks_submission(self) -> None:
        auth = self._create_submit_ready_authority()
        GlobalKillSwitch.disable()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("kill switch" in reasons[0].lower())

    def test_zt_02_unauthorized_source_strictly_blocks_action(self) -> None:
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.PROHIBITED})
        auth = ActionAuthority(registry=src_reg)
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.ASSISTED,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("PROHIBITED" in reasons[0])

    def test_zt_03_unsupported_action_class_strictly_blocks_action(self) -> None:
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.PREPARE_ALLOWED})
        auth = ActionAuthority(registry=src_reg)
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.ASSISTED,  # Requires BROWSER_FILL_ALLOWED
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("prohibits assisted fill" in reasons[0] or "PREPARE_ALLOWED" in reasons[0])

    def test_zt_04_unregistered_adapter_strictly_blocks_action(self) -> None:
        auth = ActionAuthority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="unknown_ats_adapter",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("not registered" in reasons[0])

    def test_zt_05_ungraduated_adapter_strictly_blocks_controlled_submit(self) -> None:
        # Default registry without evidence has greenhouse in ASSISTED_VERIFIED
        adapter_reg = AdapterRegistry()
        auth = ActionAuthority(adapter_registry=adapter_reg)
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("requires SUBMIT_ENABLED" in reasons[0])

    def test_zt_06_ineligible_opportunity_strictly_blocks_action(self) -> None:
        auth = self._create_submit_ready_authority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
            qualification_decision=QualificationDecision.INELIGIBLE,
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("ineligible" in reasons[0])

    def test_zt_07_uncertain_qualification_pauses_for_review(self) -> None:
        auth = self._create_submit_ready_authority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
            qualification_decision=QualificationDecision.UNCERTAIN,
        )
        self.assertEqual(dec, ActionAuthorityDecision.PAUSE_FOR_REVIEW)
        self.assertTrue("UNCERTAIN" in reasons[0])

    def test_zt_08_unverified_factual_claim_fails_closed_to_pause(self) -> None:
        tg_empty = TruthGraph()
        engine = OutboundBrowserEngine(authority=self._create_submit_ready_authority(), ledger=self.ledger)
        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=tg_empty,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)
        self.assertTrue("mandatory question(s) unresolved" in record.blocker_reason or "Red" in record.blocker_reason)

    def test_zt_09_prohibited_concept_fails_closed_to_pause(self) -> None:
        classified = FieldClassifier.classify_field("Acknowledge under penalty of perjury", name="sig", field_id="sig")
        self.assertEqual(classified.ontology_type, FieldOntologyType.LEGAL_DECLARATION)
        self.assertEqual(classified.sensitivity_class, AnswerClass.RED)

    def test_zt_10_red_question_blocks_autonomous_controlled_submit(self) -> None:
        auth = self._create_submit_ready_authority()
        red_answer = ApplicationAnswer(
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            action_id="act-zt",
            field_type=FieldOntologyType.LEGAL_DECLARATION,
            original_label="Legal Signature",
            normalized_question="legal signature",
            answer=None,
            answer_class=AnswerClass.RED,
            answer_source="red_question_policy",
            disposition="pause",
        )
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(red_answer,),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.PAUSE_FOR_REVIEW)
        self.assertTrue("Red answer(s)" in reasons[0])

    def test_zt_11_duplicate_submission_strictly_blocks_action(self) -> None:
        auth = self._create_submit_ready_authority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
            is_duplicate=True,
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("Duplicate" in reasons[0])

    def test_zt_12_captcha_challenge_strictly_blocks_action(self) -> None:
        auth = self._create_submit_ready_authority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
            captcha_detected=True,
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("CAPTCHA" in reasons[0])

    def test_zt_13_mfa_challenge_pauses_for_human_intervention(self) -> None:
        auth = self._create_submit_ready_authority()
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=self.artifact,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
            mfa_detected=True,
        )
        self.assertEqual(dec, ActionAuthorityDecision.PAUSE_FOR_REVIEW)
        self.assertTrue("MFA" in reasons[0])

    def test_zt_14_mismatched_opportunity_artifact_hash_strictly_blocks(self) -> None:
        auth = self._create_submit_ready_authority()
        bad_artifact = TailoredArtifact(
            artifact_id="art-bad",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash="mismatched_hash",
            template_version="1.0",
            policy_version="1.0",
            title="CV",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        bound_bad = BoundArtifact(artifact=bad_artifact, candidate_id="founder", workspace="default")
        dec, reasons = auth.evaluate_action(
            opportunity=self.opportunity,
            artifact=bound_bad,
            answers=(),
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
        )
        self.assertEqual(dec, ActionAuthorityDecision.BLOCK)
        self.assertTrue("stale artifact" in reasons[0])

    def test_zt_15_assisted_mode_strictly_prohibits_driver_submission(self) -> None:
        engine = OutboundBrowserEngine(authority=self._create_submit_ready_authority(), ledger=self.ledger)
        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.PREPARED)
        self.assertFalse(harness.submitted)
        self.assertEqual(harness.submits_count, 0)


if __name__ == "__main__":
    unittest.main()
