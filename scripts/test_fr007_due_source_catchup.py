from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.fr007_due_source_catchup import (
    CatchupSafetyError,
    COHORT_START_BYTES,
    MAX_COHORT_SOURCES,
    MAX_PARALLEL_SOURCE_WORKERS,
    MAX_RETAINED_WORKER_CONNECTIONS,
    OVERNIGHT_CATCHUP_CEILING_BYTES,
    assert_founder_state_unchanged,
    cohort_for_index,
    freeze_manifest_entries,
    finalize_live_run,
    manifest_sha256,
    pending_manifest_sources,
    registry_due_entries_from_schedules,
    validate_evaluation_job_rows,
    validate_manifest,
    validate_wave_contract,
    _classify_source_terminal,
    _existing_after_freeze,
    _maintenance_reason_for_cohort,
    _predict_source_batch_bytes,
)
from scripts.migration_head_guard import migration_heads_match, repository_migration_heads


def _entries(count: int) -> list[dict[str, object]]:
    return [
        {"source_id": f"source:{i:03}", "next_due_at": f"2026-10-02T00:{i:02}:00+00:00", "cadence_hours": 6.0}
        for i in range(count)
    ]


class DueSourceManifestTests(unittest.TestCase):
    def test_manifest_is_deterministic_and_hashed_after_sort(self):
        rows = _entries(6)
        first = freeze_manifest_entries(rows)
        second = freeze_manifest_entries(list(reversed(rows)))
        self.assertEqual(first, second)
        self.assertEqual(manifest_sha256(first), manifest_sha256(second))
        validate_manifest({"version": 1, "entries": first, "sha256": manifest_sha256(first)})

    def test_duplicate_source_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            freeze_manifest_entries(_entries(1) * 2)

    def test_cohorts_are_fifty_and_newly_due_ids_cannot_join_the_frozen_slice(self):
        frozen = freeze_manifest_entries(_entries(341))
        first = cohort_for_index(frozen, 0)
        last = cohort_for_index(frozen, 6)
        self.assertEqual(len(first), 50)
        self.assertEqual(len(last), 41)
        self.assertEqual(len({row["source_id"] for row in first + last}), 91)
        with self.assertRaises(CatchupSafetyError):
            validate_wave_contract(
                manifest_ids={row["source_id"] for row in frozen},
                selected_ids=["newly-due-after-freeze"],
                due_ids={"newly-due-after-freeze"},
                read_allowed_ids={"newly-due-after-freeze"},
                queue_rows=[],
                database_bytes=100,
                worker_count=1,
            )

    def test_completed_identity_is_removed_and_cannot_be_processed_twice(self):
        frozen = freeze_manifest_entries(_entries(5))
        source_id = frozen[0]["source_id"]
        pending = pending_manifest_sources(frozen, {source_id: {"status": "success"}})
        self.assertNotIn(source_id, pending)
        self.assertEqual(len(pending), 4)

    def test_previous_success_does_not_suppress_source_due_at_freeze(self):
        frozen_at = datetime(2026, 10, 2, tzinfo=timezone.utc)
        before = {"status": "ok", "finished_at": "2026-10-01T22:00:00+00:00"}
        after = {"status": "ok", "finished_at": "2026-10-02T00:05:00+00:00"}
        from unittest.mock import patch
        with patch("scripts.fr007_due_source_catchup._latest_poll", return_value=before):
            self.assertIsNone(_existing_after_freeze(None, "source:1", frozen_at))
        with patch("scripts.fr007_due_source_catchup._latest_poll", return_value=after):
            result = _existing_after_freeze(None, "source:1", frozen_at)
        self.assertEqual(result["status"], "success")

    def test_freeze_excludes_cooling_and_read_disabled_and_never_adds_later_due_sources(self):
        now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
        registry = MagicMock()
        registry._sources = {f"source:{index}": object() for index in range(4)}
        registry.is_read_allowed.side_effect = lambda source_id: source_id != "source:3"
        schedules = [
            SimpleNamespace(source_id="source:0", next_due_at=now, cooldown_until=None, cadence_hours=6),
            SimpleNamespace(source_id="source:1", next_due_at=now, cooldown_until=now.replace(hour=13), cadence_hours=6),
            SimpleNamespace(source_id="source:2", next_due_at=now.replace(hour=13), cooldown_until=None, cadence_hours=6),
            SimpleNamespace(source_id="source:3", next_due_at=now, cooldown_until=None, cadence_hours=6),
        ]
        frozen = registry_due_entries_from_schedules(schedules, registry, now)
        self.assertEqual([item["source_id"] for item in frozen], ["source:0"])
        later_due = SimpleNamespace(
            source_id="source:2", next_due_at=now, cooldown_until=None, cadence_hours=6
        )
        self.assertEqual([item["source_id"] for item in frozen], ["source:0"])
        self.assertEqual(registry_due_entries_from_schedules([later_due], registry, now)[0]["source_id"], "source:2")


class DueSourceSafetyTests(unittest.TestCase):
    def _validate(self, **overrides):
        args = {
            "manifest_ids": {f"s{i}" for i in range(5)},
            "selected_ids": [f"s{i}" for i in range(5)],
            "due_ids": {f"s{i}" for i in range(5)},
            "read_allowed_ids": {f"s{i}" for i in range(5)},
            "queue_rows": [],
            "database_bytes": COHORT_START_BYTES - 1,
            "worker_count": 5,
        }
        args.update(overrides)
        validate_wave_contract(**args)

    def test_exact_five_source_wave_and_ten_connection_envelope_are_allowed(self):
        self._validate()
        self.assertEqual(MAX_PARALLEL_SOURCE_WORKERS, 5)
        self.assertEqual(MAX_RETAINED_WORKER_CONNECTIONS, 10)

    def test_cooling_or_read_disabled_source_fails_closed(self):
        with self.assertRaises(CatchupSafetyError):
            self._validate(due_ids={"s0", "s1", "s2", "s3"})
        with self.assertRaises(CatchupSafetyError):
            self._validate(read_allowed_ids={"s0", "s1", "s2", "s3"})

    def test_unexpected_queue_work_fails_closed(self):
        with self.assertRaisesRegex(CatchupSafetyError, "queue"):
            self._validate(queue_rows=[{"id": "unrelated", "job_type": "evaluate_new"}])

    def test_390_mib_and_above_refuse_polling(self):
        for size in (OVERNIGHT_CATCHUP_CEILING_BYTES, 400 * 1024 * 1024, 425 * 1024 * 1024):
            with self.subTest(size=size), self.assertRaisesRegex(CatchupSafetyError, "ceiling"):
                self._validate(database_bytes=size)

    def test_six_workers_or_connection_envelope_above_ten_is_rejected(self):
        with self.assertRaisesRegex(CatchupSafetyError, "five runtime"):
            self._validate(worker_count=6)
        self.assertLessEqual(MAX_PARALLEL_SOURCE_WORKERS * 2, MAX_RETAINED_WORKER_CONNECTIONS)

    def test_evaluation_followup_accepts_variable_wave_job_count_but_rejects_unrelated_work(self):
        rows = [{"id": f"eval-{i}", "job_type": "evaluate_new"} for i in range(7)]
        validate_evaluation_job_rows(rows, {row["id"] for row in rows})
        with self.assertRaisesRegex(CatchupSafetyError, "outside"):
            validate_evaluation_job_rows(rows + [{"id": "other", "job_type": "poll_source"}], {row["id"] for row in rows})

    def test_founder_owned_state_must_remain_identical(self):
        counts = {
            "feedback": 4,
            "activity": 8,
            "saved_views": 2,
            "cv_selections": 10,
            "cv_variant:master": 8,
        }
        assert_founder_state_unchanged(counts, dict(counts))
        # These are generated by normal evaluation and can grow or be refreshed
        # without changing a Founder-owned action or preference.
        assert_founder_state_unchanged(
            counts,
            {**counts, "cv_selections": 12, "cv_variant:master": 9, "cv_variant:data_engineer": 3},
        )
        with self.assertRaisesRegex(CatchupSafetyError, "Founder-state"):
            assert_founder_state_unchanged(counts, {**counts, "feedback": 5})

    def test_finalizer_refuses_an_incomplete_frozen_manifest_before_database_access(self):
        entries = freeze_manifest_entries(_entries(1))
        manifest = {"version": 1, "entries": entries, "sha256": manifest_sha256(entries)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"manifest": manifest, "results": {}}), encoding="utf-8")
            with self.assertRaisesRegex(CatchupSafetyError, "not reconciled"):
                finalize_live_run(path)

    def test_transient_source_failure_is_deferred_without_stopping_other_sources(self):
        outcome = _classify_source_terminal(
            {"status": "error", "error_message": "request timeout"},
            {"error_message": "Handler raised: RuntimeError"},
        )
        self.assertEqual(outcome, ("deferred", "transient_source_failure_after_normal_retries"))
        self.assertEqual(_classify_source_terminal({"status": "ok"}, {})[0], "success")

    def test_terminal_external_http_failure_is_deferred_after_normal_retries(self):
        outcome = _classify_source_terminal(
            {"status": "error", "error_message": "HTTP Error 404: Not Found"},
            {"error_message": "Handler raised: HTTPError"},
        )
        self.assertEqual(outcome, ("deferred", "external_source_http_failure"))
        rate_limited = _classify_source_terminal(
            {"status": "error", "error_message": "429 Client Error: Too Many Requests"},
            {"error_message": "Handler raised: HTTPError"},
        )
        self.assertEqual(rate_limited[0], "deferred")
        unavailable = _classify_source_terminal(
            {"status": "error", "error_message": "HTTP Error 503: Service Unavailable"},
            {"error_message": "Handler raised: HTTPError"},
        )
        self.assertEqual(unavailable[0], "deferred")

    def test_wave_growth_projection_uses_measured_rate_with_floor_and_margin(self):
        state = {"cohorts": [], "last_wave": None}
        start = OVERNIGHT_CATCHUP_CEILING_BYTES - (512 * 1024)
        self.assertGreaterEqual(
            _predict_source_batch_bytes(state, start, 5), OVERNIGHT_CATCHUP_CEILING_BYTES
        )
        state["cohorts"] = [{"processed_sources": 50, "database_growth_bytes": 10_000_000}]
        projected = _predict_source_batch_bytes(state, start, 5)
        self.assertGreaterEqual(projected, start + int(200_000 * 5 * 1.5))

    def test_cohort_projection_uses_390_mib_ceiling_after_current_size_is_reclaimed(self):
        self.assertIsNone(
            _maintenance_reason_for_cohort(
                COHORT_START_BYTES - 1, COHORT_START_BYTES + 1
            )
        )
        self.assertEqual(
            _maintenance_reason_for_cohort(COHORT_START_BYTES, COHORT_START_BYTES),
            "measured_capacity_reaches_380_mib",
        )
        self.assertEqual(
            _maintenance_reason_for_cohort(
                COHORT_START_BYTES - 1, OVERNIGHT_CATCHUP_CEILING_BYTES
            ),
            "projected_capacity_reaches_390_mib",
        )

    def test_parser_and_database_errors_are_not_silently_deferred(self):
        for message in ("ValueError malformed source response", "psycopg IntegrityError"):
            with self.subTest(message=message), self.assertRaises(CatchupSafetyError):
                _classify_source_terminal(
                    {"status": "error", "error_message": message},
                    {"error_message": message},
                )


class MigrationHeadTests(unittest.TestCase):
    def test_current_repository_head_is_accepted_and_stale_head_fails_closed(self):
        heads = repository_migration_heads()
        self.assertTrue(heads)
        self.assertTrue(migration_heads_match(heads, heads))
        self.assertFalse(migration_heads_match(("0025_current_feed_fast_path",), heads))

    def test_runtime_workflow_is_main_only_and_serialized_with_worker_drain(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/fr007-due-source-overnight-catchup.yml").read_text(encoding="utf-8")
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("group: fr007-worker-drain", workflow)
        self.assertIn("--cohort-index", workflow)
        self.assertIn("retention-days: 30", workflow)


if __name__ == "__main__":
    unittest.main()
