from __future__ import annotations

import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import fr007_incremental_source_bootstrap as incremental
from scripts.fr007_incremental_source_bootstrap import (
    DATABASE_HARD_BUDGET,
    invariant_failures,
    projected_final_database_bytes,
    select_registry_slice,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL = json.loads(
    (ROOT / "reports/evidence/FR-007/W23_STORAGE_V2_CAPACITY_MODEL.json").read_text(encoding="utf-8")
)


def _state(*, database_bytes: int = 14_101_651, opportunities: int = 40, coverage: int = 1):
    return {
        "database_bytes": database_bytes,
        "successful_source_coverage": coverage,
        "counts": {
            "opportunities": opportunities,
            "hot_opportunities": 7,
            "cold_opportunities": 33,
            "protected_opportunities": 0,
            "feed_rows": 7,
            "evaluation_rows": 40,
            "provenance_rows": 90,
            "cold_archive_rows": 33,
            "compressed_archive_bytes": 151_049,
            "synthetic_active_feed_rows": 0,
            "max_projections_per_opportunity": 1,
            "max_evaluations_per_opportunity": 1,
            "cold_description_rows": 0,
            "cold_raw_payload_rows": 0,
            "cold_provenance_rows": 0,
            "cold_verbose_evaluation_rows": 0,
            "cold_max_reason_bytes": 94,
            "worker_jobs_total": 4,
        },
        "source_poll_status_counts": {"ok": coverage},
        "latest_source_poll": None,
        "dead_letter_error_class_counts": {},
        "public_relation_total_bytes": 1_933_312,
        "application_relation_total_bytes": 2_500_000,
        "storage_buckets": {
            "opportunity-artifacts": {"object_count": 33, "object_bytes": 151_049},
        },
        "top_relations": [],
        "top_indexes": [],
        "queue": {
            "pending": 0,
            "retry": 0,
            "running": 0,
            "expired_leases": 0,
            "oldest_due_age_seconds": None,
        },
        "database_revision": "0023_alembic_access",
    }


class IncrementalSourceBootstrapTests(unittest.TestCase):
    def test_capacity_projection_reproduces_reviewed_band_with_reserve(self):
        projected = projected_final_database_bytes(_state(), MODEL)

        self.assertGreater(projected, 150 * 1024 * 1024)
        self.assertLessEqual(projected, DATABASE_HARD_BUDGET)
        self.assertLess(projected, MODEL["projected_database_bytes_at_gate"] + 3 * 1024 * 1024)

    def test_projection_reserves_growth_and_decreases_as_corpus_converges(self):
        baseline = projected_final_database_bytes(_state(), MODEL)
        progressed = projected_final_database_bytes(
            _state(database_bytes=35_000_000, opportunities=3000, coverage=40),
            MODEL,
        )

        self.assertGreaterEqual(baseline, 14_101_651 + MODEL["benchmark_growth_bytes"])
        self.assertLess(progressed, baseline)
        self.assertGreaterEqual(progressed, 35_000_000)

    def test_projection_reflects_actual_over_budget_physical_size(self):
        current = _state(database_bytes=DATABASE_HARD_BUDGET + 1, opportunities=26_000, coverage=343)

        self.assertGreater(projected_final_database_bytes(current, MODEL), DATABASE_HARD_BUDGET)
        self.assertIn("physical_database_budget", invariant_failures(current, DATABASE_HARD_BUDGET + 1))

    def test_snapshot_invariants_stop_duplicate_projection_and_queue_leak(self):
        current = _state()
        current["counts"]["max_projections_per_opportunity"] = 2
        current["queue"]["pending"] = 1

        failures = invariant_failures(current, projected_final_database_bytes(current, MODEL))

        self.assertIn("duplicate_current_projection", failures)
        self.assertIn("queue_not_converged_at_source_boundary", failures)

    def test_registry_slice_is_stable_bounded_and_rejects_unbounded_inputs(self):
        ids = [f"source-{idx}" for idx in range(343)]

        self.assertEqual(select_registry_slice(ids, source_offset=125, max_sources=125), ids[125:250])
        with self.assertRaisesRegex(ValueError, "between 1 and 125"):
            select_registry_slice(ids, source_offset=0, max_sources=343)
        with self.assertRaisesRegex(ValueError, "inside"):
            select_registry_slice(ids, source_offset=343, max_sources=1)

    def test_workflow_is_manual_bounded_and_preserves_each_run_artifact(self):
        workflow = (ROOT / ".github/workflows/fr007-incremental-source-bootstrap.yml").read_text(encoding="utf-8")
        script = (ROOT / "scripts/fr007_incremental_source_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("timeout-minutes: 360", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("retention-days: 30", workflow)
        self.assertIn("--source-ids", script)
        self.assertIn("--time-budget-seconds", script)
        self.assertIn("source per normal scheduler/worker cycle", script)

    def test_incremental_runner_measures_before_and_after_each_source(self):
        ids = [f"source-{idx:03}" for idx in range(343)]
        registry = SimpleNamespace(_sources=set(ids), is_read_allowed=lambda _source_id: True)
        before = _state()
        after = _state(coverage=2)
        after["latest_source_poll"] = {
            "status": "ok", "raw_ingested": 12, "unique_opportunities": 8,
            "inserted": 8, "unchanged": 0, "updated": 0,
        }

        def runner(args):
            self.assertEqual(args[0:3], ["--mode", "all", "--source-ids"])
            print("captured internal payload marker")
            return 0

        with tempfile.TemporaryDirectory() as tmp, patch.object(incremental, "SourceRegistry", return_value=registry), patch.object(
            incremental, "_take_snapshot", side_effect=[before, after]
        ), patch.object(incremental, "hosted_bootstrap_main", side_effect=runner) as hosted, contextlib.redirect_stdout(
            io.StringIO()
        ) as stdout:
            report = incremental.run_incremental_bootstrap(
                source_offset=0,
                max_sources=1,
                output=Path(tmp) / "incremental.json",
            )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["sources"][0]["source_id"], ids[0])
        self.assertEqual(report["sources"][0]["before"]["database_bytes"], before["database_bytes"])
        self.assertEqual(report["sources"][0]["after"]["successful_source_coverage"], 2)
        self.assertEqual(hosted.call_count, 1)
        self.assertNotIn("captured internal payload marker", stdout.getvalue())

    def test_incremental_runner_pauses_before_write_if_projected_budget_fails(self):
        ids = [f"source-{idx:03}" for idx in range(343)]
        registry = SimpleNamespace(_sources=set(ids), is_read_allowed=lambda _source_id: True)
        before = _state(database_bytes=20_000_000)

        with tempfile.TemporaryDirectory() as tmp, patch.object(incremental, "SourceRegistry", return_value=registry), patch.object(
            incremental, "_take_snapshot", return_value=before
        ), patch.object(incremental, "hosted_bootstrap_main") as hosted:
            report = incremental.run_incremental_bootstrap(
                source_offset=0,
                max_sources=1,
                output=Path(tmp) / "incremental.json",
            )

        self.assertEqual(report["status"], "CAPACITY_OR_INVARIANT_STOP")
        self.assertIn("projected_database_budget", report["fatal_failures"])
        hosted.assert_not_called()


if __name__ == "__main__":
    unittest.main()
