import unittest
import os
import tempfile
from datetime import datetime, timezone, timedelta
from storage.engine import get_engine, init_db, get_session_factory
from worker.queue import BackgroundWorkerQueue
from storage.models import WorkerJobRecord

class TestBackgroundWorkerQueue(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_worker.db")
        self.engine = get_engine(f"sqlite:///{self.db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()
        self.queue = BackgroundWorkerQueue(self.session, worker_id="w-1")

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_enqueue_and_claim(self):
        job_id = self.queue.enqueue_job("ACQUIRE_OPPORTUNITY", {"source": "greenhouse"})
        self.assertTrue(job_id.startswith("job-"))

        claimed = self.queue.claim_next_job(lease_duration_seconds=30)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, job_id)
        self.assertEqual(claimed.status, "RUNNING")
        self.assertEqual(claimed.lease_owner, "w-1")

        self.queue.complete_job(job_id)
        job = self.session.query(WorkerJobRecord).filter_by(id=job_id).first()
        self.assertEqual(job.status, "COMPLETED")

    def test_retry_and_dead_letter(self):
        job_id = self.queue.enqueue_job("PARSE_ALERT", {"msg_id": "123"}, max_retries=2)
        
        # 1st attempt
        job1 = self.queue.claim_next_job()
        self.queue.fail_job(job_id, "Temporary network failure", backoff_seconds=0)
        job = self.session.query(WorkerJobRecord).filter_by(id=job_id).first()
        self.assertEqual(job.status, "RETRY")
        self.assertEqual(job.retry_count, 1)

        # 2nd attempt
        job2 = self.queue.claim_next_job()
        self.queue.fail_job(job_id, "Fatal parse error", backoff_seconds=0)
        job = self.session.query(WorkerJobRecord).filter_by(id=job_id).first()
        self.assertEqual(job.status, "DEAD_LETTER")
        self.assertEqual(job.retry_count, 2)

    def test_stale_lease_recovery(self):
        job_id = self.queue.enqueue_job("SYNC_PIPELINE", {})
        job = self.queue.claim_next_job(lease_duration_seconds=1)
        # Simulate worker crash and time passage
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.session.commit()

        # Another worker claims the stale job
        worker2_queue = BackgroundWorkerQueue(self.session, worker_id="w-2")
        recovered_job = worker2_queue.claim_next_job(lease_duration_seconds=30)
        self.assertIsNotNone(recovered_job)
        self.assertEqual(recovered_job.id, job_id)
        self.assertEqual(recovered_job.lease_owner, "w-2")

    def test_stale_lease_reclaim_dead_letters_poison_job(self):
        """A poison job (its handler always kills the worker process before
        complete_job/fail_job can run) must still be bounded by max_retries: the
        stale-lease reclaim path has to increment retry_count exactly as fail_job
        would, and dead-letter the job once the threshold is reached instead of
        reclaiming it forever (council C10-2).
        """
        max_retries = 3
        job_id = self.queue.enqueue_job("POISON", {}, max_retries=max_retries)

        # Simulate a dead worker: claim the job, then only ever expire its lease
        # directly -- never call complete_job or fail_job, because a process that
        # died mid-handler calls neither.
        initial = self.queue.claim_next_job(lease_duration_seconds=1)
        self.assertIsNotNone(initial, "expected the initial (non-reclaim) claim to succeed")
        self.assertEqual(initial.id, job_id)
        self.assertEqual(initial.status, "RUNNING")
        self.assertEqual(initial.retry_count, 0)
        initial.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.session.commit()

        # The job is now RUNNING with an expired lease and was never completed or
        # failed -- exactly `max_retries` stale-lease reclaims should be needed to
        # dead-letter it (the last one must not hand the poison job back out).
        for reclaim_attempt in range(1, max_retries + 1):
            result = self.queue.claim_next_job(lease_duration_seconds=1)
            if reclaim_attempt < max_retries:
                self.assertIsNotNone(result, f"expected reclaim #{reclaim_attempt} to succeed")
                self.assertEqual(result.id, job_id)
                self.assertEqual(result.status, "RUNNING")
                self.assertEqual(result.retry_count, reclaim_attempt)
                result.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
                self.session.commit()
            else:
                # The final reclaim pushes retry_count to max_retries: the job must
                # be dead-lettered, not handed back to a worker.
                self.assertIsNone(result, "a dead-lettered poison job must not be returned to a caller")

        job = self.session.query(WorkerJobRecord).filter_by(id=job_id).first()
        self.assertEqual(job.status, "DEAD_LETTER")
        self.assertEqual(job.retry_count, max_retries)
        self.assertIsNone(job.lease_owner)
        self.assertIsNone(job.lease_expires_at)
        self.assertIsNotNone(job.error_message)

        # The dead-lettered poison job must never be handed back out.
        self.assertIsNone(self.queue.claim_next_job(lease_duration_seconds=1))

    def test_expired_lease_claims_before_pending_backlog(self):
        """Expired RUNNING leases must take precedence over an arbitrarily large PENDING backlog."""
        # 1. Enqueue 50 due PENDING jobs
        pending_ids = []
        for i in range(50):
            pid = self.queue.enqueue_job("PENDING_BATCH", {"index": i})
            pending_ids.append(pid)

        # 2. Enqueue 1 stale RUNNING job
        stale_id = self.queue.enqueue_job("STALE_CRASHED", {"type": "stale"})
        stale_record = self.session.query(WorkerJobRecord).filter_by(id=stale_id).first()
        stale_record.status = "RUNNING"
        stale_record.lease_owner = "crashed-worker"
        stale_record.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        self.session.commit()

        # 3. Next claim must reclaim the stale job, NOT any of the 50 pending jobs
        claimed = self.queue.claim_next_job(lease_duration_seconds=30)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, stale_id)
        self.assertEqual(claimed.lease_owner, "w-1")
        self.assertEqual(claimed.status, "RUNNING")
        self.assertEqual(claimed.retry_count, 1)

    def test_stale_lease_dead_letter_proceeds_to_due_pending_job_in_same_call(self):
        """When an expired lease reaches max_retries during sweep, it is dead-lettered
        and the same claim_next_job() call immediately proceeds to claim due pending work.
        """
        # 1. Stale job that will dead-letter on this reclaim
        stale_id = self.queue.enqueue_job("POISON", {}, max_retries=3)
        stale_record = self.session.query(WorkerJobRecord).filter_by(id=stale_id).first()
        stale_record.status = "RUNNING"
        stale_record.retry_count = 2  # next reclaim will hit 3 >= max_retries
        stale_record.lease_owner = "dead-worker"
        stale_record.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=60)

        # 2. Due ordinary job
        fresh_id = self.queue.enqueue_job("FRESH_JOB", {"data": 123})
        self.session.commit()

        # 3. Claim: stale dead-letters, and fresh job is returned in the same call
        claimed = self.queue.claim_next_job(lease_duration_seconds=45)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, fresh_id)
        self.assertEqual(claimed.status, "RUNNING")

        # Verify stale job was committed as DEAD_LETTER
        stale_db = self.session.query(WorkerJobRecord).filter_by(id=stale_id).first()
        self.assertEqual(stale_db.status, "DEAD_LETTER")
        self.assertEqual(stale_db.retry_count, 3)

    def test_normal_fresh_job_ordering_deterministic_when_no_stale_lease(self):
        """Without expired leases, ordinary PENDING jobs are claimed deterministically by run_after."""
        now = datetime.now(timezone.utc)
        j1 = self.queue.enqueue_job("JOB_1", {}, run_after=now - timedelta(seconds=30))
        j2 = self.queue.enqueue_job("JOB_2", {}, run_after=now - timedelta(seconds=20))
        j3 = self.queue.enqueue_job("JOB_3", {}, run_after=now - timedelta(seconds=10))

        c1 = self.queue.claim_next_job()
        c2 = self.queue.claim_next_job()
        c3 = self.queue.claim_next_job()

        self.assertEqual([c1.id, c2.id, c3.id], [j1, j2, j3])


class TestWorkerStartupRegression(unittest.TestCase):
    def test_normal_worker_startup_reaches_handler_registry_without_name_error(self):
        """Worker main must execute without NameError (such as missing os import)
        and successfully construct the default handler registry.
        """
        import worker.__main__ as worker_main
        from unittest.mock import patch, MagicMock

        mock_factory = MagicMock()
        with patch.dict(os.environ, {
            "OPPORTUNITYOS_DB_URL": "postgresql" + "://fake-user:fake-pass" + "@" + "localhost.invalid/testdb",
            "OPPORTUNITYOS_TRUTH_PACK_PATH": "test_truth_pack.json",
        }):
            with patch("worker.__main__.get_engine"), \
                 patch("worker.__main__.get_session_factory", return_value=mock_factory), \
                 patch("worker.__main__.WorkerRunner.run_once") as mock_run_once:

                exit_code = worker_main.main(["--once"])
                self.assertEqual(exit_code, 0)
                mock_run_once.assert_called_once()

    def test_normal_worker_startup_with_unset_truth_pack_path(self):
        import worker.__main__ as worker_main
        from unittest.mock import patch, MagicMock

        mock_factory = MagicMock()
        env = dict(os.environ)
        env["OPPORTUNITYOS_DB_URL"] = "postgresql" + "://fake-user:fake-pass" + "@" + "localhost.invalid/testdb"
        env.pop("OPPORTUNITYOS_TRUTH_PACK_PATH", None)

        with patch.dict(os.environ, env, clear=True):
            with patch("worker.__main__.get_engine"), \
                 patch("worker.__main__.get_session_factory", return_value=mock_factory), \
                 patch("worker.__main__.WorkerRunner.run_once") as mock_run_once:

                exit_code = worker_main.main(["--once"])
                self.assertEqual(exit_code, 0)
                mock_run_once.assert_called_once()


if __name__ == "__main__":
    unittest.main()

