import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import WorkerJobRecord
from worker.scheduler import (
    DEFAULT_POLL_INTERVAL_HOURS,
    ENV_POLL_INTERVAL_HOURS,
    PollScheduler,
    get_poll_interval_hours,
)

# Minimal fixture registry: one read-allowed source, one read-disabled source.
# Mirrors the real docs/SOURCE_REGISTRY.yaml shape closely enough for
# SourceRegistry._parse_yaml_sources's line-oriented regex parser.
_FIXTURE_REGISTRY_YAML = """
sources:
  - source_id: fixture_allowed
    name: "Fixture Allowed"
    category: employment
    automation:
      read: allowed
    policy_status: reviewed_ok
    observed:
      status: allowed_ok
  - source_id: fixture_disabled
    name: "Fixture Disabled"
    category: employment
    automation:
      read: disabled
    policy_status: policy_prohibits
    observed:
      status: unknown
"""


class TestPollSchedulerBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        registry_path = Path(self.temp_dir.name) / "fixture_registry.yaml"
        registry_path.write_text(_FIXTURE_REGISTRY_YAML, encoding="utf-8")
        self.registry = SourceRegistry(registry_path=registry_path)

        db_path = Path(self.temp_dir.name) / "test_scheduler.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _pending_poll_source_jobs(self):
        session = self.session_factory()
        try:
            return (
                session.query(WorkerJobRecord)
                .filter_by(job_type="poll_source")
                .all()
            )
        finally:
            session.close()


class TestReadPolicyBoundary(TestPollSchedulerBase):
    def test_read_disabled_sources_never_enqueued(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=6)
        enqueued = scheduler.run_once()

        self.assertEqual(enqueued, ["fixture_allowed"])
        jobs = self._pending_poll_source_jobs()
        source_ids = {json.loads(j.payload_json)["source_id"] for j in jobs}
        self.assertIn("fixture_allowed", source_ids)
        self.assertNotIn("fixture_disabled", source_ids)


class TestOneJobPerSourcePerTick(TestPollSchedulerBase):
    def test_no_duplicate_while_a_poll_source_job_is_already_pending(self):
        # interval_hours=0: every source is "due" on every call regardless of
        # clock advancement, so this isolates the pending-job dedup guard
        # (rather than the due-interval check) as the thing preventing a
        # second enqueue.
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=0)

        first = scheduler.run_once()
        self.assertEqual(first, ["fixture_allowed"])

        second = scheduler.run_once()
        self.assertEqual(second, [], "must not enqueue a duplicate while a PENDING poll_source job exists")

        jobs = self._pending_poll_source_jobs()
        fixture_allowed_jobs = [j for j in jobs if json.loads(j.payload_json)["source_id"] == "fixture_allowed"]
        self.assertEqual(len(fixture_allowed_jobs), 1)

    def test_no_duplicate_while_a_retry_poll_source_job_is_pending(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=0)
        scheduler.run_once()

        session = self.session_factory()
        try:
            job = session.query(WorkerJobRecord).filter_by(job_type="poll_source").one()
            job.status = "RETRY"
            session.commit()
        finally:
            session.close()

        second = scheduler.run_once()
        self.assertEqual(second, [])
        jobs = self._pending_poll_source_jobs()
        self.assertEqual(len(jobs), 1)

    def test_enqueues_again_once_the_prior_job_is_no_longer_pending(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=0)
        scheduler.run_once()

        session = self.session_factory()
        try:
            job = session.query(WorkerJobRecord).filter_by(job_type="poll_source").one()
            job.status = "COMPLETED"
            session.commit()
        finally:
            session.close()

        second = scheduler.run_once()
        self.assertEqual(second, ["fixture_allowed"])
        jobs = self._pending_poll_source_jobs()
        self.assertEqual(len(jobs), 2)


class TestIntervalMath(TestPollSchedulerBase):
    def test_interval_elapsed_gates_reenqueue_with_injected_clock(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock_state = {"now": base}

        def fake_clock():
            return clock_state["now"]

        scheduler = PollScheduler(
            self.session_factory, registry=self.registry, interval_hours=6, clock=fake_clock
        )

        # T0: first tick -- every source is due (never enqueued before).
        self.assertEqual(scheduler.run_once(), ["fixture_allowed"])

        # Simulate the job having already been processed so the pending-job
        # dedup guard cannot be the reason a later tick does or doesn't
        # enqueue -- only the interval-math due check is exercised below.
        session = self.session_factory()
        try:
            job = session.query(WorkerJobRecord).filter_by(job_type="poll_source").one()
            job.status = "COMPLETED"
            session.commit()
        finally:
            session.close()

        # T0 + 3h: interval is 6h, not yet due.
        clock_state["now"] = base + timedelta(hours=3)
        self.assertEqual(scheduler.run_once(), [])

        # T0 + 5h59m: still not due.
        clock_state["now"] = base + timedelta(hours=5, minutes=59)
        self.assertEqual(scheduler.run_once(), [])

        # T0 + 6h: exactly the interval has elapsed -- due again.
        clock_state["now"] = base + timedelta(hours=6)
        self.assertEqual(scheduler.run_once(), ["fixture_allowed"])

    def test_first_tick_on_a_fresh_scheduler_is_always_due(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=6)
        self.assertEqual(scheduler.run_once(), ["fixture_allowed"])


class TestGetPollIntervalHours(unittest.TestCase):
    def test_default_when_unset(self):
        self.assertEqual(get_poll_interval_hours(env={}), DEFAULT_POLL_INTERVAL_HOURS)

    def test_reads_env_override(self):
        self.assertEqual(get_poll_interval_hours(env={ENV_POLL_INTERVAL_HOURS: "2"}), 2.0)

    def test_falls_back_on_invalid_value(self):
        self.assertEqual(get_poll_interval_hours(env={ENV_POLL_INTERVAL_HOURS: "not-a-number"}), DEFAULT_POLL_INTERVAL_HOURS)

    def test_falls_back_on_nonpositive_value(self):
        self.assertEqual(get_poll_interval_hours(env={ENV_POLL_INTERVAL_HOURS: "0"}), DEFAULT_POLL_INTERVAL_HOURS)
        self.assertEqual(get_poll_interval_hours(env={ENV_POLL_INTERVAL_HOURS: "-5"}), DEFAULT_POLL_INTERVAL_HOURS)

    def test_real_os_environ_used_when_env_not_injected(self):
        # No os.environ mutation here (avoids cross-test leakage); just
        # confirms the default-argument path resolves without error.
        self.assertGreater(get_poll_interval_hours(), 0)


if __name__ == "__main__":
    unittest.main()
