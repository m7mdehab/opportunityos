from __future__ import annotations

import unittest
from pathlib import Path

from scripts.fr007_storage_v2_source_gate import compare_snapshots


def _snapshot(database_bytes: int, relation_bytes: int, **overrides):
    counts = {
        "source_cold_archive_rows": 0,
        "source_compressed_archive_bytes": 0,
        "source_hot": 0,
        "source_cold": 0,
        "source_protected": 0,
        "source_opportunities": 0,
        "source_feed_rows": 0,
        "source_evaluation_rows": 0,
        "synthetic_active_feed_rows": 0,
        "max_projections_per_opportunity": 0,
        "max_evaluations_per_opportunity": 0,
        "cold_description_rows": 0,
        "cold_raw_payload_rows": 0,
        "cold_provenance_rows": 0,
        "cold_verbose_evaluation_rows": 0,
        "cold_max_reason_bytes": 0,
        "source_cold_max_reason_bytes": 0,
        "source_cold_body_rows": 0,
        "source_cold_provenance_rows": 0,
        "source_cold_verbose_evaluation_rows": 0,
    }
    counts.update(overrides)
    return {
        "source_id": "himalayas",
        "database_revision": "0023_alembic_access",
        "database_bytes": database_bytes,
        "public_relation_total_bytes": relation_bytes,
        "counts": counts,
        "latest_source_poll": {
            "status": "ok",
            "raw_ingested": 20,
            "unique_opportunities": 20,
        },
    }


def _capacity_benchmark(*, growth: int = 1024 * 1024, projected: int | None = None):
    return {
        "status": "PASS",
        "source_id": "himalayas",
        "database_revision": "0023_alembic_access",
        "population_opportunities": 26_000,
        "sample_unique_opportunities": 20,
        "benchmark_database_bytes_empty_schema": 12 * 1024 * 1024,
        "database_bytes_after_population": 12 * 1024 * 1024 + growth,
        "benchmark_growth_bytes": growth,
        "projected_database_bytes": projected,
        "projected_cold_archive_storage_bytes": 99_000_000,
        "top_relations": [{"relation": "opportunities", "total_bytes": 10_000_000}],
        "top_indexes": [{"index_name": "ix_opportunities_search_tsv", "bytes": 1_000_000}],
        "checks": {
            "exact_physical_benchmark_population": True,
            "projected_database_within_hard_budget": True,
        },
    }
class RepresentativeSourceEconomicsTests(unittest.TestCase):
    def test_registered_launcher_runs_a_fresh_credential_gate_before_source_work(self):
        root = Path(__file__).resolve().parents[1]
        launcher = (root / ".github/workflows/fr007-current-readiness-launcher.yml").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/fr007-storage-v2-representative-source.yml").read_text(encoding="utf-8")
        postgres_workflow = (root / ".github/workflows/fr007-storage-v2-postgres.yml").read_text(encoding="utf-8")
        regression_step = postgres_workflow.split("- name: Run complete PostgreSQL-backed subsystem tests", 1)[1].split(
            "- name: Upload PostgreSQL test log", 1
        )[0]
        self.assertIn("set -euo pipefail", regression_step)
        self.assertIn("python -m pytest -q 2>&1 | tee storage-v2-postgres-test.log", regression_step)
        self.assertIn("representative-credential-gate:", launcher)
        self.assertIn("mode: credential-probe", launcher)
        self.assertIn("needs: [representative-credential-gate]", launcher)
        self.assertIn("--source-id \"$SOURCE_ID\" --max-jobs 2 --time-budget-seconds 480", workflow)
        self.assertIn("OPOS_TARGET_DB_URL: ${{ secrets.CLOUD_DATABASE_URL }}", workflow)
        self.assertIn("image: postgres:17-alpine", workflow)
        self.assertIn("fr007_storage_v2_capacity_benchmark.py", workflow)
        self.assertIn("--capacity-benchmark w23-source-capacity-benchmark.json", workflow)
        probe = postgres_workflow.split("new-project-credential-probe:", 1)[1].split("private-cv-storage-verification:", 1)[0]
        self.assertIn('required_names = ("OPOS_TARGET_DB_URL", "CLOUD_DATABASE_URL")', probe)
        self.assertIn('direct_host = "db.sunjfepvdzfknglrjwhm.supabase.co"', probe)
        self.assertIn('pooler_host = "aws-0-eu-central-1.pooler.supabase.com"', probe)
        self.assertIn("endpoint-configuration-mismatch", probe)
        self.assertIn('phase = "parse-url"', probe)
        self.assertIn('category = "invalid-uri-format"', probe)
        self.assertIn('state[1] != "postgres"', probe)
        self.assertIn("effective database role as postgres", probe)
        self.assertNotIn("state[1] != expected_username", probe)
        self.assertIn("CREATE TEMP TABLE opos_fr007_credential_probe", probe)
        self.assertIn("both protected DB URL secrets must pass", probe)
        self.assertIn("classify_database_exception", probe)
        self.assertIn("route={route}", probe)
        self.assertNotIn("str(exc)", probe)

    def test_small_direct_tier_sample_passes_and_extrapolates(self):
        before = _snapshot(12 * 1024 * 1024, 2 * 1024 * 1024)
        after = _snapshot(
            12 * 1024 * 1024 + 50_000,
            2 * 1024 * 1024 + 50_000,
            source_cold_archive_rows=17,
            source_compressed_archive_bytes=34_000,
            source_hot=3,
            source_cold=17,
            source_opportunities=20,
            source_feed_rows=3,
            source_evaluation_rows=20,
            max_projections_per_opportunity=1,
            max_evaluations_per_opportunity=1,
        )
        archive_proof = {
            "source_id": "himalayas",
            "archive_objects_verified": 17,
            "compressed_bytes_downloaded": 34_000,
            "sha256_identity_verified": True,
            "download_scope": "source-scoped-cold-archives-only",
        }

        report = compare_snapshots(before, after, archive_proof, _capacity_benchmark())

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["raw_opportunities_received"], 20)
        self.assertEqual(report["cold_archive_objects_created"], 17)
        self.assertEqual(report["compressed_archive_bytes_created"], 34_000)
        self.assertLessEqual(report["projected_database_bytes"], 150 * 1024 * 1024)
        self.assertEqual(report["capacity_window_review"], "preferred<=150MiB")
        self.assertEqual(report["source_cold_archive_objects_after"], 17)

    def test_duplicated_cold_evaluation_fails_closed(self):
        before = _snapshot(12 * 1024 * 1024, 2 * 1024 * 1024)
        after = _snapshot(
            12 * 1024 * 1024 + 50_000,
            2 * 1024 * 1024 + 50_000,
            source_cold_archive_rows=17,
            source_compressed_archive_bytes=34_000,
            source_hot=3,
            source_cold=17,
            source_opportunities=20,
            source_feed_rows=3,
            source_evaluation_rows=20,
            max_projections_per_opportunity=1,
            max_evaluations_per_opportunity=1,
            cold_verbose_evaluation_rows=1,
        )
        archive_proof = {
            "source_id": "himalayas",
            "archive_objects_verified": 17,
            "compressed_bytes_downloaded": 34_000,
            "sha256_identity_verified": True,
            "download_scope": "source-scoped-cold-archives-only",
        }

        report = compare_snapshots(before, after, archive_proof, _capacity_benchmark())

        self.assertEqual(report["status"], "STOP_FOR_ARCHITECTURE_REVIEW")
        self.assertFalse(report["checks"]["cold_verbose_evaluation_absent"])

    def test_unbounded_cold_reason_text_fails_closed(self):
        before = _snapshot(12 * 1024 * 1024, 2 * 1024 * 1024)
        after = _snapshot(
            12 * 1024 * 1024 + 50_000,
            2 * 1024 * 1024 + 50_000,
            source_cold_archive_rows=17,
            source_compressed_archive_bytes=34_000,
            source_hot=3,
            source_cold=17,
            source_opportunities=20,
            source_feed_rows=3,
            source_evaluation_rows=20,
            max_projections_per_opportunity=1,
            max_evaluations_per_opportunity=1,
            source_cold_max_reason_bytes=1024,
        )
        archive_proof = {
            "source_id": "himalayas",
            "archive_objects_verified": 17,
            "compressed_bytes_downloaded": 34_000,
            "sha256_identity_verified": True,
            "download_scope": "source-scoped-cold-archives-only",
        }

        report = compare_snapshots(before, after, archive_proof, _capacity_benchmark())

        self.assertEqual(report["status"], "STOP_FOR_ARCHITECTURE_REVIEW")
        self.assertFalse(report["checks"]["source_cold_reason_representation_compact"])

    def test_empty_representative_source_is_not_an_economics_pass(self):
        before = _snapshot(12 * 1024 * 1024, 2 * 1024 * 1024)
        after = _snapshot(12 * 1024 * 1024, 2 * 1024 * 1024)
        after["latest_source_poll"] = {"status": "ok", "raw_ingested": 0, "unique_opportunities": 0}
        archive_proof = {
            "source_id": "himalayas",
            "archive_objects_verified": 0,
            "compressed_bytes_downloaded": 0,
            "sha256_identity_verified": True,
            "download_scope": "source-scoped-cold-archives-only",
        }

        with self.assertRaisesRegex(RuntimeError, "non-empty unique source sample"):
            compare_snapshots(before, after, archive_proof, _capacity_benchmark())

    def test_measured_projected_database_may_use_reviewed_150_to_200_mib_window(self):
        before = _snapshot(12 * 1024 * 1024, 2 * 1024 * 1024)
        after = _snapshot(
            12 * 1024 * 1024 + 50_000,
            2 * 1024 * 1024 + 50_000,
            source_cold_archive_rows=17,
            source_compressed_archive_bytes=34_000,
            source_hot=3,
            source_cold=17,
            source_opportunities=20,
            source_feed_rows=3,
            source_evaluation_rows=20,
            max_projections_per_opportunity=1,
            max_evaluations_per_opportunity=1,
        )
        archive_proof = {
            "source_id": "himalayas", "archive_objects_verified": 17,
            "compressed_bytes_downloaded": 34_000, "sha256_identity_verified": True,
            "download_scope": "source-scoped-cold-archives-only",
        }
        benchmark = _capacity_benchmark(growth=180 * 1024 * 1024)

        report = compare_snapshots(before, after, archive_proof, benchmark)

        self.assertEqual(report["status"], "PASS")
        self.assertGreater(report["projected_database_bytes"], 150 * 1024 * 1024)
        self.assertLessEqual(report["projected_database_bytes"], 200 * 1024 * 1024)
        self.assertEqual(
            report["capacity_window_review"],
            "inspected measured relation/index profile; hard ceiling<=200MiB",
        )

    def test_physical_projection_over_hard_database_budget_stops(self):
        before = _snapshot(12 * 1024 * 1024, 2 * 1024 * 1024)
        after = _snapshot(
            12 * 1024 * 1024 + 50_000,
            2 * 1024 * 1024 + 50_000,
            source_cold_archive_rows=17,
            source_compressed_archive_bytes=34_000,
            source_hot=3,
            source_cold=17,
            source_opportunities=20,
            source_feed_rows=3,
            source_evaluation_rows=20,
            max_projections_per_opportunity=1,
            max_evaluations_per_opportunity=1,
        )
        archive_proof = {
            "source_id": "himalayas", "archive_objects_verified": 17,
            "compressed_bytes_downloaded": 34_000, "sha256_identity_verified": True,
            "download_scope": "source-scoped-cold-archives-only",
        }

        report = compare_snapshots(
            before,
            after,
            archive_proof,
            _capacity_benchmark(growth=200 * 1024 * 1024),
        )

        self.assertEqual(report["status"], "STOP_FOR_ARCHITECTURE_REVIEW")
        self.assertFalse(report["checks"]["projected_database_within_hard_budget"])


if __name__ == "__main__":
    unittest.main()
