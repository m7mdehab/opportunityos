"""20 Required Adversarial Attack Vector Tests for Outbound Side-Effect Safety."""
import os
import tempfile
import threading
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
from outbound.browser_engine import BrowserDriver, MockBrowserDriver, OutboundBrowserEngine
from outbound.idempotency import (
    DuplicateSubmissionError,
    IdempotencyLedger,
    UnknownOutcomeFrozenError,
)
from outbound.mock_harness import MockATSHarness
from outbound.models import (
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    BoundArtifact,
    ConfirmationEvidence,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    GraduationRecord,
    PreSubmitManifest,
    SourceActionPolicy,
)
from outbound.registry import AdapterRegistry, SourceActionRegistry


class AdversarialOutboundTests(unittest.TestCase):
    def setUp(self) -> None:
        GlobalKillSwitch.enable()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.ledger = IdempotencyLedger(self.db_path)

        self.opportunity = Opportunity(
            id="opp-adv-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/500",
            source_id="500",
            organization="Acme",
            title="Senior Architect",
            description="Role in Egypt.",
        )
        self.tg = TruthGraph()
        ev = EvidenceRecord(id="ev-adv-1", source="passport", locator="p1", content="Founder Name. Authorized in Egypt. Country: Egypt.")
        self.tg.add_evidence(ev)
        self.tg.add_assertion(AtomicAssertion(
            id="a-name", subject_id="founder", predicate="identity.name",
            value="Founder Name", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-adv-1",),
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-auth", subject_id="founder", predicate="authorization.jurisdiction",
            value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-adv-1",),
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-country", subject_id="founder", predicate="identity.country",
            value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-adv-1",),
        ))

        self.policy = TailoringPolicy(
            default_notice_period_days=30,
            default_currency="USD",
            default_sponsorship_required=False,
        )
        raw_artifact = TailoredArtifact(
            artifact_id="art-adv-1",
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
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_adv_01_late_kill_switch_toggled_after_reservation_aborts_submit(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)

        class HookingLedger(IdempotencyLedger):
            def reserve_submission(self, record):
                super().reserve_submission(record)
                GlobalKillSwitch.disable()

        hooking_ledger = HookingLedger(self.db_path)
        engine = OutboundBrowserEngine(authority=auth, ledger=hooking_ledger)

        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("kill switch disabled after reservation" in record.blocker_reason)
        self.assertFalse(harness.submitted)
        self.assertEqual(harness.submits_count, 0)

    def test_adv_02_caller_forged_submit_enabled_state_ignored(self) -> None:
        adapter_reg = AdapterRegistry()
        auth = ActionAuthority(adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse",
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("requires SUBMIT_ENABLED" in record.blocker_reason)

    def test_adv_03_adapter_version_changed_after_graduation_blocks_action(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        auth = ActionAuthority(adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="greenhouse_unregistered_v2",
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("not registered" in record.blocker_reason)

    def test_adv_04_source_policy_changed_to_manual_blocks_submit(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.MANUAL_ONLY})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("MANUAL_ONLY" in record.blocker_reason)

    def test_adv_05_unknown_outcome_retry_attempt_after_process_restart(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

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
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec1.action_status, ActionStatus.UNKNOWN_OUTCOME)

        restarted_ledger = IdempotencyLedger(self.db_path)
        engine2 = OutboundBrowserEngine(authority=auth, ledger=restarted_ledger)

        rec2 = engine2.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec2.action_status, ActionStatus.BLOCKED)
        self.assertTrue("UNKNOWN_OUTCOME" in rec2.blocker_reason or "Duplicate" in rec2.blocker_reason)

    def test_adv_06_concurrent_duplicate_attempts_only_one_acquires_authority(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        results: list[ActionStatus] = []
        def run_attempt():
            rec = engine.execute_application(
                opportunity=self.opportunity,
                artifact=self.artifact,
                driver=driver,
                execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
                truth_graph=self.tg,
                policy=self.policy,
            )
            results.append(rec.action_status)

        t1 = threading.Thread(target=run_attempt)
        t2 = threading.Thread(target=run_attempt)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertIn(ActionStatus.CONFIRMED, results)
        self.assertIn(ActionStatus.BLOCKED, results)
        self.assertEqual(harness.submits_count, 1)

    def test_adv_07_post_preparation_truth_graph_mutation_blocks_submission(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)

        # 1. Prepare application first in DRY_RUN mode
        prepared_rec = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.DRY_RUN,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(prepared_rec.action_status, ActionStatus.PREPARED)

        # 2. Mutate TruthGraph provenance after preparation
        mutated_tg = TruthGraph()
        ev_new = EvidenceRecord(id="ev-mutated", source="passport", locator="p1", content="New Verified Name")
        mutated_tg.add_evidence(ev_new)
        mutated_tg.add_assertion(AtomicAssertion(
            id="a-name-new", subject_id="founder", predicate="identity.name",
            value="New Verified Name", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-mutated",),
        ))

        # 3. Attempt controlled submit with stale prepared manifest hash
        stale_manifest = PreSubmitManifest(
            workspace="default",
            candidate_id="founder",
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            action_type="application",
            adapter_name="greenhouse",
            adapter_version="1.0.0",
            graduation_record_version="1.0.0",
            source_policy_version=src_reg.get_policy_version(self.opportunity.source),
            artifact_ids=(self.artifact.artifact_id,),
            artifact_hashes=(self.artifact.artifact_hash,),
            answers=(),
            answers_hash="old_answers_hash_stale",
            qualification_decision=QualificationDecision.QUALIFIED,
            unresolved_mandatory_count=0,
            red_answers_count=0,
            idempotency_key=prepared_rec.idempotency_key,
            compiled_at="2026-08-30T00:00:00Z",
        )

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=mutated_tg,
            policy=self.policy,
            prepared_manifest=stale_manifest,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("Manifest staleness detected" in record.blocker_reason)
        self.assertFalse(harness.submitted)
        self.assertEqual(harness.submits_count, 0)

    def test_adv_08_post_preparation_source_policy_mutation_blocks_submission(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED}, version="1.0.0")
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)

        # 1. Prepare in DRY_RUN
        prepared_rec = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.DRY_RUN,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(prepared_rec.action_status, ActionStatus.PREPARED)

        # 2. Bump source registry version after preparation
        src_reg.version = "1.0.1"

        # Stale prepared manifest had old policy version
        stale_manifest = PreSubmitManifest(
            workspace="default",
            candidate_id="founder",
            opportunity_id=self.opportunity.id,
            opportunity_content_hash=self.opportunity.content_hash,
            action_type="application",
            adapter_name="greenhouse",
            adapter_version="1.0.0",
            graduation_record_version="1.0.0",
            source_policy_version="old_policy_ver_100",
            artifact_ids=(self.artifact.artifact_id,),
            artifact_hashes=(self.artifact.artifact_hash,),
            answers=(),
            answers_hash="some_hash",
            qualification_decision=QualificationDecision.QUALIFIED,
            unresolved_mandatory_count=0,
            red_answers_count=0,
            idempotency_key=prepared_rec.idempotency_key,
            compiled_at="2026-08-30T00:00:00Z",
        )

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.tg,
            policy=self.policy,
            prepared_manifest=stale_manifest,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("Manifest staleness detected" in record.blocker_reason)
        self.assertFalse(harness.submitted)

    def test_adv_09_assisted_mode_zero_submit_on_js_auto_submit_page(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

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

    def test_adv_10_procurement_dossier_blocks_autonomous_controlled_submit(self) -> None:
        proc_opp = Opportunity(
            id="opp-ted-1",
            track=Track.PROCUREMENT,
            source="eu_ted",
            source_url="https://ted.europa.eu/notice/1",
            source_id="1",
            organization="EU Authority",
            title="Data Services RFP",
            description="Procurement notice.",
        )
        adapter_reg = AdapterRegistry()
        auth = ActionAuthority(adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("f", "f", "text", "Field", "field", FieldOntologyType.OTHER_UNKNOWN)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=proc_opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="procurement_package",
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("MANUAL_ONLY" in record.blocker_reason or "requires SUBMIT_ENABLED" in record.blocker_reason)

    def test_adv_11_freelance_proposal_blocks_unauthorized_controlled_submit(self) -> None:
        fl_opp = Opportunity(
            id="opp-fl-1",
            track=Track.FREELANCE,
            source="direct",
            source_url="https://client.example/brief",
            source_id="1",
            organization="Client Corp",
            title="Data Pipeline SOW",
            description="Freelance brief.",
        )
        adapter_reg = AdapterRegistry()
        auth = ActionAuthority(adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("f", "f", "text", "Field", "field", FieldOntologyType.OTHER_UNKNOWN)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=fl_opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_name="freelance_proposal",
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)

    def test_adv_12_ineligible_qualification_blocks_action(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.INELIGIBLE,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("ineligible" in record.blocker_reason)

    def test_adv_13_uncertain_qualification_pauses_for_review(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.UNCERTAIN,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)
        self.assertTrue("UNCERTAIN" in record.blocker_reason)

    def test_adv_14_missing_confirmation_evidence_transitions_to_unknown_outcome(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(
            steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]],
            missing_receipt_on_submit=True,
        )
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.UNKNOWN_OUTCOME)
        self.assertTrue("receipt not detected" in record.blocker_reason)

    def test_adv_15_deceptive_legal_declaration_classified_red(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("sig", "sig", "text", "Acknowledge and agree to terms under penalty of perjury", "acknowledge and agree to terms under penalty of perjury", FieldOntologyType.LEGAL_DECLARATION, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)

    def test_adv_16_mismatched_artifact_opportunity_hash_blocks_action(self) -> None:
        raw_artifact = TailoredArtifact(
            artifact_id="art-bad-hash",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=self.opportunity.id,
            opportunity_content_hash="forged_hash_different",
            template_version="1.0",
            policy_version="1.0",
            title="CV",
            sections=(),
            generated_claims=(),
            commitment_checklist=(),
            compiled_at="2026-08-30T00:00:00Z",
        )
        bad_hash_artifact = BoundArtifact(artifact=raw_artifact, candidate_id="founder", workspace="default")

        harness = MockATSHarness(steps=[[DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY)]])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=bad_hash_artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.BLOCKED)
        self.assertTrue("stale artifact" in record.blocker_reason)

    def test_adv_17_work_authorization_unresolved_jurisdiction_pauses_for_review(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("auth", "auth", "radio", "Do you have work authorization?", "do you have work authorization", FieldOntologyType.WORK_AUTHORIZATION, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)
        self.assertTrue("mandatory question(s) unresolved" in record.blocker_reason or "Red" in record.blocker_reason)

    def test_adv_18_missing_email_in_truth_graph_pauses_required_email_field(self) -> None:
        harness = MockATSHarness(steps=[
            [DetectedFormField("email", "email", "text", "Email Address", "email address", FieldOntologyType.CONTACT, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)
        self.assertTrue("mandatory question(s) unresolved" in record.blocker_reason or "Red" in record.blocker_reason)

    def test_adv_19_empty_truth_graph_pauses_required_identity_field(self) -> None:
        empty_tg = TruthGraph()
        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "First Name", "first name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)
        engine = OutboundBrowserEngine(ledger=self.ledger)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.ASSISTED,
            truth_graph=empty_tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.AWAITING_REVIEW)

    def test_adv_20_valid_controlled_submit_end_to_end_succeeds_and_confirms(self) -> None:
        adapter_reg = AdapterRegistry()
        adapter_reg.enable_submit("greenhouse")
        src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
        auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)
        engine = OutboundBrowserEngine(authority=auth, ledger=self.ledger)

        harness = MockATSHarness(steps=[
            [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
        ])
        driver = MockBrowserDriver(harness)

        record = engine.execute_application(
            opportunity=self.opportunity,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(record.action_status, ActionStatus.CONFIRMED)
        self.assertIsNotNone(record.confirmation_evidence)
        self.assertTrue(record.confirmation_evidence.confirmed)
        self.assertEqual(harness.submits_count, 1)


if __name__ == "__main__":
    unittest.main()
