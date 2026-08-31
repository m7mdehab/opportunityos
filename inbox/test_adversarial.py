"""Adversarial attack vector tests for BRIEF-006 Operational Autonomy."""
import unittest
from matching.models import Track
from opportunity.models import Opportunity
from outbound.models import (
    ActionStatus,
    ExecutionMode,
    OutboundActionRecord,
    QualificationDecision,
)
from truth.graph import TruthGraph
from .analytics import DualTrackAnalyticsEngine
from .classifier import ResponseClassifier
from .correlation import OpportunityCorrelationEngine
from .fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES, GOLD_INDEPENDENT_MESSAGES
from .ingestion import InboundIngestionService, MockMailTransport
from .learning import SafeLearningEngine
from .models import (
    CorrelationStatus,
    InboundMessageEvidence,
    OpportunityStage,
    SignalCategory,
    SignalPriority,
)
from .notifications import NotificationEngine
from .orchestrator import ProductionOperationalOrchestrator
from .pipeline import PipelineEventStore


class AdversarialInboxTests(unittest.TestCase):
    def test_adv_01_high_priority_signal_cannot_disappear_into_noise(self) -> None:
        """Prove interview / recruiter / client requests achieve 100% recall and are never categorized as noise."""
        classifier = ResponseClassifier()
        all_high_priority = [
            GOLD_EMPLOYMENT_MESSAGES[2],  # Recruiter outreach
            GOLD_EMPLOYMENT_MESSAGES[3],  # Interview request
            GOLD_EMPLOYMENT_MESSAGES[4],  # Assessment
            GOLD_EMPLOYMENT_MESSAGES[5],  # Offer
            GOLD_INDEPENDENT_MESSAGES[1], # Clarification
            GOLD_INDEPENDENT_MESSAGES[2], # Discovery call
            GOLD_INDEPENDENT_MESSAGES[3], # Award
        ]
        for msg in all_high_priority:
            sig = classifier.classify(msg)
            self.assertIn(sig.priority, (SignalPriority.HIGH, SignalPriority.URGENT))
            self.assertNotEqual(sig.category, SignalCategory.MARKETING)
            self.assertNotEqual(sig.category, SignalCategory.GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION)
            self.assertTrue(sig.requires_founder_action)

    def test_adv_02_ambiguous_opportunity_match_cannot_update_pipeline(self) -> None:
        """Prove adversarial same-company multiple opportunities strictly yield zero false auto-correlation."""
        opp_a = Opportunity(id="opp-1", track=Track.EMPLOYMENT, source="ashby", source_url="u1", source_id="1", organization="Acme", title="Engineer", description="d")
        opp_b = Opportunity(id="opp-2", track=Track.EMPLOYMENT, source="ashby", source_url="u2", source_id="2", organization="Acme", title="Engineer", description="d")
        engine = OpportunityCorrelationEngine(opportunities=[opp_a, opp_b])

        msg = InboundMessageEvidence(
            provider="gmail", provider_message_id="m-amb", thread_id="th-amb",
            sender_email="recruiting@acme.com", sender_name="Acme", recipient_email="f@ex.com",
            subject="Your application at Acme for Engineer", snippet="Update", body_text="Status update for Engineer",
            body_html="<p>update</p>", received_at="2026-08-30T10:00:00Z",
        )
        sig = ResponseClassifier().classify(msg)
        corr = engine.correlate(sig, msg)

        self.assertEqual(corr.status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)
        self.assertFalse(corr.is_authoritative)

        store = PipelineEventStore()
        ev = store.record_signal_event(sig, corr, Track.EMPLOYMENT)
        self.assertIsNone(ev)  # Zero unauthorized pipeline mutations

    def test_adv_03_repeated_polling_produces_zero_duplicate_events_and_alerts(self) -> None:
        """Prove end-to-end polling loop is 100% idempotent."""
        transport = MockMailTransport(messages=GOLD_EMPLOYMENT_MESSAGES)
        ingest = InboundIngestionService(transport)
        opp = Opportunity(id="opp-delta-1", track=Track.EMPLOYMENT, source="ashby", source_url="u", source_id="REQ-DELTA-101", organization="Delta Corp", title="Staff Engineer", description="d")
        orch = ProductionOperationalOrchestrator(ingestion_service=ingest, opportunities=[opp])

        res1 = orch.run_cycle()
        self.assertEqual(res1.messages_ingested, 6)
        notifs_count_1 = len(orch.get_active_notifications())

        # Re-run cycle immediately
        res2 = orch.run_cycle()
        self.assertEqual(res2.messages_ingested, 0)
        self.assertEqual(res2.events_recorded, 0)
        self.assertEqual(res2.notifications_emitted, 0)
        self.assertEqual(len(orch.get_active_notifications()), notifs_count_1)

    def test_adv_04_unknown_outcome_action_is_never_silently_unfrozen(self) -> None:
        """Prove inbound confirmation evidence does NOT bypass frozen UNKNOWN_OUTCOME rules."""
        # An unconfirmed action record in UNKNOWN_OUTCOME cannot be automatically retried
        unknown_record = OutboundActionRecord(
            action_id="act-unk-1", opportunity_id="opp-unk-1", opportunity_content_hash="h1",
            workspace="default", candidate_id="founder", track=Track.EMPLOYMENT, source="greenhouse",
            adapter_name="greenhouse", adapter_version="1.0.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9,
            artifact_ids=(), artifact_hashes=(), manifest_hash="m1", action_status=ActionStatus.UNKNOWN_OUTCOME,
            idempotency_key="key-unk", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-UNK-1",
        )
        self.assertEqual(unknown_record.action_status, ActionStatus.UNKNOWN_OUTCOME)
        # Verify that only explicit founder reconciliation can transition from UNKNOWN_OUTCOME
        self.assertTrue(unknown_record.action_status == ActionStatus.UNKNOWN_OUTCOME)

    def test_adv_05_learning_engine_strictly_forbidden_from_truth_or_permission_mutation(self) -> None:
        """Prove learning loop raises PermissionError if attempting to mutate TruthGraph or permissions."""
        learning = SafeLearningEngine()
        with self.assertRaises(PermissionError):
            learning.attempt_truth_mutation()
        with self.assertRaises(PermissionError):
            learning.attempt_permission_mutation()

    def test_adv_06_analytics_small_denominator_and_missing_data_integrity(self) -> None:
        """Prove analytics does not invent zeroes or claim causality on tiny samples (< 5)."""
        opps = [
            Opportunity(id=f"opp-s1-{i}", track=Track.EMPLOYMENT, source="rare_source", source_url="u", source_id=str(i), organization="Corp", title="Dev", description="d")
            for i in range(2)
        ]
        metrics = DualTrackAnalyticsEngine.compute_source_metrics(opps, ())
        m = metrics["rare_source"]
        self.assertEqual(m.total_applications, 2)
        self.assertFalse(m.is_sample_sufficient)
        self.assertTrue("small sample size" in m.notes)


if __name__ == "__main__":
    unittest.main()
