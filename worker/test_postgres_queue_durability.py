"""PostgreSQL-backed worker queue durability integration tests (Item C).

Proves real PostgreSQL transactional queue guarantees:
- Concurrent worker claims with SKIP LOCKED: verify two workers claiming simultaneously never get the same job;
- Lease expiration and recovery: verify a crashed worker's job becomes reclaimable after lease expiry;
- Dead-letter handling: verify a job exceeding max retries moves to dead-letter state;
- Guarded completion: verify a stale worker cannot mark a job completed after its lease expired and another worker claimed it;
- Scheduler deduplication: verify duplicate job enqueue is idempotent and suppressed.

Skips gracefully when a real PostgreSQL database is not available.
"""
from __future__ import annotations

import json
import os
import threading
import unittest
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from storage.engine import get_engine, get_session_factory
from storage.models import Base, WorkerJobRecord
from worker.queue import BackgroundWorkerQueue
from worker.scheduler import PollScheduler


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
    "Real PostgreSQL database URL required for postgres queue durability tests (skipped outside CI when DB not configured)"
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

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def setUp(self) -> None:
        if os.environ.get("CI") and _get_pg_db_url() is None:
            self.fail("CI environment requires real PostgreSQL database for worker durability suite")
        self.test_job_ids: list[str] = []
        session = self.session_factory()
        try:
            session.query(WorkerJobRecord).filter(
                WorkerJobRecord.job_type == "poll_source"
            ).delete(synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def tearDown(self) -> None:
        if self.test_job_ids:
            session = self.session_factory()
            try:
                session.query(WorkerJobRecord).filter(
                    WorkerJobRecord.id.in_(self.test_job_ids)
                ).delete(synchronize_session=False)
                session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()

    def _enqueue(self, queue: BackgroundWorkerQueue, job_type: str = "test_pg_task", payload: dict | None = None, max_retries: int = 3) -> str:
        job_id = queue.enqueue_job(job_type, payload or {"token": uuid.uuid4().hex}, max_retries=max_retries)
        self.test_job_ids.append(job_id)
        return job_id

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
            scheduler = PollScheduler(self.session_factory, poll_interval=1.0)
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


if __name__ == "__main__":
    unittest.main()
