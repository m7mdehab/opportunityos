"""PostgreSQL-backed worker queue durability and durable scheduling integration tests.

Proves real PostgreSQL transactional queue and durable scheduling guarantees:
- Concurrent worker claims with SKIP LOCKED: verify two workers claiming simultaneously never get the same job;
- Lease expiration and recovery: verify a crashed worker's job becomes reclaimable after lease expiry;
- Dead-letter handling: verify a job exceeding max retries moves to dead-letter state;
- Guarded completion: verify a stale worker cannot mark a job completed after its lease expired and another worker claimed it;
- Scheduler deduplication: verify duplicate job enqueue is idempotent and suppressed.

Plus 10 durable scheduling & maintenance acceptance tests (FR-007 Section G):
- TEST 1: Cadence survives restart
- TEST 2: Due source survives restart
- TEST 3: No warm-up storm
- TEST 4: Concurrent schedulers
- TEST 5: Persisted cooldown
- TEST 6: Cooldown expiry
- TEST 7: Scheduler/worker crash recovery
- TEST 8: Poll Now HTTP
- TEST 9: Async projection maintenance
- TEST 10: Duplicate maintenance

Skips gracefully outside CI when a real PostgreSQL database is not available.
In CI, executes against live PostgreSQL with ZERO skips.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from starlette.testclient import TestClient

from api.app import create_app
from api.settings import Settings
from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory
from storage.feed_projection import FeedProjectionRecord
from storage.models import (
    Base,
    FounderFacetRecord,
    FounderFilterSettingRecord,
    MatchEvaluationRecord,
    OpportunityRecord,
    SourcePollRunRecord,
    SourceScheduleRecord,
    WorkerJobRecord,
)
from truth.pack import load_founder_pack
from worker.handlers import _update_source_schedule, default_handler_registry
from worker.queue import BackgroundWorkerQueue
from worker.runner import WorkerRunner
from worker.scheduler import PollScheduler, enqueue_due_sources

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PACK_PATH = REPO_ROOT / "docs" / "templates" / "truth_pack.template.yaml"


def _get_pg_db_url() -> str | None:
    for var in ("CLOUD_DATABASE_URL", "OPPORTUNITYOS_DB_URL"):
        url = os.environ.get(var, "").strip()
        if url.startswith("postgresql"):
            return url
    return None


def _should_skip() -> bool:
    if os.environ.get("CI"):
        return False
    return _get_pg_db_url() is None


@unittest.skipIf(
    _should_skip(),
    "Real PostgreSQL database URL required for postgres queue durability tests (skipped outside CI when DB not configured)",
)
class TestPostgresQueueDurability(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db_url = _get_pg_db_url()
        if cls.db_url is None:
            raise AssertionError(
                "PostgreSQL database URL (CLOUD_DATABASE_URL or OPPORTUNITYOS_DB_URL) "
                "required for postgres queue durability tests"
            )
        cls.engine = get_engine(cls.db_url)
        Base.metadata.create_all(cls.engine)
        cls.session_factory = get_session_factory(cls.engine)

        cls.tmp_dir = tempfile.mkdtemp()
        cls.valid_pack_path = os.path.join(cls.tmp_dir, "truth_pack.yaml")
        shutil.copyfile(TEMPLATE_PACK_PATH, cls.valid_pack_path)
        cls.loaded_pack = load_founder_pack(cls.valid_pack_path)
        cls.truth_pack_hash = cls.loaded_pack.truth_pack_hash

        cls.test_founder_password = "test_pw_" + secrets.token_urlsafe(16)
        cls.test_session_secret = "test_sec_" + secrets.token_urlsafe(32)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "tmp_dir") and os.path.isdir(cls.tmp_dir):
            shutil.rmtree(cls.tmp_dir, ignore_errors=True)
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def setUp(self) -> None:
        if os.environ.get("CI") and _get_pg_db_url() is None:
            self.fail("CI environment requires real PostgreSQL database for worker durability suite")
        self.test_job_ids: list[str] = []
        self._apps_to_dispose = []
        session = self.session_factory()
        try:
            session.query(WorkerJobRecord).delete(synchronize_session=False)
            session.query(SourceScheduleRecord).delete(synchronize_session=False)
            session.query(SourcePollRunRecord).delete(synchronize_session=False)
            session.query(FeedProjectionRecord).delete(synchronize_session=False)
            session.query(MatchEvaluationRecord).delete(synchronize_session=False)
            session.query(OpportunityRecord).delete(synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def tearDown(self) -> None:
        for app in self._apps_to_dispose:
            try:
                app.state.engine.dispose()
            except Exception:
                pass
        self._apps_to_dispose = []

        session = self.session_factory()
        try:
            if self.test_job_ids:
                session.query(WorkerJobRecord).filter(
                    WorkerJobRecord.id.in_(self.test_job_ids)
                ).delete(synchronize_session=False)
            session.query(SourceScheduleRecord).delete(synchronize_session=False)
            session.query(FeedProjectionRecord).delete(synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def _enqueue(
        self,
        queue: BackgroundWorkerQueue,
        job_type: str = "test_pg_task",
        payload: dict | None = None,
        max_retries: int = 3,
    ) -> str:
        job_id = queue.enqueue_job(
            job_type,
            payload or {"token": uuid.uuid4().hex},
            max_retries=max_retries,
        )
        self.test_job_ids.append(job_id)
        return job_id

    def _make_app(self):
        settings = Settings(
            db_url=self.db_url,
            founder_password=self.test_founder_password,
            session_secret=self.test_session_secret,
            truth_pack_path=self.valid_pack_path,
        )
        app = create_app(settings=settings)
        self._apps_to_dispose.append(app)
        return app

    def _logged_in_client(self, app) -> TestClient:
        client = TestClient(app)
        res = client.post("/api/auth/login", json={"password": self.test_founder_password})
        self.assertEqual(res.status_code, 200, res.text)
        return client

    # -------------------------------------------------------------------------
    # Baseline Queue Durability Tests
    # -------------------------------------------------------------------------

    def test_concurrent_worker_claims_skip_locked(self) -> None:
        """Proves two concurrent PostgreSQL sessions claiming with SKIP LOCKED never collide on the same job."""
        session_setup = self.session_factory()
        try:
            q_setup = BackgroundWorkerQueue(session_setup)
            job_ids = [self._enqueue(q_setup, payload={"idx": i}) for i in range(6)]
        finally:
            session_setup.close()

        barrier = threading.Barrier(2, timeout=10.0)
        gate_lock = threading.Lock()
        remaining_syncs = [2]

        def sync_hook():
            with gate_lock:
                should_wait = remaining_syncs[0] > 0
                if should_wait:
                    remaining_syncs[0] -= 1
            if should_wait:
                barrier.wait()

        worker1_claimed: list[str] = []
        worker2_claimed: list[str] = []

        def worker_drain(worker_id: str, dest: list[str]):
            sess = self.session_factory()
            try:
                q = BackgroundWorkerQueue(sess, worker_id=worker_id)
                for _ in range(3):
                    job = q.claim_next_job(lease_duration_seconds=60, claim_hook=sync_hook)
                    if job:
                        dest.append(job.id)
            finally:
                sess.close()

        t1 = threading.Thread(target=worker_drain, args=("pg-worker-1", worker1_claimed))
        t2 = threading.Thread(target=worker_drain, args=("pg-worker-2", worker2_claimed))

        t1.start()
        t2.start()
        t1.join(timeout=15.0)
        t2.join(timeout=15.0)

        self.assertFalse(barrier.broken, "Deterministic SKIP LOCKED claim gate timed out or broke")
        self.assertFalse(t1.is_alive(), "Worker 1 did not complete in time")
        self.assertFalse(t2.is_alive(), "Worker 2 did not complete in time")

        all_claimed = worker1_claimed + worker2_claimed
        self.assertEqual(len(all_claimed), len(set(all_claimed)), "No job was claimed by both workers")
        self.assertEqual(set(all_claimed), set(job_ids), "All 6 jobs were claimed across the two workers")
        self.assertTrue(len(worker1_claimed) > 0 and len(worker2_claimed) > 0, "Both workers claimed jobs concurrently")

    def test_lease_expiration_and_recovery(self) -> None:
        """When a worker process crashes, its expired lease is safely reclaimed with retry_count increment."""
        session1 = self.session_factory()
        session2 = self.session_factory()
        try:
            q1 = BackgroundWorkerQueue(session1, worker_id="crashed-pg-worker")
            job_id = self._enqueue(q1, max_retries=3)

            claimed1 = q1.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(claimed1)
            self.assertEqual(job_id, claimed1.id)
            self.assertEqual("RUNNING", claimed1.status)
            self.assertEqual("crashed-pg-worker", claimed1.lease_owner)

            session1.close()

            q2 = BackgroundWorkerQueue(session2, worker_id="healthy-pg-worker")
            reclaimed = q2.claim_next_job(lease_duration_seconds=60)

            self.assertIsNotNone(reclaimed)
            self.assertEqual(job_id, reclaimed.id)
            self.assertEqual("RUNNING", reclaimed.status)
            self.assertEqual("healthy-pg-worker", reclaimed.lease_owner)
            self.assertEqual(1, reclaimed.retry_count)
        finally:
            session2.close()

    def test_dead_letter_handling(self) -> None:
        """A job repeatedly dying until reaching max_retries transitions into DEAD_LETTER state."""
        session = self.session_factory()
        try:
            q = BackgroundWorkerQueue(session, worker_id="flaky-worker-1")
            job_id = self._enqueue(q, max_retries=2)

            c1 = q.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(c1)
            self.assertEqual(0, c1.retry_count)

            q2 = BackgroundWorkerQueue(session, worker_id="flaky-worker-2")
            c2 = q2.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(c2)
            self.assertEqual(1, c2.retry_count)

            q3 = BackgroundWorkerQueue(session, worker_id="sweeper-worker")
            c3 = q3.claim_next_job(lease_duration_seconds=60)
            self.assertIsNone(c3, "Dead-lettered job must not be returned for execution")

            job_row = session.query(WorkerJobRecord).filter(WorkerJobRecord.id == job_id).one()
            self.assertEqual("DEAD_LETTER", job_row.status)
            self.assertIsNone(job_row.lease_owner)
            self.assertIsNone(job_row.lease_expires_at)
            self.assertEqual(2, job_row.retry_count)
            self.assertIn("retry_count 2 reached max_retries 2", job_row.error_message)
        finally:
            session.close()

    def test_guarded_completion_rejects_stale_worker(self) -> None:
        """A worker whose lease expired cannot mark the job complete after another worker took over."""
        session1 = self.session_factory()
        session2 = self.session_factory()
        try:
            q1 = BackgroundWorkerQueue(session1, worker_id="stale-worker-1")
            job_id = self._enqueue(q1, max_retries=3)

            c1 = q1.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(c1)

            q2 = BackgroundWorkerQueue(session2, worker_id="active-worker-2")
            c2 = q2.claim_next_job(lease_duration_seconds=60)
            self.assertIsNotNone(c2)
            self.assertEqual(job_id, c2.id)
            self.assertEqual("active-worker-2", c2.lease_owner)

            success = q1.complete_job(job_id)
            self.assertFalse(success, "Guarded UPDATE must return False when lease was lost")

            refreshed = session2.query(WorkerJobRecord).filter(WorkerJobRecord.id == job_id).one()
            self.assertEqual("RUNNING", refreshed.status)
            self.assertEqual("active-worker-2", refreshed.lease_owner)

            success2 = q2.complete_job(job_id)
            self.assertTrue(success2)

            refreshed2 = session2.query(WorkerJobRecord).filter(WorkerJobRecord.id == job_id).one()
            self.assertEqual("COMPLETED", refreshed2.status)
            self.assertIsNone(refreshed2.lease_owner)
        finally:
            session1.close()
            session2.close()

    def test_scheduler_deduplication(self) -> None:
        """PollScheduler does not enqueue duplicate active jobs for the same source."""
        session = self.session_factory()
        try:
            scheduler = PollScheduler(self.session_factory, interval_hours=1.0)
            q = BackgroundWorkerQueue(session)
            job_id = self._enqueue(q, job_type="poll_source", payload={"source_id": "ted", "feed_id": "all"})

            enqueued = scheduler.run_once()
            for eid in enqueued:
                self.test_job_ids.append(eid)
            active_ted_jobs = session.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.status.in_(["PENDING", "RETRY", "RUNNING"]),
            ).all()
            ted_count = sum(1 for j in active_ted_jobs if json.loads(j.payload_json).get("source_id") == "ted")
            self.assertEqual(1, ted_count, "Scheduler must not create duplicate active jobs for the same source")
        finally:
            session.close()

    # -------------------------------------------------------------------------
    # FR-007 Section G Durable Scheduling & Maintenance Acceptance Tests
    # -------------------------------------------------------------------------

    def test_1_cadence_survives_restart(self) -> None:
        """TEST 1: Cadence survives restart: Record existing poll history, shut down

        scheduler/worker, instantiate fresh instances; verify next_due_at is
        preserved in PostgreSQL and zero jobs are enqueued before the due time.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        future_due = now + timedelta(hours=5)

        session = self.session_factory()
        try:
            sched = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                last_attempt_at=now - timedelta(hours=1),
                last_success_at=now - timedelta(hours=1),
                next_due_at=future_due,
                created_at=now,
                updated_at=now,
            )
            session.add(sched)
            session.commit()
        finally:
            session.close()

        # Simulate fresh process restart
        fresh_scheduler = PollScheduler(self.session_factory, clock=lambda: now)
        enqueued_ids = fresh_scheduler.run_once()
        self.test_job_ids.extend(enqueued_ids)

        # Remoteok is not due; verify it was not enqueued
        session_check = self.session_factory()
        try:
            jobs = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.id.in_(enqueued_ids) if enqueued_ids else False,
            ).all()
            remoteok_jobs = [j for j in jobs if json.loads(j.payload_json).get("source_id") == "remoteok"]
            self.assertEqual(len(remoteok_jobs), 0, "Not-due source must not be enqueued on restart")

            record = session_check.query(SourceScheduleRecord).filter_by(source_id="remoteok").one()
            self.assertEqual(record.next_due_at, future_due, "next_due_at must survive restart intact")
        finally:
            session_check.close()

    def test_2_due_source_survives_restart(self) -> None:
        """TEST 2: Due source survives restart: Record history older than cadence,

        shut down, start fresh instances; verify exactly the due source is enqueued once.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        past_due = now - timedelta(minutes=15)
        future_due = now + timedelta(hours=3)

        session = self.session_factory()
        try:
            sched_due = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                last_attempt_at=now - timedelta(hours=7),
                last_success_at=now - timedelta(hours=7),
                next_due_at=past_due,
                created_at=now - timedelta(hours=7),
                updated_at=now - timedelta(hours=7),
            )
            sched_not_due = SourceScheduleRecord(
                source_id="himalayas",
                cadence_hours=6.0,
                last_attempt_at=now - timedelta(hours=3),
                last_success_at=now - timedelta(hours=3),
                next_due_at=future_due,
                created_at=now - timedelta(hours=3),
                updated_at=now - timedelta(hours=3),
            )
            session.add_all([sched_due, sched_not_due])
            session.commit()
        finally:
            session.close()

        # Simulate process restart with fresh scheduler instance
        fresh_scheduler = PollScheduler(self.session_factory, clock=lambda: now)
        enqueued_ids = fresh_scheduler.run_once()
        self.test_job_ids.extend(enqueued_ids)

        session_check = self.session_factory()
        try:
            jobs = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.id.in_(enqueued_ids),
            ).all()
            enqueued_sources = [json.loads(j.payload_json).get("source_id") for j in jobs]
            self.assertIn("remoteok", enqueued_sources, "Due source must be enqueued on fresh scheduler startup")
            self.assertNotIn("himalayas", enqueued_sources, "Non-due source must not be enqueued")

            # Verify next_due_at was updated to future
            remoteok_sched = session_check.query(SourceScheduleRecord).filter_by(source_id="remoteok").one()
            self.assertGreater(remoteok_sched.next_due_at, now, "Enqueued source next_due_at must advance")
        finally:
            session_check.close()

    def test_3_no_warmup_storm(self) -> None:
        """TEST 3: No warm-up storm: Seed mixed population (due, not-due, cooling-down, disabled);

        start fresh scheduler; assert only the due subset is enqueued.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        session = self.session_factory()
        try:
            # Due source
            sched_due = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                next_due_at=now - timedelta(minutes=5),
                created_at=now,
                updated_at=now,
            )
            # Not due source
            sched_not_due = SourceScheduleRecord(
                source_id="himalayas",
                cadence_hours=6.0,
                next_due_at=now + timedelta(hours=2),
                created_at=now,
                updated_at=now,
            )
            # Cooling down source
            sched_cooling = SourceScheduleRecord(
                source_id="jobicy",
                cadence_hours=6.0,
                next_due_at=now - timedelta(hours=1),
                cooldown_until=now + timedelta(hours=12),
                created_at=now,
                updated_at=now,
            )
            session.add_all([sched_due, sched_not_due, sched_cooling])
            session.commit()
        finally:
            session.close()

        fresh_scheduler = PollScheduler(self.session_factory, clock=lambda: now)
        enqueued_ids = fresh_scheduler.run_once()
        self.test_job_ids.extend(enqueued_ids)

        session_check = self.session_factory()
        try:
            jobs = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.id.in_(enqueued_ids),
            ).all()
            enqueued_sources = [json.loads(j.payload_json).get("source_id") for j in jobs]
            self.assertIn("remoteok", enqueued_sources)
            self.assertNotIn("himalayas", enqueued_sources)
            self.assertNotIn("jobicy", enqueued_sources)
            # Verify read_disabled sources from registry are never enqueued
            reg = SourceRegistry()
            read_disabled = [s for s in reg._sources if not reg.is_read_allowed(s)]
            for s in read_disabled:
                self.assertNotIn(s, enqueued_sources)
        finally:
            session_check.close()

    def test_4_concurrent_schedulers(self) -> None:
        """TEST 4: Concurrent schedulers: Run two scheduler ticks simultaneously on the same DB;

        verify FOR UPDATE SKIP LOCKED / unique constraints prevent duplicate job enqueue.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        session = self.session_factory()
        try:
            sched = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                next_due_at=now - timedelta(minutes=10),
                created_at=now,
                updated_at=now,
            )
            session.add(sched)
            session.commit()
        finally:
            session.close()

        sched1 = PollScheduler(self.session_factory, clock=lambda: now)
        sched2 = PollScheduler(self.session_factory, clock=lambda: now)

        res1: list[str] = []
        res2: list[str] = []

        barrier = threading.Barrier(2)

        def tick1():
            barrier.wait()
            res1.extend(sched1.run_once())

        def tick2():
            barrier.wait()
            res2.extend(sched2.run_once())

        t1 = threading.Thread(target=tick1)
        t2 = threading.Thread(target=tick2)
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        all_enqueued = res1 + res2
        self.test_job_ids.extend(all_enqueued)

        session_check = self.session_factory()
        try:
            remoteok_jobs = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.status.in_(["PENDING", "RETRY", "RUNNING"]),
            ).all()
            matched = [j for j in remoteok_jobs if json.loads(j.payload_json).get("source_id") == "remoteok"]
            self.assertEqual(len(matched), 1, "Concurrent schedulers must enqueue exactly one job for the due source")
        finally:
            session_check.close()

    def test_5_persisted_cooldown(self) -> None:
        """TEST 5: Persisted cooldown: Record 403 / BLOCKED_POLL_STATUS; restart;

        verify cooldown_until remains active and source is suppressed.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        future_cooldown = now + timedelta(hours=20)

        session = self.session_factory()
        try:
            sched = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                last_status="blocked_by_policy",
                cooldown_until=future_cooldown,
                next_due_at=now - timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
            session.add(sched)
            session.commit()
        finally:
            session.close()

        fresh_scheduler = PollScheduler(self.session_factory, clock=lambda: now)
        enqueued_ids = fresh_scheduler.run_once()
        self.test_job_ids.extend(enqueued_ids)

        session_check = self.session_factory()
        try:
            jobs = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.id.in_(enqueued_ids) if enqueued_ids else False,
            ).all()
            remoteok_jobs = [j for j in jobs if json.loads(j.payload_json).get("source_id") == "remoteok"]
            self.assertEqual(len(remoteok_jobs), 0, "Cooling-down source must be suppressed on restart")

            record = session_check.query(SourceScheduleRecord).filter_by(source_id="remoteok").one()
            self.assertEqual(record.cooldown_until, future_cooldown)
        finally:
            session_check.close()

    def test_6_cooldown_expiry(self) -> None:
        """TEST 6: Cooldown expiry: Move clock past cooldown_until; verify source

        becomes eligible again without manual intervention.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        past_cooldown = now - timedelta(minutes=2)

        session = self.session_factory()
        try:
            sched = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                last_status="blocked_by_policy",
                cooldown_until=past_cooldown,
                next_due_at=past_cooldown,
                created_at=now - timedelta(hours=24),
                updated_at=now - timedelta(hours=24),
            )
            session.add(sched)
            session.commit()
        finally:
            session.close()

        fresh_scheduler = PollScheduler(self.session_factory, clock=lambda: now)
        enqueued_ids = fresh_scheduler.run_once()
        self.test_job_ids.extend(enqueued_ids)

        session_check = self.session_factory()
        try:
            jobs = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.id.in_(enqueued_ids),
            ).all()
            remoteok_jobs = [j for j in jobs if json.loads(j.payload_json).get("source_id") == "remoteok"]
            self.assertEqual(len(remoteok_jobs), 1, "Expired cooldown source must become eligible automatically")
        finally:
            session_check.close()

    def test_7_scheduler_worker_crash_recovery(self) -> None:
        """TEST 7: Scheduler/worker crash recovery: Worker crashes holding lease;

        lease expires; new worker claims and completes; verify source schedule record
        reflects last_attempt_at / last_success_at appropriately.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        session = self.session_factory()
        try:
            q = BackgroundWorkerQueue(session, worker_id="crashed-worker")
            job_id = q.enqueue_job("poll_source", {"source_id": "remoteok"})
            self.test_job_ids.append(job_id)

            sched = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                next_due_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(sched)
            session.commit()

            # Worker 1 claims with immediate expiration (0s lease)
            claimed1 = q.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(claimed1)
            self.assertEqual(claimed1.id, job_id)
        finally:
            session.close()

        # Worker 2 recovers expired lease and runs poll logic
        session2 = self.session_factory()
        try:
            q2 = BackgroundWorkerQueue(session2, worker_id="recovered-worker")
            claimed2 = q2.claim_next_job(lease_duration_seconds=60)
            self.assertIsNotNone(claimed2)
            self.assertEqual(claimed2.id, job_id)

            # Handler updates source schedule on success
            completion_time = now + timedelta(minutes=5)
            _update_source_schedule(session2, "remoteok", "ok", completion_time)
            ok = q2.complete_job(job_id)
            self.assertTrue(ok)
            session2.commit()

            sched_row = session2.query(SourceScheduleRecord).filter_by(source_id="remoteok").one()
            self.assertEqual(sched_row.last_status, "ok")
            self.assertEqual(sched_row.last_success_at, completion_time)
            self.assertEqual(sched_row.consecutive_failures, 0)
        finally:
            session2.close()

    def test_8_poll_now_http(self) -> None:
        """TEST 8: Poll Now HTTP: POST /api/worker/poll-now returns asynchronously

        before work runs, enqueues only due sources or the explicit requested source,
        and leaves feed visible.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        app = self._make_app()
        client = self._logged_in_client(app)

        session = self.session_factory()
        try:
            # Seed opportunity and feed projection so feed is visible
            opp = OpportunityRecord(
                id="opp-test-1",
                track="employment",
                title="Staff Platform Engineer",
                organization="Acme Systems",
                source_id="himalayas",
                source_url="https://himalayas.app/jobs/opp-test-1",
                description="Platform engineer role",
                content_hash="hash-opp-1",
                discovered_at=now,
                raw_payload_json="{}",
            )
            session.add(opp)
            proj = FeedProjectionRecord(
                id=f"opp-test-1:{self.truth_pack_hash}:v1",
                opportunity_id="opp-test-1",
                opportunity_content_hash="hash-opp-1",
                truth_pack_hash=self.truth_pack_hash,
                projection_version="v1",
                title="Staff Platform Engineer",
                organization="Acme Systems",
                source_id="himalayas",
                source_url="https://himalayas.app/jobs/opp-test-1",
                track="employment",
                seniority_level="senior",
                work_mode="remote",
                remote_scope="global",
                employment_type="full_time",
                fit_score=90.0,
                visible=True,
                search_text="staff platform engineer acme systems",
                projected_at=now,
            )
            session.add(proj)

            # himalayas is due, remoteok is not due
            sched_himalayas = SourceScheduleRecord(
                source_id="himalayas",
                cadence_hours=6.0,
                next_due_at=now - timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
            sched_remoteok = SourceScheduleRecord(
                source_id="remoteok",
                cadence_hours=6.0,
                next_due_at=now + timedelta(hours=4),
                created_at=now,
                updated_at=now,
            )
            session.add_all([sched_himalayas, sched_remoteok])
            session.commit()
        finally:
            session.close()

        # 1. Generic poll-now
        res = client.post("/api/worker/poll-now")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        enqueued_sids = [e["source_id"] for e in data.get("enqueued", [])]
        skipped_sids = {s["source_id"]: s["reason"] for s in data.get("skipped", [])}

        self.assertIn("himalayas", enqueued_sids)
        self.assertIn("remoteok", skipped_sids)
        self.assertEqual(skipped_sids["remoteok"], "not_due")

        # Verify job is asynchronous (in PENDING state, not executed inline)
        session_check = self.session_factory()
        try:
            himalayas_job = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source",
                WorkerJobRecord.status == "PENDING",
            ).first()
            self.assertIsNotNone(himalayas_job)
        finally:
            session_check.close()

        # Verify feed remains visible
        feed_res = client.get("/api/opportunities")
        self.assertEqual(feed_res.status_code, 200)
        feed_data = feed_res.json()
        self.assertGreaterEqual(feed_data["total"], 1)
        self.assertEqual(feed_data["items"][0]["id"], "opp-test-1")

        # 2. Explicit poll-now with force=True enqueues the requested source
        res_explicit = client.post("/api/worker/poll-now", json={"source_id": "remoteok", "force": True})
        self.assertEqual(res_explicit.status_code, 200)
        data_explicit = res_explicit.json()
        explicit_enqueued = [e["source_id"] for e in data_explicit.get("enqueued", [])]
        self.assertIn("remoteok", explicit_enqueued)

    def test_9_async_projection_maintenance(self) -> None:
        """TEST 9: Async projection maintenance: Modify a filter setting; verify HTTP

        returns immediately without bulk traversal, worker job is enqueued,
        worker runner executes refresh, projection is published.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        app = self._make_app()
        client = self._logged_in_client(app)

        session = self.session_factory()
        try:
            opp = OpportunityRecord(
                id="opp-proj-1",
                track="employment",
                title="Lead Backend Architect",
                organization="Beta Labs",
                source_id="himalayas",
                source_url="https://himalayas.app/jobs/opp-proj-1",
                description="Backend architecture with python",
                content_hash="hash-opp-proj-1",
                discovered_at=now,
                raw_payload_json="{}",
            )
            eval_record = MatchEvaluationRecord(
                id="eval-proj-1",
                opportunity_id="opp-proj-1",
                opportunity_content_hash="hash-opp-proj-1",
                truth_pack_hash=self.truth_pack_hash,
                evaluator_version="v1",
                decision="qualified",
                overall_fit_score=60.0,
                dimension_scores_json="{}",
                evaluated_at=now,
            )
            proj = FeedProjectionRecord(
                id=f"opp-proj-1:{self.truth_pack_hash}:v1",
                opportunity_id="opp-proj-1",
                opportunity_content_hash="hash-opp-proj-1",
                truth_pack_hash=self.truth_pack_hash,
                projection_version="v1",
                title="Lead Backend Architect",
                organization="Beta Labs",
                source_id="himalayas",
                source_url="https://himalayas.app/jobs/opp-proj-1",
                track="employment",
                seniority_level="senior",
                work_mode="remote",
                remote_scope="global",
                employment_type="full_time",
                fit_score=60.0,
                visible=True,
                search_text="lead backend architect beta labs",
                projected_at=now,
            )
            session.add_all([opp, eval_record, proj])
            session.commit()
        finally:
            session.close()

        # Update filter f_min_fit to 80.0
        res = client.put(
            "/api/filters/f_min_fit",
            json={"enabled": True, "params": {"min_score": 80.0}},
        )
        self.assertEqual(res.status_code, 200)

        # Verify refresh_feed_projections job was enqueued asynchronously
        session_check = self.session_factory()
        try:
            job = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "refresh_feed_projections",
                WorkerJobRecord.status == "PENDING",
            ).first()
            self.assertIsNotNone(job, "Settings write must enqueue refresh_feed_projections job")
            self.test_job_ids.append(job.id)
        finally:
            session_check.close()

        # Run worker to execute projection maintenance
        runner = WorkerRunner(self.session_factory, handlers=default_handler_registry())
        processed = runner.run_once()
        self.assertGreater(processed, 0)

        # Verify job completed and projection reflects updated filter
        session_after = self.session_factory()
        try:
            job_done = session_after.query(WorkerJobRecord).filter_by(id=job.id).one()
            self.assertEqual(job_done.status, "COMPLETED")

            updated_proj = session_after.query(FeedProjectionRecord).filter_by(
                id=f"opp-proj-1:{self.truth_pack_hash}:v1"
            ).one()
            # Since fit_score was 60.0 and min_score is now 80.0, it should be hidden
            self.assertFalse(updated_proj.visible)
        finally:
            session_after.close()

    def test_10_duplicate_maintenance(self) -> None:
        """TEST 10: Duplicate maintenance: Fire repeated filter updates in quick succession;

        verify jobs coalesce or execute idempotently without corrupting projection state.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        app = self._make_app()
        client = self._logged_in_client(app)

        session = self.session_factory()
        try:
            opp = OpportunityRecord(
                id="opp-idemp-1",
                track="employment",
                title="Data Platform Engineer",
                organization="Gamma Corp",
                source_id="himalayas",
                source_url="https://himalayas.app/jobs/opp-idemp-1",
                description="Data pipelines and analytics",
                content_hash="hash-opp-idemp-1",
                discovered_at=now,
                raw_payload_json="{}",
            )
            eval_record = MatchEvaluationRecord(
                id="eval-idemp-1",
                opportunity_id="opp-idemp-1",
                opportunity_content_hash="hash-opp-idemp-1",
                truth_pack_hash=self.truth_pack_hash,
                evaluator_version="v1",
                decision="qualified",
                overall_fit_score=95.0,
                dimension_scores_json="{}",
                evaluated_at=now,
            )
            proj = FeedProjectionRecord(
                id=f"opp-idemp-1:{self.truth_pack_hash}:v1",
                opportunity_id="opp-idemp-1",
                opportunity_content_hash="hash-opp-idemp-1",
                truth_pack_hash=self.truth_pack_hash,
                projection_version="v1",
                title="Data Platform Engineer",
                organization="Gamma Corp",
                source_id="himalayas",
                source_url="https://himalayas.app/jobs/opp-idemp-1",
                track="employment",
                seniority_level="senior",
                work_mode="remote",
                remote_scope="global",
                employment_type="full_time",
                fit_score=95.0,
                visible=True,
                search_text="data platform engineer gamma corp",
                projected_at=now,
            )
            session.add_all([opp, eval_record, proj])
            session.commit()
        finally:
            session.close()

        # Fire multiple rapid filter updates
        r1 = client.put("/api/filters/f_min_fit", json={"enabled": True, "params": {"min_score": 70.0}})
        r2 = client.put("/api/filters/f_min_fit", json={"enabled": True, "params": {"min_score": 75.0}})
        r3 = client.put("/api/filters/f_min_fit", json={"enabled": True, "params": {"min_score": 80.0}})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r3.status_code, 200)

        # Run worker until all projection refresh jobs are drained
        runner = WorkerRunner(self.session_factory, handlers=default_handler_registry())
        while True:
            done = runner.run_once()
            if done == 0:
                break

        # Verify all jobs completed cleanly without failures
        session_check = self.session_factory()
        try:
            jobs = session_check.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "refresh_feed_projections"
            ).all()
            for j in jobs:
                self.assertEqual(j.status, "COMPLETED")
                self.assertIsNone(j.error_message)

            # Verify final projection is coherent and visible (fit 95.0 >= min 80.0)
            proj_final = session_check.query(FeedProjectionRecord).filter_by(
                id=f"opp-idemp-1:{self.truth_pack_hash}:v1"
            ).one()
            self.assertTrue(proj_final.visible)
        finally:
            session_check.close()


if __name__ == "__main__":
    unittest.main()
