"""``PollScheduler``: periodically enqueues ``poll_source`` jobs.

One tick enqueues at most one ``poll_source`` job per read-allowed source
whose interval has elapsed, and never enqueues a duplicate while a
PENDING/RETRY ``poll_source`` job for that source is already queued -- a
scheduler that piles up jobs while the worker is slow (or a source's poll
takes longer than the tick) is a defect, not an optimisation.

Read-disabled sources are never enqueued. This is a policy boundary
enforced by ``opportunity.registry.SourceRegistry.is_read_allowed`` (backed
by ``docs/SOURCE_REGISTRY.yaml``), not a scheduler optimisation -- the same
boundary ``worker.handlers.make_poll_source_handler`` itself re-checks
before ever calling a transport, and that ``api/routes_api.py``'s
``/worker/poll-now`` endpoint already enforces the same way.

On ``evaluate_new``: this scheduler does **not** enqueue ``evaluate_new``
itself. ``worker.handlers.make_poll_source_handler`` already enqueues one
``evaluate_new`` job after every successful ``poll_source`` persist (see its
docstring: "``evaluate_new`` is still enqueued unconditionally after a
successful persist... it is now a backfill/safety net for whatever [the
handler's own inline evaluation] pass missed"). A scheduler-level enqueue on
top of that would be a redundant duplicate for the very same tick's
already-enqueued ``evaluate_new`` job, with nothing new for it to do beyond
what the inline pass and the handler's own enqueue already cover. The one
case a scheduler-level enqueue would additionally help -- re-evaluating
existing opportunities after the founder edits their truth pack, with no
new poll in between -- is out of scope for this deliverable (D8 is the
poll scheduler and the local runner, not truth-pack-change reactivity) and
is not exercised by any acceptance criterion here; a future deliverable can
add a periodic, poll-independent ``evaluate_new`` re-check if that gap
needs closing.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from core.logging import get_logger
from opportunity.registry import SourceRegistry
from storage.models import WorkerJobRecord
from worker.queue import BackgroundWorkerQueue

logger = get_logger("opportunityos.worker.scheduler")

#: Environment variable controlling the poll interval, in hours. See
#: ``get_poll_interval_hours``.
ENV_POLL_INTERVAL_HOURS = "OPPORTUNITYOS_POLL_INTERVAL_HOURS"

#: Default poll interval, in hours, when the environment variable above is
#: unset, empty, or not a valid positive number.
DEFAULT_POLL_INTERVAL_HOURS = 6.0

#: Job types this scheduler is responsible for enqueuing.
_SCHEDULED_JOB_TYPE = "poll_source"

#: A zero-arg callable returning a new SQLAlchemy ``Session``.
SessionFactory = Callable[[], object]

#: A zero-arg callable returning the current UTC time, injectable so
#: interval math is testable without sleeping.
Clock = Callable[[], datetime]


def get_poll_interval_hours(env: Optional[Mapping[str, str]] = None) -> float:
    """Read ``OPPORTUNITYOS_POLL_INTERVAL_HOURS`` from ``env`` (default: ``os.environ``).

    Falls back to ``DEFAULT_POLL_INTERVAL_HOURS`` if the variable is unset,
    empty, not parseable as a number, or not strictly positive.
    """
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


class PollScheduler:
    """Enqueues ``poll_source`` for every read-allowed source on an interval.

    Each call into ``run_once`` that touches the database opens its own
    session from ``session_factory`` and closes it before returning, exactly
    like ``worker.runner.WorkerRunner`` -- a ``PollScheduler`` (and the
    sessions it creates) must never be shared across threads.

    Due-ness is tracked in-memory (``_last_enqueued_at``, keyed by
    source_id), not in the database: this is why ``clock`` is injectable --
    tests drive interval math by advancing a fake clock across ``run_once``
    calls instead of sleeping for real hours. A freshly constructed
    scheduler treats every read-allowed source as due on its first tick.
    """

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

    # -- source enumeration -------------------------------------------------

    def _read_allowed_source_ids(self) -> list[str]:
        # SourceRegistry (opportunity/registry.py, out of D8's file scope) has
        # no public "list all sources" accessor -- only per-id lookups
        # (get_policy/is_read_allowed). `_sources` is read-only here; nothing
        # is mutated. This mirrors the identical, already-committed pattern
        # in api/routes_api.py's /sources/health and /worker/poll-now.
        return [
            source_id
            for source_id in self.registry._sources
            if self.registry.is_read_allowed(source_id)
        ]

    # -- due-ness -------------------------------------------------------------

    def _is_due(self, source_id: str, now: datetime) -> bool:
        last = self._last_enqueued_at.get(source_id)
        if last is None:
            return True
        elapsed_hours = (now - last).total_seconds() / 3600.0
        return elapsed_hours >= self.interval_hours

    # -- duplicate suppression -------------------------------------------------

    def _pending_poll_source_ids(self, session) -> set[str]:
        """source_ids with a PENDING/RETRY ``poll_source`` job already queued."""
        rows = (
            session.query(WorkerJobRecord.payload_json)
            .filter(
                WorkerJobRecord.job_type == _SCHEDULED_JOB_TYPE,
                WorkerJobRecord.status.in_(["PENDING", "RETRY"]),
            )
            .all()
        )
        pending: set[str] = set()
        for (payload_json,) in rows:
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except (TypeError, ValueError):
                continue
            source_id = payload.get("source_id") if isinstance(payload, dict) else None
            if source_id:
                pending.add(source_id)
        return pending

    # -- one tick ---------------------------------------------------------------

    def run_once(self) -> list[str]:
        """Enqueue ``poll_source`` for every read-allowed, due source that has
        no PENDING/RETRY ``poll_source`` job already queued.

        Returns the list of source_ids actually enqueued this tick (empty if
        none were due, or all due sources already had a job in flight).
        """
        now = self.clock()
        session = self.session_factory()
        try:
            queue = BackgroundWorkerQueue(session)
            already_pending = self._pending_poll_source_ids(session)
            enqueued: list[str] = []
            for source_id in self._read_allowed_source_ids():
                if not self._is_due(source_id, now):
                    continue
                if source_id in already_pending:
                    logger.info(
                        "worker.scheduler_skip_pending",
                        extra={
                            "component": "worker.scheduler",
                            "extra_data": {"source_id": source_id},
                        },
                    )
                    continue
                queue.enqueue_job(_SCHEDULED_JOB_TYPE, {"source_id": source_id})
                self._last_enqueued_at[source_id] = now
                enqueued.append(source_id)
                logger.info(
                    "worker.scheduler_enqueued",
                    extra={
                        "component": "worker.scheduler",
                        "extra_data": {"source_id": source_id},
                    },
                )
            return enqueued
        finally:
            session.close()

    # -- continuous loop ----------------------------------------------------------

    def run_forever(self) -> None:
        """Tick every ``tick_interval_seconds`` until ``stop_event`` is set."""
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
                except Exception as exc:  # noqa: BLE001 - a transient DB error must not kill the scheduler
                    logger.error(
                        "worker.scheduler_tick_error",
                        extra={"component": "worker.scheduler", "extra_data": {"error": str(exc)}},
                    )
                self.stop_event.wait(self.tick_interval_seconds)
        finally:
            logger.info("worker.scheduler_stopped", extra={"component": "worker.scheduler"})
