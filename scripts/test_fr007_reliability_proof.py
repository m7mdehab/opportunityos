import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.fr007_reliability_proof import prove_a4, prove_a5, prove_a6, run
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import WorkerJobRecord
from worker.queue import BackgroundWorkerQueue
from worker.runner import WorkerRunner


class ReliabilityProofContractTests(unittest.TestCase):
    def test_missing_postgres_is_blocked_not_pass(self):
        with patch.dict(os.environ, {}, clear=True):
            report = run(None)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual({item["state"] for item in report["scenarios"]}, {"BLOCKED"})

    def test_a4_requires_real_http_probe(self):
        self.assertEqual(prove_a4(Mock(), http_probe=None)["state"], "BLOCKED")

    def test_a4_rejects_insufficient_persisted_data(self):
        with patch("scripts.fr007_reliability_proof._table_exists", return_value=True):
            result = prove_a4(Mock(), http_probe=lambda: {
            "opportunity_count": 1,
            "projection_count": 1,
            "failed_or_stuck_job_count": 0,
                "worker_started": False,
            })
        self.assertEqual(result["state"], "FAIL")

    def test_a4_rejects_worker_started(self):
        with patch("scripts.fr007_reliability_proof._table_exists", return_value=True):
            result = prove_a4(Mock(), http_probe=lambda: {
            "opportunity_count": 2,
            "projection_count": 2,
            "failed_or_stuck_job_count": 2,
            "worker_started": True,
            "feed_status": 200,
            "search_status": 200,
            "detail_status": 200,
            "pagination_status": 200,
            "search_matched": True,
                "pagination_distinct": True,
            })
        self.assertEqual(result["state"], "FAIL")

    def test_a4_validates_http_read_statuses(self):
        with patch("scripts.fr007_reliability_proof._table_exists", return_value=True):
            result = prove_a4(Mock(), http_probe=lambda: {
            "opportunity_count": 2,
            "projection_count": 2,
            "failed_or_stuck_job_count": 2,
            "worker_started": False,
            "feed_status": 500,
            "search_status": 200,
            "detail_status": 200,
            "pagination_status": 200,
            "search_matched": True,
                "pagination_distinct": True,
            })
        self.assertEqual(result["state"], "FAIL")

    def test_a5_requires_real_handler_probe(self):
        self.assertEqual(prove_a5(Mock(), source_probe=None)["state"], "BLOCKED")

    def test_a5_source_failure_does_not_hide_good_source(self):
        result = prove_a5(Mock(), source_probe=lambda: {
            "bad_failed": True,
            "good_persisted": True,
            "runner_continued": True,
            "bad_job_status": "RETRY",
            "good_job_status": "COMPLETED",
            "scheduler_tick_ok": True,
            "feed_readable": True,
            "artifact_retrievable": True,
        })
        self.assertEqual(result["state"], "PASS")

    def test_a5_rejects_missing_job_completion_invariants(self):
        result = prove_a5(Mock(), source_probe=lambda: {
            "bad_failed": True,
            "good_persisted": True,
            "runner_continued": True,
            "bad_job_status": "PENDING",
            "good_job_status": "COMPLETED",
            "scheduler_tick_ok": True,
            "feed_readable": True,
            "artifact_retrievable": True,
        })
        self.assertEqual(result["state"], "FAIL")

    def test_a6_requires_real_persistence_probe(self):
        self.assertEqual(prove_a6(Mock(), idempotency_probe=None)["state"], "BLOCKED")

    def test_a6_preserves_unknown_concurrency_outcome(self):
        result = prove_a6(Mock(), idempotency_probe=lambda: {
            "stable_identity": True,
            "stable_provenance": True,
            "changed_content_reverified": True,
            "no_duplicate_identity": True,
            "concurrency": "INTEGRITY_ERROR_WITH_CANONICAL_DB",
            "concurrent_opp_count": 1,
            "concurrent_provenance_duplicates": 0,
            "race_threads_complete": True,
            "poll_counts": [1, 2, 3, 4, 5],
            "poll_run_outcomes": ["inserted", "unchanged", "unchanged", "unchanged", "unchanged"],
            "changed_poll_run_outcome": "updated",
        })
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(result["details"]["concurrency"], "INTEGRITY_ERROR_WITH_CANONICAL_DB")

    def test_a6_rejects_non_canonical_database(self):
        result = prove_a6(Mock(), idempotency_probe=lambda: {
            "stable_identity": True,
            "stable_provenance": True,
            "changed_content_reverified": True,
            "no_duplicate_identity": True,
            "concurrency": "INTEGRITY_ERROR_WITH_CANONICAL_DB",
            "concurrent_opp_count": 2,
            "concurrent_provenance_duplicates": 1,
            "poll_counts": [1, 2, 3, 4, 5],
            "poll_run_outcomes": ["inserted", "unchanged", "unchanged", "unchanged", "unchanged"],
            "changed_poll_run_outcome": "updated",
        })
        self.assertEqual(result["state"], "FAIL")

    def test_a6_rejects_incomplete_concurrency_observation(self):
        result = prove_a6(Mock(), idempotency_probe=lambda: {
            "stable_identity": True,
            "stable_provenance": True,
            "changed_content_reverified": True,
            "no_duplicate_identity": True,
            "concurrency": "CONCURRENT_IDEMPOTENT",
            "concurrent_opp_count": 1,
            "concurrent_provenance_duplicates": 0,
            "race_threads_complete": False,
            "poll_counts": [1, 2, 3, 4, 5],
            "poll_run_outcomes": ["inserted", "unchanged", "unchanged", "unchanged", "unchanged"],
            "changed_poll_run_outcome": "updated",
        })
        self.assertEqual(result["state"], "FAIL")

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
                check.close()
                session.close()
                engine.dispose()


@unittest.skipUnless(os.environ.get("FR007_RELIABILITY_POSTGRES"), "disposable PostgreSQL workflow only")
class DisposablePostgresReliabilityTests(unittest.TestCase):
    def test_end_to_end_state_contract(self):
        dsn = os.environ["OPPORTUNITYOS_DB_URL"]
        report = run(dsn)
        self.assertEqual(report["status"], "PASS", report)
        scenarios = {item["scenario"]: item for item in report["scenarios"]}
        self.assertEqual(set(scenarios.keys()), {"A4", "A5", "A6"})
        for name, item in scenarios.items():
            self.assertEqual(item["state"], "PASS", f"Scenario {name} did not PASS: {item}")

        # Assert concrete A4 observations
        a4_details = scenarios["A4"]["details"]
        self.assertGreaterEqual(a4_details["opportunity_count"], 2)
        self.assertGreaterEqual(a4_details["projection_count"], 2)
        self.assertGreaterEqual(a4_details["failed_or_stuck_job_count"], 2)
        self.assertEqual(a4_details["feed_status"], 200)
        self.assertEqual(a4_details["search_status"], 200)
        self.assertEqual(a4_details["detail_status"], 200)
        self.assertEqual(a4_details["pagination_status"], 200)
        self.assertFalse(a4_details["worker_started"])
        self.assertTrue(a4_details["search_matched"])
        self.assertTrue(a4_details["pagination_distinct"])

        # Assert concrete A5 observations
        a5_details = scenarios["A5"]["details"]
        self.assertTrue(a5_details["bad_failed"])
        self.assertIn(a5_details["bad_job_status"], ("RETRY", "DEAD_LETTER"))
        self.assertTrue(a5_details["good_persisted"])
        self.assertEqual(a5_details["good_job_status"], "COMPLETED")
        self.assertTrue(a5_details["runner_continued"])
        self.assertTrue(a5_details["scheduler_tick_ok"])
        self.assertTrue(a5_details["feed_readable"])
        self.assertTrue(a5_details["artifact_retrievable"])

        # Assert concrete A6 observations
        a6_details = scenarios["A6"]["details"]
        self.assertTrue(a6_details["stable_identity"])
        self.assertTrue(a6_details["stable_provenance"])
        self.assertTrue(a6_details["changed_content_reverified"])
        self.assertTrue(a6_details["no_duplicate_identity"])
        self.assertIn(
            a6_details["concurrency"],
            ("CONCURRENT_IDEMPOTENT", "INTEGRITY_ERROR_WITH_CANONICAL_DB"),
        )
        self.assertTrue(a6_details["race_threads_complete"])
        self.assertEqual(a6_details["concurrent_opp_count"], 1)
        self.assertEqual(a6_details["concurrent_provenance_duplicates"], 0)
        self.assertEqual(len(a6_details["poll_counts"]), 5)
        self.assertEqual(
            a6_details["poll_run_outcomes"],
            ["inserted", "unchanged", "unchanged", "unchanged", "unchanged"],
        )
        self.assertEqual(a6_details["changed_poll_run_outcome"], "updated")


if __name__ == "__main__":
    unittest.main()
