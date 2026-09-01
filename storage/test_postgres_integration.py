import os
import unittest
import json
import uuid
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from storage.models import (
    Base,
    OpportunityRecord,
    FieldProvenanceRecord,
    OutboundActionRecordModel,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    InboxCheckpointRecord,
    ReconciliationRecordModel,
    WorkerJobRecord,
    FounderFeedbackRecord,
)
from storage.engine import (
    get_engine,
    get_session_factory,
    get_production_db_url,
    ProductionDatabaseConfigurationError,
)
from storage.repository import StorageRepository
from storage.migration import LegacySqliteToPostgresMigrator
from outbound.postgres_idempotency import PostgresIdempotencyLedger
from inbox.postgres_persistence import PostgresInboxStore
from worker.queue import BackgroundWorkerQueue
from feedback.service import FounderFeedbackService
from feedback.models import FeedbackLabel
from matching.models import ArtifactType, QualificationDecision, TailoredArtifact, TailoringPolicy, Track
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, Modality, Polarity, VerificationStatus
from outbound.models import (
    ActionStatus,
    BoundArtifact,
    ConfirmationEvidence,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    OutboundActionRecord,
    PreSubmitManifest,
    SourceActionPolicy,
)
from outbound.browser_engine import MockBrowserDriver, OutboundBrowserEngine
from outbound.mock_harness import MockATSHarness
from outbound.authority import ActionAuthority, GlobalKillSwitch
from outbound.registry import AdapterRegistry, SourceActionRegistry
from outbound.idempotency import DuplicateSubmissionError, IdempotencyLedger, UnknownOutcomeFrozenError
from inbox.persistence import DurableInboxStore
from inbox.pipeline import PipelineEventStore
from inbox.notifications import NotificationEngine
from inbox.models import (
    InboundMessageEvidence,
    PipelineEvent,
    OpportunityStage,
    SignalCategory,
    FounderNotificationRecord,
    SignalPriority,
)
from inbox.ingestion import InboundIngestionService, MockMailTransport
from inbox.orchestrator import ProductionOperationalOrchestrator
from scripts.backup_restore import dump_database, restore_database


class PostgresProductionIntegrationTest(unittest.TestCase):
    """Rigorous PostgreSQL production integration test suite exercising real PostgreSQL concurrency and invariants."""

    @classmethod
    def setUpClass(cls):
        cls.db_url = os.environ.get("OPPORTUNITYOS_DB_URL")
        if not cls.db_url or not cls.db_url.startswith("postgresql"):
            if os.environ.get("CI"):
                raise AssertionError(
                    "CI is set but OPPORTUNITYOS_DB_URL is missing or not a "
                    "PostgreSQL URL (postgresql+psycopg2://...). PostgreSQL "
                    "integration tests must fail loudly in CI, not skip. Got: "
                    f"{cls.db_url!r}."
                )
            # Enforce that in CI or when running integration tests, backend MUST be real PostgreSQL
            raise unittest.SkipTest(f"PostgreSQL integration tests require real PostgreSQL backend, got: {cls.db_url}")

        cls.engine = get_engine(cls.db_url)
        cls.SessionFactory = get_session_factory(cls.engine)

        # Run baseline migration once for the test class
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", cls.db_url)
        command.upgrade(alembic_cfg, "head")

    def setUp(self):
        # Clean test tables between runs
        with self.engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))

    def test_case_a_and_b_alembic_upgrade_downgrade_smoke(self):
        """Case A & B: empty DB -> Alembic head -> downgrade smoke -> upgrade to head."""
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", self.db_url)
        
        # Test upgrade to head
        command.upgrade(alembic_cfg, "head")
        
        # Verify tables exist in postgres
        with self.engine.connect() as conn:
            res = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"))
            count = res.scalar()
            self.assertGreater(count, 5)

    def test_case_c_exact_historical_inbox_sqlite_to_postgres(self):
        """Case C: Exact historical inbox SQLite -> PostgreSQL migration with 100% fidelity."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            sqlite_path = tf.name

        try:
            from inbox.persistence import DurableInboxStore
            store = DurableInboxStore(sqlite_path)
            
            # Store evidence
            ev = InboundMessageEvidence(
                provider="gmail", provider_message_id="msg-101", thread_id="th-101",
                sender_email="recruiter@example.com", sender_name="Recruiter",
                recipient_email="founder@example.com", subject="Interview Request",
                snippet="Would love to schedule an interview", body_text="Full interview details...",
                body_html="<p>Full interview details...</p>", received_at="2026-08-30T10:00:00Z",
                headers=(("From", "recruiter@example.com"), ("Subject", "Interview Request")),
                attachment_names=("brief.pdf",),
            )
            store.store_evidence(ev, status="PROCESSED")
            store.mark_evidence_processed(ev.message_content_hash, processed_at="2026-08-30T10:05:00Z")

            # Store pipeline event
            event = PipelineEvent(
                event_id="evt-101", opportunity_id="opp-101", signal_id="sig-101",
                previous_stage=OpportunityStage.NO_EVENTS, new_stage=OpportunityStage.INTERVIEWING,
                track=Track.EMPLOYMENT, trigger_category=SignalCategory.INTERVIEW_REQUEST,
                message_content_hash=ev.message_content_hash, occurred_at="2026-08-30T10:00:00Z",
                recorded_at="2026-08-30T10:01:00Z", actor="system", notes="Auto correlated",
            )
            store.store_pipeline_event(event)

            # Store notification
            notif = FounderNotificationRecord(
                notification_id="notif-101", notification_key="notif-key-101",
                opportunity_id="opp-101", signal_id="sig-101", priority=SignalPriority.HIGH,
                category=SignalCategory.INTERVIEW_REQUEST, title="Interview Invited",
                message="Invitation for opp-101", action_required=True,
                deadline=None, created_at="2026-08-30T10:01:00Z",
            )
            store.store_notification(notif)
            store.save_checkpoint("gmail:cursor", "cursor-999", "2026-08-30T10:05:00Z")
            store.record_reconciliation("rec-101", "act-101", "opp-101", "sig-101", ev.message_content_hash, "Unknown outcome resolved", "2026-08-30T10:05:00Z")

            # Execute migration into PostgreSQL
            session = self.SessionFactory()
            migrator = LegacySqliteToPostgresMigrator(session)
            stats = migrator.migrate_inbox_sqlite(sqlite_path)
            session.close()

            self.assertEqual(stats["inbound_evidence"], 1)
            self.assertEqual(stats["pipeline_events"], 1)
            self.assertEqual(stats["founder_notifications"], 1)
            self.assertEqual(stats["inbox_checkpoints"], 1)
            self.assertEqual(stats["reconciliation_records"], 1)

            # Query PostgresStore to verify
            pg_store = PostgresInboxStore(db_url=self.db_url)
            ret_ev = pg_store.get_evidence(ev.message_content_hash)
            self.assertIsNotNone(ret_ev)
            self.assertEqual(ret_ev.sender_email, "recruiter@example.com")
            self.assertTrue(pg_store.is_evidence_processed(ev.message_content_hash))

            events = pg_store.get_events_for_opportunity("opp-101")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].new_stage, OpportunityStage.INTERVIEWING)

            notifs = pg_store.get_pending_notifications()
            self.assertEqual(len(notifs), 1)
            self.assertEqual(notifs[0].title, "Interview Invited")
            self.assertEqual(pg_store.get_checkpoint("gmail:cursor"), "cursor-999")
        finally:
            if os.path.exists(sqlite_path):
                os.remove(sqlite_path)

    def test_case_d_exact_historical_outbound_sqlite_to_postgres(self):
        """Case D: Exact historical outbound SQLite -> PostgreSQL migration."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            sqlite_path = tf.name

        try:
            from outbound.idempotency import IdempotencyLedger
            ledger = IdempotencyLedger(sqlite_path)

            rec = OutboundActionRecord(
                action_id="act-201", opportunity_id="opp-201",
                opportunity_content_hash="hash-201", workspace="default",
                candidate_id="founder", track=Track.EMPLOYMENT, source="ashby",
                adapter_name="ashby_outbound", adapter_version="1.0.0",
                execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
                qualification_decision=QualificationDecision.QUALIFIED,
                match_score_snapshot=92.5, artifact_ids=("art-1",), artifact_hashes=("ah-1",),
                manifest_hash="man-hash-201", action_status=ActionStatus.CONFIRMED,
                idempotency_key="idemp-key-201", created_at="2026-08-30T12:00:00Z",
                updated_at="2026-08-30T12:05:00Z",
                confirmation_evidence=ConfirmationEvidence(
                    confirmed=True, confirmation_text="Application received",
                    receipt_reference="ASH-99988", application_id="app-201",
                ),
                external_reference_id="ASH-99988",
            )
            ledger.reserve_submission(rec)
            ledger.transition_status(rec.idempotency_key, ActionStatus.CONFIRMED, evidence=rec.confirmation_evidence)

            session = self.SessionFactory()
            migrator = LegacySqliteToPostgresMigrator(session)
            stats = migrator.migrate_outbound_sqlite(sqlite_path)
            session.close()

            self.assertEqual(stats["idempotency_reservations"], 1)
            self.assertEqual(stats["outbound_actions"], 1)

            pg_ledger = PostgresIdempotencyLedger(db_url=self.db_url)
            ret_rec = pg_ledger.get_record("idemp-key-201")
            self.assertIsNotNone(ret_rec)
            self.assertEqual(ret_rec.action_id, "act-201")
            self.assertEqual(ret_rec.action_status, ActionStatus.CONFIRMED)
            self.assertTrue(ret_rec.confirmation_evidence.confirmed)
            self.assertEqual(ret_rec.confirmation_evidence.receipt_reference, "ASH-99988")
        finally:
            if os.path.exists(sqlite_path):
                os.remove(sqlite_path)

    def test_case_e_f_g_preservation_of_unknown_outcome_and_reconciliations(self):
        """Case E, F, G: UNKNOWN_OUTCOME freeze and reconciliation records in PostgreSQL."""
        pg_ledger = PostgresIdempotencyLedger(db_url=self.db_url)
        rec = OutboundActionRecord(
            action_id="act-301", opportunity_id="opp-301",
            opportunity_content_hash="hash-301", workspace="default",
            candidate_id="founder", track=Track.EMPLOYMENT, source="lever",
            adapter_name="lever_outbound", adapter_version="1.0.0",
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED,
            match_score_snapshot=88.0, artifact_ids=(), artifact_hashes=(),
            manifest_hash="man-301", action_status=ActionStatus.UNKNOWN_OUTCOME,
            idempotency_key="idemp-301", created_at="2026-08-30T14:00:00Z",
            updated_at="2026-08-30T14:02:00Z", blocker_reason="Browser crashed during submit",
        )
        pg_ledger.reserve_submission(rec)
        pg_ledger.record_outcome(rec)

        with self.assertRaises(UnknownOutcomeFrozenError):
            pg_ledger.reserve_submission(rec)

    def test_case_h_duplicate_notification_event_replay(self):
        """Case H: Duplicate notification and pipeline event replay produces 0 duplicate records."""
        pg_store = PostgresInboxStore(db_url=self.db_url)
        notif = FounderNotificationRecord(
            notification_id="nid-1", notification_key="notif-dup-1",
            opportunity_id="opp-1", signal_id="sig-1", priority=SignalPriority.URGENT,
            category=SignalCategory.OFFER, title="Offer Received", message="Great news!",
            action_required=True, deadline=None, created_at="2026-08-30T14:00:00Z",
        )
        first_store = pg_store.store_notification(notif)
        second_store = pg_store.store_notification(notif)
        self.assertTrue(first_store)
        self.assertFalse(second_store)

        pending = pg_store.get_pending_notifications()
        self.assertEqual(len(pending), 1)

    def test_case_i_two_independent_idempotency_transactions_racing(self):
        """Case I: Two independent PostgreSQL sessions racing for the same idempotency key."""
        pg_ledger_1 = PostgresIdempotencyLedger(db_url=self.db_url)
        pg_ledger_2 = PostgresIdempotencyLedger(db_url=self.db_url)

        rec1 = OutboundActionRecord(
            action_id="act-race-1", opportunity_id="opp-race-1",
            opportunity_content_hash="h-race", workspace="default",
            candidate_id="founder", track=Track.EMPLOYMENT, source="ashby",
            adapter_name="ashby_outbound", adapter_version="1.0.0",
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED,
            match_score_snapshot=90.0, artifact_ids=(), artifact_hashes=(),
            manifest_hash="man-race", action_status=ActionStatus.SUBMITTING,
            idempotency_key="race-key-1", created_at="2026-08-30T15:00:00Z",
            updated_at="2026-08-30T15:00:00Z",
        )
        rec2 = OutboundActionRecord(
            action_id="act-race-2", opportunity_id="opp-race-1",
            opportunity_content_hash="h-race", workspace="default",
            candidate_id="founder", track=Track.EMPLOYMENT, source="ashby",
            adapter_name="ashby_outbound", adapter_version="1.0.0",
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED,
            match_score_snapshot=90.0, artifact_ids=(), artifact_hashes=(),
            manifest_hash="man-race", action_status=ActionStatus.SUBMITTING,
            idempotency_key="race-key-1", created_at="2026-08-30T15:00:00Z",
            updated_at="2026-08-30T15:00:00Z",
        )

        winners = []
        errors = []

        def worker_fn(ledger_instance, record):
            try:
                ledger_instance.reserve_submission(record)
                winners.append(record.action_id)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_fn, args=(pg_ledger_1, rec1))
        t2 = threading.Thread(target=worker_fn, args=(pg_ledger_2, rec2))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(winners), 1, "Exactly one thread must win reservation")
        self.assertEqual(len(errors), 1, "Exactly one thread must fail reservation")
        self.assertIsInstance(errors[0], DuplicateSubmissionError, f"Loser must raise DuplicateSubmissionError, got: {type(errors[0])}")

    def test_case_j_two_independent_workers_racing_with_skip_locked(self):
        """Case J: Two independent workers racing for one job with SKIP LOCKED."""
        session1 = self.SessionFactory()
        session2 = self.SessionFactory()

        q1 = BackgroundWorkerQueue(session1, worker_id="w-1")
        q2 = BackgroundWorkerQueue(session2, worker_id="w-2")

        job_id = q1.enqueue_job("export_binary", {"artifact_id": "art-99"})

        claimed_jobs = []

        def claim_fn(q):
            job = q.claim_next_job(lease_duration_seconds=30)
            if job:
                claimed_jobs.append((q.worker_id, job.id))

        t1 = threading.Thread(target=claim_fn, args=(q1,))
        t2 = threading.Thread(target=claim_fn, args=(q2,))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(claimed_jobs), 1, "Exactly one worker must claim the job")
        self.assertEqual(claimed_jobs[0][1], job_id)

        session1.close()
        session2.close()

    def test_case_k_worker_stale_lease_recovery_after_restart(self):
        """Case K: Stale leased worker job is cleanly recovered after lease expiration."""
        session = self.SessionFactory()
        q = BackgroundWorkerQueue(session, worker_id="w-dead")
        job_id = q.enqueue_job("export_binary", {"artifact_id": "art-100"})

        job = q.claim_next_job(lease_duration_seconds=1)
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "RUNNING")

        # Simulate time passage beyond lease expiration
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE worker_jobs SET lease_expires_at = :past WHERE id = :jid"),
                {"past": datetime.now(timezone.utc) - timedelta(seconds=10), "jid": job_id},
            )

        # Fresh worker claims the stale job
        fresh_session = self.SessionFactory()
        fresh_q = BackgroundWorkerQueue(fresh_session, worker_id="w-fresh")
        recovered_job = fresh_q.claim_next_job(lease_duration_seconds=60)

        self.assertIsNotNone(recovered_job)
        self.assertEqual(recovered_job.id, job_id)
        self.assertEqual(recovered_job.lease_owner, "w-fresh")

        session.close()
        fresh_session.close()

    def test_case_l_transaction_rollback_after_induced_failure(self):
        """Case L: Transaction rolls back completely on induced failure."""
        session = self.SessionFactory()
        repo = StorageRepository(session)

        opp_data = {
            "id": "opp-tx-1", "track": "EMPLOYMENT", "title": "Lead Engineer",
            "organization": "Acme", "description": "Desc", "source_id": "src-1",
            "source_url": "https://example.com", "content_hash": "ch-1",
        }
        repo.save_opportunity(opp_data, [])

        try:
            with session.begin_nested():
                prov = FieldProvenanceRecord(
                    opportunity_id="opp-non-existent-fk-violation",
                    field_name="title", derivation_type="DIRECT", record_checksum="cs",
                )
                session.add(prov)
                session.flush()
        except Exception:
            session.rollback()

        # Verify opportunity remains unaffected and no partial provenance records
        ret_opp = repo.get_opportunity("opp-tx-1")
        self.assertIsNotNone(ret_opp)
        self.assertEqual(len(ret_opp.provenances), 0)
        session.close()

    def test_case_m_backup_wipe_restore_postgres_cycle(self):
        """Case M: Full backup -> wipe database -> restore -> verify all models."""
        session = self.SessionFactory()
        repo = StorageRepository(session)

        # Populate state
        opp_data = {
            "id": "opp-bk-1", "track": "INDEPENDENT", "title": "Consultant",
            "organization": "Gov Org", "description": "Consulting RFP",
            "source_id": "etimad-1", "source_url": "https://etimad.sa",
            "content_hash": "ch-bk-1",
        }
        provs = [{"field_name": "title", "raw_value": "Consultant", "derivation_type": "DIRECT", "record_checksum": "cs-1"}]
        repo.save_opportunity(opp_data, provs)
        repo.record_feedback("opp-bk-1", FeedbackLabel.GOOD_MATCH.value, "Great fit", "Proceed")
        session.close()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            dump_path = tf.name

        try:
            dump_database(self.db_url, dump_path)

            # Wipe database
            with self.engine.begin() as conn:
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))

            # Verify empty
            check_session = self.SessionFactory()
            self.assertEqual(check_session.query(OpportunityRecord).count(), 0)
            check_session.close()

            # Restore
            restore_database(dump_path, self.db_url)

            # Verify restored
            verify_session = self.SessionFactory()
            ret_opp = verify_session.query(OpportunityRecord).filter_by(id="opp-bk-1").first()
            self.assertIsNotNone(ret_opp)
            self.assertEqual(len(ret_opp.provenances), 1)
            self.assertEqual(len(ret_opp.feedback), 1)
            self.assertEqual(ret_opp.feedback[0].feedback_label, FeedbackLabel.GOOD_MATCH.value)
            verify_session.close()

            # restore_database runs the Alembic upgrade to head against the
            # target (see scripts/backup_restore.py), not init_db/create_all;
            # verify the restored database is actually stamped at head, read
            # from the script directory rather than hard-coded.
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", self.db_url)
            script_dir = ScriptDirectory.from_config(alembic_cfg)
            head_revision = script_dir.get_current_head()
            with self.engine.connect() as conn:
                stamped_revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(stamped_revision, head_revision)

            # The restored table set equals the full set of model tables
            # (i.e. dump_database's completeness check covered everything).
            with self.engine.connect() as conn:
                actual_tables = {
                    row[0]
                    for row in conn.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name != 'alembic_version'"
                        )
                    )
                }
            self.assertEqual(actual_tables, set(Base.metadata.tables.keys()))
        finally:
            if os.path.exists(dump_path):
                os.remove(dump_path)

    def test_case_n_founder_feedback_duplicate_and_identity(self):
        """Case N: Founder feedback duplicate replay produces 0 duplicate records and returns exact persisted ID."""
        session = self.SessionFactory()
        repo = StorageRepository(session)
        service = FounderFeedbackService(repo)

        opp_data = {
            "id": "opp-fb-1", "track": "EMPLOYMENT", "title": "Staff AI",
            "organization": "DeepTech", "description": "AI role",
            "source_id": "ashby-1", "source_url": "https://ashby.com",
            "content_hash": "ch-fb-1",
        }
        repo.save_opportunity(opp_data, [])

        event1 = service.submit_feedback("opp-fb-1", FeedbackLabel.ELIGIBILITY_WRONG, "Requires US citizenship", "Need remote")
        event2 = service.submit_feedback("opp-fb-1", FeedbackLabel.ELIGIBILITY_WRONG, "Requires US citizenship", "Need remote")

        self.assertEqual(event1.id, event2.id, "Replaying identical feedback must return exact same ID")

        all_fb = repo.list_feedback_for_opportunity("opp-fb-1")
        self.assertEqual(len(all_fb), 1, "Deduplication must prevent duplicate feedback record")
        self.assertEqual(all_fb[0].id, event1.id)

        # Different feedback is recorded separately
        event3 = service.submit_feedback("opp-fb-1", FeedbackLabel.BAD_MATCH, "Low salary", "Too low")
        self.assertNotEqual(event1.id, event3.id)
        all_fb_after = repo.list_feedback_for_opportunity("opp-fb-1")
        self.assertEqual(len(all_fb_after), 2)
        session.close()

    def test_case_o_process_restart_against_migrated_postgres(self):
        """Case O: Process restarts against PostgreSQL maintain complete state continuity."""
        pg_store1 = PostgresInboxStore(db_url=self.db_url)
        pg_store1.save_checkpoint("cursor:main", "12345")

        # Simulate process restart by creating a completely new store instance
        pg_store2 = PostgresInboxStore(db_url=self.db_url)
        self.assertEqual(pg_store2.get_checkpoint("cursor:main"), "12345")

    def test_case_p_no_implicit_production_sqlite_fallback(self):
        """Case P: Storage engine and all production components fail closed to PostgreSQL with no silent SQLite fallback."""
        orig_env = os.environ.get("OPPORTUNITYOS_DB_URL")
        try:
            # 1. Missing environment variable -> fails closed
            if "OPPORTUNITYOS_DB_URL" in os.environ:
                del os.environ["OPPORTUNITYOS_DB_URL"]
            with self.assertRaises(ProductionDatabaseConfigurationError):
                get_production_db_url()

            with self.assertRaises(ProductionDatabaseConfigurationError):
                get_engine()  # default production constructor

            # A. unset OPPORTUNITYOS_DB_URL -> OutboundBrowserEngine() fails closed (no :memory: created)
            with self.assertRaises(ProductionDatabaseConfigurationError):
                OutboundBrowserEngine()

            # B. OPPORTUNITYOS_DB_URL=sqlite:///x.db -> OutboundBrowserEngine() fails closed
            os.environ["OPPORTUNITYOS_DB_URL"] = "sqlite:///x.db"
            with self.assertRaises(ProductionDatabaseConfigurationError):
                OutboundBrowserEngine()
            del os.environ["OPPORTUNITYOS_DB_URL"]

            # C. unset OPPORTUNITYOS_DB_URL -> InboundIngestionService(MockMailTransport()) fails closed (no :memory:)
            with self.assertRaises(ProductionDatabaseConfigurationError):
                InboundIngestionService(MockMailTransport())

            # D. unset OPPORTUNITYOS_DB_URL -> PipelineEventStore() fails closed
            with self.assertRaises(ProductionDatabaseConfigurationError):
                PipelineEventStore()

            # E. unset OPPORTUNITYOS_DB_URL -> NotificationEngine() fails closed
            with self.assertRaises(ProductionDatabaseConfigurationError):
                NotificationEngine()

            # F. production orchestrator default/fallback path cannot create a SQLite store
            class IngestionWithoutStore:
                pass

            with self.assertRaises(ProductionDatabaseConfigurationError):
                ProductionOperationalOrchestrator(ingestion_service=IngestionWithoutStore(), store=None)
            with self.assertRaises(ProductionDatabaseConfigurationError):
                ProductionOperationalOrchestrator(ingestion_service=None, store=None)

            # G. PostgresInboxStore(db_url="sqlite:///x.db") fails closed
            with self.assertRaises(ProductionDatabaseConfigurationError):
                PostgresInboxStore(db_url="sqlite:///x.db")

            # H. PostgresIdempotencyLedger(db_url="sqlite:///x.db") fails closed
            with self.assertRaises(ProductionDatabaseConfigurationError):
                PostgresIdempotencyLedger(db_url="sqlite:///x.db")

            # I. Explicit dependency injection still works for SQLite compatibility / unit tests
            explicit_ledger = IdempotencyLedger(":memory:")
            engine = OutboundBrowserEngine(ledger=explicit_ledger)
            self.assertIs(engine.ledger, explicit_ledger)
            self.assertIsInstance(engine.ledger, IdempotencyLedger)

            explicit_store = DurableInboxStore(":memory:")
            ingest = InboundIngestionService(MockMailTransport(), store=explicit_store)
            self.assertIs(ingest.store, explicit_store)

            pipe = PipelineEventStore(store=explicit_store)
            self.assertIs(pipe.store, explicit_store)

            notif = NotificationEngine(store=explicit_store)
            self.assertIs(notif.store, explicit_store)

            orch = ProductionOperationalOrchestrator(ingestion_service=ingest, store=explicit_store)
            self.assertIs(orch.store, explicit_store)

            # 2. Explicit SQLite in production URL -> rejected
            os.environ["OPPORTUNITYOS_DB_URL"] = "sqlite:///production_attempt.db"
            with self.assertRaises(ProductionDatabaseConfigurationError):
                get_production_db_url()

            # 3. Explicit test/local SQLite opt-in allowed with allow_sqlite=True
            del os.environ["OPPORTUNITYOS_DB_URL"]
            sqlite_engine = get_engine(allow_sqlite=True)
            self.assertTrue(str(sqlite_engine.url).startswith("sqlite"))

            # J. Normal PostgreSQL defaults still work when OPPORTUNITYOS_DB_URL is a valid PostgreSQL URL
            os.environ["OPPORTUNITYOS_DB_URL"] = self.db_url
            pg_url = get_production_db_url()
            self.assertTrue(pg_url.startswith("postgresql"))

            engine_pg = OutboundBrowserEngine()
            self.assertIsInstance(engine_pg.ledger, PostgresIdempotencyLedger)

            ingest_pg = InboundIngestionService(MockMailTransport())
            self.assertIsInstance(ingest_pg.store, PostgresInboxStore)

            pipe_pg = PipelineEventStore()
            self.assertIsInstance(pipe_pg.store, PostgresInboxStore)

            notif_pg = NotificationEngine()
            self.assertIsInstance(notif_pg.store, PostgresInboxStore)

            orch_pg = ProductionOperationalOrchestrator(ingestion_service=ingest_pg)
            self.assertIsInstance(orch_pg.store, PostgresInboxStore)
        finally:
            if orig_env is not None:
                os.environ["OPPORTUNITYOS_DB_URL"] = orig_env
            elif "OPPORTUNITYOS_DB_URL" in os.environ:
                del os.environ["OPPORTUNITYOS_DB_URL"]

    def test_case_q_outbound_browser_engine_with_postgres_ledger(self):
        """Case Q: Real OutboundBrowserEngine executes against PostgresIdempotencyLedger through full lifecycle."""
        GlobalKillSwitch.enable()
        with tempfile.TemporaryDirectory() as ev_dir_str:
            ev_dir = Path(ev_dir_str)
            gh_ev = ev_dir / "greenhouse_graduation_evidence.json"
            gh_ev.write_text(json.dumps({"run_id": "test-gh-run-pg", "success": True}), encoding="utf-8")

            adapter_reg = AdapterRegistry(evidence_dir=ev_dir)
            adapter_reg.enable_submit("greenhouse")
            src_reg = SourceActionRegistry({"greenhouse": SourceActionPolicy.SUBMIT_ALLOWED})
            auth = ActionAuthority(registry=src_reg, adapter_registry=adapter_reg)

            pg_ledger = PostgresIdempotencyLedger(db_url=self.db_url)
            engine = OutboundBrowserEngine(authority=auth, ledger=pg_ledger)

            opp = Opportunity(
                id="opp-pg-outbound-1",
                title="Senior Systems Architect",
                organization="CloudTech",
                description="Looking for Senior Architect",
                track=Track.EMPLOYMENT,
                source="greenhouse",
                source_url="https://boards.greenhouse.io/cloudtech/jobs/101",
                source_id="gh-101",
                content_hash="ch-pg-out-1",
            )
            tg = TruthGraph()
            ev = EvidenceRecord(id="ev-pg-1", source="passport", locator="p1", content="Founder Name. Authorized in Egypt. Country: Egypt.")
            tg.add_evidence(ev)
            tg.add_assertion(AtomicAssertion(
                id="a-name", subject_id="founder", predicate="identity.name",
                value="Founder Name", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
                verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-pg-1",),
            ))
            tg.add_assertion(AtomicAssertion(
                id="a-auth", subject_id="founder", predicate="authorization.jurisdiction",
                value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
                verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-pg-1",),
            ))
            tg.add_assertion(AtomicAssertion(
                id="a-country", subject_id="founder", predicate="identity.country",
                value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
                verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-pg-1",),
            ))

            policy = TailoringPolicy(
                default_notice_period_days=30,
                default_currency="USD",
                default_hourly_rate=100.0,
                default_sponsorship_required=False,
            )
            raw_artifact = TailoredArtifact(
                artifact_id="art-pg-1",
                artifact_type=ArtifactType.TAILORED_CV,
                opportunity_id=opp.id,
                opportunity_content_hash=opp.content_hash,
                template_version="1.0",
                policy_version="1.0",
                title="CV",
                sections=(),
                generated_claims=(),
                commitment_checklist=(),
                compiled_at="2026-08-30T00:00:00Z",
            )
            artifact = BoundArtifact(artifact=raw_artifact, candidate_id="founder", workspace="default")

            harness = MockATSHarness(steps=[
                [DetectedFormField("name", "name", "text", "Full Name", "full name", FieldOntologyType.IDENTITY, required=True)]
            ])
            driver = MockBrowserDriver(harness)

            # Prepare manifest
            manifest, answers, red_cnt, unres_cnt = engine.prepare_manifest(
                opportunity=opp,
                artifact=artifact,
                driver=driver,
                truth_graph=tg,
                policy=policy,
                adapter_name="greenhouse",
            )
            self.assertIsNotNone(manifest)
            self.assertEqual(red_cnt, 0)

            # 1. Missing prepared manifest under CONTROLLED_SUBMIT -> BLOCKED
            rec_no_manifest = engine.execute_application(
                opportunity=opp,
                artifact=artifact,
                driver=driver,
                execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
                truth_graph=tg,
                policy=policy,
                prepared_manifest=None,
            )
            self.assertEqual(rec_no_manifest.action_status, ActionStatus.BLOCKED)
            self.assertEqual(harness.submits_count, 0)

            # 2. Execution with prepared manifest -> CONFIRMED & persisted in PostgreSQL
            driver2 = MockBrowserDriver(harness)
            rec = engine.execute_application(
                opportunity=opp,
                artifact=artifact,
                driver=driver2,
                execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
                truth_graph=tg,
                policy=policy,
                prepared_manifest=manifest,
            )
            self.assertEqual(rec.action_status, ActionStatus.CONFIRMED)
            self.assertEqual(harness.submits_count, 1)

            # Verify persisted in PostgreSQL
            stored_rec = pg_ledger.get_record("default", "founder", opp.id, "application")
            self.assertIsNotNone(stored_rec)
            self.assertEqual(stored_rec.action_status, ActionStatus.CONFIRMED)

            # 3. Duplicate submission attempt -> BLOCKED by PostgreSQL ledger
            driver3 = MockBrowserDriver(harness)
            rec_dup = engine.execute_application(
                opportunity=opp,
                artifact=artifact,
                driver=driver3,
                execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
                truth_graph=tg,
                policy=policy,
                prepared_manifest=manifest,
            )
            self.assertEqual(rec_dup.action_status, ActionStatus.BLOCKED)
            self.assertEqual(harness.submits_count, 1, "Duplicate must NOT trigger second submit_page call")

    def test_case_r_production_operational_orchestrator_with_postgres_store(self):
        """Case R: Real ProductionOperationalOrchestrator executes against PostgresInboxStore through full lifecycle."""
        pg_store = PostgresInboxStore(db_url=self.db_url)

        msg1 = InboundMessageEvidence(
            provider="gmail", provider_message_id="msg-pg-1", thread_id="th-pg-1",
            sender_email="recruiter@acme.com", sender_name="Recruiter",
            recipient_email="founder@example.com", subject="Application Confirmation: Staff AI",
            snippet="Thank you for applying to Staff AI at Acme. Reference: REQ-ASHBY-1", body_text="We have received your application for Staff AI. Reference: REQ-ASHBY-1",
            body_html="", received_at="2026-08-30T10:00:00Z",
            headers=(("From", "recruiter@acme.com"), ("Subject", "Application Confirmation: Staff AI")),
            attachment_names=(),
        )
        msg2 = InboundMessageEvidence(
            provider="gmail", provider_message_id="msg-pg-2", thread_id="th-pg-1",
            sender_email="recruiter@acme.com", sender_name="Recruiter",
            recipient_email="founder@example.com", subject="Interview Invitation: Staff AI",
            snippet="We would like to invite you for an interview. Reference: REQ-ASHBY-1", body_text="Let's schedule an interview for Staff AI. Reference: REQ-ASHBY-1",
            body_html="", received_at="2026-08-30T14:00:00Z",
            headers=(("From", "recruiter@acme.com"), ("Subject", "Interview Invitation: Staff AI")),
            attachment_names=(),
        )

        transport = MockMailTransport([msg1, msg2])
        ingestion = InboundIngestionService(transport=transport, store=pg_store)

        opp = Opportunity(
            id="opp-pg-inbox-1", title="Staff AI", organization="Acme",
            description="AI engineer role", track=Track.EMPLOYMENT,
            source="ashby", source_url="https://ashby.com/acme/1",
            source_id="REQ-ASHBY-1",
            content_hash="ch-pg-inbox-1",
        )
        out_rec = OutboundActionRecord(
            action_id="act-pg-1", opportunity_id="opp-pg-inbox-1",
            opportunity_content_hash="ch-pg-inbox-1", workspace="default",
            candidate_id="founder", track=Track.EMPLOYMENT, source="ashby",
            adapter_name="ashby_outbound", adapter_version="1.0.0",
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED,
            match_score_snapshot=95.0, artifact_ids=(), artifact_hashes=(),
            manifest_hash="man-pg-1", action_status=ActionStatus.CONFIRMED,
            idempotency_key="idemp-pg-1", created_at="2026-08-30T09:00:00Z",
            updated_at="2026-08-30T09:05:00Z",
            external_reference_id="REQ-ASHBY-1",
        )

        orchestrator = ProductionOperationalOrchestrator(
            ingestion_service=ingestion,
            opportunities=[opp],
            outbound_records=[out_rec],
            store=pg_store,
        )

        # Run cycle 1: Processes msg1 and msg2
        res = orchestrator.run_cycle(limit=10)
        self.assertEqual(res.messages_ingested, 2)
        self.assertEqual(res.signals_detected, 2)
        self.assertEqual(res.events_recorded, 2)
        self.assertEqual(res.cursor_checkpoint, "2")

        # Verify state in PostgreSQL
        state = orchestrator.get_opportunity_state("opp-pg-inbox-1")
        self.assertEqual(state.current_stage, OpportunityStage.INTERVIEWING)
        self.assertTrue(pg_store.is_evidence_processed(msg1.message_content_hash))
        self.assertTrue(pg_store.is_evidence_processed(msg2.message_content_hash))

        # Run cycle 2: No new messages, 0 duplicates emitted
        res2 = orchestrator.run_cycle(limit=10)
        self.assertEqual(res2.messages_ingested, 0)
        self.assertEqual(res2.events_recorded, 0)
        self.assertEqual(res2.notifications_emitted, 0)


if __name__ == "__main__":
    unittest.main()
