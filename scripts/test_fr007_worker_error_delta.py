from __future__ import annotations

import io
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.fr007_worker_error_delta import aggregate_shard_results, count_error_tokens, run_shard


class WorkerErrorDeltaTests(unittest.TestCase):
    def test_counts_only_required_error_classes_case_insensitively(self):
        counts = count_error_tokens([
            "psycopg2.errors.UniqueViolation: duplicate key",
            "EMAXCONNSESSION from provider pool",
            "ReadOnlySqlTransaction transaction is read only",
            "unrelated error",
        ])
        self.assertEqual(counts, {
            "EMAXCONNSESSION": 1,
            "UniqueViolation": 1,
            "ReadOnlySqlTransaction": 1,
        })

    def test_protected_shard_requires_exact_normal_settings(self):
        with self.assertRaisesRegex(ValueError, "exactly 30 jobs / 480 seconds"):
            run_shard(
                max_jobs=29,
                time_budget_seconds=480,
                worker_id="w227-recovery-run-1",
                shard=1,
                output=Path("unused.json"),
            )

    def test_success_artifact_contains_zero_run_scoped_deltas_and_no_raw_logs(self):
        class FakeChild:
            stdout = io.StringIO("mode=drain dry_run=False schedules=0 enqueued=0 processed=0\n")

            def wait(self):
                return 0

        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "delta.json"
            with patch("scripts.fr007_worker_error_delta.subprocess.Popen", return_value=FakeChild()):
                result = run_shard(
                    max_jobs=30,
                    time_budget_seconds=480,
                    worker_id="w227-recovery-run-1",
                    shard=1,
                    output=output,
                )
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["raw_worker_logs_recorded"])
            self.assertTrue(all(item["delta"] == 0 for item in result["error_counts_since_shard_start"].values()))
            self.assertEqual(output.read_text(encoding="utf-8").count("UniqueViolation"), 1)

    def test_forbidden_error_delta_fails_the_shard(self):
        class FakeChild:
            stdout = io.StringIO("psycopg2.errors.ReadOnlySqlTransaction\n")

            def wait(self):
                return 0

        with TemporaryDirectory() as temp_dir:
            with patch("scripts.fr007_worker_error_delta.subprocess.Popen", return_value=FakeChild()):
                with self.assertRaisesRegex(RuntimeError, "forbidden new PostgreSQL error"):
                    run_shard(
                        max_jobs=30,
                        time_budget_seconds=480,
                        worker_id="w227-recovery-run-1",
                        shard=1,
                        output=Path(temp_dir) / "delta.json",
                    )

    def test_aggregate_requires_five_unique_shards_and_emits_run_delta(self):
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            for shard in range(1, 6):
                payload = {
                    "status": "PASS",
                    "run_id": "12345",
                    "worker_id": f"w227-recovery-12345-{shard}",
                    "shard": shard,
                    "jobs_limit": 30,
                    "time_budget_seconds": 480,
                    "error_counts_since_shard_start": {
                        token: {"baseline": 0, "final": 0, "delta": 0}
                        for token in ("EMAXCONNSESSION", "UniqueViolation", "ReadOnlySqlTransaction")
                    },
                }
                (directory / f"shard-{shard}.json").write_text(__import__("json").dumps(payload), encoding="utf-8")

            aggregate = aggregate_shard_results(directory, run_id="12345")

        self.assertEqual(aggregate["status"], "PASS")
        self.assertEqual(aggregate["shards"], 5)
        self.assertEqual(aggregate["new_error_delta_since_proof_start"]["UniqueViolation"]["delta"], 0)

    def test_aggregate_fails_closed_on_error_or_nonzero_delta(self):
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            for shard in range(1, 6):
                payload = {
                    "status": "PASS",
                    "run_id": "12345",
                    "worker_id": f"w227-recovery-12345-{shard}",
                    "shard": shard,
                    "jobs_limit": 30,
                    "time_budget_seconds": 480,
                    "error_counts_since_shard_start": {
                        token: {"baseline": 0, "final": int(token == "UniqueViolation"), "delta": int(token == "UniqueViolation")}
                        for token in ("EMAXCONNSESSION", "UniqueViolation", "ReadOnlySqlTransaction")
                    },
                }
                (directory / f"shard-{shard}.json").write_text(json.dumps(payload), encoding="utf-8")

            aggregate = aggregate_shard_results(directory, run_id="12345")

        self.assertEqual(aggregate["status"], "FAIL")
        self.assertEqual(aggregate["new_error_delta_since_proof_start"]["UniqueViolation"]["delta"], 5)

    def test_aggregate_rejects_missing_duplicate_or_foreign_run_shards(self):
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            payload = {
                "status": "PASS",
                "run_id": "12345",
                "jobs_limit": 30,
                "time_budget_seconds": 480,
                "error_counts_since_shard_start": {
                    token: {"baseline": 0, "final": 0, "delta": 0}
                    for token in ("EMAXCONNSESSION", "UniqueViolation", "ReadOnlySqlTransaction")
                },
            }
            for shard in range(1, 5):
                (directory / f"shard-{shard}.json").write_text(
                    json.dumps({**payload, "shard": shard}), encoding="utf-8"
                )
            with self.assertRaisesRegex(ValueError, "exactly five"):
                aggregate_shard_results(directory, run_id="12345")

            (directory / "shard-5.json").write_text(json.dumps({**payload, "shard": 4}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "each of the five unique"):
                aggregate_shard_results(directory, run_id="12345")

            (directory / "shard-5.json").write_text(json.dumps({**payload, "shard": 5, "run_id": "other"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different hosted proof run"):
                aggregate_shard_results(directory, run_id="12345")

    def test_final_runtime_workflow_runs_and_aggregates_the_exact_five_shards(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github" / "workflows" / "fr007-final-runtime-closure.yml").read_text(encoding="utf-8")
        self.assertIn("matrix: {shard: [1, 2, 3, 4, 5]}", workflow)
        self.assertIn("scripts/fr007_worker_error_delta.py --max-jobs 30", workflow)
        self.assertIn("--time-budget-seconds 480", workflow)
        self.assertIn("--shard \"${{ matrix.shard }}\"", workflow)
        self.assertIn("name: fr007-w227-error-delta-${{ github.run_id }}-${{ matrix.shard }}", workflow)
        self.assertIn("pattern: fr007-w227-error-delta-${{ github.run_id }}-*", workflow)
        self.assertIn("merge-multiple: true", workflow)
        self.assertIn("--aggregate-dir w227-error-deltas", workflow)
        self.assertIn("python scripts/fr007_capacity_closure.py preflight", workflow)
        self.assertNotIn("0021_storage_v2", workflow)
        self.assertIn("0023_alembic_access", workflow)
        self.assertIn('print(f"PROBE_FAILURE={type(exc).__name__}")', workflow)


if __name__ == "__main__":
    unittest.main()
