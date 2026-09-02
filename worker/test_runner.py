import logging
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opportunity.registry import SourceRegistry
from opportunity.transport import BaseTransport, MockTransport, TransportResponse
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import WorkerJobRecord
from worker.handlers import make_poll_source_handler
from worker.queue import BackgroundWorkerQueue
from worker.runner import UNKNOWN_JOB_TYPE_MARKER, WorkerRunner


class TestWorkerRunner(unittest.TestCase):
    """Unit tests for WorkerRunner against SQLite (explicit injection, per worker/test_worker.py convention)."""

    def setUp(self):
        # Defensive test-isolation guard, not a WorkerRunner behavior: when this
        # module runs as part of the full `unittest discover` suite, a storage.*
        # test module's setUpClass runs Alembic migrations first, and Alembic's
        # migrations/env.py calls logging.config.fileConfig() (disable_existing_
        # loggers=True by default), which disables this already-imported logger
        # for the rest of the process. That's a logging-visibility side effect
        # only -- it never affects job dispatch/fencing correctness -- but it
        # would silently break assertLogs-based tests below, so force it back on.
        logging.getLogger("opportunityos.worker.runner").disabled = False

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

    def test_heartbeat_renews_lease_so_slow_handler_still_completes_once(self):
        """A handler that outlives lease_seconds must still complete exactly once:
        the runner's heartbeat thread keeps renewing the lease while it runs, so the
        ownership fence at completion time still sees a valid, unexpired lease."""
        job_id = self.queue.enqueue_job("slow", {}, max_retries=3)

        def slow_handler(payload):
            # Outlives the 1s lease; only heartbeat renewal keeps the eventual
            # completion from being fenced off as belonging to an expired lease.
            time.sleep(1.3)

        runner = WorkerRunner(
            self.session_factory,
            {"slow": slow_handler},
            worker_id="w-heartbeat",
            lease_seconds=1,
        )
        processed = runner.run_once()

        self.assertTrue(processed)
        job = self._job_status(job_id)
        self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(job.retry_count, 0)

    def test_stolen_lease_refuses_to_write_outcome(self):
        """If another worker's stale-lease sweep has already taken over a job, this
        runner must refuse to write complete/fail for it rather than clobber the new
        owner's outcome -- it must detect the lost lease and log, not overwrite."""
        job_id = self.queue.enqueue_job("noop", {}, max_retries=3)

        runner = WorkerRunner(self.session_factory, {"noop": lambda payload: None}, worker_id="w-original")

        claim_session = self.session_factory()
        try:
            claim_queue = BackgroundWorkerQueue(claim_session, worker_id="w-original")
            job = claim_queue.claim_next_job(lease_duration_seconds=60)
            self.assertIsNotNone(job)
            self.assertEqual(job.lease_owner, "w-original")

            # Simulate a second worker's stale-lease sweep stealing this job out from
            # under the first worker while it is (nominally) still "running" it.
            thief_session = self.session_factory()
            try:
                thief_row = thief_session.query(WorkerJobRecord).filter_by(id=job_id).first()
                thief_row.lease_owner = "w-thief"
                thief_row.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
                thief_session.commit()
            finally:
                thief_session.close()

            with self.assertLogs("opportunityos.worker.runner", level="ERROR") as log_capture:
                runner._complete_job_fenced(claim_session, claim_queue, job_id, "noop")

            self.assertTrue(
                any("worker.lease_lost" in message for message in log_capture.output),
                f"expected a worker.lease_lost log line, got: {log_capture.output}",
            )
        finally:
            claim_session.close()

        # The stolen job's state, as the thief left it, must be untouched by w-original.
        job = self._job_status(job_id)
        self.assertEqual(job.status, "RUNNING")
        self.assertEqual(job.lease_owner, "w-thief")


class TestPollSourceHandler(unittest.TestCase):
    """Coverage for worker.handlers.poll_source's two branches: refused and fetched.

    D10 specifies "1 poll_source with fixture", but storage/test_postgres_integration.py's
    Case S only exercises the read-disabled (refusal) branch. These tests cover both,
    with no network I/O: MockTransport (or a wrapper around it) is always the injected
    transport.
    """

    def test_poll_source_refuses_read_disabled_source_without_fetching(self):
        registry = SourceRegistry()
        self.assertFalse(
            registry.is_read_allowed("ashby:openai"),
            "ashby:openai must be read-disabled for this test to be meaningful",
        )

        class ExplodingTransport(BaseTransport):
            def fetch(self, request):
                raise AssertionError("transport.fetch must not be called for a read-disabled source")

        refusals = []
        handler = make_poll_source_handler(
            registry=registry,
            transport=ExplodingTransport(),
            refusal_sink=refusals.append,
        )

        handler({"source_id": "ashby:openai"})

        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["source_id"], "ashby:openai")

    def test_poll_source_fetches_and_ingests_for_read_allowed_source(self):
        registry = SourceRegistry()
        self.assertTrue(
            registry.is_read_allowed("himalayas"),
            "himalayas must be read-allowed for this test to be meaningful",
        )

        fixture_path = Path(__file__).resolve().parents[1] / "opportunity" / "fixtures" / "himalayas.json"
        fixture_payload = fixture_path.read_text(encoding="utf-8")

        fetch_calls = []

        class RecordingTransport(BaseTransport):
            def __init__(self, inner):
                self._inner = inner

            def fetch(self, request):
                fetch_calls.append((request.source_id, request.url))
                return self._inner.fetch(request)

        inner_transport = MockTransport(
            {"himalayas": TransportResponse(status_code=200, body=fixture_payload, latency_ms=5)}
        )

        refusals = []
        handler = make_poll_source_handler(
            registry=registry,
            transport=RecordingTransport(inner_transport),
            refusal_sink=refusals.append,
        )

        handler({"source_id": "himalayas"})

        self.assertEqual(len(fetch_calls), 1, "the governed acquisition path must actually have fetched")
        self.assertEqual(fetch_calls[0][0], "himalayas")
        self.assertEqual(refusals, [], "a read-allowed source must never record a refusal")


if __name__ == "__main__":
    unittest.main()
