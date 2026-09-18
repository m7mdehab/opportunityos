"""``PollScheduler``: periodically enqueues ``poll_source`` jobs.

One tick enqueues at most one ``poll_source`` job per read-allowed source
whose interval has elapsed, and never enqueues a duplicate while a
PENDING/RETRY/RUNNING ``poll_source`` job for that source is already in flight.

Read-disabled sources are never enqueued. This is a policy boundary
enforced by ``opportunity.registry.SourceRegistry.is_read_allowed`` (backed
by ``docs/SOURCE_REGISTRY.yaml``).

FR-007 Wave 11: Source cadence, next-due timestamps, and rate-limit cooldowns
are persisted in the PostgreSQL ``source_schedules`` table. Scheduler and
worker process restarts do not reset next_due timestamps or trigger warm-up
storms.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional

from sqlalchemy import or_

from core.logging import get_logger
from opportunity.registry import SourceRegistry
from storage.models import SourcePollRunRecord, SourceScheduleRecord, WorkerJobRecord
from worker.handlers import BLOCKED_POLL_STATUS
from worker.queue import BackgroundWorkerQueue

logger = get_logger("opportunityos.worker.scheduler")

#: Environment variable controlling the poll interval, in hours.
ENV_POLL_INTERVAL_HOURS = "OPPORTUNITYOS_POLL_INTERVAL_HOURS"

#: Default poll interval, in hours, when the environment variable above is unset.
DEFAULT_POLL_INTERVAL_HOURS = 6.0

#: Job types this scheduler is responsible for enqueuing.
_SCHEDULED_JOB_TYPE = "poll_source"
_SCHEDULED_REVERIFY_JOB_TYPE = "reverify_stale"

SessionFactory = Callable[[], object]
Clock = Callable[[], datetime]


def get_poll_interval_hours(env: Optional[Mapping[str, str]] = None) -> float:
    """Read ``OPPORTUNITYOS_POLL_INTERVAL_HOURS`` from ``env`` (default: ``os.environ``)."""
    source = env if env is not None else os.environ
    raw = source.get(ENV_POLL_INTERVAL_HOURS)
    if not raw:
        return DEFAULT_POLL_INTERVAL_HOURS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "worker.scheduler_invalid_interval_env",
            extra={"component": "worker.scheduler", "extra_data": {"raw_value": raw}},
        )
        return DEFAULT_POLL_INTERVAL_HOURS
    if value <= 0:
        logger.warning(
            "worker.scheduler_nonpositive_interval_env",
            extra={"component": "worker.scheduler", "extra_data": {"raw_value": raw}},
        )
        return DEFAULT_POLL_INTERVAL_HOURS
    return value


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


_CADENCE_FIELD_RE = re.compile(r"(?m)^\s*poll_cadence_hours:\s*([0-9.]+)")


def _parse_cadence_hours(content: str) -> dict[str, float]:
    """Per-source ``poll_cadence_hours:`` -> hours from registry YAML."""
    cadences: dict[str, float] = {}
    chunks = re.split(r"(?m)^\s*-\s+source_id:\s*", content)
    for chunk in chunks[1:]:
        lines = chunk.strip().splitlines()
        if not lines:
            continue
        source_id = lines[0].strip().strip("\"'")
        match = _CADENCE_FIELD_RE.search(chunk)
        if match:
            try:
                cadences[source_id] = float(match.group(1))
            except ValueError:
                continue
    return cadences


def _to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _active_poll_source_ids(session) -> set[str]:
    """source_ids with an active (PENDING, RETRY, or RUNNING) poll_source job."""
    rows = (
        session.query(WorkerJobRecord.payload_json)
        .filter(
            WorkerJobRecord.job_type == _SCHEDULED_JOB_TYPE,
            WorkerJobRecord.status.in_(["PENDING", "RETRY", "RUNNING"]),
        )
        .all()
    )
    active: set[str] = set()
    for (payload_json,) in rows:
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (TypeError, ValueError):
            continue
        source_id = payload.get("source_id") if isinstance(payload, dict) else None
        if source_id:
            active.add(source_id)
    return active


def _blocked_source_ids_from_db(session) -> set[str]:
    """source_ids with any ``source_poll_runs`` row recording BLOCKED_POLL_STATUS."""
    rows = (
        session.query(SourcePollRunRecord.source_id)
        .filter(SourcePollRunRecord.status == BLOCKED_POLL_STATUS)
        .distinct()
        .all()
    )
    return {source_id for (source_id,) in rows}


def get_or_create_source_schedule(
    session,
    source_id: str,
    cadence_hours: float,
    now: datetime,
) -> SourceScheduleRecord:
    """Retrieve or bootstrap the durable SourceScheduleRecord for a source.

    Initial bootstrap rule:
    - If never polled before: next_due_at is set to now (immediately eligible on initial bootstrap).
    - If prior SourcePollRunRecord rows exist:
      last_attempt_at is latest run started_at.
      last_success_at is latest ok run started_at.
      next_due_at is last_attempt_at + cadence_hours.
      If latest run was blocked, cooldown_until is preserved.

    Restart is NOT bootstrap: an existing row's next_due_at / cooldown_until
    is preserved across restarts.
    """
    now_naive = _to_naive_utc(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    record = session.query(SourceScheduleRecord).filter_by(source_id=source_id).first()
    if record is not None:
        if record.cadence_hours != cadence_hours:
            record.cadence_hours = cadence_hours
        return record

    latest = (
        session.query(SourcePollRunRecord.started_at, SourcePollRunRecord.status)
        .filter(SourcePollRunRecord.source_id == source_id)
        .order_by(SourcePollRunRecord.started_at.desc())
        .first()
    )
    if latest is not None:
        last_attempt = _to_naive_utc(latest[0])
        ok_run = (
            session.query(SourcePollRunRecord.started_at)
            .filter(SourcePollRunRecord.source_id == source_id, SourcePollRunRecord.status == "ok")
            .order_by(SourcePollRunRecord.started_at.desc())
            .first()
        )
        last_success = _to_naive_utc(ok_run[0]) if ok_run else None
        next_due = (last_attempt or now_naive) + timedelta(hours=cadence_hours)
        cooldown = None
        if latest[1] == BLOCKED_POLL_STATUS:
            cooldown = (last_attempt or now_naive) + timedelta(hours=24)
            next_due = max(next_due, cooldown)
    else:
        last_attempt = None
        last_success = None
        next_due = now_naive
        cooldown = None

    values = {
        "source_id": source_id,
        "cadence_hours": cadence_hours,
        "last_attempt_at": last_attempt,
        "last_success_at": last_success,
        "next_due_at": next_due,
        "cooldown_until": cooldown,
        "consecutive_failures": 0,
        "last_status": latest[1] if latest else None,
        "created_at": now_naive,
        "updated_at": now_naive,
    }

    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(SourceScheduleRecord)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["source_id"])
        )
        session.execute(stmt)
        session.flush()
    elif dialect_name == "sqlite":
        stmt = SourceScheduleRecord.__table__.insert().prefix_with("OR IGNORE").values(**values)
        session.execute(stmt)
        session.flush()
    else:
        try:
            with session.begin_nested():
                record = SourceScheduleRecord(**values)
                session.add(record)
                session.flush()
        except Exception:
            pass

    return session.query(SourceScheduleRecord).filter_by(source_id=source_id).one()


def enqueue_due_sources(
    session,
    *,
    registry: Optional[SourceRegistry] = None,
    now: Optional[datetime] = None,
    source_id: Optional[str] = None,
    interval_hours: Optional[float] = None,
    force: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Enqueue due/eligible poll_source jobs.

    Returns (enqueued, skipped) lists:
      enqueued: [{"source_id": str, "job_id": str}, ...]
      skipped: [{"source_id": str, "reason": str}, ...]
    """
    reg = registry or SourceRegistry()
    curr_now = now or datetime.now(timezone.utc)
    curr_now_naive = _to_naive_utc(curr_now) or datetime.now(timezone.utc).replace(tzinfo=None)
    default_interval = interval_hours if interval_hours is not None else get_poll_interval_hours()

    try:
        content = reg.path.read_text(encoding="utf-8")
        cadence_map = _parse_cadence_hours(content)
    except OSError:
        cadence_map = {}

    def _cadence_for(sid: str) -> float:
        return cadence_map.get(sid, default_interval)

    queue = BackgroundWorkerQueue(session)
    enqueued: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    # Single-source explicit request
    if source_id is not None:
        if not reg.is_read_allowed(source_id):
            skipped.append({"source_id": source_id, "reason": "read_disabled_by_policy"})
            return enqueued, skipped

        get_or_create_source_schedule(session, source_id, _cadence_for(source_id), curr_now)

        # Serialize eligibility + enqueue + cadence advancement on the durable
        # source schedule row. The queue insert is flushed without committing
        # so another scheduler cannot observe an unlocked, still-due row.
        bind = session.get_bind()
        is_postgres = bool(bind and bind.dialect.name == "postgresql")
        sched_query = session.query(SourceScheduleRecord).filter_by(source_id=source_id)
        if is_postgres:
            sched_query = sched_query.with_for_update()
        sched = sched_query.one()

        if sched.cooldown_until is not None and sched.cooldown_until > curr_now_naive:
            skipped.append({"source_id": source_id, "reason": "cooling_down"})
            return enqueued, skipped

        active = _active_poll_source_ids(session)
        if source_id in active:
            skipped.append({"source_id": source_id, "reason": "already_queued"})
            return enqueued, skipped

        if not force and sched.next_due_at > curr_now_naive:
            skipped.append({"source_id": source_id, "reason": "not_due"})
            return enqueued, skipped

        job_id = queue.enqueue_job(
            _SCHEDULED_JOB_TYPE, {"source_id": source_id}, commit=False
        )
        # Enqueue reserves the next cadence window but is not itself a
        # source attempt. last_attempt_at is written only by the poll handler
        # when acquisition actually begins/completes.
        sched.next_due_at = curr_now_naive + timedelta(hours=sched.cadence_hours)
        sched.updated_at = curr_now_naive
        enqueued.append({"source_id": source_id, "job_id": job_id})
        return enqueued, skipped

    # Generic request: evaluate all sources in registry
    read_allowed = [s for s in reg._sources if reg.is_read_allowed(s)]
    read_disabled = [s for s in reg._sources if not reg.is_read_allowed(s)]
    for s in read_disabled:
        skipped.append({"source_id": s, "reason": "read_disabled_by_policy"})

    if not read_allowed:
        return enqueued, skipped

    # Ensure schedules exist for all read_allowed sources
    for s in read_allowed:
        get_or_create_source_schedule(session, s, _cadence_for(s), curr_now)

    # In PostgreSQL, lock schedule rows with FOR UPDATE SKIP LOCKED. The
    # queue insert and next_due_at advancement remain in the same transaction,
    # so overlapping scheduler instances cannot both enqueue the same source.
    bind = session.get_bind()
    is_postgres = bool(bind and bind.dialect.name == "postgresql")

    query = session.query(SourceScheduleRecord).filter(
        SourceScheduleRecord.source_id.in_(read_allowed),
    )
    if is_postgres:
        query = query.with_for_update(skip_locked=True)

    schedules = query.all()
    active_sources = _active_poll_source_ids(session)
    for sched in schedules:
        sid = sched.source_id

        # Durable cooldown/Retry-After state is the scheduling authority.
        # Historical blocked poll rows must not suppress a source forever
        # after its persisted cooldown has expired.
        if sched.cooldown_until is not None and sched.cooldown_until > curr_now_naive:
            skipped.append({"source_id": sid, "reason": "cooling_down"})
            continue

        if sid in active_sources:
            skipped.append({"source_id": sid, "reason": "already_queued"})
            continue

        if sched.next_due_at > curr_now_naive:
            skipped.append({"source_id": sid, "reason": "not_due"})
            continue

        job_id = queue.enqueue_job(
            _SCHEDULED_JOB_TYPE, {"source_id": sid}, commit=False
        )
        # Enqueue reserves the next cadence window but is not itself a
        # source attempt. last_attempt_at is written only by the poll handler
        # when acquisition actually begins/completes.
        sched.next_due_at = curr_now_naive + timedelta(hours=sched.cadence_hours)
        sched.updated_at = curr_now_naive
        active_sources.add(sid)
        enqueued.append({"source_id": sid, "job_id": job_id})

    return enqueued, skipped


class PollScheduler:
    """Enqueues ``poll_source`` for read-allowed due sources on their durable cadence."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        registry: Optional[SourceRegistry] = None,
        interval_hours: Optional[float] = None,
        clock: Clock = _default_clock,
        tick_interval_seconds: float = 30.0,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        self.session_factory = session_factory
        self.registry = registry or SourceRegistry()
        self.interval_hours = (
            interval_hours if interval_hours is not None else get_poll_interval_hours()
        )
        self.clock = clock
        self.tick_interval_seconds = tick_interval_seconds
        self.stop_event = stop_event or threading.Event()
        self._last_enqueued_at: dict[str, datetime] = {}
        self._cadence_hours: dict[str, float] = self._load_cadence_hours()
        self._blocked_this_session: set[str] = set()

    def _load_cadence_hours(self) -> dict[str, float]:
        try:
            content = self.registry.path.read_text(encoding="utf-8")
        except OSError:
            return {}
        return _parse_cadence_hours(content)

    def get_cadence_hours(self, source_id: str) -> float:
        return self._cadence_hours.get(source_id, self.interval_hours)

    def _read_allowed_source_ids(self) -> list[str]:
        return [
            source_id
            for source_id in self.registry._sources
            if self.registry.is_read_allowed(source_id)
        ]

    def _is_due(self, source_id: str, now: datetime, session) -> bool:
        now_naive = _to_naive_utc(now) or datetime.now(timezone.utc).replace(tzinfo=None)
        cadence = self.get_cadence_hours(source_id)
        sched = get_or_create_source_schedule(session, source_id, cadence, now)
        if sched.cooldown_until is not None and sched.cooldown_until > now_naive:
            return False
        return sched.next_due_at <= now_naive

    def _blocked_source_ids_from_db(self, session) -> set[str]:
        return _blocked_source_ids_from_db(session)

    def _pending_poll_source_ids(self, session) -> set[str]:
        return _active_poll_source_ids(session)

    @staticmethod
    def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
        return _as_utc(value)

    def _reverify_is_due(self, session, now: datetime) -> bool:
        rows = (
            session.query(WorkerJobRecord.status, WorkerJobRecord.run_after)
            .filter(WorkerJobRecord.job_type == _SCHEDULED_REVERIFY_JOB_TYPE)
            .order_by(WorkerJobRecord.run_after.desc())
            .all()
        )
        if not rows:
            return True

        active_statuses = {"PENDING", "RETRY", "RUNNING"}
        if any((status or "").upper() in active_statuses for status, _ in rows):
            return False

        latest_run_after = _as_utc(rows[0][1])
        if latest_run_after is None:
            return True
        return (now - latest_run_after).total_seconds() >= 86400.0

    def run_once(self) -> list[str]:
        now = self.clock()
        session = self.session_factory()
        try:
            queue = BackgroundWorkerQueue(session)
            enqueued_items, _ = enqueue_due_sources(
                session,
                registry=self.registry,
                now=now,
                interval_hours=self.interval_hours,
            )
            for item in enqueued_items:
                self._last_enqueued_at[item["source_id"]] = now
                logger.info(
                    "worker.scheduler_enqueued",
                    extra={
                        "component": "worker.scheduler",
                        "extra_data": {"source_id": item["source_id"]},
                    },
                )

            if self._reverify_is_due(session, now):
                queue.enqueue_job(_SCHEDULED_REVERIFY_JOB_TYPE, {}, run_after=now, commit=False)
                logger.info(
                    "worker.scheduler_enqueued_reverify",
                    extra={"component": "worker.scheduler"},
                )

            session.commit()
            return [item["source_id"] for item in enqueued_items]
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def run_forever(self) -> None:
        logger.info(
            "worker.scheduler_started",
            extra={
                "component": "worker.scheduler",
                "extra_data": {
                    "interval_hours": self.interval_hours,
                    "tick_interval_seconds": self.tick_interval_seconds,
                },
            },
        )
        try:
            while not self.stop_event.is_set():
                try:
                    self.run_once()
                except Exception as exc:
                    logger.error(
                        "worker.scheduler_tick_error",
                        extra={"component": "worker.scheduler", "extra_data": {"error": str(exc)}},
                    )
                self.stop_event.wait(self.tick_interval_seconds)
        finally:
            logger.info("worker.scheduler_stopped", extra={"component": "worker.scheduler"})
