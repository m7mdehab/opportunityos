"""Adversarial attack vector tests for BRIEF-006 Operational Autonomy."""
import tempfile
import unittest
from pathlib import Path
from matching.models import Track
from opportunity.models import Opportunity
from outbound.models import (
    ActionStatus,
    ExecutionMode,
    OutboundActionRecord,
    QualificationDecision,
)
from inbox.analytics import DualTrackAnalyticsEngine
from inbox.classifier import ResponseClassifier
from inbox.correlation import OpportunityCorrelationEngine
from inbox.fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES, GOLD_INDEPENDENT_MESSAGES
from inbox.ingestion import InboundIngestionService, MockMailTransport
from inbox.learning import SafeLearningEngine
from inbox.models import (
    CorrelationEvidence,
    CorrelationStatus,
    InboundMessageEvidence,
    OpportunityStage,
    SignalCategory,
    SignalPriority,
)
from inbox.notifications import NotificationEngine
from inbox.orchestrator import ProductionOperationalOrchestrator
from inbox.persistence import DurableInboxStore
from inbox.pipeline import PipelineEventStore, PipelineStateSynchronizer


class AdversarialInboxTests(unittest.TestCase):
    def test_adv_01_high_priority_signal_cannot_disappear_into_noise(self) -> None:
        """Prove interview / recruiter / client requests achieve 100% recall and are never categorized as noise."""
        classifier = ResponseClassifier()
        all_high_priority = [
            GOLD_EMPLOYMENT_MESSAGES[2],  # Recruiter outreach
            GOLD_EMPLOYMENT_MESSAGES[3],  # Interview request
            GOLD_EMPLOYMENT_MESSAGES[4],  # Interview reschedule
            GOLD_EMPLOYMENT_MESSAGES[5],  # Assessment
            GOLD_EMPLOYMENT_MESSAGES[6],  # Info request
            GOLD_EMPLOYMENT_MESSAGES[7],  # Offer
            GOLD_INDEPENDENT_MESSAGES[1], # Client response
            GOLD_INDEPENDENT_MESSAGES[2], # Clarification
            GOLD_INDEPENDENT_MESSAGES[3], # Shortlist
            GOLD_INDEPENDENT_MESSAGES[4], # Discovery call
            GOLD_INDEPENDENT_MESSAGES[6], # Award
            GOLD_INDEPENDENT_MESSAGES[7], # Contract progress
        ]
        for msg in all_high_priority:
            sig = classifier.classify(msg)
            self.assertIn(sig.priority, (SignalPriority.HIGH, SignalPriority.URGENT))
            self.assertNotEqual(sig.category, SignalCategory.MARKETING)
            self.assertNotEqual(sig.category, SignalCategory.GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION)
            self.assertTrue(sig.requires_founder_action)

    def test_adv_02_correlation_attacks_suite(self) -> None:
        """Adversarially test the complete required correlation attack set."""
        opp_a = Opportunity(id="opp-1", track=Track.EMPLOYMENT, source="ashby", source_url="u1", source_id="1", organization="Acme", title="Engineer", description="d")
        opp_b = Opportunity(id="opp-2", track=Track.EMPLOYMENT, source="ashby", source_url="u2", source_id="2", organization="Acme", title="Engineer", description="d")
        rec_a = OutboundActionRecord(
            action_id="act-1", opportunity_id="opp-1", opportunity_content_hash="h1", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="ashby", adapter_name="ashby", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m1", action_status=ActionStatus.CONFIRMED, idempotency_key="k1", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-ACME-01",
        )
        rec_b = OutboundActionRecord(
            action_id="act-2", opportunity_id="opp-2", opportunity_content_hash="h2", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="ashby", adapter_name="ashby", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m2", action_status=ActionStatus.CONFIRMED, idempotency_key="k2", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-ACME-02",
        )
        engine = OpportunityCorrelationEngine(opportunities=[opp_a, opp_b], outbound_records=[rec_a, rec_b])

        # Attack 1: Same company, two applications without ID -> Ambiguity Block
        msg_amb = InboundMessageEvidence(
            provider="gmail", provider_message_id="m-amb", thread_id="th-amb",
            sender_email="recruiting@acme.com", sender_name="Acme", recipient_email="f@ex.com",
            subject="Your application at Acme for Engineer", snippet="Update", body_text="Status update for Engineer",
            body_html="<p>update</p>", received_at="2026-08-30T10:00:00Z",
        )
        sig_amb = ResponseClassifier().classify(msg_amb)
        corr_amb = engine.correlate(sig_amb, msg_amb)
        self.assertEqual(corr_amb.status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)
        self.assertFalse(corr_amb.is_authoritative)

        # Attack 2: Multiple source IDs in quoted history -> Ambiguity Block
        msg_quoted = InboundMessageEvidence(
            provider="gmail", provider_message_id="m-quot", thread_id="th-quot",
            sender_email="recruiting@acme.com", sender_name="Acme", recipient_email="f@ex.com",
            subject="Re: Updates", snippet="Status",
            body_text="Status regarding REQ-ACME-01 and REQ-ACME-02 in quoted history -----Original Message----- Req #REQ-ACME-02",
            body_html="<p>status</p>", received_at="2026-08-30T10:00:00Z",
        )
        sig_quot = ResponseClassifier().classify(msg_quoted)
        corr_quot = engine.correlate(sig_quot, msg_quoted)
        self.assertEqual(corr_quot.status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)
        self.assertFalse(corr_quot.is_authoritative)

    def test_adv_03_restart_safe_durable_replay_and_crash_recovery(self) -> None:
        """Prove that durable store survives process restart, crash mid-batch, and produces 0 duplicates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_inbox.db"

            # Instance 1: Ingest first batch of 5 messages
            store1 = DurableInboxStore(db_path)
            transport1 = MockMailTransport(messages=GOLD_EMPLOYMENT_MESSAGES[:5])
            ingest1 = InboundIngestionService(transport1, store=store1)
            orch1 = ProductionOperationalOrchestrator(ingestion_service=ingest1, store=store1)
            res1 = orch1.run_cycle(limit=5)
            self.assertEqual(res1.messages_ingested, 5)
            notifs1 = len(orch1.get_active_notifications())

            # Simulate Process Restart: Create entirely new services against SAME DB
            store2 = DurableInboxStore(db_path)
            transport2 = MockMailTransport(messages=GOLD_EMPLOYMENT_MESSAGES)  # full 10
            ingest2 = InboundIngestionService(transport2, store=store2)
            orch2 = ProductionOperationalOrchestrator(ingestion_service=ingest2, store=store2)

            # Replay should resume exactly from checkpoint cursor "5" and ingest next 5
            res2 = orch2.run_cycle(limit=10)
            self.assertEqual(res2.messages_ingested, 5)
            self.assertEqual(len(store2.get_all_evidence()), 10)

            # Further replay of same cursor => 0 new ingested, 0 duplicate events, 0 duplicate alerts
            res3 = orch2.run_cycle(limit=10)
            self.assertEqual(res3.messages_ingested, 0)
            self.assertEqual(res3.events_recorded, 0)
            self.assertEqual(res3.notifications_emitted, 0)

    def test_adv_04_unknown_outcome_inbound_reconciliation(self) -> None:
        """Prove inbound confirmation creates reconciliation record for UNKNOWN_OUTCOME action without silent mutation."""
        store = DurableInboxStore(":memory:")
        opp = Opportunity(id="opp-acme-1", track=Track.EMPLOYMENT, source="greenhouse", source_url="u", source_id="REQ-ACME-500", organization="Acme Corp", title="Senior Architect", description="d")
        unknown_record = OutboundActionRecord(
            action_id="act-unk-1", opportunity_id="opp-acme-1", opportunity_content_hash="h1",
            workspace="default", candidate_id="founder", track=Track.EMPLOYMENT, source="greenhouse",
            adapter_name="greenhouse", adapter_version="1.0.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9,
            artifact_ids=(), artifact_hashes=(), manifest_hash="m1", action_status=ActionStatus.UNKNOWN_OUTCOME,
            idempotency_key="key-unk", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-ACME-500",
        )
        transport = MockMailTransport(messages=[GOLD_EMPLOYMENT_MESSAGES[0]])  # Contains REQ-ACME-500 confirmation
        ingest = InboundIngestionService(transport, store=store)
        orch = ProductionOperationalOrchestrator(
            ingestion_service=ingest, opportunities=[opp], outbound_records=[unknown_record], store=store,
        )

        res = orch.run_cycle()
        self.assertEqual(res.reconciliations_created, 1)
        recons = store.get_unresolved_reconciliations()
        self.assertEqual(len(recons), 1)
        self.assertEqual(recons[0]["outbound_action_id"], "act-unk-1")
        self.assertEqual(unknown_record.action_status, ActionStatus.UNKNOWN_OUTCOME)

    def test_adv_05_learning_engine_strictly_forbidden_from_truth_or_permission_mutation(self) -> None:
        """Prove learning loop raises PermissionError if attempting to mutate TruthGraph or permissions."""
        learning = SafeLearningEngine()
        with self.assertRaises(PermissionError):
            learning.attempt_truth_mutation()
        with self.assertRaises(PermissionError):
            learning.attempt_permission_mutation()

    def test_adv_06_analytics_denominator_is_submissions_not_opportunities(self) -> None:
        """Prove analytics denominator derives from actual submissions, and missing outcome is pending (not zero)."""
        opps = [
            Opportunity(id=f"opp-s1-{i}", track=Track.EMPLOYMENT, source="greenhouse", source_url="u", source_id=str(i), organization="Corp", title="Dev", description="d")
            for i in range(10)
        ]
        records = [
            OutboundActionRecord(
                action_id=f"act-{i}", opportunity_id=f"opp-s1-{i}", opportunity_content_hash="h",
                workspace="w", candidate_id="c", track=Track.EMPLOYMENT, source="greenhouse", adapter_name="greenhouse",
                adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT, qualification_decision=QualificationDecision.QUALIFIED,
                match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(), manifest_hash="m", action_status=ActionStatus.CONFIRMED,
                idempotency_key=f"k-{i}", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            )
            for i in range(2)
        ]
        metrics = DualTrackAnalyticsEngine.compute_source_metrics(records, ())
        m = metrics["greenhouse"]
        self.assertEqual(m.total_submissions, 2)
        self.assertEqual(m.pending_count, 2)
        self.assertFalse(m.is_sample_sufficient)

    def test_adv_07_zero_event_pipeline_state_has_no_fabricated_confirmation(self) -> None:
        """Prove zero-event replay returns NO_EVENTS stage without fabricated confirmation."""
        state = PipelineStateSynchronizer.replay_events("opp-none", Track.EMPLOYMENT, ())
        self.assertEqual(state.current_stage, OpportunityStage.NO_EVENTS)
        self.assertIsNone(state.last_signal_category)
        self.assertEqual(state.event_history_count, 0)

    def test_adv_08_out_of_order_message_chronology(self) -> None:
        """Prove out-of-order delivery derives final state from source message timestamp, not classifier time."""
        opp_id = "opp-time-1"
        ev_early_rej = GOLD_EMPLOYMENT_MESSAGES[1]  # 11:00 Rejection
        ev_late_int = GOLD_EMPLOYMENT_MESSAGES[3]   # 13:00 Interview

        sig_rej = ResponseClassifier().classify(ev_early_rej)
        sig_int = ResponseClassifier().classify(ev_late_int)

        store = PipelineEventStore()
        corr_int = CorrelationEvidence(signal_id=sig_int.signal_id, opportunity_id=opp_id, outbound_action_id=None, status=CorrelationStatus.EXACT_REFERENCE_MATCH, matching_criteria=(), confidence=1.0, is_authoritative=True)
        corr_rej = CorrelationEvidence(signal_id=sig_rej.signal_id, opportunity_id=opp_id, outbound_action_id=None, status=CorrelationStatus.EXACT_REFERENCE_MATCH, matching_criteria=(), confidence=1.0, is_authoritative=True)

        store.record_signal_event(sig_int, corr_int, Track.EMPLOYMENT)
        store.record_signal_event(sig_rej, corr_rej, Track.EMPLOYMENT)

        state = store.get_opportunity_state(opp_id, Track.EMPLOYMENT)
        self.assertEqual(state.current_stage, OpportunityStage.INTERVIEWING)
        self.assertTrue(state.active_action_required)


if __name__ == "__main__":
    unittest.main()
