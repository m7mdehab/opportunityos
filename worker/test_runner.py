import os
import tempfile
import threading
import unittest

from storage.engine import get_engine, get_session_factory, init_db
from storage.models import WorkerJobRecord
from worker.queue import BackgroundWorkerQueue
from worker.runner import UNKNOWN_JOB_TYPE_MARKER, WorkerRunner


class TestWorkerRunner(unittest.TestCase):
    """Unit tests for WorkerRunner against SQLite (explicit injection, per worker/test_worker.py convention)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_runner.db")
        self.engine = get_engine(f"sqlite:///{self.db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        # A dedicated session for setup/assertions (separate from the runner's own sessions).
        self.setup_session = self.session_factory()
        self.queue = BackgroundWorkerQueue(self.setup_session, worker_id="test-setup")

    def tearDown(self):
        self.setup_session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _job_status(self, job_id: str) -> WorkerJobRecord:
        self.setup_session.expire_all()
        return self.setup_session.query(WorkerJobRecord).filter_by(id=job_id).first()

    def test_run_once_dispatches_to_registered_handler(self):
        calls = []

        def handler(payload):
            calls.append(payload)

        job_id = self.queue.enqueue_job("noop", {"a": 1})

        runner = WorkerRunner(
            self.session_factory,
            {"noop": handler},
            worker_id="w-dispatch",
        )
        processed = runner.run_once()

        self.assertTrue(processed)
        self.assertEqual(calls, [{"a": 1}])
        job = self._job_status(job_id)
        self.assertEqual(job.status, "COMPLETED")

    def test_run_once_returns_false_when_no_work(self):
        runner = WorkerRunner(self.session_factory, {"noop": lambda payload: None}, worker_id="w-idle")
        processed = runner.run_once()
        self.assertFalse(processed)

    def test_unknown_job_type_fails_with_distinctive_message(self):
        job_id = self.queue.enqueue_job("does_not_exist", {}, max_retries=5)

        runner = WorkerRunner(self.session_factory, {"noop": lambda payload: None}, worker_id="w-unknown")
        processed = runner.run_once()

        self.assertTrue(processed)
        job = self._job_status(job_id)
        self.assertIn(job.status, ("RETRY", "DEAD_LETTER"))
        self.assertIn(UNKNOWN_JOB_TYPE_MARKER, job.error_message)

    def test_handler_exception_triggers_fail_job(self):
        def failing_handler(payload):
            raise RuntimeError("boom")

        job_id = self.queue.enqueue_job("explode", {}, max_retries=5)

        runner = WorkerRunner(self.session_factory, {"explode": failing_handler}, worker_id="w-fail")
        processed = runner.run_once()

        self.assertTrue(processed)
        job = self._job_status(job_id)
        self.assertEqual(job.status, "RETRY")
        self.assertEqual(job.retry_count, 1)
        self.assertIn("boom", job.error_message)

    def test_repeated_failures_reach_dead_letter_after_max_retries(self):
        def failing_handler(payload):
            raise RuntimeError("always fails")

        job_id = self.queue.enqueue_job("explode", {}, max_retries=2)

        runner = WorkerRunner(self.session_factory, {"explode": failing_handler}, worker_id="w-deadletter")

        # Backoff after the first failure defers run_after into the future, so directly
        # drive the queue for subsequent attempts rather than waiting on run_forever's poll.
        runner.run_once()
        job = self._job_status(job_id)
        self.assertEqual(job.status, "RETRY")
        self.assertEqual(job.retry_count, 1)

        # Clear the backoff delay so the next claim is immediately eligible.
        from datetime import datetime, timezone

        job.run_after = datetime.now(timezone.utc)
        self.setup_session.commit()

        runner.run_once()
        job = self._job_status(job_id)
        self.assertEqual(job.status, "DEAD_LETTER")
        self.assertEqual(job.retry_count, 2)

    def test_run_forever_honours_max_jobs(self):
        for i in range(5):
            self.queue.enqueue_job("noop", {"i": i})

        calls = []
        runner = WorkerRunner(
            self.session_factory,
            {"noop": lambda payload: calls.append(payload)},
            worker_id="w-maxjobs",
            poll_interval=0.01,
        )
        processed_count = runner.run_forever(max_jobs=3)

        self.assertEqual(processed_count, 3)
        self.assertEqual(len(calls), 3)

    def test_run_forever_honours_stop_event(self):
        stop_event = threading.Event()
        stop_event.set()  # already stopped before the loop starts

        self.queue.enqueue_job("noop", {})

        runner = WorkerRunner(
            self.session_factory,
            {"noop": lambda payload: None},
            worker_id="w-stopped",
            stop_event=stop_event,
            poll_interval=0.01,
        )
        processed_count = runner.run_forever(max_jobs=10)

        self.assertEqual(processed_count, 0)

    def test_run_forever_stop_event_set_concurrently_halts_loop(self):
        stop_event = threading.Event()

        # Enqueue more jobs than we expect to process before stopping.
        for i in range(50):
            self.queue.enqueue_job("noop", {"i": i})

        processed_before_stop = []

        def handler(payload):
            processed_before_stop.append(payload)
            if len(processed_before_stop) == 2:
                stop_event.set()

        runner = WorkerRunner(
            self.session_factory,
            {"noop": handler},
            worker_id="w-concurrent-stop",
            stop_event=stop_event,
            poll_interval=0.01,
        )
        processed_count = runner.run_forever()

        self.assertEqual(processed_count, 2)
        self.assertTrue(stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
