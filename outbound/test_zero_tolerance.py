"""15 Required Zero-Tolerance Invariant Tests for Outbound Side-Effect Safety."""
import os
import tempfile
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
from outbound.idempotency import (
    DuplicateSubmissionError,
    IdempotencyLedger,
    UnknownOutcomeFrozenError,
)
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
from outbound.registry import AdapterRegistry, SourceActionRegistry


class ZeroToleranceSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        GlobalKillSwitch.enable()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.ledger = IdempotencyLedger(self.db_path)

        self.opportunity = Opportunity(
            id="opp-zt-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/100",
            source_id="100",
            organization="Acme Corp",
            title="Staff Engineer",
            description="Staff Engineer position in Egypt.",
        )
        self.truth_graph = TruthGraph()
        ev = EvidenceRecord(id="ev-founder-1", source="passport", locator="p1", content="Founder Name is verified. Authorized in Egypt.")
        self.truth_graph.add_evidence(ev)
        self.truth_graph.add_assertion(AtomicAssertion(
            id="a-founder-name", subject_id="founder", predicate="identity.name",
            value="Founder Name", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-founder-1",),
        ))
        self.truth_graph.add_assertion(AtomicAssertion(
            id="a-founder-auth", subject_id="founder", predicate="authorization.jurisdiction",
            value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-founder-1",),
        ))

        self.policy = TailoringPolicy(
            default_notice_period_days=30,
            default_currency="USD",
        )
        raw_artifact = TailoredArtifact(
            artifact_id="art-zt-1",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            template_version="1.0",
            policy_version="1.0",
            title="Tailored CV",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        self.raw_artifact = raw_artifact
        self.artifact = BoundArtifact(artifact=raw_artifact, candidate_id="founder", workspace="default")

    def tearDown(self) -> None:
        GlobalKillSwitch.enable()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_01_accidental_submit_in_assisted_mode_zero_tolerance(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.PREPARED)
        self.assertFalse(harness.submitted)
        self.assertEqual(harness.submits_count, 0)

    def test_02_duplicate_submission_zero_tolerance(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger, adapter_registry=adapter_reg, source_registry=src_reg)

        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)

        rec1 = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(rec1.action_status, ActionStatus.CONFIRMED)

        rec2 = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(rec2.action_status, ActionStatus.BLOCKED)
        self.assertTrue("Duplicate submission" in rec2.blocker_reason)
        self.assertEqual(harness.submits_count, 1)

    def test_03_unauthorized_red_question_auto_answer_zero_tolerance(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("legal", "legal", "checkbox", "Do you agree to non-compete terms under penalty of perjury?", "do you agree to non compete", FieldOntologyType.LEGAL_DECLARATION, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)
        self.assertTrue("Red question" in record.blocker_reason or "unresolved" in record.blocker_reason)

    def test_04_captcha_bypass_attempt_zero_tolerance(self) -> None:
        harness = MockATSHarness(
            steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]],
            captcha_barrier=True,
        )
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("CAPTCHA" in record.blocker_reason)
        self.assertFalse(harness.submitted)

    def test_05_mfa_bypass_attempt_zero_tolerance(self) -> None:
        harness = MockATSHarness(
            steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]],
            mfa_barrier=True,
        )
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)
        self.assertTrue("MFA" in record.blocker_reason)

    def test_06_raw_artifact_controlled_submit_zero_tolerance(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger, adapter_registry=adapter_reg, source_registry=src_reg)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.raw_artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("Raw unowned TailoredArtifact prohibited" in record.blocker_reason)

    def test_07_wrong_opportunity_artifact_upload_zero_tolerance(self) -> None:
        raw_artifact = TailoredArtifact(
            artifact_id="art-wrong-opp",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id="other-opp-999",
            opportunity_content_hash="other-hash",
            template_version="1.0",
            policy_version="1.0",
            title="CV",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        wrong_opp_artifact = BoundArtifact(artifact=raw_artifact, candidate_id="founder", workspace="default")

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=wrong_opp_artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("does not match target" in record.blocker_reason)

    def test_08_stale_artifact_upload_zero_tolerance(self) -> None:
        raw_artifact = TailoredArtifact(
            artifact_id="art-stale",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash="stale_content_hash_000",
            template_version="1.0",
            policy_version="1.0",
            title="CV",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        stale_artifact = BoundArtifact(artifact=raw_artifact, candidate_id="founder", workspace="default")

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=stale_artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("stale artifact" in record.blocker_reason)

    def test_09_unvalidated_artifact_upload_zero_tolerance(self) -> None:
        raw_artifact = TailoredArtifact(
            artifact_id="art-bad",
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
            artifact_hash="forged_hash_invalid",
        )
        bad_artifact = BoundArtifact(artifact=raw_artifact, candidate_id="founder", workspace="default")

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=bad_artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("validation failed" in record.blocker_reason)

    def test_10_submission_after_kill_switch_zero_tolerance(self) -> None:
        GlobalKillSwitch.disable()
        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("kill switch" in record.blocker_reason)
        self.assertFalse(harness.submitted)

    def test_11_submission_with_unknown_source_policy_zero_tolerance(self) -> None:
        unknown_opp = Opportunity(
            id="opp-unk",
            track=Track.EMPLOYMENT,
            source="evil_unknown_platform",
            source_url="https://evil.example/jobs/1",
            source_id="1",
            organization="Evil",
            title="Role",
            description="Desc",
        )
        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=unknown_opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("PROHIBITED" in record.blocker_reason)

    def test_12_submission_by_non_graduated_adapter_zero_tolerance(self) -> None:
        adapter_reg = AdapterRegistry()
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger, adapter_registry=adapter_reg, source_registry=src_reg)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("requires SUBMIT_ENABLED" in record.blocker_reason)

    def test_13_auto_retry_after_unknown_outcome_zero_tolerance(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger, adapter_registry=adapter_reg, source_registry=src_reg)

        harness = MockATSHarness(
            steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]],
            network_error_on_submit=True,
        )
        driver = MockBrowserDriver(harness)

        rec1 = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(rec1.action_status, ActionStatus.UNKNOWN_OUTCOME)

        rec2 = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(rec2.action_status, ActionStatus.BLOCKED)
        self.assertTrue("UNKNOWN_OUTCOME" in rec2.blocker_reason or "Duplicate" in rec2.blocker_reason)

    def test_14_action_with_unresolved_mandatory_commitment_zero_tolerance(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("unresolved", "unresolved", "text", "Mandatory Unanswered Question", "mandatory unanswered question", FieldOntologyType.OTHER_UNKNOWN, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.truth_graph,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)
        self.assertTrue("mandatory question(s) unresolved" in record.blocker_reason or "Red" in record.blocker_reason)

    def test_15_fabricated_application_answer_zero_tolerance(self) -> None:
        with self.assertRaises(ValueError):
            ApplicationAnswer(
                opportunity_id=self.opportunity.id,
                opportunity_content_hash=self.opportunity.content_hash,
                action_id="act-1",
                field_type=FieldOntologyType.IDENTITY,
                original_label="Name",
                normalized_question="name",
                answer="Fabricated Name",
                answer_class=AnswerClass.GREEN,
                answer_source="fabricated_source",
                assertion_ids=(),
            )


if __name__ == "__main__":
    unittest.main()
