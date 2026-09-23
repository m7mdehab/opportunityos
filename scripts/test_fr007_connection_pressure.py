"""Regression coverage for FR-007 hosted worker connection pressure."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import fr007_hosted_bootstrap as bootstrap
from storage.engine import get_engine
from worker.handlers import make_poll_source_handler


class TestHostedWorkerPool(unittest.TestCase):
    def test_explicit_postgres_pool_is_small_and_finite(self) -> None:
        engine = get_engine(
            "postgresql+psycopg2://localhost/example",
            pool_size=2,
            max_overflow=0,
            pool_timeout=30.0,
            pool_pre_ping=True,
            application_name=bootstrap.HOSTED_WORKER_APPLICATION_NAME,
        )
        try:
            self.assertEqual(engine.pool.size(), 2)
            self.assertEqual(engine.pool._max_overflow, 0)
            self.assertEqual(engine.pool._timeout, 30.0)
        finally:
            engine.dispose()

    def test_invalid_pool_controls_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            get_engine(
                "postgresql+psycopg2://localhost/example",
                pool_size=0,
            )
        with self.assertRaises(ValueError):
            get_engine(
                "postgresql+psycopg2://localhost/example",
                max_overflow=-1,
            )
        with self.assertRaises(ValueError):
            get_engine(
                "postgresql+psycopg2://localhost/example",
                pool_timeout=0,
            )


class TestHostedBootstrapConnectionReuse(unittest.TestCase):
    def test_drain_injects_process_session_factory_into_default_handlers(self) -> None:
        fake_factory = object()
        fake_handlers = {"noop": lambda payload: None}
        runner = MagicMock()
        runner.run_once.return_value = False

        with (
            patch.object(bootstrap, "default_handler_registry", return_value=fake_handlers) as registry,
            patch.object(bootstrap, "WorkerRunner", return_value=runner) as runner_cls,
            patch.dict(os.environ, {"OPPORTUNITYOS_TRUTH_PACK_PATH": "founder/truth_pack.yaml.gz.b64"}),
        ):
            processed = bootstrap._drain(
                fake_factory,
                max_jobs=5,
                budget=10.0,
                worker_id="proof-worker-1",
            )

        self.assertEqual(processed, 0)
        registry.assert_called_once_with(
            session_factory=fake_factory,
            truth_pack_path="founder/truth_pack.yaml.gz.b64",
        )
        runner_cls.assert_called_once_with(
            fake_factory,
            fake_handlers,
            worker_id="proof-worker-1",
            poll_interval=0.1,
            allowed_job_types=None,
        )

    def test_source_shards_restrict_claims_to_poll_jobs(self) -> None:
        fake_factory = object()
        runner = MagicMock()
        runner.run_once.return_value = False

        with patch.object(bootstrap, "default_handler_registry", return_value={}), patch.object(
            bootstrap, "WorkerRunner", return_value=runner
        ) as runner_cls:
            bootstrap._drain(
                fake_factory,
                max_jobs=1,
                budget=10.0,
                worker_id="source-shard-1",
                poll_source_only=True,
            )

        runner_cls.assert_called_once_with(
            fake_factory,
            {},
            worker_id="source-shard-1",
            poll_interval=0.1,
            allowed_job_types={"poll_source"},
        )

    def test_all_mode_closes_enqueue_session_before_drain_and_uses_bounded_pool(self) -> None:
        fake_engine = MagicMock()
        fake_session = MagicMock()
        state = {"closed": False}

        def close_session() -> None:
            state["closed"] = True

        fake_session.close.side_effect = close_session

        def fake_factory():
            return fake_session

        def assert_closed_before_drain(session_factory, **kwargs):
            self.assertIs(session_factory, fake_factory)
            self.assertTrue(state["closed"], "bootstrap/enqueue session must close before drain starts")
            return 0

        db_url = "postgresql+psycopg2://db.example.test/opportunityos"

        with (
            patch.dict(os.environ, {"OPOS_TARGET_DB_URL": db_url}, clear=False),
            patch.object(bootstrap, "get_engine", return_value=fake_engine) as get_engine_mock,
            patch.object(bootstrap, "get_session_factory", return_value=fake_factory),
            patch.object(bootstrap, "SourceRegistry", return_value=MagicMock()),
            patch.object(bootstrap, "_source_schedules", return_value=3),
            patch.object(bootstrap, "enqueue_due_sources", return_value=([], [])),
            patch.object(bootstrap, "_drain", side_effect=assert_closed_before_drain) as drain_mock,
        ):
            rc = bootstrap.main(["--mode", "all", "--max-jobs", "1", "--time-budget-seconds", "1"])

        self.assertEqual(rc, 0)
        get_engine_mock.assert_called_once_with(
            db_url,
            pool_size=bootstrap.HOSTED_WORKER_POOL_SIZE,
            max_overflow=bootstrap.HOSTED_WORKER_MAX_OVERFLOW,
            pool_timeout=bootstrap.HOSTED_WORKER_POOL_TIMEOUT_SECONDS,
            pool_pre_ping=True,
            application_name=bootstrap.HOSTED_WORKER_APPLICATION_NAME,
        )
        drain_mock.assert_called_once()
        fake_engine.dispose.assert_called_once()


class TestPollSourceTransactionBoundary(unittest.TestCase):
    def test_network_fetch_happens_before_database_session_is_opened(self) -> None:
        session_calls = {"count": 0}

        class FakeSession:
            def rollback(self):
                return None

            def close(self):
                return None

        def session_factory():
            session_calls["count"] += 1
            return FakeSession()

        class FakeRegistry:
            def is_read_allowed(self, source_id):
                return True

        fake_pipeline = SimpleNamespace(
            acquisition=SimpleNamespace(rate_limiter=None),
        )

        def execute_discovery(*, source_ids):
            self.assertEqual(session_calls["count"], 0)
            return SimpleNamespace(health_reports=[], opportunities=[])

        fake_pipeline.execute_discovery = execute_discovery

        handler = make_poll_source_handler(
            registry=FakeRegistry(),
            transport=MagicMock(),
            session_factory=session_factory,
            pack_loader=lambda _path: SimpleNamespace(graph=None, truth_pack_hash="test-pack"),
        )

        with (
            patch("worker.handlers.OpportunityPipeline", return_value=fake_pipeline),
            patch("worker.handlers.StorageRepository"),
            patch("worker.handlers.persist_evaluated_batch", side_effect=RuntimeError("stop after session opens")),
            patch("worker.handlers._write_poll_run_record"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop after session opens"):
                handler({"source_id": "example-source"})

        self.assertGreaterEqual(session_calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
