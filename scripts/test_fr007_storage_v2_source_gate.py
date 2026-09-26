from __future__ import annotations

import unittest
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import fr007_storage_v2_source_gate as source_gate
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
        "database_revision": "0025_current_feed_fast_path",
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
        "database_revision": "0025_current_feed_fast_path",
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


def _archive_inventory_connection(objects: int, compressed_bytes: int):
    result = MagicMock()
    result.mappings.return_value.one.return_value = {
        "archive_objects": objects,
        "compressed_bytes": compressed_bytes,
    }
    connection = MagicMock()
    connection.execute.return_value = result
    return connection


class RepresentativeSourceEconomicsTests(unittest.TestCase):
    def test_archive_storage_timeout_is_retried_with_bounded_backoff(self):
        attempts = {"count": 0}

        def flaky_get(*_args, **_kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                try:
                    raise TimeoutError("transient")
                except TimeoutError as cause:
                    raise source_gate.ArtifactStorageError("private artifact get failed") from cause
            return b"verified"

        with patch.object(source_gate, "get_cold_object", side_effect=flaky_get), patch.object(
            source_gate.time, "sleep"
        ) as sleep:
            body = source_gate._get_cold_object_with_retry("opaque-key", "opaque-sha", client=object())

        self.assertEqual(body, b"verified")
        self.assertEqual(attempts["count"], 2)
        sleep.assert_called_once_with(0.5)

    def test_archive_storage_not_found_is_fail_closed_without_retry(self):
        from urllib.error import HTTPError

        error = source_gate.ArtifactStorageError("private artifact get failed")
        error.__cause__ = HTTPError("https://redacted.invalid", 404, "not found", {}, None)
        with patch.object(source_gate, "get_cold_object", side_effect=error) as get_object:
            with self.assertRaisesRegex(RuntimeError, "object_not_found"):
                source_gate._get_cold_object_with_retry("opaque-key", "opaque-sha", client=object())
        get_object.assert_called_once()

    def test_incremental_archive_verification_is_source_scoped_and_bounded(self):
        since = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)
        record = {
            "opportunity_id": "opportunity-id",
            "content_hash": "content-hash",
            "object_key": "cold/one.gz",
            "payload_sha256": "payload-sha",
            "compressed_size_bytes": 4,
            "storage_backend": "supabase_storage",
        }
        result = MagicMock()
        result.mappings.return_value.all.return_value = [record]
        connection = MagicMock()
        connection.execute.return_value = result
        client = MagicMock()

        with (
            patch.object(source_gate, "client_from_env", return_value=client),
            patch.object(source_gate, "get_cold_object", return_value=b"data") as get_object,
            patch.object(source_gate, "unpack", return_value={"canonical_description": "real text"}) as unpack,
        ):
            proof = source_gate.verify_source_archives(
                connection,
                source_id="himalayas",
                since=since,
                max_objects=10,
                max_archive_bytes=1024,
            )

        statement, params = connection.execute.call_args.args
        self.assertIn("a.archived_at > CAST", str(statement))
        self.assertEqual(params["source_id"], "himalayas")
        self.assertEqual(params["since"], since)
        self.assertEqual(params["max_objects_plus_one"], 11)
        self.assertEqual(proof["archive_objects_verified"], 1)
        self.assertEqual(proof["compressed_bytes_downloaded"], 4)
        self.assertTrue(proof["sha256_identity_verified"])
        self.assertNotIn("last_verified_opportunity_id", proof)
        get_object.assert_called_once_with("cold/one.gz", "payload-sha", client=client)
        unpack.assert_called_once_with(
            b"data", "payload-sha", opportunity_id="opportunity-id", content_hash="content-hash"
        )
        client.ensure_private_bucket.assert_called_once()

    def test_incremental_archive_verification_fails_closed_at_object_limit(self):
        rows = [
            {
                "opportunity_id": f"op-{idx}",
                "content_hash": f"content-{idx}",
                "object_key": f"cold/{idx}.gz",
                "payload_sha256": f"sha-{idx}",
                "compressed_size_bytes": 1,
                "storage_backend": "supabase_storage",
            }
            for idx in range(2)
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        connection = MagicMock()
        connection.execute.return_value = result
        with patch.object(source_gate, "client_from_env") as client_from_env:
            with self.assertRaisesRegex(RuntimeError, "bounded verifier limit"):
                source_gate.verify_source_archives(connection, source_id="himalayas", max_objects=1)
        client_from_env.assert_not_called()

    def test_successful_corpus_archive_query_uses_successful_sources_and_stable_cursor(self):
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        connection = MagicMock()
        connection.execute.return_value = result

        proof = source_gate.verify_source_archives(
            connection,
            source_id=source_gate.CORPUS_SOURCE_ID,
            max_objects=500,
            max_archive_bytes=32 * 1024 * 1024,
            after_opportunity_id="opaque-cursor",
            include_cursor=True,
        )

        statement, params = connection.execute.call_args.args
        self.assertIn("o.source_id IN (SELECT DISTINCT source_id", str(statement))
        self.assertIn("o.id > :after_opportunity_id", str(statement))
        self.assertNotIn("source_id", params)
        self.assertEqual(params["after_opportunity_id"], "opaque-cursor")
        self.assertEqual(proof["download_scope"], "successful-corpus-cold-archives-only")
        self.assertEqual(proof["last_verified_opportunity_id"], "opaque-cursor")
        self.assertFalse(proof["has_more"])

    def test_successful_corpus_archive_page_accepts_the_one_row_pagination_sentinel(self):
        rows = [
            {
                "opportunity_id": f"op-{idx:04d}",
                "content_hash": f"content-{idx}",
                "object_key": f"cold/{idx}.gz",
                "payload_sha256": f"sha-{idx}",
                "compressed_size_bytes": 1,
                "storage_backend": "supabase_storage",
            }
            for idx in range(501)
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        connection = MagicMock()
        connection.execute.return_value = result
        client = MagicMock()

        with (
            patch.object(source_gate, "client_from_env", return_value=client),
            patch.object(source_gate, "get_cold_object", return_value=b"x") as get_object,
            patch.object(source_gate, "unpack", return_value={"canonical_description": "real text"}),
        ):
            proof = source_gate.verify_source_archives(
                connection,
                source_id=source_gate.CORPUS_SOURCE_ID,
                max_objects=500,
                max_archive_bytes=32 * 1024 * 1024,
                include_cursor=True,
            )

        self.assertEqual(proof["archive_objects_verified"], 500)
        self.assertEqual(proof["compressed_bytes_downloaded"], 500)
        self.assertEqual(proof["last_verified_opportunity_id"], "op-0499")
        self.assertTrue(proof["has_more"])
        self.assertEqual(get_object.call_count, 500)

    def test_archive_object_checksum_verification_uses_at_most_five_concurrent_downloads(self):
        rows = [
            {
                "opportunity_id": f"op-{idx}",
                "content_hash": f"content-{idx}",
                "object_key": f"cold/{idx}.gz",
                "payload_sha256": f"sha-{idx}",
                "compressed_size_bytes": 1,
                "storage_backend": "supabase_storage",
            }
            for idx in range(5)
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        connection = MagicMock()
        connection.execute.return_value = result
        barrier = threading.Barrier(5, timeout=5.0)
        lock = threading.Lock()
        concurrent = {"active": 0, "peak": 0}

        def download(*_args, **_kwargs):
            with lock:
                concurrent["active"] += 1
                concurrent["peak"] = max(concurrent["peak"], concurrent["active"])
            barrier.wait()
            with lock:
                concurrent["active"] -= 1
            return b"x"

        with patch.object(source_gate, "client_from_env", return_value=MagicMock()), patch.object(
            source_gate, "get_cold_object", side_effect=download
        ), patch.object(source_gate, "unpack", return_value={"canonical_description": "real"}):
            proof = source_gate.verify_source_archives(
                connection,
                source_id="himalayas",
                max_objects=5,
                max_archive_bytes=1024,
            )

        self.assertEqual(proof["archive_objects_verified"], 5)
        self.assertEqual(proof["compressed_bytes_downloaded"], 5)
        self.assertEqual(concurrent["peak"], 5)

    def test_successful_corpus_archives_are_verified_in_bounded_pages(self):
        first = {
            "archive_objects_verified": 500,
            "compressed_bytes_downloaded": 2_000_000,
            "last_verified_opportunity_id": "opportunity-0500",
        }
        second = {
            "archive_objects_verified": 313,
            "compressed_bytes_downloaded": 1_252_000,
            "last_verified_opportunity_id": "opportunity-0813",
        }
        connection = _archive_inventory_connection(813, 3_252_000)
        with patch.object(source_gate, "verify_source_archives", side_effect=[first, second]) as verify:
            proof = source_gate.verify_successful_corpus_archives(connection)

        self.assertEqual(proof["archive_objects_verified"], 813)
        self.assertEqual(proof["compressed_bytes_downloaded"], 3_252_000)
        self.assertEqual(proof["pages_verified"], 2)
        self.assertEqual(proof["current_cold_archive_objects"], 813)
        self.assertEqual(proof["current_cold_archive_compressed_bytes"], 3_252_000)
        calls = [call.kwargs for call in verify.call_args_list]
        self.assertEqual(calls[0]["max_objects"], 500)
        self.assertEqual(calls[0]["max_archive_bytes"], 32 * 1024 * 1024)
        self.assertIsNone(calls[0]["after_opportunity_id"])
        self.assertEqual(calls[1]["after_opportunity_id"], "opportunity-0500")

    def test_successful_corpus_archive_verifier_stops_on_aggregate_object_limit(self):
        connection = _archive_inventory_connection(source_gate.CORPUS_ARCHIVE_OBJECT_LIMIT + 1, 1)
        with patch.object(source_gate, "verify_source_archives") as verify:
            with self.assertRaisesRegex(RuntimeError, "total object or egress bound"):
                source_gate.verify_successful_corpus_archives(connection)
        verify.assert_not_called()

    def test_successful_corpus_archive_verifier_covers_26k_scale_with_one_bounded_pass(self):
        expected_objects = 26_000
        expected_bytes = 64 * 1024 * 1024 + 1
        connection = _archive_inventory_connection(expected_objects, expected_bytes)
        pages = [
            {
                "archive_objects_verified": 500,
                "compressed_bytes_downloaded": 1_290_555,
                "last_verified_opportunity_id": f"cursor-{index}",
            }
            for index in range(51)
        ]
        pages.append({
            "archive_objects_verified": 500,
            "compressed_bytes_downloaded": 1_290_560,
            "last_verified_opportunity_id": "cursor-final",
        })
        pages.append({"archive_objects_verified": 0, "compressed_bytes_downloaded": 0})
        with patch.object(source_gate, "verify_source_archives", side_effect=pages) as verify:
            proof = source_gate.verify_successful_corpus_archives(connection)

        self.assertEqual(proof["archive_objects_verified"], expected_objects)
        self.assertEqual(proof["compressed_bytes_downloaded"], expected_bytes)
        self.assertEqual(proof["pages_verified"], 52)
        self.assertEqual(verify.call_count, 53)
        self.assertGreater(source_gate.CORPUS_ARCHIVE_TOTAL_LIMIT, expected_bytes)
        self.assertGreaterEqual(source_gate.CORPUS_ARCHIVE_OBJECT_LIMIT, 26_000)

    def test_successful_corpus_archive_verifier_stops_before_egress_cap(self):
        connection = _archive_inventory_connection(1, source_gate.CORPUS_ARCHIVE_TOTAL_LIMIT + 1)
        with patch.object(source_gate, "verify_source_archives") as verify:
            with self.assertRaisesRegex(RuntimeError, "total object or egress bound"):
                source_gate.verify_successful_corpus_archives(connection)
        verify.assert_not_called()

    def test_registered_launcher_runs_a_fresh_credential_gate_before_source_work(self):
        root = Path(__file__).resolve().parents[1]
        launcher = (root / ".github/workflows/fr007-current-readiness-launcher.yml").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/fr007-storage-v2-representative-source.yml").read_text(encoding="utf-8")
        source_gate_script = (root / "scripts/fr007_storage_v2_source_gate.py").read_text(encoding="utf-8")
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
        self.assertIn("benchmark_only:", workflow)
        self.assertIn("verify_successful_corpus_archives", source_gate_script)
        self.assertIn("capacity-reforecast", launcher)
        self.assertIn("source_id: __successful_corpus__", launcher)
        self.assertIn("benchmark_only: true", launcher)
        self.assertIn("--model-output w23-capacity-model.json", workflow)
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
