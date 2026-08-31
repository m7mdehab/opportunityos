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
            GOLD_INDEPENDENT_MESSAGES[8], # Procurement amendment
            GOLD_INDEPENDENT_MESSAGES[9], # Procurement deadline change
        ]
        for msg in all_high_priority:
            sig = classifier.classify(msg)
            self.assertIn(sig.priority, (SignalPriority.HIGH, SignalPriority.URGENT))
            self.assertNotEqual(sig.category, SignalCategory.MARKETING)
            self.assertNotEqual(sig.category, SignalCategory.GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION)
            self.assertTrue(sig.requires_founder_action)

    def test_adv_02_complete_correlation_attacks_suite(self) -> None:
        """Adversarially test the complete required 9-point correlation attack set."""
        opp_a = Opportunity(id="opp-1", track=Track.EMPLOYMENT, source="ashby", source_url="u1", source_id="REQ-01", organization="Acme Corp", title="Software Architect", description="d")
        opp_b = Opportunity(id="opp-2", track=Track.EMPLOYMENT, source="ashby", source_url="u2", source_id="REQ-02", organization="Acme Corp", title="Software Architect", description="d")
        opp_stale = Opportunity(id="opp-stale", track=Track.EMPLOYMENT, source="ashby", source_url="u3", source_id="REQ-OLD-99", organization="Acme Corp", title="Junior Architect", description="d")
        opp_buyer_1 = Opportunity(id="opp-b1", track=Track.PROCUREMENT, source="ted", source_url="u4", source_id="TED-01", organization="Gov Contracting", title="Data Services", description="d")
        opp_buyer_2 = Opportunity(id="opp-b2", track=Track.PROCUREMENT, source="ted", source_url="u5", source_id="TED-02", organization="Gov Contracting", title="Data Services", description="d")

        rec_a = OutboundActionRecord(
            action_id="act-1", opportunity_id="opp-1", opportunity_content_hash="h1", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="ashby", adapter_name="ashby", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m1", action_status=ActionStatus.CONFIRMED, idempotency_key="k1", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-01",
        )
        rec_b = OutboundActionRecord(
            action_id="act-2", opportunity_id="opp-2", opportunity_content_hash="h2", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="ashby", adapter_name="ashby", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m2", action_status=ActionStatus.CONFIRMED, idempotency_key="k2", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-02",
        )
        rec_stale = OutboundActionRecord(
            action_id="act-stale", opportunity_id="opp-stale", opportunity_content_hash="h3", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="ashby", adapter_name="ashby", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m3", action_status=ActionStatus.FAILED, idempotency_key="k3", created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z",
            external_reference_id="REQ-OLD-99",
        )

        engine = OpportunityCorrelationEngine(
            opportunities=[opp_a, opp_b, opp_stale, opp_buyer_1, opp_buyer_2],
            outbound_records=[rec_a, rec_b, rec_stale],
        )
        classifier = ResponseClassifier()

        # 1. Same company, two applications without ID
        m1 = InboundMessageEvidence(provider="gmail", provider_message_id="m1", thread_id="th1", sender_email="hr@acme.com", sender_name="Acme", recipient_email="f@ex.com", subject="Your application at Acme Corp for Software Architect", snippet="", body_text="Update", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m1), m1).status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)

        # 2. Near-identical titles across opportunities
        m2 = InboundMessageEvidence(provider="gmail", provider_message_id="m2", thread_id="th2", sender_email="hr@acme.com", sender_name="Acme", recipient_email="f@ex.com", subject="Software Architect Role Update", snippet="", body_text="Regarding Software Architect", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m2), m2).status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)

        # 3. Recruiter replying about a different requisition (REQ-9999)
        m3 = InboundMessageEvidence(provider="gmail", provider_message_id="m3", thread_id="th3", sender_email="recruiter@acme.com", sender_name="Recruiter", recipient_email="f@ex.com", subject="Requisition REQ-9999 Update", snippet="", body_text="Regarding Req #REQ-9999", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m3), m3).status, CorrelationStatus.UNLINKED)

        # 4. Forwarded email chain with conflicting context
        m4 = InboundMessageEvidence(provider="gmail", provider_message_id="m4", thread_id="th4", sender_email="forwarder@partner.com", sender_name="Partner", recipient_email="f@ex.com", subject="Fwd: Acme Application", snippet="", body_text="Fwd: Regarding your Acme application", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m4), m4).status, CorrelationStatus.UNLINKED)

        # 5. Missing application ID with multiple matches
        m5 = InboundMessageEvidence(provider="gmail", provider_message_id="m5", thread_id="th5", sender_email="no-reply@acme.com", sender_name="Acme", recipient_email="f@ex.com", subject="Status update from Acme Corp", snippet="", body_text="We are reviewing applications.", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m5), m5).status, CorrelationStatus.UNLINKED)

        # 6. Stale prior application mentioned alongside current
        m6 = InboundMessageEvidence(provider="gmail", provider_message_id="m6", thread_id="th6", sender_email="hr@acme.com", sender_name="Acme", recipient_email="f@ex.com", subject="Regarding REQ-OLD-99 and REQ-01", snippet="", body_text="Updates for REQ-OLD-99 and REQ-01", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m6), m6).status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)

        # 7. Multiple source IDs in quoted history
        m7 = InboundMessageEvidence(provider="gmail", provider_message_id="m7", thread_id="th7", sender_email="rec@acme.com", sender_name="Acme", recipient_email="f@ex.com", subject="Re: Update", snippet="", body_text="Status -----Original Message----- Req #REQ-01 and Req #REQ-02", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m7), m7).status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)

        # 8. Generic corporate sender without opportunity reference
        m8 = InboundMessageEvidence(provider="gmail", provider_message_id="m8", thread_id="th8", sender_email="info@corporate.example", sender_name="Corporate Info", recipient_email="f@ex.com", subject="General Information", snippet="", body_text="General company information.", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m8), m8).status, CorrelationStatus.UNLINKED)

        # 9. Ambiguous buyer name across multiple procurement tenders
        m9 = InboundMessageEvidence(provider="gmail", provider_message_id="m9", thread_id="th9", sender_email="procurement@gov.example", sender_name="Gov Contracting", recipient_email="f@ex.com", subject="Update from Gov Contracting regarding Data Services", snippet="", body_text="Update on Data Services tender", body_html="", received_at="2026-08-30T10:00:00Z")
        self.assertEqual(engine.correlate(classifier.classify(m9), m9).status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)

    def test_adv_03_real_partial_batch_crash_recovery(self) -> None:
        """Prove that a process crash after message 2 in a 5-message batch resumes messages 3-5 without duplicating 1-2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "crash_test.db"
            test_batch = list(GOLD_EMPLOYMENT_MESSAGES[:5])

            # Instance 1: Deliberately raise/crash after message 2 is processed
            store1 = DurableInboxStore(db_path)
            transport1 = MockMailTransport(messages=test_batch)
            ingest1 = InboundIngestionService(transport1, store=store1)
            orch1 = ProductionOperationalOrchestrator(ingestion_service=ingest1, store=store1)

            def crash_hook(idx: int, msg: InboundMessageEvidence) -> None:
                if idx == 2:
                    raise RuntimeError("SIMULATED PROCESS CRASH AFTER MESSAGE 2")

            with self.assertRaises(RuntimeError):
                orch1.run_cycle(limit=5, hook_after_message=crash_hook)

            # Checkpoint cursor was NOT advanced because cycle crashed before batch completion
            self.assertEqual(orch1.get_checkpoint_cursor(), "0")
            # Evidence exists for messages 1 and 2 as PROCESSED, but 3-5 were not processed
            self.assertTrue(store1.is_evidence_processed(test_batch[0].message_content_hash))
            self.assertTrue(store1.is_evidence_processed(test_batch[1].message_content_hash))

            # Destroy instances 1 completely
            del orch1, ingest1, transport1, store1

            # Instance 2: Restart fresh against SAME SQLite DB
            store2 = DurableInboxStore(db_path)
            transport2 = MockMailTransport(messages=test_batch)
            ingest2 = InboundIngestionService(transport2, store=store2)
            orch2 = ProductionOperationalOrchestrator(ingestion_service=ingest2, store=store2)

            # Re-run cycle: poll_new_messages returns only unprocessed messages 3, 4, 5
            res2 = orch2.run_cycle(limit=5)
            self.assertEqual(res2.messages_ingested, 3)  # Messages 3-5 processed!
            # Checkpoint now advances to "5"
            self.assertEqual(orch2.get_checkpoint_cursor(), "5")

            # Verify all 5 messages are now PROCESSED
            for m in test_batch:
                self.assertTrue(store2.is_evidence_processed(m.message_content_hash))

            # Replay from cursor "5" => 0 ingested, 0 duplicates
            res3 = orch2.run_cycle(limit=5)
            self.assertEqual(res3.messages_ingested, 0)
            self.assertEqual(res3.events_recorded, 0)
            self.assertEqual(res3.notifications_emitted, 0)

    def test_adv_03b_crash_after_evidence_before_classification(self) -> None:
        """Prove that a crash right after evidence persistence but before signal classification resumes safely without dropping messages or duplicating evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "crash_evidence.db"
            test_batch = list(GOLD_EMPLOYMENT_MESSAGES[:3])

            store1 = DurableInboxStore(db_path)
            transport1 = MockMailTransport(messages=test_batch)
            ingest1 = InboundIngestionService(transport1, store=store1)

            # Ingestion polls and stores evidence, but process crashes before orchestrator classifies
            msgs, cur = ingest1.poll_new_messages(limit=3)
            self.assertEqual(len(msgs), 3)
            self.assertEqual(len(store1.get_all_evidence()), 3)

            # Destroy instances
            del ingest1, transport1, store1

            # Restart fresh against same DB
            store2 = DurableInboxStore(db_path)
            transport2 = MockMailTransport(messages=test_batch)
            ingest2 = InboundIngestionService(transport2, store=store2)
            orch2 = ProductionOperationalOrchestrator(ingestion_service=ingest2, store=store2)

            # Run cycle: unprocessed messages are fully classified and completed
            res = orch2.run_cycle(limit=3)
            self.assertEqual(res.messages_ingested, 3)
            self.assertEqual(len(store2.get_all_evidence()), 3)  # No duplicate evidence!

    def test_adv_03c_crash_after_pipeline_event_before_notification(self) -> None:
        """Prove that a crash right after pipeline event persistence but before notification emission resumes safely with exact-once semantics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "crash_event.db"
            opp = Opportunity(id="opp-delta-1", track=Track.EMPLOYMENT, source="ashby", source_url="u", source_id="REQ-DELTA-101", organization="Delta Corp", title="Staff Engineer", description="d")
            test_batch = [GOLD_EMPLOYMENT_MESSAGES[3]]  # Interview invitation

            store1 = DurableInboxStore(db_path)
            transport1 = MockMailTransport(messages=test_batch)
            ingest1 = InboundIngestionService(transport1, store=store1)
            orch1 = ProductionOperationalOrchestrator(ingestion_service=ingest1, opportunities=[opp], store=store1)

            # Manually simulate pipeline event recorded, but crash before notification and mark_processed
            sig = orch1.classifier.classify(test_batch[0])
            corr = orch1.correlation_engine.correlate(sig, test_batch[0])
            orch1.store.store_evidence(test_batch[0])
            orch1.pipeline_store.record_signal_event(sig, corr, Track.EMPLOYMENT)
            self.assertEqual(len(store1.get_all_pipeline_events()), 1)
            self.assertEqual(len(store1.get_all_notifications()), 0)

            # Destroy instances
            del orch1, ingest1, transport1, store1

            # Restart fresh against same DB
            store2 = DurableInboxStore(db_path)
            transport2 = MockMailTransport(messages=test_batch)
            ingest2 = InboundIngestionService(transport2, store=store2)
            orch2 = ProductionOperationalOrchestrator(ingestion_service=ingest2, opportunities=[opp], store=store2)

            # Re-run cycle
            res = orch2.run_cycle(limit=1)
            self.assertEqual(res.messages_ingested, 1)
            # Event was ignored on re-insert (0 duplicate events)
            self.assertEqual(len(store2.get_all_pipeline_events()), 1)
            # Notification is emitted exactly once
            self.assertEqual(len(store2.get_all_notifications()), 1)

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

    def test_adv_06_multi_dimensional_analytics_coverage(self) -> None:
        """Prove analytics computes metrics across all supported dimensions and explicitly marks UNAVAILABLE."""
        records = [
            OutboundActionRecord(
                action_id=f"act-{i}", opportunity_id=f"opp-s1-{i}", opportunity_content_hash="h",
                workspace="w", candidate_id="c", track=Track.EMPLOYMENT, source="greenhouse", adapter_name="greenhouse",
                adapter_version="1.0.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT, qualification_decision=QualificationDecision.QUALIFIED,
                match_score_snapshot=0.85 if i % 2 == 0 else 0.45, artifact_ids=(), artifact_hashes=(), manifest_hash="m", action_status=ActionStatus.CONFIRMED,
                idempotency_key=f"k-{i}", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            )
            for i in range(4)
        ]
        multi_metrics = DualTrackAnalyticsEngine.compute_multi_dimensional_metrics(records, ())
        self.assertIn("source", multi_metrics)
        self.assertIn("track", multi_metrics)
        self.assertIn("score_band", multi_metrics)
        self.assertIn("role_family", multi_metrics)
        # Verify UNAVAILABLE dimension reporting
        self.assertIn("UNAVAILABLE", multi_metrics["role_family"])

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
