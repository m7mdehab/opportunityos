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


if __name__ == "__main__":
    unittest.main()
