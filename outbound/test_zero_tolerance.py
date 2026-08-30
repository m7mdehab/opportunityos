"""15 Required Zero-Tolerance Safety Tests for BRIEF-005."""
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


class TestZeroToleranceInvariants(unittest.TestCase):
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

    # 1. Accidental submit in ASSISTED mode
    def test_zero_accidental_submit_in_assisted_mode(self) -> None:
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
        self.assertFalse(harness.submitted, "ASSISTED mode must never trigger submission")
        self.assertEqual(rec.action_status, ActionStatus.PREPARED)

    # 2. Duplicate submission
    def test_zero_duplicate_submission(self) -> None:
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

        # Attempting second submit on same opportunity
        rec2 = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec2.action_status, ActionStatus.BLOCKED)
        self.assertIn("duplicate", rec2.blocker_reason.lower())

    # 3. Unauthorized Red-question auto-answer
    def test_zero_unauthorized_red_question_auto_answer(self) -> None:
        f_red = FieldClassifier.classify_field("Do you agree to binding non-compete terms?", name="legal_term")
        self.assertEqual(f_red.sensitivity_class, AnswerClass.RED)
        from outbound.answer_engine import ApplicationAnswerEngine
        ae = ApplicationAnswerEngine(self.tg, self.policy)
        res = ae.answer_field(f_red, self.opp)
        self.assertEqual(res.answer_class, AnswerClass.RED)
        self.assertEqual(res.disposition, "pause")

    # 4. CAPTCHA bypass attempt
    def test_zero_captcha_bypass_attempt(self) -> None:
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
        self.assertIn("captcha", rec.blocker_reason.lower())
        self.assertFalse(harness.submitted)

    # 5. MFA bypass attempt
    def test_zero_mfa_bypass_attempt(self) -> None:
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
        self.assertIn("mfa", rec.blocker_reason.lower())
        self.assertFalse(harness.submitted)

    # 6. Wrong-user artifact upload
    def test_zero_wrong_user_artifact_upload(self) -> None:
        from outbound.artifact_selector import ApplicationArtifactSelector
        selector = ApplicationArtifactSelector()
        art, errors = selector.select_artifact(
            candidate_id="other-founder",
            opportunity=self.opp,
            artifact_type=ArtifactType.TAILORED_CV,
            available_artifacts=(),
            truth_graph=self.tg,
        )
        self.assertIsNone(art)

    # 7. Wrong-opportunity artifact upload
    def test_zero_wrong_opportunity_artifact_upload(self) -> None:
        wrong_artifact = make_test_artifact("art-wrong-opp", "opp-different-999", "opp-hash-1")
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=wrong_artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)
        self.assertIn("does not match target", rec.blocker_reason)

    # 8. Stale artifact upload
    def test_zero_stale_artifact_upload(self) -> None:
        stale_artifact = make_test_artifact("art-stale", "opp-1", "old-stale-hash-000")
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
        self.assertIn("does not match current opportunity hash", rec.blocker_reason)

    # 9. Unvalidated artifact upload
    def test_zero_unvalidated_artifact_upload(self) -> None:
        from matching.models import GeneratedClaim, ArtifactSection
        unvalidated_art = make_test_artifact(
            "art-unval", "opp-1", "opp-hash-1",
            sections=(ArtifactSection(
                section_id="sec-1", heading="Summary", content="Fictional claim",
                items=(), assertion_ids=(), evidence_ids=(),
            ),),
            generated_claims=(GeneratedClaim(
                claim_id="c-1", text="Fictional claim", section_id="sec-1",
                assertion_ids=(), evidence_ids=(), predicate="",
            ),)
        )
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=unvalidated_art,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)
        self.assertIn("validation failed", rec.blocker_reason.lower())

    # 10. Submission after global kill switch
    def test_zero_submission_after_kill_switch(self) -> None:
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
        self.assertIn("kill switch", rec.blocker_reason.lower())

    # 11. Submission with unknown source action policy
    def test_zero_submission_with_unknown_source_policy(self) -> None:
        unregistered_opp = Opportunity(
            id="opp-unreg", track=Track.EMPLOYMENT, source="unknown_mystery_board",
            source_url="https://mystery.com", source_id="1", organization="Mystery",
            title="Engineer", description="Mystery role", content_hash="hash-u",
        )
        unregistered_art = make_test_artifact("art-u", "opp-unreg", "hash-u")
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=unregistered_opp,
            artifact=unregistered_art,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.SUBMIT_ENABLED,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)
        self.assertIn("prohibited", rec.blocker_reason.lower())

    # 12. Submission by non-graduated adapter
    def test_zero_submission_by_non_graduated_adapter(self) -> None:
        harness = MockATSHarness()
        driver = MockBrowserDriver(harness)
        rec = self.engine.execute_application(
            opportunity=self.opp,
            artifact=self.artifact,
            driver=driver,
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            adapter_state=AdapterLifecycleState.EXPERIMENTAL,
            truth_graph=self.tg,
            policy=self.policy,
        )
        self.assertEqual(rec.action_status, ActionStatus.BLOCKED)
        self.assertIn("requires submit_enabled", rec.blocker_reason.lower())

    # 13. Auto-retry after UNKNOWN_OUTCOME
    def test_zero_auto_retry_after_unknown_outcome(self) -> None:
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
        self.assertEqual(rec.action_status, ActionStatus.UNKNOWN_OUTCOME)

    # 14. External action with unresolved mandatory commitment
    def test_zero_action_with_unresolved_mandatory_commitment(self) -> None:
        from outbound.answer_engine import ApplicationAnswerEngine
        empty_policy = TailoringPolicy()
        ae = ApplicationAnswerEngine(self.tg, empty_policy)
        f_spon = FieldClassifier.classify_field("Will you require sponsorship?", name="sponsorship", required=True)
        ans = ae.answer_field(f_spon, self.opp)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")

    # 15. Fabricated application answer
    def test_zero_fabricated_application_answer(self) -> None:
        from outbound.models import ApplicationAnswer
        with self.assertRaises(ValueError):
            ApplicationAnswer(
                opportunity_id="opp-1",
                opportunity_content_hash="opp-hash-1",
                action_id="act-1",
                field_type=FieldOntologyType.IDENTITY,
                original_label="Name",
                normalized_question="name",
                answer="Hallucinated Name",
                answer_class=AnswerClass.GREEN,
                answer_source="hallucinated",
            )


if __name__ == "__main__":
    unittest.main()
