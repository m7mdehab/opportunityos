"""Tests for queue durability and scheduler persistence in worker_jobs.

Proves:
- Concurrent workers atomically claim separate jobs with distinct leases;
- Crash recovery: expired worker leases are reclaimed with retry_count increment;
- Dead-letter: jobs whose leases repeatedly expire are dead-lettered at max_retries;
- Guarded completion: lost leases prevent stale workers from clobbering state;
- Scheduler deduplication: duplicate active jobs are suppressed and state is preserved across restarts.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from storage.engine import get_engine, get_session_factory, init_db
from storage.models import WorkerJobRecord
from worker.queue import BackgroundWorkerQueue
from worker.scheduler import PollScheduler


class TestQueueDurability(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_durability.db")
        self.engine = get_engine(f"sqlite:///{self.db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_concurrent_worker_claims_no_overlap(self):
        """Two workers claiming from the queue claim distinct jobs without colliding."""
        session1 = self.session_factory()
        session2 = self.session_factory()
        try:
            queue1 = BackgroundWorkerQueue(session1, worker_id="worker-node-1")
            queue2 = BackgroundWorkerQueue(session2, worker_id="worker-node-2")

            # Enqueue 2 jobs
            job_a = queue1.enqueue_job("test_job", {"index": 1})
            job_b = queue1.enqueue_job("test_job", {"index": 2})

            # Worker 1 claims first job
            claimed_1 = queue1.claim_next_job(lease_duration_seconds=60)
            self.assertIsNotNone(claimed_1)
            self.assertEqual("RUNNING", claimed_1.status)
            self.assertEqual("worker-node-1", claimed_1.lease_owner)

            # Worker 2 claims next job
            claimed_2 = queue2.claim_next_job(lease_duration_seconds=60)
            self.assertIsNotNone(claimed_2)
            self.assertEqual("RUNNING", claimed_2.status)
            self.assertEqual("worker-node-2", claimed_2.lease_owner)

            # Ensure they claimed distinct jobs
            self.assertNotEqual(claimed_1.id, claimed_2.id)
            self.assertEqual({job_a, job_b}, {claimed_1.id, claimed_2.id})

            # A third claim yields None since both are RUNNING
            self.assertIsNone(queue1.claim_next_job())
        finally:
            session1.close()
            session2.close()

    def test_claim_filter_leaves_non_source_work_for_the_normal_queue(self):
        session = self.session_factory()
        try:
            queue = BackgroundWorkerQueue(session, worker_id="source-only-worker")
            poll_id = queue.enqueue_job("poll_source", {"source_id": "fixture-a"})
            eval_id = queue.enqueue_job("evaluate_new", {})

            claimed = queue.claim_next_job(allowed_job_types={"poll_source"})
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, poll_id)
            self.assertEqual(claimed.job_type, "poll_source")
            self.assertIsNone(queue.claim_next_job(allowed_job_types={"poll_source"}))

            session.expire_all()
            untouched = session.query(WorkerJobRecord).filter_by(id=eval_id).one()
            self.assertEqual(untouched.status, "PENDING")
            with self.assertRaisesRegex(ValueError, "must be non-empty"):
                queue.claim_next_job(allowed_job_types=set())
        finally:
            session.close()

    def test_crash_recovery_stale_lease_reclaim(self):
        """When a worker crashes or drops dead, its expired lease is reclaimed by another worker."""
        session1 = self.session_factory()
        session2 = self.session_factory()
        try:
            queue1 = BackgroundWorkerQueue(session1, worker_id="crashed-worker")
            job_id = queue1.enqueue_job("long_task", {"step": "ingest"}, max_retries=3)

            # Claim job with a lease that expires immediately in the past
            claimed = queue1.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(claimed)
            self.assertEqual(job_id, claimed.id)

            # Simulate worker dying: session closes without completing/failing
            session1.close()

            # Now worker 2 starts up and sweeps for runnable / stale jobs
            queue2 = BackgroundWorkerQueue(session2, worker_id="healthy-worker")
            reclaimed = queue2.claim_next_job(lease_duration_seconds=60)

            self.assertIsNotNone(reclaimed)
            self.assertEqual(job_id, reclaimed.id)
            self.assertEqual("RUNNING", reclaimed.status)
            self.assertEqual("healthy-worker", reclaimed.lease_owner)
            self.assertEqual(1, reclaimed.retry_count)  # incremented on crash recovery
        finally:
            session2.close()

    def test_stale_lease_dead_letters_on_max_retries(self):
        """A poison-pill job whose lease expires repeatedly is marked DEAD_LETTER once max_retries is reached."""
        session = self.session_factory()
        try:
            queue = BackgroundWorkerQueue(session, worker_id="worker-a")
            job_id = queue.enqueue_job("crash_task", {}, max_retries=2)

            # First claim (retry_count = 0)
            job = queue.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(job)
            self.assertEqual(0, job.retry_count)

            # Manually expire lease
            job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            session.commit()

            # Second claim sweeps expired lease (retry_count increments to 1 < max_retries 2)
            job2 = queue.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(job2)
            self.assertEqual(1, job2.retry_count)

            # Manually expire lease again
            job2.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            session.commit()

            # Third claim sweeps expired lease: retry_count reaches 2 >= max_retries 2 -> DEAD_LETTER
            job3 = queue.claim_next_job(lease_duration_seconds=60)
            self.assertIsNone(job3)  # Dead-lettered jobs are not returned to workers

            session.expire_all()
            record = session.query(WorkerJobRecord).filter_by(id=job_id).first()
            self.assertEqual("DEAD_LETTER", record.status)
            self.assertIn("Lease expired without completion", record.error_message)
        finally:
            session.close()

    def test_guarded_completion_prevents_lost_lease_clobber(self):
        """Worker A cannot mark a job COMPLETED if its lease was reclaimed by Worker B."""
        session1 = self.session_factory()
        session2 = self.session_factory()
        try:
            queue1 = BackgroundWorkerQueue(session1, worker_id="worker-slow")
            queue2 = BackgroundWorkerQueue(session2, worker_id="worker-fast")

            job_id = queue1.enqueue_job("work_item", {})
            claimed1 = queue1.claim_next_job(lease_duration_seconds=0)
            self.assertIsNotNone(claimed1)

            # Worker 2 sweeps the stale lease
            claimed2 = queue2.claim_next_job(lease_duration_seconds=60)
            self.assertIsNotNone(claimed2)
            self.assertEqual("worker-fast", claimed2.lease_owner)

            # Now Worker 1 wakes up and attempts to complete the job
            success = queue1.complete_job(job_id)
            self.assertFalse(success, "Worker 1 must not complete a job whose lease it lost")

            # Verify Worker 2 still owns the running job
            session2.expire_all()
            record = session2.query(WorkerJobRecord).filter_by(id=job_id).first()
            self.assertEqual("RUNNING", record.status)
            self.assertEqual("worker-fast", record.lease_owner)

            # Worker 2 completes successfully
            self.assertTrue(queue2.complete_job(job_id))
            session2.expire_all()
            record = session2.query(WorkerJobRecord).filter_by(id=job_id).first()
            self.assertEqual("COMPLETED", record.status)
        finally:
            session1.close()
            session2.close()

    def test_scheduler_deduplication_and_restart_durability(self):
        """PollScheduler suppresses duplicate enqueues for active sources and preserves state across restarts."""
        scheduler1 = PollScheduler(self.session_factory, tick_interval_seconds=1.0)
        enqueued_first_tick = scheduler1.run_once()
        self.assertGreater(len(enqueued_first_tick), 0, "First tick must enqueue eligible sources")

        # Second tick immediately after should enqueue 0 duplicate jobs
        enqueued_second_tick = scheduler1.run_once()
        self.assertEqual(0, len(enqueued_second_tick), "Second tick must not enqueue duplicates for active sources")

        # Simulate scheduler restart (new process / instance)
        scheduler2 = PollScheduler(self.session_factory, tick_interval_seconds=1.0)
        enqueued_on_restart = scheduler2.run_once()
        self.assertEqual(
            0,
            len(enqueued_on_restart),
            "Restarted scheduler must inspect persistent worker_jobs and suppress duplicate active jobs",
        )


if __name__ == "__main__":
    unittest.main()
