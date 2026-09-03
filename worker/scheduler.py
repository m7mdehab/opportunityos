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
import re
import threading
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from core.logging import get_logger
from opportunity.registry import SourceRegistry
from storage.models import SourcePollRunRecord, WorkerJobRecord
from worker.handlers import BLOCKED_POLL_STATUS
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


#: Matches a ``poll_cadence_hours: <number>`` line anywhere within one
#: source's YAML block in ``docs/SOURCE_REGISTRY.yaml`` (or a test fixture
#: shaped like it). Line-oriented on purpose, mirroring
#: ``opportunity.registry.SourceRegistry._parse_yaml_sources``'s own
#: dependency-free regex parser exactly (this module must not add a YAML
#: library dependency, and ``opportunity/registry.py`` is frozen for this
#: work order so the cadence field cannot live on its ``SourcePolicy``
#: dataclass -- the scheduler reads the registry file itself instead).
_CADENCE_FIELD_RE = re.compile(r"(?m)^\s*poll_cadence_hours:\s*([0-9.]+)")


def _parse_cadence_hours(content: str) -> dict[str, float]:
    """Per-source ``poll_cadence_hours:`` -> hours, parsed the same way
    ``SourceRegistry._parse_yaml_sources`` splits the file into one chunk per
    ``- source_id: ...`` entry. A source with no ``poll_cadence_hours`` field
    is simply absent from the returned mapping -- callers apply their own
    default (see ``PollScheduler.get_cadence_hours``).
    """
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
        # Per-source cadence read once at construction from the same
        # docs/SOURCE_REGISTRY.yaml (or fixture) file self.registry loaded --
        # policy data next to the source's rate limits, not a Python table.
        # A source absent from this mapping (no `poll_cadence_hours:` field)
        # falls back to `self.interval_hours` in get_cadence_hours below.
        self._cadence_hours: dict[str, float] = self._load_cadence_hours()
        # Sources that returned 403/429 on a poll this session (see
        # _blocked_source_ids_from_db): once observed, a source_id stays in
        # this set for the rest of this PollScheduler instance's lifetime --
        # cadence is a floor, not a licence, and this union is deliberately
        # one-directional (never cleared) so a still-blocking source is not
        # retried just because its cadence interval elapsed again.
        self._blocked_this_session: set[str] = set()

    def _load_cadence_hours(self) -> dict[str, float]:
        try:
            content = self.registry.path.read_text(encoding="utf-8")
        except OSError:
            return {}
        return _parse_cadence_hours(content)

    def get_cadence_hours(self, source_id: str) -> float:
        """The declared cadence for ``source_id``, or ``self.interval_hours``
        (the existing global default) when the registry entry has no
        ``poll_cadence_hours`` field."""
        return self._cadence_hours.get(source_id, self.interval_hours)

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
        return elapsed_hours >= self.get_cadence_hours(source_id)

    # -- 403/429 session blocklist -------------------------------------------

    def _blocked_source_ids_from_db(self, session) -> set[str]:
        """source_ids with any ``source_poll_runs`` row recorded
        ``status="blocked"`` (worker.handlers.BLOCKED_POLL_STATUS) -- a poll
        that returned HTTP 403 or 429. Cadence is a floor, not a licence:
        such a source is never re-enqueued by this scheduler instance again,
        regardless of how much time (or how many due cadence intervals)
        pass -- see ``_blocked_this_session``.
        """
        rows = (
            session.query(SourcePollRunRecord.source_id)
            .filter(SourcePollRunRecord.status == BLOCKED_POLL_STATUS)
            .distinct()
            .all()
        )
        return {source_id for (source_id,) in rows}

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
            # Monotonic union: a source_id observed blocked (403/429) on any
            # prior tick of this scheduler instance stays blocked for the
            # rest of its session even if this tick's DB query no longer
            # returns it for some reason.
            self._blocked_this_session |= self._blocked_source_ids_from_db(session)
            enqueued: list[str] = []
            for source_id in self._read_allowed_source_ids():
                if source_id in self._blocked_this_session:
                    logger.info(
                        "worker.scheduler_skip_blocked",
                        extra={
                            "component": "worker.scheduler",
                            "extra_data": {"source_id": source_id},
                        },
                    )
                    continue
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
