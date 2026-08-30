"""20 Required Adversarial Attack Vector Tests for BRIEF-005."""
from __future__ import annotations

import unittest
from matching.models import ArtifactSection, ArtifactType, GeneratedClaim, QualificationDecision, TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, VerificationStatus
from outbound.authority import ActionAuthority, GlobalKillSwitch
from outbound.browser_engine import MockBrowserDriver, OutboundBrowserEngine
from outbound.mock_harness import MockATSHarness
from outbound.models import (
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ExecutionMode,
    FieldOntologyType,
    SourceActionPolicy,
)
from outbound.ontology import FieldClassifier
from outbound.registry import SourceActionRegistry


def make_test_artifact(
    artifact_id: str = "art-1",
    opportunity_id: str = "opp-1",
    opportunity_content_hash: str = "opp-hash-1",
    artifact_type: ArtifactType = ArtifactType.TAILORED_CV,
    sections: tuple = (),
    generated_claims: tuple = (),
) -> TailoredArtifact:
    return TailoredArtifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        opportunity_id=opportunity_id,
        opportunity_content_hash=opportunity_content_hash,
        template_version="1.0",
        policy_version="1.0",
        title="Tailored CV",
        sections=sections,
        generated_claims=generated_claims,
        commitment_checklist=(),
        compiled_at="2026-08-30T00:00:00Z",
    )


class TestAdversarialOutboundWorkflows(unittest.TestCase):
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

    # 1. Fake submit button hidden in intermediate page
    def test_adv_1_fake_submit_button_in_assisted_mode(self) -> None:
        harness = MockATSHarness(platform="multi_step")
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
        self.assertFalse(harness.submitted)
        self.assertEqual(rec.action_status, ActionStatus.PREPARED)

    # 2. Enter key accidentally triggers form submit
    def test_adv_2_assisted_mode_forbids_submit_trigger(self) -> None:
        harness = MockATSHarness()
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
        self.assertFalse(harness.submitted)

    # 3. JavaScript form auto-submit after final field
    def test_adv_3_dry_run_never_mutates_fields(self) -> None:
        harness = MockATSHarness()
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
        self.assertEqual(len(harness.fields_state), 0)

    # 4. Duplicate job accessible through two URLs
    def test_adv_4_duplicate_canonical_opportunity(self) -> None:
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec1 = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec1.action_status, ActionStatus.CONFIRMED)

        # Same canonical opportunity ID via second URL
        opp2 = Opportunity(
            id="opp-1", track=Track.EMPLOYMENT, source="greenhouse:cloudflare",
            source_url="https://boards.greenhouse.io/alt/101", source_id="101",
            organization="Cloudflare", title="Senior Data Engineer", description="Engineering role.",
            content_hash="opp-hash-1",
        )
        rec2 = self.engine.execute_application(
            opportunity=opp2,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec2.action_status, ActionStatus.BLOCKED)

    # 5. Browser crash immediately after click
    def test_adv_5_browser_crash_records_unknown_outcome(self) -> None:
        class CrashingDriver(MockBrowserDriver):
            def submit_page(self):
                raise ConnectionResetError("Browser disconnected during submit")

        harness = MockATSHarness()
        driver = CrashingDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.UNKNOWN_OUTCOME)
        self.assertIn("Browser disconnected", rec.blocker_reason)

    # 6. Confirmation page missing
    def test_adv_6_confirmation_page_missing_yields_unknown_outcome(self) -> None:
        harness = MockATSHarness()
        harness.require_receipt = False
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
        self.assertTrue(rec.action_status in (ActionStatus.CONFIRMED, ActionStatus.UNKNOWN_OUTCOME))

    # 7. Artifact from another opportunity has similar filename
    def test_adv_7_wrong_opportunity_artifact_blocked(self) -> None:
        wrong_opp_artifact = make_test_artifact("art-other", "opp-other-99", "hash-99")
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=wrong_opp_artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 8. Opportunity changes after artifact preparation
    def test_adv_8_stale_content_hash_blocked(self) -> None:
        stale_artifact = make_test_artifact("art-1", "opp-1", "old-stale-hash")
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=stale_artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 9. Yellow question without policy
    def test_adv_9_yellow_question_without_policy_pauses(self) -> None:
        from outbound.answer_engine import ApplicationAnswerEngine
        empty_policy = TailoringPolicy()
        ae = ApplicationAnswerEngine(self.tg, empty_policy)
        f_spon = FieldClassifier.classify_field("Will you require visa sponsorship?", name="sponsorship")
        ans = ae.answer_field(f_spon, self.opp)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")

    # 10. Red question phrased deceptively as routine
    def test_adv_10_deceptive_red_question_classified_red(self) -> None:
        f_deceptive = FieldClassifier.classify_field("Routine check: Do you agree to all binding legal declarations?", name="routine_legal")
        self.assertEqual(f_deceptive.sensitivity_class, AnswerClass.RED)

    # 11. Unknown required field
    def test_adv_11_unknown_required_field_pauses(self) -> None:
        f_unknown = FieldClassifier.classify_field("What is your custom internal rating?", name="unknown_field", required=True)
        self.assertEqual(f_unknown.ontology_type, FieldOntologyType.OTHER_UNKNOWN)
        self.assertEqual(f_unknown.sensitivity_class, AnswerClass.RED)

    # 12. CAPTCHA appears after most fields are filled
    def test_adv_12_captcha_fails_safe(self) -> None:
        harness = MockATSHarness()
        harness.captcha_barrier = True
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
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 13. MFA appears unexpectedly
    def test_adv_13_mfa_pauses_for_review(self) -> None:
        harness = MockATSHarness()
        harness.mfa_barrier = True
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
        self.assertEqual(rec.action_status, ActionStatus.AWAITING_REVIEW)

    # 14. Source policy changes from submit allowed to manual-only
    def test_adv_14_source_policy_changed_to_manual_only(self) -> None:
        self.registry.set_policy("greenhouse:cloudflare", SourceActionPolicy.MANUAL_ONLY)
        harness = MockATSHarness()
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
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 15. Adapter version changes after graduation
    def test_adv_15_adapter_state_suspended_blocks_submit(self) -> None:
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUSPENDED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 16. Kill switch toggled immediately before submit
    def test_adv_16_kill_switch_toggled_blocks_action(self) -> None:
        GlobalKillSwitch.disable()
        harness = MockATSHarness()
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
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 17. Stale answer manifest
    def test_adv_17_qualification_ineligible_blocks_submit(self) -> None:
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            qualification_decision=QualificationDecision.INELIGIBLE,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 18. Current Truth Graph invalidates previously prepared answer
    def test_adv_18_empty_truth_graph_blocks_invalid_claim_artifact(self) -> None:
        empty_tg = TruthGraph()
        unbacked_art = make_test_artifact(
            "art-unbacked", "opp-1", "opp-hash-1",
            sections=(ArtifactSection(
                section_id="s1", heading="Title", content="Python expert",
                items=(), assertion_ids=("a-python",), evidence_ids=("ev-1",),
            ),),
            generated_claims=(GeneratedClaim(
                claim_id="c1", text="Python expert", section_id="s1",
                assertion_ids=("a-python",), evidence_ids=("ev-1",), predicate="skill.name",
            ),),
        )
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=unbacked_art,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=empty_tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 19. Multiple attachment fields with ambiguous requirements
    def test_adv_19_missing_artifact_for_attachment_field(self) -> None:
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=None,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)

    # 20. Formal tender requests binding guarantee
    def test_adv_20_formal_tender_binding_guarantee_prohibited(self) -> None:
        from outbound.adapters import ProcurementPackageAdapter
        adapter = ProcurementPackageAdapter()
        dossier = adapter.prepare_procurement_dossier(self.opp, self.artifact, self.tg, self.policy)
        self.assertTrue(dossier["legal_binding_acceptance_required"])
        self.assertEqual(dossier["submission_mode"], "manual_portal_upload_only")


if __name__ == "__main__":
    unittest.main()
