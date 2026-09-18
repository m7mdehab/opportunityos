import unittest
import os
import tempfile
from unittest.mock import Mock

from scripts.fr007_reliability_proof import prove_a5, prove_a6, run
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import WorkerJobRecord
from worker.queue import BackgroundWorkerQueue
from worker.runner import WorkerRunner


class ReliabilityProofContractTests(unittest.TestCase):
    def test_missing_postgres_is_blocked_not_pass(self):
        report = run(None)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual({item["state"] for item in report["scenarios"]}, {"BLOCKED"})

    def test_a5_requires_real_handler_probe(self):
        self.assertEqual(prove_a5(Mock())["state"], "BLOCKED")

    def test_a5_source_failure_does_not_hide_good_source(self):
        result = prove_a5(Mock(), source_probe=lambda: {
            "bad_failed": True, "good_persisted": True, "runner_continued": True,
            "bad_retryable": True,
        })
        self.assertEqual(result["state"], "PASS")

    def test_a6_requires_real_persistence_probe(self):
        self.assertEqual(prove_a6(Mock())["state"], "BLOCKED")

    def test_a6_preserves_unknown_concurrency_outcome(self):
        result = prove_a6(Mock(), idempotency_probe=lambda: {
            "stable_identity": True, "stable_provenance": True,
            "changed_content_reverified": True, "no_duplicate_identity": True,
            "concurrency": "RETRYABLE_INTEGRITY_ERROR",
        })
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(result["details"]["concurrency"], "RETRYABLE_INTEGRITY_ERROR")

    def test_probe_failure_is_fail_not_success(self):
        self.assertEqual(prove_a5(Mock(), source_probe=lambda: {}).get("state"), "FAIL")

    def test_real_runner_seam_records_bad_job_and_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = get_engine(f"sqlite:///{directory}/runner.db", allow_sqlite=True)
            init_db(engine)
            factory = get_session_factory(engine)
            session = factory()
            queue = BackgroundWorkerQueue(session, worker_id="proof-worker")
            bad_id = queue.enqueue_job("bad", {"source_id": "SOURCE_BAD"}, max_retries=2)
            good_id = queue.enqueue_job("good", {"source_id": "SOURCE_GOOD"})
            seen = []
            runner = WorkerRunner(factory, {
                "bad": lambda payload: (_ for _ in ()).throw(RuntimeError("fixture failure")),
                "good": lambda payload: seen.append(payload["source_id"]),
            }, worker_id="proof-worker")
            runner.run_once()
            runner.run_once()
            check = factory()
            try:
                bad = check.get(WorkerJobRecord, bad_id)
                good = check.get(WorkerJobRecord, good_id)
                self.assertEqual(bad.status, "RETRY")
                self.assertEqual(good.status, "COMPLETED")
                self.assertEqual(seen, ["SOURCE_GOOD"])
            finally:
                check.close(); session.close(); engine.dispose()


@unittest.skipUnless(os.environ.get("FR007_RELIABILITY_POSTGRES"), "disposable PostgreSQL workflow only")
class DisposablePostgresReliabilityTests(unittest.TestCase):
    def test_end_to_end_state_contract(self):
        report = run(
            os.environ["OPPORTUNITYOS_DB_URL"],
            source_probe=lambda: {"bad_failed": True, "good_persisted": True, "runner_continued": True},
            idempotency_probe=lambda: {"stable_identity": True, "stable_provenance": True,
                                       "changed_content_reverified": True, "no_duplicate_identity": True,
                                       "concurrency": "RETRYABLE_INTEGRITY_ERROR"},
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual({item["state"] for item in report["scenarios"]}, {"PASS"})


if __name__ == "__main__":
    unittest.main()
