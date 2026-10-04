import json
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import SourcePollRunRecord, SourceScheduleRecord, WorkerJobRecord
from worker.handlers import BLOCKED_POLL_STATUS
from worker.scheduler import (
    DEFAULT_POLL_INTERVAL_HOURS,
    ENV_POLL_INTERVAL_HOURS,
    PollScheduler,
    OVERNIGHT_CATCHUP_CEILING_BYTES,
    controlled_catchup_capacity_allowed,
    enqueue_due_catchup_sources,
    enqueue_due_sources,
    get_poll_interval_hours,
    implicit_source_schedule_creation_enabled,
)
from scripts.db_capacity_guard import BLOCK_BYTES, WARN_BYTES, CapacitySnapshot

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

    def _reverify_jobs(self):
        session = self.session_factory()
        try:
            return (
                session.query(WorkerJobRecord)
                .filter_by(job_type="reverify_stale")
                .order_by(WorkerJobRecord.run_after.asc())
                .all()
            )
        finally:
            session.close()

    def _set_reverify_status(self, status):
        session = self.session_factory()
        try:
            job = session.query(WorkerJobRecord).filter_by(job_type="reverify_stale").one()
            job.status = status
            session.commit()
        finally:
            session.close()


class TestControlledOvernightCatchupEnqueue(unittest.TestCase):
    def test_catchup_capacity_boundary_and_readonly_recovery_always_refuse(self):
        self.assertTrue(controlled_catchup_capacity_allowed(
            CapacitySnapshot(390 * 1024 * 1024 - 1, False, False, "WARN_CAPACITY")
        ))
        for snapshot in (
            CapacitySnapshot(390 * 1024 * 1024, False, False, "WARN_CAPACITY"),
            CapacitySnapshot(100, True, False, "READ_ONLY"),
            CapacitySnapshot(100, False, True, "IN_RECOVERY"),
        ):
            self.assertFalse(controlled_catchup_capacity_allowed(snapshot))

    def test_exact_five_manifest_sources_enqueue_under_warning_capacity(self):
        source_ids = [f"fixture_{index}" for index in range(5)]
        registry = MagicMock()
        registry._sources = {source_id: object() for source_id in source_ids}
        registry.is_read_allowed.return_value = True
        session = MagicMock()
        session.get_bind.return_value.dialect.name = "postgresql"
        session.connection.return_value = object()
        empty_queue = MagicMock()
        empty_queue.filter.return_value.scalar.return_value = 0
        schedule_query = MagicMock()
        now = datetime(2026, 10, 2, 12, 0)
        schedules = [SimpleNamespace(
            source_id=source_id,
            cadence_hours=6.0,
            next_due_at=now - timedelta(minutes=1),
            cooldown_until=None,
        ) for source_id in source_ids]
        schedule_query.filter.return_value.with_for_update.return_value.all.return_value = schedules
        session.query.side_effect = [empty_queue, schedule_query]
        queue = MagicMock()
        queue.enqueue_job.side_effect = [f"job-{index}" for index in range(5)]
        warning_snapshot = CapacitySnapshot(WARN_BYTES, False, False, "WARN_CAPACITY")

        with patch("worker.scheduler.inspect_connection", return_value=warning_snapshot), \
             patch("worker.scheduler._lock_warning_poll_scheduler"), \
             patch("worker.scheduler.BackgroundWorkerQueue", return_value=queue):
            result = enqueue_due_catchup_sources(
                session, source_ids, registry=registry, now=now.replace(tzinfo=timezone.utc)
            )

        self.assertEqual([row["source_id"] for row in result], source_ids)
        self.assertEqual(queue.enqueue_job.call_count, 5)
        self.assertTrue(all(row.next_due_at > now for row in schedules))

    def test_frozen_due_manifest_survives_later_cadence_advance(self):
        source_ids = ["fixture_allowed"]
        registry = MagicMock()
        registry._sources = {source_ids[0]: object()}
        registry.is_read_allowed.return_value = True
        session = MagicMock()
        session.get_bind.return_value.dialect.name = "postgresql"
        session.connection.return_value = object()
        freeze_time = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 10, 2, 9, 10, tzinfo=timezone.utc)
        schedule = SimpleNamespace(
            source_id=source_ids[0], cadence_hours=6.0,
            next_due_at=datetime(2026, 10, 2, 12, 13),
            cooldown_until=None,
        )
        empty_queue = MagicMock()
        empty_queue.filter.return_value.scalar.return_value = 0
        schedule_query = MagicMock()
        schedule_query.filter.return_value.with_for_update.return_value.all.return_value = [schedule]
        session.query.side_effect = [empty_queue, schedule_query]
        queue = MagicMock()
        queue.enqueue_job.return_value = "job-catchup"

        with patch("worker.scheduler.inspect_connection", return_value=CapacitySnapshot(
            WARN_BYTES, False, False, "WARN_CAPACITY"
        )), patch("worker.scheduler._lock_warning_poll_scheduler"), \
             patch("worker.scheduler.BackgroundWorkerQueue", return_value=queue):
            result = enqueue_due_catchup_sources(
                session,
                source_ids,
                registry=registry,
                now=now,
                frozen_due_at={source_ids[0]: freeze_time - timedelta(minutes=1)},
                manifest_created_at=freeze_time,
            )

        self.assertEqual(result, [{"source_id": source_ids[0], "job_id": "job-catchup"}])
        queue.enqueue_job.assert_called_once()

    def test_frozen_due_manifest_rejects_source_not_due_at_freeze(self):
        source_ids = ["fixture_allowed"]
        registry = MagicMock()
        registry._sources = {source_ids[0]: object()}
        registry.is_read_allowed.return_value = True
        session = MagicMock()
        freeze_time = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "not due at manifest creation"):
            enqueue_due_catchup_sources(
                session,
                source_ids,
                registry=registry,
                frozen_due_at={source_ids[0]: freeze_time + timedelta(minutes=1)},
                manifest_created_at=freeze_time,
            )

    def test_explicit_lane_refuses_capacity_and_cooling_sources(self):
        source_ids = ["fixture_allowed"]
        registry = MagicMock()
        registry._sources = {source_ids[0]: object()}
        registry.is_read_allowed.return_value = True
        session = MagicMock()
        session.get_bind.return_value.dialect.name = "postgresql"
        session.connection.return_value = object()
        queue = MagicMock()
        cooling = SimpleNamespace(
            source_id=source_ids[0], cadence_hours=6.0,
            next_due_at=datetime(2026, 10, 2, 11, 0),
            cooldown_until=datetime(2026, 10, 2, 13, 0),
        )
        empty_queue = MagicMock()
        empty_queue.filter.return_value.scalar.return_value = 0
        schedule_query = MagicMock()
        schedule_query.filter.return_value.with_for_update.return_value.all.return_value = [cooling]
        session.query.side_effect = [empty_queue, schedule_query]
        with patch("worker.scheduler.inspect_connection", return_value=CapacitySnapshot(
            400 * 1024 * 1024, False, False, "HEAVY_WORK_PAUSED"
        )), patch("worker.scheduler._lock_warning_poll_scheduler"), \
             patch("worker.scheduler.BackgroundWorkerQueue", return_value=queue):
            with self.assertRaisesRegex(RuntimeError, "capacity"):
                enqueue_due_catchup_sources(session, source_ids, registry=registry)
        queue.enqueue_job.assert_not_called()

        with patch("worker.scheduler.inspect_connection", return_value=CapacitySnapshot(
            WARN_BYTES, False, False, "WARN_CAPACITY"
        )), patch("worker.scheduler._lock_warning_poll_scheduler"), \
             patch("worker.scheduler.BackgroundWorkerQueue", return_value=queue):
            with self.assertRaisesRegex(RuntimeError, "cooling"):
                enqueue_due_catchup_sources(session, source_ids, registry=registry,
                                             now=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc))
        queue.enqueue_job.assert_not_called()

class TestReadPolicyBoundary(TestPollSchedulerBase):
    def test_read_disabled_sources_never_enqueued(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=6)
        enqueued = scheduler.run_once()

        self.assertEqual(enqueued, ["fixture_allowed"])
        jobs = self._pending_poll_source_jobs()
        source_ids = {json.loads(j.payload_json)["source_id"] for j in jobs}
        self.assertIn("fixture_allowed", source_ids)
        self.assertNotIn("fixture_disabled", source_ids)


class TestBoundedHostedEnqueue(TestPollSchedulerBase):
    def test_capacity_pause_does_not_create_schedules_or_queue_jobs(self):
        session = self.session_factory()
        try:
            # Exercise the PostgreSQL-specific pre-enqueue branch while keeping
            # the fixture DB local and deterministic; the branch exits before
            # any PostgreSQL-only query or insert is reached.
            with patch("worker.scheduler._scheduler_capacity", return_value=CapacitySnapshot(
                BLOCK_BYTES, False, False, "HEAVY_WORK_PAUSED"
            )), patch(
                "worker.scheduler._lock_warning_poll_scheduler"
            ), patch(
                "scripts.db_capacity_guard.inspect_connection",
                return_value=CapacitySnapshot(BLOCK_BYTES, False, False, "HEAVY_WORK_PAUSED"),
            ):
                enqueued, skipped = enqueue_due_sources(
                    session,
                    registry=self.registry,
                    source_id="fixture_allowed",
                    now=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            self.assertEqual(enqueued, [])
            self.assertEqual(skipped, [{"source_id": "fixture_allowed", "reason": "capacity_pause"}])
            self.assertEqual(session.query(SourceScheduleRecord).count(), 0)
            self.assertEqual(session.query(WorkerJobRecord).count(), 0)
        finally:
            session.close()

    def test_warning_capacity_refuses_to_extend_a_full_five_source_poll_wave(self):
        session = self.session_factory()
        try:
            for index in range(5):
                session.add(WorkerJobRecord(
                    id=f"already-pending-{index}",
                    job_type="poll_source",
                    payload_json=json.dumps({"source_id": f"active-source-{index}"}),
                    status="PENDING",
                    retry_count=2,
                    max_retries=3,
                    run_after=datetime(2026, 1, 1),
                    created_at=datetime(2026, 1, 1),
                    updated_at=datetime(2026, 1, 1),
                ))
            session.commit()
            with patch(
                "worker.scheduler._scheduler_capacity",
                return_value=CapacitySnapshot(WARN_BYTES, False, False, "WARN_CAPACITY"),
            ), patch("worker.scheduler._lock_warning_poll_scheduler"):
                enqueued, skipped = enqueue_due_sources(
                    session, registry=self.registry,
                    now=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )
            self.assertEqual(enqueued, [])
            self.assertEqual(skipped[0]["reason"], "warning_capacity_poll_work_already_active")
            jobs = session.query(WorkerJobRecord).filter_by(job_type="poll_source").all()
            self.assertEqual(len(jobs), 5)
            self.assertTrue(all(job.retry_count == 2 for job in jobs))
        finally:
            session.close()

    def test_warning_capacity_enqueues_at_most_five_due_sources(self):
        registry_path = Path(self.temp_dir.name) / "multiple_sources.yaml"
        extra_sources = "".join(
            f"""  - source_id: fixture_{index}
    name: Fixture {index}
    category: employment
    automation:
      read: allowed
    policy_status: reviewed_ok
    observed:
      status: allowed_ok
"""
            for index in range(1, 7)
        )
        registry_path.write_text(
            _FIXTURE_REGISTRY_YAML.replace(
                "  - source_id: fixture_disabled",
                extra_sources + "  - source_id: fixture_disabled",
            ),
            encoding="utf-8",
        )
        registry = SourceRegistry(registry_path=registry_path)
        session = self.session_factory()
        try:
            with patch(
                "worker.scheduler._scheduler_capacity",
                return_value=CapacitySnapshot(WARN_BYTES, False, False, "WARN_CAPACITY"),
            ), patch("worker.scheduler._lock_warning_poll_scheduler"):
                enqueued, _ = enqueue_due_sources(
                    session, registry=registry,
                    now=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )
                self.assertEqual(len(enqueued), 5)
                again, skipped = enqueue_due_sources(
                    session, registry=registry,
                    now=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )
            self.assertEqual(again, [])
            self.assertEqual(skipped[0]["reason"], "warning_capacity_poll_work_already_active")
            self.assertEqual(
                session.query(WorkerJobRecord).filter_by(job_type="poll_source").count(),
                5,
            )
        finally:
            session.close()

    def test_explicit_active_poll_cap_applies_below_warning_capacity(self):
        registry_path = Path(self.temp_dir.name) / "bounded_normal_sources.yaml"
        extra_sources = "".join(
            f"""  - source_id: normal_{index}
    name: Normal {index}
    category: employment
    automation:
      read: allowed
    policy_status: reviewed_ok
    observed:
      status: allowed_ok
"""
            for index in range(1, 7)
        )
        registry_path.write_text(
            _FIXTURE_REGISTRY_YAML.replace(
                "  - source_id: fixture_disabled",
                extra_sources + "  - source_id: fixture_disabled",
            ),
            encoding="utf-8",
        )
        registry = SourceRegistry(registry_path=registry_path)
        session = self.session_factory()
        try:
            with patch("worker.scheduler._lock_warning_poll_scheduler"):
                enqueued, _ = enqueue_due_sources(
                    session,
                    registry=registry,
                    now=datetime(2026, 1, 2, tzinfo=timezone.utc),
                    max_active_poll_sources=5,
                )
            self.assertEqual(len(enqueued), 5)
            self.assertEqual(
                session.query(WorkerJobRecord).filter_by(job_type="poll_source").count(),
                5,
            )
        finally:
            session.close()

    def test_warning_capacity_ceiling_stops_new_source_work_without_advancing_schedule(self):
        session = self.session_factory()
        try:
            with patch(
                "worker.scheduler._scheduler_capacity",
                return_value=CapacitySnapshot(
                    OVERNIGHT_CATCHUP_CEILING_BYTES,
                    False,
                    False,
                    "WARN_CAPACITY",
                ),
            ), patch("worker.scheduler._lock_warning_poll_scheduler"):
                enqueued, skipped = enqueue_due_sources(
                    session,
                    registry=self.registry,
                    now=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )
            self.assertEqual(enqueued, [])
            self.assertEqual(skipped, [{"source_id": "*", "reason": "warning_capacity_ceiling"}])
            self.assertEqual(session.query(WorkerJobRecord).count(), 0)
            self.assertEqual(session.query(SourceScheduleRecord).count(), 0)
        finally:
            session.close()

    def test_due_before_freezes_one_sweep_and_prevents_repoll_during_same_run(self):
        session = self.session_factory()
        try:
            cutoff = datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc)
            later = cutoff + timedelta(hours=13)
            enqueued, _ = enqueue_due_sources(
                session,
                registry=self.registry,
                now=cutoff,
                due_before=cutoff,
            )
            self.assertEqual(len(enqueued), 1)
            job = session.query(WorkerJobRecord).filter_by(id=enqueued[0]["job_id"]).one()
            job.status = "COMPLETED"
            session.commit()

            # The source's next_due_at is now after the frozen cutoff. Even
            # though wall-clock time is much later, this same sweep must not
            # poll it a second time.
            again, _ = enqueue_due_sources(
                session,
                registry=self.registry,
                now=later,
                due_before=cutoff,
                create_missing_schedules=False,
            )
            self.assertEqual(again, [])
            self.assertEqual(
                session.query(WorkerJobRecord).filter_by(job_type="poll_source").count(),
                1,
            )
        finally:
            session.close()

    def test_existing_schedules_only_does_not_seed_registry_sources(self):
        session = self.session_factory()
        try:
            enqueued, skipped = enqueue_due_sources(
                session,
                registry=self.registry,
                now=datetime(2026, 1, 1, tzinfo=timezone.utc),
                create_missing_schedules=False,
            )
            self.assertEqual(enqueued, [])
            self.assertEqual(
                session.query(SourceScheduleRecord).count(),
                0,
                "routine hosted enqueue must not materialize schedules for every registry source",
            )
            self.assertEqual(
                session.query(WorkerJobRecord).filter_by(job_type="poll_source").count(),
                0,
            )
            self.assertIn(
                {"source_id": "fixture_disabled", "reason": "read_disabled_by_policy"},
                skipped,
            )
        finally:
            session.close()

    def test_explicit_source_filter_does_not_create_a_missing_schedule(self):
        session = self.session_factory()
        try:
            enqueued, _ = enqueue_due_sources(
                session,
                registry=self.registry,
                source_ids=["fixture_allowed"],
                now=datetime(2026, 1, 1, tzinfo=timezone.utc),
                create_missing_schedules=False,
            )
            self.assertEqual(enqueued, [])
            self.assertEqual(session.query(SourceScheduleRecord).count(), 0)
            self.assertEqual(session.query(WorkerJobRecord).count(), 0)
        finally:
            session.close()

    def test_hosted_poll_scheduler_does_not_implicitly_seed_registry(self):
        scheduler = PollScheduler(
            self.session_factory,
            registry=self.registry,
            initialize_missing_schedules=False,
        )
        self.assertEqual(scheduler.run_once(), [])
        session = self.session_factory()
        try:
            self.assertEqual(session.query(SourceScheduleRecord).count(), 0)
            self.assertEqual(
                session.query(WorkerJobRecord).filter_by(job_type="poll_source").count(),
                0,
            )
        finally:
            session.close()

    def test_hosted_environment_disables_implicit_schedule_initialization(self):
        self.assertTrue(implicit_source_schedule_creation_enabled("local"))
        for environment in ("cloud", "prod", "production"):
            with self.subTest(environment=environment):
                self.assertFalse(implicit_source_schedule_creation_enabled(environment))


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


class TestDurablePollCadence(TestPollSchedulerBase):
    def test_restart_respects_latest_successful_poll_time(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock_state = {"now": base + timedelta(hours=1)}

        session = self.session_factory()
        try:
            session.add(
                SourcePollRunRecord(
                    id="spr-before-restart",
                    source_id="fixture_allowed",
                    started_at=base.replace(tzinfo=None),
                    finished_at=base.replace(tzinfo=None),
                    status="ok",
                )
            )
            session.commit()
        finally:
            session.close()

        scheduler = PollScheduler(
            self.session_factory,
            registry=self.registry,
            interval_hours=6,
            clock=lambda: clock_state["now"],
        )

        self.assertEqual(
            scheduler.run_once(),
            [],
            "a restart must not repoll a source before its durable cadence elapses",
        )

        clock_state["now"] = base + timedelta(hours=6)
        self.assertEqual(scheduler.run_once(), ["fixture_allowed"])


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


class TestDurableReverifyCadence(TestPollSchedulerBase):
    def _scheduler(self, clock_state):
        return PollScheduler(
            self.session_factory,
            registry=self.registry,
            interval_hours=6,
            clock=lambda: clock_state["now"],
        )

    def test_first_tick_enqueues_one_reverify_job_with_durable_timestamp(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        scheduler = self._scheduler({"now": base})

        scheduler.run_once()

        jobs = self._reverify_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, "PENDING")
        self.assertEqual(jobs[0].run_after.replace(tzinfo=timezone.utc), base)

    def test_less_than_24_hours_does_not_enqueue_again(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock_state = {"now": base}
        scheduler = self._scheduler(clock_state)
        scheduler.run_once()
        self._set_reverify_status("COMPLETED")

        clock_state["now"] = base + timedelta(hours=23, minutes=59)
        scheduler.run_once()

        self.assertEqual(len(self._reverify_jobs()), 1)

    def test_at_least_24_hours_enqueues_once(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock_state = {"now": base}
        scheduler = self._scheduler(clock_state)
        scheduler.run_once()
        self._set_reverify_status("COMPLETED")

        clock_state["now"] = base + timedelta(hours=24)
        scheduler.run_once()

        jobs = self._reverify_jobs()
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[-1].run_after.replace(tzinfo=timezone.utc), clock_state["now"])

    def test_pending_and_retry_rows_deduplicate_even_when_due(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock_state = {"now": base}
        scheduler = self._scheduler(clock_state)
        scheduler.run_once()

        clock_state["now"] = base + timedelta(hours=24)
        scheduler.run_once()
        self.assertEqual(len(self._reverify_jobs()), 1)

        self._set_reverify_status("RETRY")
        scheduler.run_once()
        self.assertEqual(len(self._reverify_jobs()), 1)

    def test_fresh_scheduler_instance_preserves_recent_cadence(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first_clock = {"now": base}
        self._scheduler(first_clock).run_once()
        self._set_reverify_status("COMPLETED")

        restarted_clock = {"now": base + timedelta(hours=12)}
        self._scheduler(restarted_clock).run_once()

        self.assertEqual(len(self._reverify_jobs()), 1)

    def test_evidence_records_durable_queue_rows_and_cadence_decisions(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock_state = {"now": base}

        def snapshot(label):
            rows = [
                {
                    "id": job.id,
                    "status": job.status,
                    "run_after": job.run_after.isoformat(),
                }
                for job in self._reverify_jobs()
            ]
            print(
                "R3_QUEUE_SNAPSHOT "
                + json.dumps({"label": label, "now": clock_state["now"].isoformat(), "rows": rows})
            )

        self._scheduler(clock_state).run_once()
        snapshot("first_tick_enqueued")

        self._set_reverify_status("COMPLETED")
        clock_state["now"] = base + timedelta(hours=23, minutes=59)
        self._scheduler(clock_state).run_once()
        snapshot("less_than_24h_suppressed")

        clock_state["now"] = base + timedelta(hours=24)
        self._scheduler(clock_state).run_once()
        snapshot("at_24h_enqueued")

        self.assertEqual(len(self._reverify_jobs()), 2)


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


# FR-007 W11: blocked transport outcomes become durable cooldown state, not
# permanent historical bans. A restart before cooldown expiry remains
# suppressed; once the persisted cooldown/next-due instant expires, the source
# becomes eligible again without manual intervention.
class TestBlockedSourceDurableCooldown(unittest.TestCase):
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

    def test_blocked_history_suppresses_restart_until_bootstrap_cooldown_expires(self):
        self._seed_blocked_run("fixture_allowed", 403)
        scheduler = PollScheduler(
            self.session_factory,
            registry=self.registry,
            interval_hours=6,
            clock=lambda: datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(scheduler.run_once(), [])

        session = self.session_factory()
        try:
            row = session.query(SourceScheduleRecord).filter_by(source_id="fixture_allowed").one()
            self.assertEqual(row.cooldown_until, datetime(2026, 1, 2))
            self.assertEqual(row.next_due_at, datetime(2026, 1, 2))
        finally:
            session.close()

    def test_expired_bootstrap_cooldown_becomes_eligible_after_restart(self):
        self._seed_blocked_run("fixture_allowed", 429)
        before = PollScheduler(
            self.session_factory,
            registry=self.registry,
            interval_hours=6,
            clock=lambda: datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(before.run_once(), [])

        after = PollScheduler(
            self.session_factory,
            registry=self.registry,
            interval_hours=6,
            clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(after.run_once(), ["fixture_allowed"])

    def test_unblocked_source_is_unaffected(self):
        scheduler = PollScheduler(self.session_factory, registry=self.registry, interval_hours=0)
        self.assertEqual(scheduler.run_once(), ["fixture_allowed"])

if __name__ == "__main__":
    unittest.main()
