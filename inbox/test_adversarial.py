"""Adversarial attack vector tests for BRIEF-006 Operational Autonomy."""
import sqlite3
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
    PipelineEvent,
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

            # Ingest & record event, then simulate crash before notification and mark_evidence_processed
            msgs, _ = ingest1.poll_new_messages(limit=1)
            sig = orch1.classifier.classify(msgs[0])
            corr = orch1.correlation_engine.correlate(sig, msgs[0])
            orch1.pipeline_store.record_signal_event(sig, corr, Track.EMPLOYMENT)
            self.assertEqual(len(store1.get_all_pipeline_events()), 1)
            self.assertEqual(len(store1.get_all_notifications()), 0)
            self.assertFalse(store1.is_evidence_processed(msgs[0].message_content_hash))

            # Destroy instances completely
            del orch1, ingest1, transport1, store1

            # Restart fresh against same DB
            store2 = DurableInboxStore(db_path)
            transport2 = MockMailTransport(messages=test_batch)
            ingest2 = InboundIngestionService(transport2, store=store2)
            orch2 = ProductionOperationalOrchestrator(ingestion_service=ingest2, opportunities=[opp], store=store2)

            # Re-run cycle: unprocessed message resumes
            res = orch2.run_cycle(limit=1)
            self.assertEqual(res.messages_ingested, 1)
            # Event was deduplicated on re-insert (0 duplicate events)
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


    def test_adv_09_legacy_schema_migration_and_idempotency(self) -> None:
        """Prove that opening a real pre-PR56 BRIEF-006 legacy SQLite database upgrades cleanly without data loss or error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy_inbox.db"

            # 1. Create exact legacy PR55 schema (without processing_status or processed_at)
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE inbound_evidence (
                    message_content_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_message_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    sender_email TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    body_text TEXT NOT NULL,
                    body_html TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    headers_json TEXT NOT NULL,
                    attachment_names_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE pipeline_events (
                    event_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    previous_stage TEXT NOT NULL,
                    new_stage TEXT NOT NULL,
                    track TEXT NOT NULL,
                    trigger_category TEXT NOT NULL,
                    message_content_hash TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    UNIQUE(signal_id, opportunity_id)
                )
            """)
            # Insert representative legacy evidence
            ev1 = GOLD_EMPLOYMENT_MESSAGES[0]
            ev2 = GOLD_EMPLOYMENT_MESSAGES[1]
            conn.execute(
                "INSERT INTO inbound_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ev1.message_content_hash, ev1.provider, ev1.provider_message_id, ev1.thread_id, ev1.sender_email, ev1.sender_name, ev1.recipient_email, ev1.subject, ev1.snippet, ev1.body_text, ev1.body_html, ev1.received_at, "[]", "[]"),
            )
            conn.execute(
                "INSERT INTO inbound_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ev2.message_content_hash, ev2.provider, ev2.provider_message_id, ev2.thread_id, ev2.sender_email, ev2.sender_name, ev2.recipient_email, ev2.subject, ev2.snippet, ev2.body_text, ev2.body_html, ev2.received_at, "[]", "[]"),
            )
            conn.commit()
            conn.close()

            # 2. Instantiate new DurableInboxStore against the legacy database
            store = DurableInboxStore(db_path)

            # 3. Prove migration succeeded: columns exist and data remains intact
            all_ev = store.get_all_evidence()
            self.assertEqual(len(all_ev), 2)
            # Legacy evidence defaults conservatively to FETCHED to guarantee zero message/notification loss
            self.assertFalse(store.is_evidence_processed(ev1.message_content_hash))
            self.assertFalse(store.is_evidence_processed(ev2.message_content_hash))

            # 4. Prove repeated startup is idempotent
            store2 = DurableInboxStore(db_path)
            self.assertEqual(len(store2.get_all_evidence()), 2)

    def test_adv_09b_legacy_event_before_notification_migration_and_replay(self) -> None:
        """Mandatory test: PR55 legacy DB with pipeline event persisted but NO founder notification and unadvanced cursor.
        Prove:
        1. store migrates and message is NOT considered fully processed (remains FETCHED);
        2. replay from unchanged cursor does not duplicate existing pipeline event;
        3. missing founder notification is emitted exactly once;
        4. evidence becomes PROCESSED only after replay completes;
        5. checkpoint then advances;
        6. subsequent restart/replay has 0 duplicate events and 0 duplicate notifications.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy_event_no_notif.db"
            opp = Opportunity(id="opp-delta-1", track=Track.EMPLOYMENT, source="ashby", source_url="u", source_id="REQ-DELTA-101", organization="Delta Corp", title="Staff Engineer", description="d")
            msg = GOLD_EMPLOYMENT_MESSAGES[3]  # Interview invitation

            # Construct exact PR55 legacy DB
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE inbound_evidence (
                    message_content_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_message_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    sender_email TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    body_text TEXT NOT NULL,
                    body_html TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    headers_json TEXT NOT NULL,
                    attachment_names_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE pipeline_events (
                    event_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    previous_stage TEXT NOT NULL,
                    new_stage TEXT NOT NULL,
                    track TEXT NOT NULL,
                    trigger_category TEXT NOT NULL,
                    message_content_hash TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    UNIQUE(signal_id, opportunity_id)
                )
            """)
            conn.execute("""
                CREATE TABLE founder_notifications (
                    notification_key TEXT PRIMARY KEY,
                    notification_id TEXT NOT NULL,
                    opportunity_id TEXT,
                    signal_id TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    action_required INTEGER NOT NULL,
                    deadline TEXT,
                    created_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL,
                    acknowledged_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE inbox_checkpoints (
                    checkpoint_key TEXT PRIMARY KEY,
                    cursor_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Insert inbound evidence and pipeline event (persisted in PR55 before simulated crash), but NO notification, cursor="0"
            conn.execute(
                "INSERT INTO inbound_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (msg.message_content_hash, msg.provider, msg.provider_message_id, msg.thread_id, msg.sender_email, msg.sender_name, msg.recipient_email, msg.subject, msg.snippet, msg.body_text, msg.body_html, msg.received_at, "[]", "[]"),
            )
            sig = ResponseClassifier().classify(msg)
            conn.execute(
                "INSERT INTO pipeline_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("ev-legacy-1", "opp-delta-1", sig.signal_id, "applied", "interviewing", "employment", "interview_request", msg.message_content_hash, "2026-08-30T10:00:00Z", "2026-08-30T10:00:00Z", "agent", "legacy event"),
            )
            conn.execute(
                "INSERT INTO inbox_checkpoints VALUES (?, ?, ?)",
                ("inbox_checkpoint:gmail", "0", "2026-08-30T10:00:00Z"),
            )
            conn.commit()
            conn.close()

            # 1. Instantiate new DurableInboxStore and migrate
            store = DurableInboxStore(db_path)

            # 2. Prove the message is NOT considered fully processed (remains FETCHED)
            self.assertFalse(store.is_evidence_processed(msg.message_content_hash))
            self.assertEqual(len(store.get_all_notifications()), 0)
            self.assertEqual(len(store.get_all_pipeline_events()), 1)

            # 3. Create fresh ingestion / orchestrator instances against that DB
            transport = MockMailTransport(messages=[msg])
            ingest = InboundIngestionService(transport, store=store)
            orch = ProductionOperationalOrchestrator(ingestion_service=ingest, opportunities=[opp], store=store)

            # 4. Replay from unchanged cursor "0"
            res = orch.run_cycle(limit=1)
            self.assertEqual(res.messages_ingested, 1)

            # 5. Prove existing pipeline event is not duplicated
            self.assertEqual(len(store.get_all_pipeline_events()), 1)

            # 6. Prove missing founder notification is emitted exactly once
            notifs = store.get_all_notifications()
            self.assertEqual(len(notifs), 1)
            self.assertEqual(notifs[0].priority, SignalPriority.URGENT)

            # 7. Prove evidence becomes PROCESSED only after replay completes
            self.assertTrue(store.is_evidence_processed(msg.message_content_hash))

            # 8. Prove checkpoint cursor advances to "1"
            self.assertEqual(orch.get_checkpoint_cursor(), "1")

            # 9. Destroy and restart again against same DB: prove 0 duplicate events and 0 duplicate notifications
            del orch, ingest, transport, store

            store_restart = DurableInboxStore(db_path)
            transport_restart = MockMailTransport(messages=[msg])
            ingest_restart = InboundIngestionService(transport_restart, store=store_restart)
            orch_restart = ProductionOperationalOrchestrator(ingestion_service=ingest_restart, opportunities=[opp], store=store_restart)

            res_restart = orch_restart.run_cycle(limit=1)
            self.assertEqual(res_restart.messages_ingested, 0)
            self.assertEqual(len(store_restart.get_all_pipeline_events()), 1)
            self.assertEqual(len(store_restart.get_all_notifications()), 1)

    def test_adv_10_strict_reference_prefix_collision_and_receipt_authority(self) -> None:
        """Prove stored REQ-12345 + inbound REQ-1234 is NOT authoritative, and receipt_reference is a first-class exact authority."""
        from outbound.models import ConfirmationEvidence
        opp1 = Opportunity(id="opp-1", track=Track.EMPLOYMENT, source="greenhouse", source_url="u1", source_id="REQ-12345", organization="Acme", title="Engineer", description="d")
        rec1 = OutboundActionRecord(
            action_id="act-1", opportunity_id="opp-1", opportunity_content_hash="h1", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="greenhouse", adapter_name="greenhouse", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m1", action_status=ActionStatus.CONFIRMED, idempotency_key="k1", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-12345",
            confirmation_evidence=ConfirmationEvidence(confirmed=True, confirmation_text="OK", receipt_reference="RECEIPT-EXACT-999"),
        )
        engine = OpportunityCorrelationEngine(opportunities=[opp1], outbound_records=[rec1])
        classifier = ResponseClassifier()

        # Inbound with prefix REQ-1234 (must NOT match REQ-12345)
        m_prefix = InboundMessageEvidence(
            provider="gmail", provider_message_id="m-p", thread_id="th-p",
            sender_email="recruiting@acme.com", sender_name="Acme", recipient_email="f@ex.com",
            subject="Update regarding Req #REQ-1234", snippet="", body_text="Regarding Req #REQ-1234", body_html="", received_at="2026-08-30T10:00:00Z",
        )
        corr_p = engine.correlate(classifier.classify(m_prefix), m_prefix)
        self.assertFalse(corr_p.is_authoritative)
        self.assertNotEqual(corr_p.status, CorrelationStatus.EXACT_REFERENCE_MATCH)

        # Inbound with exact normalized REQ-12345 (MUST match)
        m_exact = InboundMessageEvidence(
            provider="gmail", provider_message_id="m-e", thread_id="th-e",
            sender_email="recruiting@acme.com", sender_name="Acme", recipient_email="f@ex.com",
            subject="Update regarding Req #REQ-12345", snippet="", body_text="Regarding Req #REQ-12345", body_html="", received_at="2026-08-30T10:00:00Z",
        )
        corr_e = engine.correlate(classifier.classify(m_exact), m_exact)
        self.assertTrue(corr_e.is_authoritative)
        self.assertEqual(corr_e.status, CorrelationStatus.EXACT_REFERENCE_MATCH)
        self.assertEqual(corr_e.opportunity_id, "opp-1")

        # Inbound with exact receipt_reference RECEIPT-EXACT-999 (MUST match)
        m_receipt = InboundMessageEvidence(
            provider="gmail", provider_message_id="m-r", thread_id="th-r",
            sender_email="recruiting@acme.com", sender_name="Acme", recipient_email="f@ex.com",
            subject="Submission Confirmation", snippet="", body_text="Receipt Reference: RECEIPT-EXACT-999 confirmed.", body_html="", received_at="2026-08-30T10:00:00Z",
        )
        corr_r = engine.correlate(classifier.classify(m_receipt), m_receipt)
        self.assertTrue(corr_r.is_authoritative)
        self.assertEqual(corr_r.status, CorrelationStatus.EXACT_REFERENCE_MATCH)
        self.assertEqual(corr_r.opportunity_id, "opp-1")

    def test_adv_11_qualified_conversation_analytics_derivation(self) -> None:
        """Prove qualified_conversation analytics derives accurately from pipeline events while unobserved remain pending."""
        rec_qual = OutboundActionRecord(
            action_id="act-q", opportunity_id="opp-q", opportunity_content_hash="h1", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="greenhouse", adapter_name="greenhouse", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m1", action_status=ActionStatus.CONFIRMED, idempotency_key="kq", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
        )
        rec_pending = OutboundActionRecord(
            action_id="act-p", opportunity_id="opp-p", opportunity_content_hash="h2", workspace="w", candidate_id="c",
            track=Track.EMPLOYMENT, source="greenhouse", adapter_name="greenhouse", adapter_version="1.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9, artifact_ids=(), artifact_hashes=(),
            manifest_hash="m2", action_status=ActionStatus.CONFIRMED, idempotency_key="kp", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
        )
        # Event indicating interview invitation for opp-q
        ev_interview = PipelineEvent(
            event_id="ev-int-1", opportunity_id="opp-q", signal_id="sig-int",
            previous_stage=OpportunityStage.NO_EVENTS, new_stage=OpportunityStage.INTERVIEWING,
            track=Track.EMPLOYMENT, trigger_category=SignalCategory.INTERVIEW_REQUEST,
            message_content_hash="h-int", occurred_at="2026-08-30T10:00:00Z", recorded_at="2026-08-30T10:00:00Z",
            actor="agent", notes="",
        )

        dim_metrics = DualTrackAnalyticsEngine.compute_dimension_metrics(
            outbound_records=[rec_qual, rec_pending],
            events=[ev_interview],
            dimension="qualified_conversation",
        )
        self.assertIn("qualified_conversation_achieved", dim_metrics)
        self.assertIn("pending_outcome", dim_metrics)
        self.assertEqual(dim_metrics["qualified_conversation_achieved"].total_submissions, 1)
        self.assertEqual(dim_metrics["pending_outcome"].total_submissions, 1)

if __name__ == "__main__":
    unittest.main()
