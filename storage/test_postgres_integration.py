import os
import unittest
import json
import uuid
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

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
    MatchEvaluationRecord,
    OpportunityFamilyRecord,
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

        migration_0002_tables = (
            "match_evaluations",
            "source_poll_runs",
            "founder_opportunity_views",
            "founder_triage_states",
        )

        # Test upgrade to head
        command.upgrade(alembic_cfg, "head")

        # Verify tables exist in postgres
        with self.engine.connect() as conn:
            res = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"))
            count = res.scalar()
            self.assertGreater(count, 5)

            res = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_name = ANY(:names)"),
                {"names": list(migration_0002_tables)},
            )
            self.assertEqual(res.scalar(), 4, "all four 0002 tables must exist at head")

        # Downgrade to 0001_baseline_schema: the four 0002 tables, and every
        # index/constraint belonging to them, must be gone.
        command.downgrade(alembic_cfg, "0001_baseline_schema")

        with self.engine.connect() as conn:
            res = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_name = ANY(:names)"),
                {"names": list(migration_0002_tables)},
            )
            self.assertEqual(res.scalar(), 0, "all four 0002 tables must be absent after downgrade to 0001")

            res = conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE "
                "indexname ILIKE '%match_evaluations%' OR indexname ILIKE '%source_poll_runs%' OR "
                "indexname ILIKE '%founder_opportunity_views%' OR indexname ILIKE '%founder_triage_states%'"
            ))
            self.assertEqual(res.fetchall(), [], "no orphan index belonging to the 0002 tables may survive downgrade")

            res = conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE "
                "conname ILIKE '%match_evaluations%' OR conname ILIKE '%source_poll_runs%' OR "
                "conname ILIKE '%founder_opportunity_views%' OR conname ILIKE '%founder_triage_states%'"
            ))
            self.assertEqual(res.fetchall(), [], "no orphan constraint belonging to the 0002 tables may survive downgrade")

        # Upgrade again: the four tables must come back.
        command.upgrade(alembic_cfg, "head")

        with self.engine.connect() as conn:
            res = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_name = ANY(:names)"),
                {"names": list(migration_0002_tables)},
            )
            self.assertEqual(res.scalar(), 4, "all four 0002 tables must exist again after re-upgrading to head")

    def test_d3_target_roles_filter_seed_reverts_to_rank_only(self):
        """A1S (BRIEF-FR-006 order A1S-seed): 0004's data migration reverts the
        `target_roles` filter's seeded `mode` from 0003's `label_only` (a
        council repair) back to `rank_only` (Overseer decision, FR-005 review
        §3.1), guarded on the row's current value so re-running `upgrade` at
        head is a data no-op and `downgrade` never clobbers a mode the founder
        set by hand to something else."""
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", self.db_url)

        def target_roles_row():
            with self.engine.connect() as conn:
                return conn.execute(
                    text(
                        "SELECT filter_id, mode FROM founder_filter_settings "
                        "WHERE filter_id = 'target_roles'"
                    )
                ).fetchone()

        # Seed a scratch DB through 0003 only -- its own upgrade() inserts the
        # `label_only` row for target_roles -- before 0004 ever runs.
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "0003_provenance_identity")
        row = target_roles_row()
        self.assertIsNotNone(row, "0003 must seed a target_roles row")
        self.assertEqual(tuple(row), ("target_roles", "label_only"))

        # A1S.1: alembic upgrade head -> rank_only.
        command.upgrade(alembic_cfg, "head")
        row = target_roles_row()
        self.assertEqual(tuple(row), ("target_roles", "rank_only"))

        # A1S.2: downgrade across the 0004 data migration -> label_only.
        # The current head is 0005, whose schema-only downgrade must not
        # reverse 0004's target_roles seed override by itself.
        command.downgrade(alembic_cfg, "0003_provenance_identity")
        row = target_roles_row()
        self.assertEqual(tuple(row), ("target_roles", "label_only"))

        # A1S.3: alembic upgrade head twice in a row -- second run is a
        # data no-op, the row stays rank_only, both calls exit 0 (no raise).
        command.upgrade(alembic_cfg, "head")
        row = target_roles_row()
        self.assertEqual(tuple(row), ("target_roles", "rank_only"))
        command.upgrade(alembic_cfg, "head")
        row = target_roles_row()
        self.assertEqual(tuple(row), ("target_roles", "rank_only"))

    def test_search_tsv_gin_index_exists_at_head(self):
        """BRIEF-FR-006 C2.3: `ix_opportunities_search_tsv` (migration
        `0004_founder_control`, frozen for this work order) is present on
        `opportunities` after `alembic upgrade head`."""
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", self.db_url)
        command.upgrade(alembic_cfg, "head")

        with self.engine.connect() as conn:
            names = {
                row[0]
                for row in conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'opportunities'")
                )
            }
        print(f"C2.3: pg_indexes for opportunities = {sorted(names)}")
        self.assertIn("ix_opportunities_search_tsv", names)

    def test_search_backfill_finds_pre_0004_rows(self):
        """Council review #3, finding 6: a row inserted while the schema was
        at `0003_provenance_identity` (before `search_tsv` existed) must be
        findable by full-text search after `alembic upgrade head` -- 0004's
        `upgrade()` must backfill `search_tsv` for pre-existing rows, not
        just add the column and index for rows written afterward."""
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", self.db_url)

        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "0003_provenance_identity")

        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO opportunities "
                    "(id, track, title, organization, description, source_id, source_url, content_hash) "
                    "VALUES (:id, :track, :title, :organization, :description, :source_id, :source_url, :content_hash)"
                ),
                {
                    "id": "OPP-PRE-0004",
                    "track": "EMPLOYMENT",
                    "title": "Distributed Systems Engineer",
                    "organization": "Alexandria Cloud Labs",
                    "description": "Build resilient distributed systems.",
                    "source_id": "greenhouse:alexandria-pre",
                    "source_url": "https://boards.greenhouse.io/alexandria/pre-0004",
                    "content_hash": "hash-pre-0004",
                },
            )

        command.upgrade(alembic_cfg, "head")

        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id FROM opportunities "
                    "WHERE search_tsv @@ plainto_tsquery('english', 'Distributed Systems') "
                    "AND id = :id"
                ),
                {"id": "OPP-PRE-0004"},
            ).fetchone()
        self.assertIsNotNone(
            row,
            "a row inserted at 0003 must be findable by full-text search "
            "after upgrading to head -- 0004 must backfill search_tsv for "
            "pre-existing rows, not leave it NULL",
        )

    def test_match_evaluations_unique_constraint_enforced_by_database(self):
        """(opportunity_id, truth_pack_hash) duplicates are rejected by PostgreSQL itself."""
        session = self.SessionFactory()
        try:
            opp = OpportunityRecord(
                id="opp-uq-1",
                track=Track.EMPLOYMENT.value,
                title="Backend Engineer",
                organization="Acme Corp",
                description="Build things.",
                source_id="src-1",
                source_url="https://example.com/job/1",
                content_hash="hash-1",
            )
            session.add(opp)
            session.commit()

            first = MatchEvaluationRecord(
                id="me-1",
                opportunity_id="opp-uq-1",
                truth_pack_hash="tph-1",
                qualification_decision="qualified",
                fit_score=88.5,
                dimension_scores_json="{}",
                reasons_json="[]",
                policy_version="v1",
                evaluated_at=datetime.now(timezone.utc),
            )
            session.add(first)
            session.commit()

            duplicate = MatchEvaluationRecord(
                id="me-2",
                opportunity_id="opp-uq-1",
                truth_pack_hash="tph-1",
                qualification_decision="uncertain",
                fit_score=50.0,
                dimension_scores_json="{}",
                reasons_json="[]",
                policy_version="v1",
                evaluated_at=datetime.now(timezone.utc),
            )
            session.add(duplicate)
            with self.assertRaises(IntegrityError):
                session.commit()
        finally:
            session.rollback()
            session.close()

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

            # Wipe database: drop the schema entirely, not just its rows.
            # TRUNCATE (the previous approach) removes rows but leaves the
            # schema -- including alembic_version, which lives outside
            # Base.metadata and so survives a TRUNCATE loop over
            # Base.metadata.sorted_tables untouched. With only a row-level
            # wipe, the alembic-head and restored-table-set assertions below
            # would pass even if restore_database() ran no migration at all
            # (e.g. if it were reverted to init_db()/create_all()) -- that is
            # exactly the regression D5 exists to prevent, so the wipe must
            # actually destroy the schema for those assertions to be
            # load-bearing.
            Base.metadata.drop_all(self.engine)
            with self.engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

            # Verify empty: no tables at all remain in the schema.
            with self.engine.connect() as conn:
                remaining_table_count = conn.execute(
                    text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
                ).scalar()
            self.assertEqual(remaining_table_count, 0)

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


    def test_case_s_worker_runner_end_to_end(self):
        """Case S: two concurrent WorkerRunners drain a mixed job queue against real PostgreSQL.

        Enqueues 3 noop jobs, 1 poll_source job targeting a read-disabled source
        (ashby:openai), and 1 always-failing job with max_retries=1. Both
        WorkerRunners are released from a shared barrier at the same instant (so
        the FOR UPDATE SKIP LOCKED race is actually exercised rather than one
        runner draining the queue before the other starts), and each tracked
        handler sleeps briefly so multiple jobs remain PENDING while both workers
        are active. Asserts: every job reaches a terminal state exactly once (no
        double-dispatch), both runners actually dispatched at least one job (so a
        silently-serialised run fails this test instead of passing it), the
        failing job reaches DEAD_LETTER, and the poll_source job records a
        refusal instead of fetching.
        """
        from collections import Counter

        from opportunity.registry import SourceRegistry
        from opportunity.transport import MockTransport
        from worker.handlers import default_handler_registry
        from worker.runner import WorkerRunner

        registry = SourceRegistry()
        self.assertFalse(
            registry.is_read_allowed("ashby:openai"),
            "ashby:openai must be read-disabled for this test to be meaningful",
        )

        refusals = []
        refusal_lock = threading.Lock()

        def refusal_sink(record):
            with refusal_lock:
                refusals.append(dict(record))

        # No fixture response is configured: ashby:openai must be refused before any
        # fetch is attempted, so MockTransport must never be asked to serve a response.
        mock_transport = MockTransport()

        base_handlers = default_handler_registry(
            registry=registry, transport=mock_transport, refusal_sink=refusal_sink
        )

        expected_markers = {"noop-1", "noop-2", "noop-3", "poll-ashby", "always-fail"}
        # (worker_id, marker) per dispatch -- attributes each dispatch to the runner
        # that actually claimed it, so we can assert both runners did real work and
        # that no job was ever dispatched more than once (to either runner).
        processed_records = []
        processed_lock = threading.Lock()
        stop_event = threading.Event()

        def track(inner_handler, owner_worker_id):
            def wrapped(payload):
                marker = payload.get("marker")
                with processed_lock:
                    processed_records.append((owner_worker_id, marker))
                    should_stop = expected_markers.issubset({m for _, m in processed_records})
                if should_stop:
                    stop_event.set()
                # Let the underlying handler's outcome (success or exception) propagate
                # unchanged so WorkerRunner still drives complete_job / fail_job.
                inner_handler(payload)

            return wrapped

        def always_failing(payload):
            raise RuntimeError("induced permanent failure")

        def handlers_for(owner_worker_id):
            return {
                "noop": track(base_handlers["noop"], owner_worker_id),
                "poll_source": track(base_handlers["poll_source"], owner_worker_id),
                "always_failing": track(always_failing, owner_worker_id),
            }

        enqueue_session = self.SessionFactory()
        enqueue_queue = BackgroundWorkerQueue(enqueue_session, worker_id="s-enqueue")
        job_ids = {
            "noop-1": enqueue_queue.enqueue_job("noop", {"marker": "noop-1"}),
            "noop-2": enqueue_queue.enqueue_job("noop", {"marker": "noop-2"}),
            "noop-3": enqueue_queue.enqueue_job("noop", {"marker": "noop-3"}),
            "poll-ashby": enqueue_queue.enqueue_job(
                "poll_source", {"source_id": "ashby:openai", "marker": "poll-ashby"}
            ),
            "always-fail": enqueue_queue.enqueue_job(
                "always_failing", {"marker": "always-fail"}, max_retries=1
            ),
        }
        enqueue_session.close()
        self.assertEqual(set(job_ids.keys()), expected_markers)

        runner1 = WorkerRunner(
            self.SessionFactory, handlers_for("s-runner-1"), worker_id="s-runner-1",
            poll_interval=0.05, stop_event=stop_event,
        )
        runner2 = WorkerRunner(
            self.SessionFactory, handlers_for("s-runner-2"), worker_id="s-runner-2",
            poll_interval=0.05, stop_event=stop_event,
        )

        # Deterministic two-runner synchronisation via claim_next_job's claim_hook
        # (worker/queue.py D1), replacing the previous thread-start barrier plus
        # in-handler sleep. The hook fires after a row has been selected and
        # mutated in-session but before commit, so gating the *first two* hook
        # invocations (system-wide, whichever runner reaches them first) on a
        # 2-party barrier forces those two claim_next_job calls to overlap: the
        # second, concurrent claim is forced to run its own SELECT ... FOR UPDATE
        # SKIP LOCKED against the first (still row-locked, uncommitted) claim, so
        # it necessarily picks a *different* job row. A single thread cannot
        # supply both barrier parties itself -- it stays blocked inside its own
        # claim_next_job call until a second party arrives -- so the two gated
        # claims are necessarily one from each runner. That guarantees both
        # runners claim distinct jobs before either is allowed to proceed, with no
        # in-flight sleep. This also makes the previous thread-start barrier
        # redundant: a thread blocked at the claim gate cannot race ahead and
        # drain the queue solo regardless of exactly when the other thread's
        # runner loop starts, so it is removed rather than kept alongside this.
        original_claim_next_job = BackgroundWorkerQueue.claim_next_job
        gate_barrier = threading.Barrier(2, timeout=10)
        gate_lock = threading.Lock()
        gate_remaining = [2]

        def _gated_claim_hook():
            with gate_lock:
                should_wait = gate_remaining[0] > 0
                if should_wait:
                    gate_remaining[0] -= 1
            if should_wait:
                gate_barrier.wait()

        def _synchronized_claim_next_job(self, lease_duration_seconds=60):
            return original_claim_next_job(
                self, lease_duration_seconds=lease_duration_seconds, claim_hook=_gated_claim_hook
            )

        BackgroundWorkerQueue.claim_next_job = _synchronized_claim_next_job
        try:
            def _drive(runner):
                runner.run_forever(max_jobs=5)

            t1 = threading.Thread(target=_drive, args=(runner1,))
            t2 = threading.Thread(target=_drive, args=(runner2,))
            t1.start()
            t2.start()
            t1.join(timeout=30)
            t2.join(timeout=30)
        finally:
            BackgroundWorkerQueue.claim_next_job = original_claim_next_job

        # If either runner raised before reaching its first gated claim (or the
        # barrier otherwise timed out), threading.Barrier.wait raises
        # BrokenBarrierError -- which run_forever's broad `except Exception` around
        # run_once swallows, so both runners would silently fall back to ungated,
        # merely-probabilistic claiming instead of the guaranteed overlap this test
        # is meant to prove. Assert the barrier was never broken so this test
        # cannot pass by accident via that silent degradation.
        self.assertFalse(
            gate_barrier.broken,
            "gate_barrier broke -- Case S's deterministic claim overlap was never "
            "actually exercised; this run degraded to the old probabilistic regime",
        )

        self.assertFalse(t1.is_alive(), "runner1 did not finish within the test timeout")
        self.assertFalse(t2.is_alive(), "runner2 did not finish within the test timeout")

        # Load-bearing concurrency assertion #1: the multiset of processed job markers
        # has no duplicates, i.e. no job was dispatched to a handler more than once even
        # though two WorkerRunners raced for the same queue via SKIP LOCKED.
        marker_counts = Counter(marker for _, marker in processed_records)
        self.assertEqual(
            set(marker_counts.keys()), expected_markers, "every enqueued job must be processed exactly once"
        )
        for marker, count in marker_counts.items():
            self.assertEqual(count, 1, f"job '{marker}' was dispatched {count} times, expected exactly 1")

        # Load-bearing concurrency assertion #2: both runners must actually have
        # claimed and dispatched at least one job. If SKIP LOCKED contention were not
        # really exercised (e.g. one runner silently drained the whole queue before
        # the other's first claim), this fails instead of the test passing vacuously.
        worker_id_counts = Counter(worker_id for worker_id, _ in processed_records)
        self.assertGreater(
            worker_id_counts.get("s-runner-1", 0), 0, f"runner1 processed no jobs: {worker_id_counts}"
        )
        self.assertGreater(
            worker_id_counts.get("s-runner-2", 0), 0, f"runner2 processed no jobs: {worker_id_counts}"
        )

        verify_session = self.SessionFactory()
        try:
            for marker, job_id in job_ids.items():
                job = verify_session.query(WorkerJobRecord).filter_by(id=job_id).first()
                self.assertIsNotNone(job, f"job '{marker}' ({job_id}) missing from database")
                if marker == "always-fail":
                    self.assertEqual(job.status, "DEAD_LETTER")
                    self.assertEqual(job.retry_count, 1)
                else:
                    self.assertEqual(job.status, "COMPLETED", f"job '{marker}' did not complete: {job.status}")
        finally:
            verify_session.close()

        # The read-disabled source must have been refused, not fetched.
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["source_id"], "ashby:openai")

    def test_case_u_poll_source_persists_idempotently(self):
        """Case U: poll_source persists a fixture batch idempotently against real PostgreSQL.

        Runs the ``poll_source`` handler twice for one read-allowed fixture
        source (``himalayas``, offline ``MockTransport`` fixture -- no network
        access, ever): asserts rows appear on the first run, the
        ``opportunities`` row count is unchanged on the second (identical)
        run, ``field_provenances`` rows exist for the persisted opportunity,
        and a third run with a mutated payload (same identity, different
        content) takes the re-verification path -- updating ``is_stale`` /
        ``reverified_at`` in place -- rather than inserting a duplicate row.
        """
        import json as _json

        from opportunity.registry import SourceRegistry
        from opportunity.transport import MockTransport, TransportResponse
        from worker.handlers import default_handler_registry

        registry = SourceRegistry()
        self.assertTrue(
            registry.is_read_allowed("himalayas"),
            "himalayas must be read-allowed for this test to be meaningful",
        )

        fixture_path = Path(__file__).resolve().parents[1] / "opportunity" / "fixtures" / "himalayas.json"
        fixture_payload = fixture_path.read_text(encoding="utf-8")

        mock_transport = MockTransport(
            {"himalayas": TransportResponse(status_code=200, body=fixture_payload, latency_ms=5)}
        )

        refusals = []
        handlers = default_handler_registry(
            registry=registry,
            transport=mock_transport,
            refusal_sink=refusals.append,
            session_factory=self.SessionFactory,
        )
        poll_source = handlers["poll_source"]

        # First run: rows must appear.
        poll_source({"source_id": "himalayas"})

        verify_session = self.SessionFactory()
        try:
            opp_rows = verify_session.query(OpportunityRecord).all()
            self.assertEqual(len(opp_rows), 1, "fixture has exactly one job posting")
            opp_id = opp_rows[0].id
            original_content_hash = opp_rows[0].content_hash
            self.assertFalse(opp_rows[0].is_stale)
            self.assertIsNone(opp_rows[0].reverified_at)

            prov_rows = (
                verify_session.query(FieldProvenanceRecord)
                .filter_by(opportunity_id=opp_id)
                .all()
            )
            self.assertGreater(len(prov_rows), 0, "field_provenances rows must exist for the persisted opportunity")
            original_prov_count = len(prov_rows)
        finally:
            verify_session.close()

        # Second run: identical payload -- row count must be unchanged (idempotent).
        poll_source({"source_id": "himalayas"})

        verify_session = self.SessionFactory()
        try:
            opp_count = verify_session.query(OpportunityRecord).count()
            self.assertEqual(opp_count, 1, "re-running the same batch must insert nothing")
            unchanged_row = verify_session.query(OpportunityRecord).filter_by(id=opp_id).first()
            self.assertEqual(unchanged_row.content_hash, original_content_hash)
            self.assertIsNone(unchanged_row.reverified_at, "an unchanged posting must not be re-verified")

            prov_count_after_run2 = (
                verify_session.query(FieldProvenanceRecord)
                .filter_by(opportunity_id=opp_id)
                .count()
            )
            self.assertEqual(
                prov_count_after_run2,
                original_prov_count,
                "an identical re-poll must not accumulate duplicate field_provenances rows "
                "(D5: (opportunity_id, field_name, record_checksum) is a natural-identity "
                "unique constraint, and re-persist must be idempotent against it)",
            )
        finally:
            verify_session.close()

        # Third run: mutated payload under the same identity -- must update in
        # place (re-verification path), not insert a duplicate.
        fixture_data = _json.loads(fixture_payload)
        fixture_data["jobs"][0]["title"] = "Principal Backend Architect (Updated)"
        mutated_payload = _json.dumps(fixture_data)
        mock_transport.set_response(
            "himalayas", TransportResponse(status_code=200, body=mutated_payload, latency_ms=5)
        )

        poll_source({"source_id": "himalayas"})

        verify_session = self.SessionFactory()
        try:
            opp_count = verify_session.query(OpportunityRecord).count()
            self.assertEqual(opp_count, 1, "a changed posting under the same identity must update, not duplicate")
            updated_row = verify_session.query(OpportunityRecord).filter_by(id=opp_id).first()
            self.assertIsNotNone(updated_row)
            self.assertEqual(updated_row.title, "Principal Backend Architect (Updated)")
            self.assertNotEqual(updated_row.content_hash, original_content_hash)
            self.assertFalse(updated_row.is_stale)
            self.assertIsNotNone(updated_row.reverified_at, "a changed posting must set reverified_at")

            prov_count_after_run3 = (
                verify_session.query(FieldProvenanceRecord)
                .filter_by(opportunity_id=opp_id)
                .count()
            )
            self.assertEqual(
                prov_count_after_run3,
                original_prov_count,
                "a changed posting under the same identity must replace field_provenances rows "
                "in place, not accumulate duplicates alongside the old ones",
            )
        finally:
            verify_session.close()

        self.assertEqual(refusals, [], "a read-allowed source must never record a refusal")


    def test_case_v_evaluate_new_persists_match_evaluations(self):
        """Case V: evaluate_new persists match_evaluations rows against real PostgreSQL.

        Persists two fixture opportunities through the sanctioned
        opportunity.persistence.persist_batch seam, then runs the
        evaluate_new worker handler with an injected truth pack (a
        pack_loader returning a canned LoadedPack -- private/ is never
        touched). Asserts one match_evaluations row per opportunity with a
        real qualification_decision, a fit_score on the 0-100 scale, and a
        real evaluated_at timestamp.

        Then changes the (injected) truth-pack hash and reruns evaluate_new:
        asserts a second row appears per opportunity under the new hash,
        while the first row's own stored fields (id, decision, fit_score,
        dimension_scores_json, evaluated_at) are read back unchanged -- so
        this actually distinguishes "inserted a second row" from "overwrote
        the first row and left only one row behind under the wrong hash".
        """
        from matching.test_qualification import create_test_graph, create_test_opportunity
        from opportunity.persistence import persist_batch
        from opportunity.pipeline import IngestionBatch
        from truth.pack import LoadedPack, PackValidationReport
        from worker.handlers import make_evaluate_new_handler

        opportunities = (
            create_test_opportunity(opp_id="case-v-opp-1", title="Senior Backend Engineer"),
            create_test_opportunity(opp_id="case-v-opp-2", title="Staff Platform Engineer"),
        )
        batch = IngestionBatch(
            batch_id="batch-case-v",
            run_id="run-case-v",
            ingested_at="2026-09-02",
            opportunities=opportunities,
            clusters=(),
            health_reports=(),
            total_raw_ingested=len(opportunities),
            total_unique_opportunities=len(opportunities),
            exact_duplicates_removed=0,
            cross_source_duplicates_clustered=0,
            ambiguous_duplicates_count=0,
            track_counts=(),
            eligibility_counts=(),
        )

        session = self.SessionFactory()
        try:
            repository = StorageRepository(session)
            persist_result = persist_batch(batch, repository)
            self.assertEqual(persist_result.inserted_count, 2, "both fixture opportunities must be freshly inserted")
        finally:
            session.close()

        truth_graph = create_test_graph()
        report = PackValidationReport(valid=True, section_counts=(("evidence", 1),), findings=())

        def _pack_loader_for(hash_value):
            loaded = LoadedPack(graph=truth_graph, report=report, truth_pack_hash=hash_value)
            return lambda path: loaded

        handler_v1 = make_evaluate_new_handler(
            session_factory=self.SessionFactory,
            pack_loader=_pack_loader_for("truth-pack-hash-v1"),
        )
        handler_v1({})

        verify_session = self.SessionFactory()
        try:
            rows_v1 = (
                verify_session.query(MatchEvaluationRecord)
                .filter_by(truth_pack_hash="truth-pack-hash-v1")
                .order_by(MatchEvaluationRecord.opportunity_id.asc())
                .all()
            )
            self.assertEqual(len(rows_v1), 2, "one match_evaluations row per opportunity under the first hash")
            for row in rows_v1:
                self.assertIn(row.qualification_decision, {"qualified", "ineligible", "uncertain"})
                self.assertGreaterEqual(row.fit_score, 0.0)
                self.assertLessEqual(row.fit_score, 100.0)
                self.assertIsNotNone(row.evaluated_at)

            first_row_snapshot = {
                "id": rows_v1[0].id,
                "opportunity_id": rows_v1[0].opportunity_id,
                "qualification_decision": rows_v1[0].qualification_decision,
                "fit_score": rows_v1[0].fit_score,
                "dimension_scores_json": rows_v1[0].dimension_scores_json,
                "evaluated_at": rows_v1[0].evaluated_at,
            }

            total_rows_after_v1 = verify_session.query(MatchEvaluationRecord).count()
            self.assertEqual(total_rows_after_v1, 2, "no rows must exist yet under any other hash")
        finally:
            verify_session.close()

        # Re-running evaluate_new under the SAME hash must not duplicate rows
        # (idempotent upsert on (opportunity_id, truth_pack_hash)).
        handler_v1({})
        verify_session = self.SessionFactory()
        try:
            unchanged_count = (
                verify_session.query(MatchEvaluationRecord)
                .filter_by(truth_pack_hash="truth-pack-hash-v1")
                .count()
            )
            self.assertEqual(unchanged_count, 2, "re-running evaluate_new under the same hash must not duplicate rows")
        finally:
            verify_session.close()

        # Now the founder's truth pack changes (new hash): evaluate_new must
        # add a second row per opportunity, and must leave the first hash's
        # rows completely untouched.
        handler_v2 = make_evaluate_new_handler(
            session_factory=self.SessionFactory,
            pack_loader=_pack_loader_for("truth-pack-hash-v2"),
        )
        handler_v2({})

        verify_session = self.SessionFactory()
        try:
            rows_v2 = (
                verify_session.query(MatchEvaluationRecord)
                .filter_by(truth_pack_hash="truth-pack-hash-v2")
                .all()
            )
            self.assertEqual(len(rows_v2), 2, "one new match_evaluations row per opportunity under the second hash")

            total_rows = verify_session.query(MatchEvaluationRecord).count()
            self.assertEqual(total_rows, 4, "the second hash must add rows, not replace the first hash's rows")

            first_row_reloaded = (
                verify_session.query(MatchEvaluationRecord)
                .filter_by(id=first_row_snapshot["id"])
                .first()
            )
            self.assertIsNotNone(first_row_reloaded, "the first hash's row must still exist by its original id")
            self.assertEqual(first_row_reloaded.opportunity_id, first_row_snapshot["opportunity_id"])
            self.assertEqual(first_row_reloaded.truth_pack_hash, "truth-pack-hash-v1")
            self.assertEqual(first_row_reloaded.qualification_decision, first_row_snapshot["qualification_decision"])
            self.assertEqual(first_row_reloaded.fit_score, first_row_snapshot["fit_score"])
            self.assertEqual(first_row_reloaded.dimension_scores_json, first_row_snapshot["dimension_scores_json"])
            self.assertEqual(first_row_reloaded.evaluated_at, first_row_snapshot["evaluated_at"])

            rows_v1_after = (
                verify_session.query(MatchEvaluationRecord)
                .filter_by(truth_pack_hash="truth-pack-hash-v1")
                .count()
            )
            self.assertEqual(rows_v1_after, 2, "the first hash's rows must still number exactly 2, untouched")
        finally:
            verify_session.close()
    def _race_two_claims(self, job_id, *, lease_duration_seconds=30):
        """Race two independent sessions' claim_next_job calls against one job,
        releasing both from a 2-party barrier at (as close to) the same instant so
        the underlying SELECT ... FOR UPDATE SKIP LOCKED contention is actually
        exercised rather than one call simply running to completion before the
        other starts. Returns the two results as claimed-job-id-or-None, in call
        order (r1, r2) -- not the ORM objects, which would be detached once this
        method closes both sessions below and thus unsafe for the caller to touch.
        """
        session1 = self.SessionFactory()
        session2 = self.SessionFactory()
        q1 = BackgroundWorkerQueue(session1, worker_id="race-1")
        q2 = BackgroundWorkerQueue(session2, worker_id="race-2")

        start_barrier = threading.Barrier(2, timeout=10)
        results = {}

        def _claim(q, key):
            start_barrier.wait()
            claimed = q.claim_next_job(lease_duration_seconds=lease_duration_seconds)
            results[key] = claimed.id if claimed is not None else None

        t1 = threading.Thread(target=_claim, args=(q1, "r1"))
        t2 = threading.Thread(target=_claim, args=(q2, "r2"))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertFalse(t1.is_alive(), "racer 1 did not finish within the test timeout")
        self.assertFalse(t2.is_alive(), "racer 2 did not finish within the test timeout")
        self.assertFalse(start_barrier.broken, "start_barrier broke -- the race was never actually exercised")

        session1.close()
        session2.close()
        return results["r1"], results["r2"]

    def test_case_t_stale_lease_reclaim_race(self):
        """Case T: two sessions race to reclaim one job whose lease has already
        expired -- simulating two workers both sweeping for a job left behind by a
        crashed third worker. SELECT ... FOR UPDATE SKIP LOCKED must guarantee
        exactly one winner even under real contention, and the winner's reclaim
        must increment retry_count exactly once (not twice, and not zero times).

        This is then extended (same test, second phase) to the dead-letter
        threshold race: with max_retries=1, a single reclaim exhausts the budget,
        so neither racer may be handed the job -- both must see None -- and the
        job must end up DEAD_LETTER with retry_count == 1, not RUNNING for either
        racer and not retried a second time.
        """
        # --- Phase 1: a plain reclaim race (max_retries well above the threshold). ---
        enqueue_session = self.SessionFactory()
        enqueue_queue = BackgroundWorkerQueue(enqueue_session, worker_id="t-enqueue")
        job_id = enqueue_queue.enqueue_job(
            "export_binary", {"artifact_id": "art-case-t-1"}, max_retries=5
        )
        enqueue_session.close()

        # Simulate a dead worker: claim the job once, then force the lease into the
        # past directly -- never calling complete_job/fail_job, exactly as a
        # process that died mid-handler would not.
        setup_session = self.SessionFactory()
        setup_queue = BackgroundWorkerQueue(setup_session, worker_id="t-dead-1")
        dead_claim = setup_queue.claim_next_job(lease_duration_seconds=1)
        self.assertIsNotNone(dead_claim)
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE worker_jobs SET lease_expires_at = :past WHERE id = :jid"),
                {"past": datetime.now(timezone.utc) - timedelta(seconds=10), "jid": job_id},
            )
        setup_session.close()

        r1, r2 = self._race_two_claims(job_id)

        winners = [r for r in (r1, r2) if r is not None]
        self.assertEqual(
            len(winners), 1, f"exactly one racer must reclaim the stale-leased job, got r1={r1!r} r2={r2!r}"
        )
        self.assertEqual(winners[0], job_id)

        verify_session = self.SessionFactory()
        try:
            job = verify_session.query(WorkerJobRecord).filter_by(id=job_id).first()
            self.assertIsNotNone(job)
            self.assertEqual(job.status, "RUNNING")
            self.assertEqual(job.retry_count, 1, "retry_count must be incremented exactly once by the race, not twice")
        finally:
            verify_session.close()

        # --- Phase 2: the dead-letter threshold race (max_retries == 1). ---
        enqueue_session2 = self.SessionFactory()
        enqueue_queue2 = BackgroundWorkerQueue(enqueue_session2, worker_id="t-enqueue-2")
        job_id_2 = enqueue_queue2.enqueue_job(
            "export_binary", {"artifact_id": "art-case-t-2"}, max_retries=1
        )
        enqueue_session2.close()

        setup_session2 = self.SessionFactory()
        setup_queue2 = BackgroundWorkerQueue(setup_session2, worker_id="t-dead-2")
        dead_claim_2 = setup_queue2.claim_next_job(lease_duration_seconds=1)
        self.assertIsNotNone(dead_claim_2)
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE worker_jobs SET lease_expires_at = :past WHERE id = :jid"),
                {"past": datetime.now(timezone.utc) - timedelta(seconds=10), "jid": job_id_2},
            )
        setup_session2.close()

        r1_dl, r2_dl = self._race_two_claims(job_id_2)

        self.assertIsNone(r1_dl, "a reclaim that exhausts max_retries must not be handed to either racer")
        self.assertIsNone(r2_dl, "a reclaim that exhausts max_retries must not be handed to either racer")

        verify_session2 = self.SessionFactory()
        try:
            job2 = verify_session2.query(WorkerJobRecord).filter_by(id=job_id_2).first()
            self.assertIsNotNone(job2)
            self.assertEqual(job2.status, "DEAD_LETTER")
            self.assertEqual(job2.retry_count, 1)
            self.assertIsNone(job2.lease_owner)
            self.assertIsNone(job2.lease_expires_at)
        finally:
            verify_session2.close()


class A1MFounderControlRoundTripTest(unittest.TestCase):
    """A1M (BRIEF-FR-006, migration 0004_founder_control) -- round-trip every
    new ``opportunities`` column through StorageRepository.save_opportunity /
    get_opportunity, including the null case for every nullable column."""

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
            raise unittest.SkipTest(f"PostgreSQL integration tests require real PostgreSQL backend, got: {cls.db_url}")

        cls.engine = get_engine(cls.db_url)
        cls.SessionFactory = get_session_factory(cls.engine)

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", cls.db_url)
        command.upgrade(alembic_cfg, "head")

    def setUp(self):
        with self.engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))

    def _base_opp_data(self, opp_id: str) -> dict:
        return {
            "id": opp_id,
            "track": "employment",
            "title": "Backend Engineer",
            "organization": "Acme Corp",
            "description": "Build things.",
            "source_id": "src-1",
            "source_url": "https://example.com/job/1",
            "content_hash": f"hash-{opp_id}",
        }

    def test_every_new_column_round_trips_with_values(self):
        session = self.SessionFactory()
        try:
            repository = StorageRepository(session)
            opp_data = self._base_opp_data("opp-a1m-full")
            opp_data.update({
                "work_mode": "hybrid",
                "work_mode_source": "extracted",
                "location_country": "EG",
                "location_city": "Cairo",
                "location_region": "MENA",
                "remote_scope": "regional",
                "remote_scope_regions": json.dumps(["EG", "AE"]),
                "employment_type": "full_time",
                "seniority_level": "senior",
                "compensation_min": 50000,
                "compensation_max": 80000,
                "compensation_currency": "USD",
                "compensation_period": "annual",
                "title_family": "engineering",
                "title_level": "senior",
                "family_key": "acme:backend-engineer",
                "search_tsv": "'backend':1 'engineer':2",
            })
            repository.save_opportunity(opp_data, provenances=[])

            fetched = repository.get_opportunity("opp-a1m-full")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.work_mode, "hybrid")
            self.assertEqual(fetched.work_mode_source, "extracted")
            self.assertEqual(fetched.location_country, "EG")
            self.assertEqual(fetched.location_city, "Cairo")
            self.assertEqual(fetched.location_region, "MENA")
            self.assertEqual(fetched.remote_scope, "regional")
            self.assertEqual(fetched.remote_scope_regions, json.dumps(["EG", "AE"]))
            self.assertEqual(fetched.employment_type, "full_time")
            self.assertEqual(fetched.seniority_level, "senior")
            self.assertEqual(fetched.compensation_min, 50000)
            self.assertEqual(fetched.compensation_max, 80000)
            self.assertEqual(fetched.compensation_currency, "USD")
            self.assertEqual(fetched.compensation_period, "annual")
            self.assertEqual(fetched.title_family, "engineering")
            self.assertEqual(fetched.title_level, "senior")
            self.assertEqual(fetched.family_key, "acme:backend-engineer")
            self.assertIsNotNone(fetched.search_tsv)
        finally:
            session.close()

    def test_every_nullable_new_column_round_trips_with_null(self):
        session = self.SessionFactory()
        try:
            repository = StorageRepository(session)
            # Deliberately omit every new column: opp_data.get(...) defaults
            # apply (the four NOT NULL columns fall back to "unspecified";
            # every nullable new column is left unset -> None).
            opp_data = self._base_opp_data("opp-a1m-null")
            repository.save_opportunity(opp_data, provenances=[])

            fetched = repository.get_opportunity("opp-a1m-null")
            self.assertIsNotNone(fetched)
            # NOT NULL columns: default applied, never None.
            self.assertEqual(fetched.work_mode, "unspecified")
            self.assertEqual(fetched.remote_scope, "unspecified")
            self.assertEqual(fetched.employment_type, "unspecified")
            self.assertEqual(fetched.seniority_level, "unspecified")
            # Nullable columns: the null case.
            self.assertIsNone(fetched.work_mode_source)
            self.assertIsNone(fetched.location_country)
            self.assertIsNone(fetched.location_city)
            self.assertIsNone(fetched.location_region)
            self.assertIsNone(fetched.remote_scope_regions)
            self.assertIsNone(fetched.compensation_min)
            self.assertIsNone(fetched.compensation_max)
            self.assertIsNone(fetched.compensation_currency)
            self.assertIsNone(fetched.compensation_period)
            self.assertIsNone(fetched.title_family)
            self.assertIsNone(fetched.title_level)
            self.assertIsNone(fetched.family_key)
            # BRIEF-FR-006 C2 (search): superseded assertion -- at A1M time
            # `search_tsv` genuinely stayed NULL because nothing populated
            # it yet. C2's whole job is to populate it on every
            # `save_opportunity` call (see `storage.repository.
            # _refresh_search_tsv`), so a row with real title/organization/
            # description text -- exactly what `_base_opp_data` supplies --
            # must come back indexed, not NULL, even though every *other*
            # new column here was deliberately left unset.
            self.assertIsNotNone(fetched.search_tsv)
        finally:
            session.close()

    def test_new_tables_round_trip_via_orm(self):
        """Direct ORM round-trip for the four genuinely-new A1M tables
        (opportunity_families, founder_facets, founder_saved_views,
        artifact_cache) -- StorageRepository has no dedicated methods for
        these yet (out of this work order's scope), so this exercises the
        ORM models/migration directly."""
        from storage.models import (
            ArtifactCacheRecord,
            FounderFacetRecord,
            FounderSavedViewRecord,
            OpportunityFamilyRecord,
        )

        session = self.SessionFactory()
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            session.add(OpportunityFamilyRecord(
                family_key="acme:backend-engineer", employer="Acme Corp",
                normalized_title="Backend Engineer", member_count=3,
                best_member_id="opp-a1m-full", split_out=False, updated_at=now,
            ))
            session.add(FounderFacetRecord(
                facet_id="work_mode", mode="include", values_json=json.dumps(["remote"]), updated_at=now,
            ))
            session.add(FounderSavedViewRecord(
                id="view-1", name="Remote Only", facets_json=json.dumps({}),
                search_query="python", is_default=True, created_at=now, updated_at=now,
            ))
            session.add(ArtifactCacheRecord(
                cache_key="cache-1", opportunity_id="opp-a1m-full",
                truth_pack_hash="tph-1", template_id="tmpl-1", artifact_kind="resume",
                content_type="application/pdf", payload=b"%PDF-fake", created_at=now,
            ))
            session.commit()

            fam = session.query(OpportunityFamilyRecord).filter_by(family_key="acme:backend-engineer").first()
            self.assertIsNotNone(fam)
            self.assertEqual(fam.employer, "Acme Corp")
            self.assertTrue(fam.split_out is False)

            facet = session.query(FounderFacetRecord).filter_by(facet_id="work_mode").first()
            self.assertIsNotNone(facet)
            self.assertEqual(facet.mode, "include")

            sv = session.query(FounderSavedViewRecord).filter_by(id="view-1").first()
            self.assertIsNotNone(sv)
            self.assertTrue(sv.is_default is True)

            art = session.query(ArtifactCacheRecord).filter_by(cache_key="cache-1").first()
            self.assertIsNotNone(art)
            self.assertEqual(bytes(art.payload), b"%PDF-fake")
        finally:
            session.close()

    def test_case_t_family_upsert_and_split_out_round_trip(self):
        """A2.6 (BRIEF-FR-006 clustering): StorageRepository's
        opportunity_families methods -- upsert_family is idempotent and
        preserves a founder's split_out choice across a re-cluster, and
        set_family_split_out round-trips: collapse -> split -> collapse."""
        session = self.SessionFactory()
        repo = StorageRepository(session)
        try:
            fam = repo.upsert_family(
                family_key="cf:senior-customer-engineer",
                employer="Cloudflare",
                normalized_title="customer_solutions_engineering:senior",
                member_count=14,
                best_member_id="cf-sce-05",
            )
            self.assertEqual(fam.member_count, 14)
            self.assertFalse(fam.split_out)
            row_count_after_insert = session.query(OpportunityFamilyRecord).count()
            self.assertEqual(row_count_after_insert, 1, "collapsed: one row per family")

            # Step 1 (collapse, baseline): fetched family is collapsed.
            fetched = repo.get_family("cf:senior-customer-engineer")
            self.assertIsNotNone(fetched)
            self.assertFalse(fetched.split_out)

            # Step 2 (split): set_family_split_out(True) persists the toggle.
            split = repo.set_family_split_out("cf:senior-customer-engineer", True)
            self.assertIsNotNone(split)
            self.assertTrue(split.split_out)
            after_split = repo.get_family("cf:senior-customer-engineer")
            self.assertTrue(after_split.split_out)
            row_count_after_split = session.query(OpportunityFamilyRecord).count()
            self.assertEqual(row_count_after_split, 1, "split_out toggles a flag, never adds/removes family rows")

            # A re-cluster (upsert with fresh member_count/best_member_id) must
            # not silently undo the founder's split_out choice.
            reupserted = repo.upsert_family(
                family_key="cf:senior-customer-engineer",
                employer="Cloudflare",
                normalized_title="customer_solutions_engineering:senior",
                member_count=15,
                best_member_id="cf-sce-06",
            )
            self.assertEqual(reupserted.member_count, 15)
            self.assertTrue(reupserted.split_out, "re-clustering must preserve an existing split_out choice")

            # Step 3 (collapse again): set_family_split_out(False) reverses it.
            collapsed_again = repo.set_family_split_out("cf:senior-customer-engineer", False)
            self.assertFalse(collapsed_again.split_out)
            after_collapse = repo.get_family("cf:senior-customer-engineer")
            self.assertFalse(after_collapse.split_out)
            row_count_after_collapse = session.query(OpportunityFamilyRecord).count()
            self.assertEqual(row_count_after_collapse, 1)

            print(
                "A2.6 split_out round-trip row counts: "
                f"after_insert={row_count_after_insert} after_split={row_count_after_split} "
                f"after_collapse={row_count_after_collapse}"
            )

            # set_family_split_out on a non-existent family: no write, returns None.
            missing = repo.set_family_split_out("no-such-family", True)
            self.assertIsNone(missing)

            families = repo.list_families()
            self.assertEqual(len(families), 1)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
