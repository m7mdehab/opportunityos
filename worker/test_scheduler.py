import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import SourcePollRunRecord, WorkerJobRecord
from worker.handlers import BLOCKED_POLL_STATUS
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


# E4F3.2: per-source cadence, declared as a `poll_cadence_hours:` field on
# each registry entry (default when absent).
_CADENCE_FIXTURE_REGISTRY_YAML = """
sources:
  - source_id: fixture_hourly
    name: "Fixture Hourly (HN/Reddit/remote-board-like)"
    category: employment
    poll_cadence_hours: 1
    automation:
      read: allowed
    policy_status: reviewed_ok
    observed:
      status: allowed_ok
  - source_id: fixture_daily
    name: "Fixture Daily (procurement-like)"
    category: independent
    poll_cadence_hours: 24
    automation:
      read: allowed
    policy_status: reviewed_ok
    observed:
      status: allowed_ok
  - source_id: fixture_no_cadence_field
    name: "Fixture No Cadence Field (ATS-board-like, gets the default)"
    category: employment
    automation:
      read: allowed
    policy_status: reviewed_ok
    observed:
      status: allowed_ok
"""


class TestCadenceFieldPerSource(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        registry_path = Path(self.temp_dir.name) / "cadence_registry.yaml"
        registry_path.write_text(_CADENCE_FIXTURE_REGISTRY_YAML, encoding="utf-8")
        self.registry = SourceRegistry(registry_path=registry_path)

        db_path = Path(self.temp_dir.name) / "test_cadence.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_get_cadence_hours_reads_the_registry_field(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=6)
        self.assertEqual(scheduler.get_cadence_hours("fixture_hourly"), 1.0)
        self.assertEqual(scheduler.get_cadence_hours("fixture_daily"), 24.0)

    def test_source_with_no_cadence_field_gets_the_default(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=6)
        self.assertEqual(scheduler.get_cadence_hours("fixture_no_cadence_field"), 6.0)

    def test_each_source_class_is_scheduled_at_its_own_declared_cadence(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock_state = {"now": base}

        def fake_clock():
            return clock_state["now"]

        scheduler = PollScheduler(
            self.session_factory, registry=self.registry, interval_hours=6, clock=fake_clock
        )

        # T0: every source is due on its first tick regardless of cadence.
        first = set(scheduler.run_once())
        self.assertEqual(first, {"fixture_hourly", "fixture_daily", "fixture_no_cadence_field"})

        # Mark every enqueued job COMPLETED so the pending-job dedup guard
        # cannot be the reason a source is/isn't re-enqueued below.
        session = self.session_factory()
        try:
            for job in session.query(WorkerJobRecord).filter_by(job_type="poll_source").all():
                job.status = "COMPLETED"
            session.commit()
        finally:
            session.close()

        # T0 + 2h: the hourly source is due again; the 6h-default and 24h
        # (daily) sources are not.
        clock_state["now"] = base + timedelta(hours=2)
        self.assertEqual(set(scheduler.run_once()), {"fixture_hourly"})

        session = self.session_factory()
        try:
            for job in (
                session.query(WorkerJobRecord)
                .filter(
                    WorkerJobRecord.job_type == "poll_source",
                    WorkerJobRecord.status.in_(["PENDING", "RETRY"]),
                )
                .all()
            ):
                job.status = "COMPLETED"
            session.commit()
        finally:
            session.close()

        # T0 + 7h: the 6h-default source is now also due; the 24h (daily)
        # procurement-like source still is not.
        clock_state["now"] = base + timedelta(hours=7)
        self.assertEqual(set(scheduler.run_once()), {"fixture_hourly", "fixture_no_cadence_field"})


# E4F3.3: cadence is a floor, not a licence -- a source that returned 403 or
# 429 (worker.handlers.BLOCKED_POLL_STATUS) is not rescheduled in the same
# scheduler session no matter how due its cadence says it is.
class TestBlockedSourceNotRescheduledThisSession(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        registry_path = Path(self.temp_dir.name) / "fixture_registry.yaml"
        registry_path.write_text(_FIXTURE_REGISTRY_YAML, encoding="utf-8")
        self.registry = SourceRegistry(registry_path=registry_path)

        db_path = Path(self.temp_dir.name) / "test_blocked.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _seed_blocked_run(self, source_id: str, status_code: int):
        session = self.session_factory()
        try:
            session.add(
                SourcePollRunRecord(
                    id=f"spr-fixture-{status_code}",
                    source_id=source_id,
                    started_at=datetime(2026, 1, 1),
                    finished_at=datetime(2026, 1, 1),
                    status=BLOCKED_POLL_STATUS,
                    refusal_reason=f"http_{status_code}",
                )
            )
            session.commit()
        finally:
            session.close()

    def test_a_403_blocked_source_is_never_rescheduled_this_session(self):
        self._seed_blocked_run("fixture_allowed", 403)
        # interval_hours=0: every source is "due" on every tick regardless of
        # clock advancement, isolating the block check as the only thing that
        # could prevent an enqueue here.
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=0)

        self.assertEqual(scheduler.run_once(), [], "a 403-blocked source must not be enqueued")
        self.assertEqual(scheduler.run_once(), [], "still not enqueued on a later tick this session")

    def test_a_429_blocked_source_is_never_rescheduled_this_session(self):
        self._seed_blocked_run("fixture_allowed", 429)
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=0)

        self.assertEqual(scheduler.run_once(), [], "a 429-blocked source must not be enqueued")

    def test_an_unblocked_source_is_unaffected(self):
        # No blocked row seeded at all -- sanity check that the block-lookup
        # machinery itself doesn't suppress a normal, healthy source.
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=0)
        self.assertEqual(scheduler.run_once(), ["fixture_allowed"])


if __name__ == "__main__":
    unittest.main()
