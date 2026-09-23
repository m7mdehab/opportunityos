from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import fr007_hosted_bootstrap as bootstrap


class RepresentativeSourceScopeTests(unittest.TestCase):
    def test_source_schedule_is_limited_to_requested_read_allowed_source(self):
        registry = SimpleNamespace(
            _sources={"himalayas", "other-source"},
            path=Path("registry-does-not-exist.yaml"),
            is_read_allowed=lambda source_id: source_id == "himalayas",
        )
        session = MagicMock()

        with patch.object(bootstrap, "get_or_create_source_schedule") as schedule:
            count = bootstrap._source_schedules(
                session,
                registry,
                dry_run=False,
                source_id="himalayas",
            )

        self.assertEqual(count, 1)
        schedule.assert_called_once()
        self.assertEqual(schedule.call_args.args[1], "himalayas")

    def test_source_schedule_batch_is_explicit_and_limited_to_five(self):
        registry = SimpleNamespace(
            _sources={"himalayas", "other-source", "not-read-allowed"},
            path=Path("registry-does-not-exist.yaml"),
            is_read_allowed=lambda source_id: source_id != "not-read-allowed",
        )
        session = MagicMock()
        with patch.object(bootstrap, "get_or_create_source_schedule") as schedule:
            count = bootstrap._source_schedules(
                session,
                registry,
                dry_run=False,
                source_ids=["himalayas", "other-source"],
            )
        self.assertEqual(count, 2)
        self.assertEqual([call.args[1] for call in schedule.call_args_list], ["himalayas", "other-source"])
        session.commit.assert_called_once()

    def test_unscoped_bootstrap_is_rejected_before_database_access(self):
        with self.assertRaisesRegex(SystemExit, "requires an explicit"):
            bootstrap.main(["--mode", "bootstrap"])

    def test_source_batch_cli_is_capped_and_rejects_duplicates(self):
        too_many = ",".join(f"source-{idx}" for idx in range(6))
        with self.assertRaisesRegex(SystemExit, "limited to five"):
            bootstrap.main(["--mode", "bootstrap", "--source-ids", too_many])
        with self.assertRaisesRegex(SystemExit, "duplicate"):
            bootstrap.main(["--mode", "bootstrap", "--source-ids", "himalayas,himalayas"])

    def test_unregistered_or_disallowed_source_fails_before_creating_a_schedule(self):
        registry = SimpleNamespace(
            _sources={"himalayas", "disabled-source"},
            path=Path("registry-does-not-exist.yaml"),
            is_read_allowed=lambda source_id: source_id == "himalayas",
        )
        session = MagicMock()
        for source_id, message in (
            ("missing-source", "unregistered"),
            ("disabled-source", "not read-allowed"),
        ):
            with self.subTest(source_id=source_id):
                with self.assertRaisesRegex(ValueError, message):
                    bootstrap._source_schedules(
                        session,
                        registry,
                        dry_run=False,
                        source_id=source_id,
                    )
        session.commit.assert_not_called()

    def test_representative_path_rejects_existing_runnable_work(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.count.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "empty runnable worker queue"):
            bootstrap._assert_no_runnable_jobs(session)

    def test_cli_source_scope_is_bounded_and_only_all_mode(self):
        with self.assertRaisesRegex(SystemExit, "only with --mode all"):
            bootstrap.main(["--mode", "drain", "--source-id", "himalayas"])

        with self.assertRaisesRegex(SystemExit, "at most 2 jobs"):
            bootstrap.main(
                ["--mode", "all", "--source-id", "himalayas", "--max-jobs", "3"]
            )

    def test_all_mode_passes_explicit_source_id_to_scheduler(self):
        fake_engine = MagicMock()
        fake_session = MagicMock()
        fake_session.query.return_value.filter.return_value.count.return_value = 0
        fake_session.close.return_value = None
        factory = lambda: fake_session
        registry = SimpleNamespace(
            _sources={"himalayas", "other-source"},
            path=Path("registry-does-not-exist.yaml"),
            is_read_allowed=lambda source_id: source_id == "himalayas",
        )

        with (
            patch.dict(os.environ, {"OPOS_TARGET_DB_URL": "postgresql://not-a-real-secret/db"}, clear=False),
            patch.object(bootstrap, "SourceRegistry", return_value=registry),
            patch.object(bootstrap, "get_engine", return_value=fake_engine),
            patch.object(bootstrap, "get_session_factory", return_value=factory),
            patch.object(bootstrap, "get_or_create_source_schedule"),
            patch.object(bootstrap, "enqueue_due_sources", return_value=(
                [{"source_id": "himalayas", "job_id": "job-1"}], []
            )) as enqueue,
            patch.object(bootstrap, "_drain", return_value=2) as drain,
        ):
            rc = bootstrap.main([
                "--mode", "all", "--source-id", "himalayas", "--max-jobs", "2",
                "--time-budget-seconds", "480",
            ])

        self.assertEqual(rc, 0)
        self.assertEqual(enqueue.call_args.kwargs, {"registry": registry, "source_id": "himalayas"})
        drain.assert_called_once_with(
            factory,
            max_jobs=2,
            budget=480.0,
            worker_id=None,
        )
        fake_engine.dispose.assert_called_once()

    def test_all_mode_source_batch_enqueues_only_the_explicit_batch(self):
        fake_engine = MagicMock()
        fake_session = MagicMock()
        fake_session.query.return_value.filter.return_value.count.return_value = 0
        factory = lambda: fake_session
        registry = SimpleNamespace(
            _sources={"himalayas", "other-source", "unselected-source"},
            path=Path("registry-does-not-exist.yaml"),
            is_read_allowed=lambda _source_id: True,
        )
        ids = ["himalayas", "other-source"]
        selected = [{"source_id": sid, "job_id": f"job-{idx}"} for idx, sid in enumerate(ids)]
        with (
            patch.dict(os.environ, {"OPOS_TARGET_DB_URL": "postgresql://not-a-real-secret/db"}, clear=False),
            patch.object(bootstrap, "SourceRegistry", return_value=registry),
            patch.object(bootstrap, "get_engine", return_value=fake_engine),
            patch.object(bootstrap, "get_session_factory", return_value=factory),
            patch.object(bootstrap, "get_or_create_source_schedule"),
            patch.object(bootstrap, "enqueue_due_sources", return_value=(selected, [])) as enqueue,
            patch.object(bootstrap, "_drain", return_value=2),
        ):
            rc = bootstrap.main([
                "--mode", "all", "--source-ids", ",".join(ids),
                "--max-jobs", "2", "--time-budget-seconds", "480",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(
            enqueue.call_args.kwargs,
            {
                "registry": registry,
                "source_ids": ids,
                "force": True,
                "create_missing_schedules": False,
            },
        )
        fake_engine.dispose.assert_called_once()

    def test_generic_enqueue_never_creates_unseeded_registry_schedules(self):
        fake_engine = MagicMock()
        fake_session = MagicMock()
        factory = lambda: fake_session
        registry = SimpleNamespace(
            _sources={"himalayas", "other-source"},
            path=Path("registry-does-not-exist.yaml"),
            is_read_allowed=lambda _source_id: True,
        )
        with (
            patch.dict(os.environ, {"OPOS_TARGET_DB_URL": "postgresql://not-a-real-secret/db"}, clear=False),
            patch.object(bootstrap, "SourceRegistry", return_value=registry),
            patch.object(bootstrap, "get_engine", return_value=fake_engine),
            patch.object(bootstrap, "get_session_factory", return_value=factory),
            patch.object(bootstrap, "get_or_create_source_schedule") as schedule,
            patch.object(bootstrap, "enqueue_due_sources", return_value=([], [])) as enqueue,
        ):
            rc = bootstrap.main(["--mode", "enqueue"])
        self.assertEqual(rc, 0)
        schedule.assert_not_called()
        self.assertEqual(
            enqueue.call_args.kwargs,
            {"registry": registry, "create_missing_schedules": False},
        )
        fake_engine.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
