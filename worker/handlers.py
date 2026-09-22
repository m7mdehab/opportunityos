"""Job handlers for the background worker runner.

Three job types are supported:
  - ``noop``: does nothing; used for smoke tests / queue plumbing checks.
  - ``poll_source``: invokes the governed opportunity acquisition path for one
    source, after checking the SourceRegistry read policy. A source whose read
    automation is disabled is refused (never fetched) and the refusal is
    recorded via a structured log line, a ``source_poll_runs`` row
    (``status="refused"``), and, when provided, an injectable refusal sink --
    this is the mechanism the end-to-end test observes. A source that is
    allowed is fetched, normalized, and persisted (via
    ``opportunity.persistence.persist_batch``) to the ``opportunities`` /
    ``field_provenances`` tables, then evaluated INLINE, at full fidelity,
    from the batch's own in-memory ``Opportunity`` objects (not a
    reconstruction -- see ``make_poll_source_handler``'s docstring), a
    ``source_poll_runs`` row is written (``status="ok"``, with the batch and
    persist counts), and an ``evaluate_new`` job is enqueued as a backfill
    safety net for whatever the inline pass missed.
  - ``evaluate_new``: evaluates every opportunity that has no
    ``match_evaluations`` or ``feed_projection`` row for the *current*
    founder truth-pack hash (see
    ``matching.evaluate_persist.evaluate_and_store``), reconstructing each
    ``Opportunity`` best-effort from ``OpportunityRecord``/
    ``field_provenances`` (see ``_reconstruct_opportunity`` -- this is
    strictly a backfill path now; ``poll_source`` evaluates its own fresh
    batch inline at full fidelity, see above). Loads the pack via
    ``truth.pack.load_founder_pack`` (path injectable so tests never touch
    ``private/``); refuses cleanly (logs and returns, no partial writes) if no
    valid pack is available.
"""
from __future__ import annotations

import json
import uuid
from time import perf_counter
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, MutableMapping, Optional

from sqlalchemy import or_, text

from core.logging import get_logger, redact_data
from matching.evaluate_persist import evaluate_and_store
from matching.scorer import OpportunityScorer
from opportunity.clustering import compute_family_key
from opportunity.models import (
    Compensation,
    CompensationInterval,
    EmploymentType,
    GeographicEligibility,
    Opportunity,
    RemoteScope,
    SeniorityLevel,
    SourceHealthStatus,
    Track,
    WorkMode,
)
from opportunity.persistence import persist_batch
from opportunity.pipeline import OpportunityPipeline
from opportunity.registry import SourceRegistry
from opportunity.transport import AcquisitionService, BaseTransport, HttpTransport, RateLimiter
from storage.models import FieldProvenanceRecord, MatchEvaluationRecord, OpportunityRecord, SourcePollRunRecord, SourceScheduleRecord
from storage.feed_projection import FeedProjectionRecord
try:
    # A1M's own reextract_all interface point (see below) into the concurrent
    # A1-extract work order's extraction functions. Imported defensively: if
    # A1-extract has not landed on this branch yet, ``reextract_all`` degrades
    # to a documented no-op rather than failing worker startup.
    from opportunity.extraction import extract_founder_control_fields as _default_founder_control_extractor  # type: ignore
except ImportError:
    _default_founder_control_extractor = None
from storage.repository import StorageRepository
from truth.pack import LoadedPack, TruthPackInvalid, TruthPackMissing, load_founder_pack
from worker.queue import BackgroundWorkerQueue

logger = get_logger("opportunityos.worker.handlers")

#: Reason code recorded when poll_source refuses a read-disabled source.
REFUSAL_REASON_READ_DISABLED = "read_disabled_by_policy"

RefusalSink = Callable[[Mapping[str, str]], None]
#: A zero-arg callable returning a new SQLAlchemy ``Session`` (i.e. a
#: ``sessionmaker``/``storage.engine.get_session_factory(engine)`` result).
SessionFactory = Callable[[], Any]
#: A one-arg callable ``(path) -> LoadedPack`` (or raising
#: ``TruthPackMissing``/``TruthPackInvalid``), matching
#: ``truth.pack.load_founder_pack``'s own signature. Used by ``evaluate_new``
#: so tests can inject a pack without touching ``private/truth_pack.yaml``.
PackLoader = Callable[[Any], LoadedPack]

# Sized from the disposable PostgreSQL worker envelope: one evaluator handles
# at most this many rows, then coalesces one successor when work remains.
EVALUATE_NEW_BATCH_SIZE = 100


def _acquire_source_persistence_lock(session: Any, source_id: str) -> None:
    """Compatibility no-op retained for W22.4 callers.

    Source-wide locking is intentionally not used because repository writes
    commit internally. Identity races are serialized by
    ``StorageRepository.lock_opportunity_identity`` at each commit boundary.
    """
    bind = getattr(session, "bind", None)
    if bind is None or getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return
    # Kept as a compatibility shim for callers/tests from W22.4.  The actual
    # correctness lock now lives at the opportunity write boundary because
    # StorageRepository.save_opportunity commits internally.
    # Keep this shim explicit so older callers cannot reintroduce a source-wide
    # transaction lock around repository methods that commit internally.
    return None


def noop(payload: dict) -> None:
    """Smoke-test handler: accepts any payload and does nothing."""
    return None


def _to_utc_naive(value: datetime) -> datetime:
    """Normalize to a naive ``datetime`` carrying UTC wall-clock time, for
    writing into any of this module's ``DateTime`` (i.e. PostgreSQL
    ``TIMESTAMP WITHOUT TIME ZONE``) columns -- ``source_poll_runs.started_at``/
    ``finished_at`` here, mirroring the identical fix (and identical
    reasoning) in ``matching.evaluate_persist._to_utc_naive``.

    psycopg2 does not simply drop the tzinfo off a tz-aware ``datetime``
    written into such a column: PostgreSQL converts it to the *session's*
    ``timezone`` GUC first and only then stores it naive. On a session whose
    timezone isn't UTC (this project's own local dev database defaults to
    ``Africa/Cairo``), a tz-aware UTC value written straight through comes
    back several hours off from what was actually passed in. Converting to
    UTC and stripping tzinfo before the value reaches psycopg2 avoids the
    conversion entirely.
    """
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _record_refusal(source_id: str, refusal_sink: Optional[RefusalSink]) -> None:
    record = {"source_id": source_id, "reason": REFUSAL_REASON_READ_DISABLED}
    logger.warning(
        "worker.poll_source_refused",
        extra={"component": "worker.handlers", "extra_data": redact_data(dict(record))},
    )
    if refusal_sink is not None:
        refusal_sink(record)


def _production_session_factory() -> Any:
    """Lazily build the production (real ``OPPORTUNITYOS_DB_URL``) session factory.

    Deferred import + deferred construction: importing ``worker.handlers`` (or
    building a handler with an explicitly injected ``session_factory``, as
    every test does) must never require database configuration to be present.
    This mirrors exactly what ``worker/__main__.py`` already does for the
    ``WorkerRunner`` itself (``get_production_db_url`` -> ``get_engine`` ->
    ``get_session_factory``), so ``python -m worker`` persists poll_source
    results through the same fail-closed production configuration path
    without ``worker/__main__.py`` needing any change.
    """
    from storage.engine import get_engine, get_production_db_url, get_session_factory

    engine = get_engine(get_production_db_url())
    return get_session_factory(engine)


def _update_source_schedule(
    session: Any,
    source_id: str,
    started_at: datetime,
    status: str,
    *,
    finished_at: Optional[datetime] = None,
    error_message: Optional[str] = None,
    cooldown_seconds: Optional[float] = None,
) -> None:
    """Update durable SourceScheduleRecord state to keep cadence and cooldowns in sync."""
    sched = session.query(SourceScheduleRecord).filter_by(source_id=source_id).first()
    if sched is None:
        return
    fin = finished_at or datetime.now(timezone.utc)
    sched.last_attempt_at = _to_utc_naive(started_at)
    sched.updated_at = _to_utc_naive(fin)
    sched.last_status = status
    sched.error_message = error_message
    if status == "ok":
        sched.last_success_at = _to_utc_naive(fin)
        sched.consecutive_failures = 0
        sched.cooldown_until = None
        sched.next_due_at = _to_utc_naive(started_at + timedelta(hours=sched.cadence_hours))
    elif status == BLOCKED_POLL_STATUS:
        sched.consecutive_failures += 1
        cd_secs = cooldown_seconds if cooldown_seconds is not None else 3600.0
        cd_until = _to_utc_naive(fin + timedelta(seconds=cd_secs))
        sched.cooldown_until = cd_until
        if sched.next_due_at is None or cd_until > sched.next_due_at:
            sched.next_due_at = cd_until
    else:
        sched.consecutive_failures += 1


def _write_poll_run_record(
    resolve_session_factory: Callable[[], SessionFactory],
    *,
    source_id: str,
    job_id: Optional[str],
    started_at: datetime,
    status: str,
    refusal_reason: Optional[str] = None,
    raw_ingested: int = 0,
    unique_opportunities: int = 0,
    inserted: int = 0,
    unchanged: int = 0,
    updated: int = 0,
    error_message: Optional[str] = None,
    cooldown_seconds: Optional[float] = None,
) -> None:
    """Write one ``source_poll_runs`` row on its own, independent session.

    Used for the ``refused`` and ``error`` outcomes, which must not depend on
    (or be entangled with) the main fetch/persist session -- a refusal never
    opens that session at all, and an error may have already rolled it back.
    The ``ok`` outcome is instead written on the same session as the persist
    (see ``make_poll_source_handler``) so it commits atomically with the
    batch it describes.

    Only a missing/invalid production database configuration is swallowed
    (logged, then this function simply returns): that lets a handler built
    with no injected ``session_factory`` and no ``OPPORTUNITYOS_DB_URL`` set
    -- e.g. a narrow unit test exercising only the refusal branch, as
    ``worker/test_runner.py::TestPollSourceHandler`` already does -- keep
    working exactly as before, without requiring database setup just to
    observe a refusal. Any other error (a genuinely configured but failing
    database) propagates rather than being silently dropped.
    """
    from storage.engine import ProductionDatabaseConfigurationError

    try:
        session_factory = resolve_session_factory()
    except ProductionDatabaseConfigurationError:
        logger.warning(
            "worker.source_poll_run_record_skipped_no_db",
            extra={"component": "worker.handlers", "extra_data": {"source_id": source_id, "status": status}},
        )
        return

    session = session_factory()
    try:
        now_utc = datetime.now(timezone.utc)
        record = SourcePollRunRecord(
            id=f"spr-{uuid.uuid4().hex[:16]}",
            source_id=source_id,
            job_id=job_id,
            started_at=_to_utc_naive(started_at),
            finished_at=_to_utc_naive(now_utc),
            status=status,
            refusal_reason=refusal_reason,
            raw_ingested=raw_ingested,
            unique_opportunities=unique_opportunities,
            inserted=inserted,
            unchanged=unchanged,
            updated=updated,
            error_message=error_message,
        )
        session.add(record)
        _update_source_schedule(
            session,
            source_id,
            started_at,
            status,
            finished_at=now_utc,
            error_message=error_message,
            cooldown_seconds=cooldown_seconds,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


#: Status recorded on ``source_poll_runs`` when a source's own poll returned
#: HTTP 403/429 this run: distinct from ``"ok"`` (empty-but-authorized) and
#: ``"refused"`` (registry read policy) so ``worker.scheduler.PollScheduler``
#: can tell "nothing to fetch" apart from "cool this source down". The
#: durable source_schedules row controls when it becomes eligible again.
#: Cadence is a floor, not a licence.
BLOCKED_POLL_STATUS = "blocked"

#: HTTP status codes that mean "stop asking this source this session",
#: shared by the generic (``execute_discovery``/health-report) path and the
#: Hacker News governed multi-step fetch below.
_BLOCKED_STATUS_CODES = frozenset({403, 429})

#: Health statuses (see ``opportunity.health.SourceHealthMonitor.record_run``)
#: that correspond to the same 403/429 durable-cooldown condition
#: for a source polled through the normal ``OpportunityPipeline.execute_discovery``
#: / ``process_payloads`` path (which never raises for a non-2xx transport
#: response -- it just health-reports it and yields zero opportunities).
_BLOCKED_HEALTH_STATUSES = frozenset({SourceHealthStatus.POLICY_RESTRICTION, SourceHealthStatus.RATE_LIMITED})


def _retry_after_seconds(report: Any, now: datetime) -> Optional[float]:
    """Parse a Retry-After health diagnostic into a non-negative delay.

    Supports both RFC integer delta-seconds and HTTP-date values. Invalid or
    absent values return None so callers can apply a conservative fallback.
    """
    try:
        raw = dict(report.diagnostics).get("retry_after")
    except Exception:
        return None
    if raw is None:
        return None
    text_value = str(raw).strip()
    if not text_value:
        return None
    try:
        seconds = float(text_value)
        return max(0.0, seconds)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (parsed.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None

#: The one source this work order wires a live, governed, multi-step fetch
#: for (see ``_fetch_hacker_news_who_is_hiring_governed`` below). Every other
#: source's single-request fetch already goes through
#: ``OpportunityPipeline.execute_discovery`` -> ``AcquisitionService.acquire``.
HACKER_NEWS_SOURCE_ID = "hacker_news_who_is_hiring"

_HN_FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"


def _hn_governed_get(acquisition: AcquisitionService, source_id: str, url: str) -> tuple[Optional[Any], Optional[int]]:
    """One governed GET -- registry preflight, shared rate limiter, injectable
    transport, all via ``AcquisitionService.acquire`` -- returning
    ``(parsed_json_or_None, status_code)``.
    """
    result = acquisition.acquire(source_id=source_id, url=url, method="GET")
    status = result.response.status_code
    if not result.authorized or not result.response.is_success or not result.response.body:
        return None, status
    try:
        return json.loads(result.response.body), status
    except (TypeError, ValueError):
        return None, status


def _fetch_hacker_news_who_is_hiring_governed(
    acquisition: AcquisitionService,
    source_id: str = HACKER_NEWS_SOURCE_ID,
    max_comments: int = 200,
) -> tuple[Optional[str], Optional[int]]:
    """Governed re-implementation of the multi-step Firebase orchestration
    documented (but left un-wired, on purpose) by
    ``opportunity.adapters.hacker_news.fetch_who_is_hiring_payload``.

    That module is frozen for this work order (E23 owns it) and its live
    fetch uses raw ``urllib`` directly, bypassing the registry gate, the
    shared rate limiter, and test injection entirely -- exactly the
    "clearly marked seam" its own docstring describes for integration here.
    This function performs the identical three-step orchestration (resolve
    the current thread via the ``whoishiring`` user's submissions, fetch the
    thread item, fetch each top-level comment) but every request goes
    through the same injected ``AcquisitionService`` (registry
    ``is_read_allowed``/``validate_preflight`` + the shared ``RateLimiter`` +
    an injectable ``BaseTransport``) used everywhere else, so it is
    offline-testable with a ``MockTransport`` and stops immediately --
    recording the blocking status rather than raising -- the moment any step
    returns 403/429, per this source's own read-only policy gate.
    """
    user, status = _hn_governed_get(acquisition, source_id, f"{_HN_FIREBASE_BASE}/user/whoishiring.json")
    if user is None:
        return None, status
    submitted_ids = list(user.get("submitted", []))[:60]

    thread_item: Optional[dict] = None
    for item_id in submitted_ids:
        item, status = _hn_governed_get(acquisition, source_id, f"{_HN_FIREBASE_BASE}/item/{item_id}.json")
        if status in _BLOCKED_STATUS_CODES:
            return None, status
        if item and isinstance(item, dict) and str(item.get("title", "")).lower().startswith("ask hn: who is hiring"):
            thread_item = item
            break
    if thread_item is None:
        return json.dumps({"thread_id": None, "thread_title": "", "comments": []}), 200

    comments: list[dict] = []
    for kid_id in list(thread_item.get("kids", []))[:max_comments]:
        kid, status = _hn_governed_get(acquisition, source_id, f"{_HN_FIREBASE_BASE}/item/{kid_id}.json")
        if status in _BLOCKED_STATUS_CODES:
            return None, status
        if not kid or kid.get("deleted") or kid.get("dead"):
            continue
        comments.append(kid)

    return (
        json.dumps({
            "thread_id": thread_item.get("id"),
            "thread_title": thread_item.get("title", ""),
            "comments": comments,
        }),
        200,
    )


def make_poll_source_handler(
    *,
    registry: Optional[SourceRegistry] = None,
    transport: Optional[BaseTransport] = None,
    adapters=None,
    refusal_sink: Optional[RefusalSink] = None,
    session_factory: Optional[SessionFactory] = None,
    truth_pack_path: Optional[Any] = None,
    pack_loader: Optional[PackLoader] = None,
    scorer: Optional[OpportunityScorer] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> Callable[[dict], None]:
    """Build a ``poll_source`` handler bound to the given (injectable) dependencies.

    ``transport`` is the injectable fetcher: production code should pass nothing
    (defaults to the real ``HttpTransport``); tests must inject a ``MockTransport``
    with fixture data so no network I/O occurs.

    ``session_factory`` is the injectable session source used to persist a
    fetched batch (``opportunity.persistence.persist_batch``). It defaults to
    the real production database (built lazily, on first use, from
    ``OPPORTUNITYOS_DB_URL``) so tests must inject their own (e.g. a SQLite or
    test-Postgres ``sessionmaker``) to avoid touching production data. The
    read-disabled refusal path never calls ``transport`` and never resolves
    the fetch/persist session at all -- it still, as of this deliverable,
    writes a ``source_poll_runs`` row (``status="refused"``), but that write
    happens on its own independent session via ``_write_poll_run_record``, so
    the fetch/persist session lifecycle described above is unaffected.

    After a successful persist, this handler evaluates the batch's own
    in-memory ``Opportunity`` objects -- the ones ``execute_discovery`` just
    produced, with real ``responsibilities``/``requirements`` populated --
    directly via ``matching.evaluate_persist.evaluate_and_store``, at full
    fidelity. This is deliberately NOT the same code path as
    ``evaluate_new``'s ``_reconstruct_opportunity``, which rebuilds an
    ``Opportunity`` from ``OpportunityRecord``/``field_provenances`` and can
    only recover ``responsibilities``/``requirements`` as empty tuples (see
    its own docstring) -- every opportunity evaluated that way has its
    ``fit_score`` systematically depressed on any dimension that scores those
    fields (the scorer weights ``responsibilities`` at 0.15 and parses
    ``requirements`` for scope). Evaluating the fresh in-memory batch here
    means the founder's measured fit scores are never taken from the lossy
    path for opportunities freshly discovered by this handler.
    ``truth_pack_path``/``pack_loader`` mirror ``evaluate_new``'s: production
    passes neither (defaults to ``truth.pack.load_founder_pack``, reading
    ``private/truth_pack.yaml``); tests must inject a ``pack_loader`` so no
    test touches ``private/``. If no valid pack is available
    (``TruthPackMissing``/``TruthPackInvalid``), this handler skips the
    inline evaluation (logs and continues) rather than failing the whole
    poll -- persistence and the ``evaluate_new`` enqueue still happen, so
    those opportunities are picked up as backfill once the pack is fixed.
    ``evaluate_new`` is still enqueued unconditionally after a successful
    persist, exactly as the brief requires: it is now a backfill/safety net
    for whatever this inline pass missed (a failed individual evaluation, a
    pack that was unavailable at poll time, or any pre-existing unevaluated
    row), not the primary scoring path for a fresh poll.
    """
    reg = registry or SourceRegistry()
    fetch_transport = transport or HttpTransport()
    pack_loader_fn = pack_loader or load_founder_pack
    # Built once, reused by every handler() call: gives the Hacker News
    # governed multi-step fetch (below) the same registry gate + injectable
    # transport as the rest of this handler, and a RateLimiter that actually
    # paces across separate polls of this source within one worker process,
    # not just within one call.
    hn_acquisition = AcquisitionService(registry=reg, transport=fetch_transport)
    # Council review 4, finding 9: docs/SOURCE_REGISTRY.yaml's generated Greenhouse/
    # Lever entries declare `rate_limits.documented: shared_per_ats_host`, but
    # `OpportunityPipeline.__init__` builds its own `AcquisitionService` (and thus its
    # own fresh, per-source `RateLimiter`) every time -- and this handler builds a new
    # `OpportunityPipeline` per job (below), so nothing was actually shared even across
    # two jobs polling boards on the very same ATS host. Built once here, reused by
    # every handler() call, and assigned onto each fresh pipeline's `.acquisition`
    # below so pacing is process-wide, not per-job -- combined with
    # `AcquisitionService.acquire` now keying its limiter by host (see
    # `opportunity/transport.py`), this makes pacing genuinely shared per ATS host
    # across boards *and* across jobs, matching what the registry claims.
    process_rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()
    _session_factory_holder: list[Optional[SessionFactory]] = [session_factory]

    def _resolve_session_factory() -> SessionFactory:
        if _session_factory_holder[0] is None:
            _session_factory_holder[0] = _production_session_factory()
        return _session_factory_holder[0]

    def handler(payload: dict) -> None:
        source_id = payload.get("source_id") if payload else None
        if not source_id:
            raise ValueError("poll_source payload requires a non-empty 'source_id'")
        job_id = payload.get("job_id") if payload else None
        started_at = datetime.now(timezone.utc)

        if not reg.is_read_allowed(source_id):
            # Refusal is decided and logged/sunk before any DB write is even
            # attempted; the DB write below never touches the network and is
            # itself best-effort (see _write_poll_run_record).
            _record_refusal(source_id, refusal_sink)
            _write_poll_run_record(
                _resolve_session_factory,
                source_id=source_id,
                job_id=job_id,
                started_at=started_at,
                status="refused",
                refusal_reason=REFUSAL_REASON_READ_DISABLED,
            )
            return

        logger.info(
            "worker.poll_source_fetching",
            extra={"component": "worker.handlers", "extra_data": {"source_id": source_id}},
        )
        acquisition_started = perf_counter()
        try:
            pipeline = OpportunityPipeline(adapters=adapters, registry=reg, transport=fetch_transport)
            pipeline.acquisition.rate_limiter = process_rate_limiter
            if source_id == HACKER_NEWS_SOURCE_ID:
                # Hacker News needs a governed multi-step Firebase fetch (see
                # _fetch_hacker_news_who_is_hiring_governed's docstring) instead
                # of the generic single-request execute_discovery path every
                # other source uses. A 403/429 on any step is not raised: it is
                # recorded (status="blocked") and this poll returns cleanly, the
                # same "stop asking this source, don't crash the worker"
                # contract every other source gets from health_reports below.
                hn_payload, hn_status = _fetch_hacker_news_who_is_hiring_governed(hn_acquisition, source_id)
                if hn_payload is None:
                    blocked = hn_status in _BLOCKED_STATUS_CODES
                    _write_poll_run_record(
                        _resolve_session_factory,
                        source_id=source_id,
                        job_id=job_id,
                        started_at=started_at,
                        status=BLOCKED_POLL_STATUS if blocked else "error",
                        refusal_reason=f"http_{hn_status}" if blocked else None,
                        error_message=None if blocked else f"hacker_news_who_is_hiring fetch failed (status={hn_status})",
                    )
                    return
                batch = pipeline.process_payloads(
                    {source_id: hn_payload},
                    now_iso=started_at.strftime("%Y-%m-%d"),
                    run_id=job_id or "run_default",
                    status_codes={source_id: hn_status or 200},
                )
            else:
                batch = pipeline.execute_discovery(source_ids=[source_id])
            acquisition_duration = perf_counter() - acquisition_started
        except Exception as exc:
            _write_poll_run_record(
                _resolve_session_factory,
                source_id=source_id,
                job_id=job_id,
                started_at=started_at,
                status="error",
                error_message=str(exc),
            )
            raise

        # A source polled through execute_discovery/process_payloads never
        # raises for a non-2xx transport response -- it health-reports it and
        # yields zero opportunities for that source. Detect that here (rather
        # than only for Hacker News) so any source's 403/429 is recorded as
        # BLOCKED_POLL_STATUS, not a misleadingly-empty "ok", and
        # worker.scheduler.PollScheduler can act on it. Cadence is a floor,
        # not a licence.
        blocked_report = next(
            (
                r
                for r in batch.health_reports
                if r.source_id == source_id and r.status in _BLOCKED_HEALTH_STATUSES
            ),
            None,
        )

        session = _resolve_session_factory()()
        try:
            persistence_started = perf_counter()
            repository = StorageRepository(session)
            result = persist_batch(batch, repository)
            persistence_duration = perf_counter() - persistence_started

            # Inline, full-fidelity evaluation of THIS batch's own in-memory
            # Opportunity objects (real responsibilities/requirements) --
            # see this function's docstring for why this must not be the
            # lossy _reconstruct_opportunity path evaluate_new uses.
            evaluated_inline_count = 0
            inline_started = perf_counter()
            try:
                pack = pack_loader_fn(truth_pack_path)
            except (TruthPackMissing, TruthPackInvalid) as exc:
                pack = None
                logger.warning(
                    "worker.poll_source_evaluate_skipped_no_pack",
                    extra={
                        "component": "worker.handlers",
                        "extra_data": {"source_id": source_id, "reason": type(exc).__name__},
                    },
                )

            if pack is not None:
                inline_evaluated_at = datetime.now(timezone.utc)
                persisted_ids = set(result.persisted_ids)
                # Unchanged rows are deliberately never evaluated inline.  A
                # row without the current evaluation remains eligible for the
                # bounded evaluate_new safety net below; doing it here would
                # turn a large re-poll into thousands of serialized commits.
                inline_ids = persisted_ids
                for opp in batch.opportunities:
                    if opp.id not in inline_ids:
                        continue
                    evaluate_and_store(
                        opp,
                        pack.graph,
                        repository,
                        truth_pack_hash=pack.truth_pack_hash,
                        evaluated_at=inline_evaluated_at,
                        scorer=scorer,
                    )
                    evaluated_inline_count += 1
            inline_duration = perf_counter() - inline_started

            # evaluate_new remains the backfill/safety net -- it will only
            # find work here if the inline pass above was skipped (no valid
            # pack yet) or missed something; every opportunity this handler
            # just evaluated inline already has a match_evaluations row for
            # the current truth-pack hash, so evaluate_new is a fast no-op
            # for them.
            queue = BackgroundWorkerQueue(session)
            queue.enqueue_evaluate_new_coalesced(commit=False)

            finished_at = datetime.now(timezone.utc)
            poll_run = SourcePollRunRecord(
                id=f"spr-{uuid.uuid4().hex[:16]}",
                source_id=source_id,
                job_id=job_id,
                started_at=_to_utc_naive(started_at),
                finished_at=_to_utc_naive(finished_at),
                status=BLOCKED_POLL_STATUS if blocked_report is not None else "ok",
                refusal_reason=(f"blocked_{blocked_report.status.value}" if blocked_report is not None else None),
                raw_ingested=batch.total_raw_ingested,
                unique_opportunities=batch.total_unique_opportunities,
                inserted=result.inserted_count,
                unchanged=result.unchanged_count,
                updated=result.updated_count,
            )
            session.add(poll_run)
            cd_secs = None
            if blocked_report is not None:
                retry_after = _retry_after_seconds(blocked_report, finished_at)
                if blocked_report.status == SourceHealthStatus.RATE_LIMITED:
                    # Respect Retry-After when present; otherwise use a bounded
                    # conservative fallback. Never permit an immediate retry.
                    cd_secs = max(60.0, retry_after if retry_after is not None else 3600.0)
                else:
                    # Policy/WAF restrictions receive a longer floor even if a
                    # short or malformed Retry-After is returned.
                    cd_secs = max(86400.0, retry_after or 0.0)
            _update_source_schedule(
                session,
                source_id,
                started_at,
                poll_run.status,
                finished_at=finished_at,
                cooldown_seconds=cd_secs,
            )
            finalization_started = perf_counter()
            session.commit()
            finalization_duration = perf_counter() - finalization_started
            total_duration = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info(
                "worker.poll_source_persisted",
                extra={
                    "component": "worker.handlers",
                    "extra_data": {
                        "source_id": source_id,
                        "inserted": result.inserted_count,
                        "unchanged": result.unchanged_count,
                        "updated": result.updated_count,
                        "evaluated_inline": evaluated_inline_count,
                        "stage_seconds": {
                            "persistence": round(persistence_duration, 3),
                            "inline_evaluation": round(inline_duration, 3),
                            "acquisition_parse": round(acquisition_duration, 3),
                            "poll_finalization": round(finalization_duration, 3),
                            "total": round(total_duration, 3),
                        },
                    },
                },
            )
        except Exception as exc:
            session.rollback()
            session.close()
            _write_poll_run_record(
                _resolve_session_factory,
                source_id=source_id,
                job_id=job_id,
                started_at=started_at,
                status="error",
                error_message=str(exc),
            )
            raise
        else:
            session.close()

    return handler


def _first_field_provenance_map(session: Any, opportunity_id: str) -> dict[str, str]:
    """Map ``field_name -> normalized_value`` for one opportunity's provenance rows.

    Ordered by primary-key ascending so that if more than one row exists for
    the same ``field_name`` (e.g. after a content-changed re-poll rewrote
    provenance), the most recently written row wins.
    """
    rows = (
        session.query(FieldProvenanceRecord)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(FieldProvenanceRecord.id.asc())
        .all()
    )
    prov_map: dict[str, str] = {}
    for row in rows:
        if row.normalized_value is not None:
            prov_map[row.field_name] = row.normalized_value
    return prov_map


def _enum_or_default(enum_cls: Any, value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _reconstruct_opportunity(
    session: Any,
    record: OpportunityRecord,
    *,
    archive_payload: Optional[Mapping[str, Any]] = None,
) -> Opportunity:
    """Best-effort reconstruction of an ``Opportunity`` from a persisted row.

    ``title``, ``description``, and ``organization`` are stored with full
    fidelity on ``OpportunityRecord`` itself and are used verbatim here.
    ``skills`` (stored as a single comma-joined provenance value),
    ``seniority``, ``employment_type``, and ``geographic_eligibility`` (status
    only) are recovered on a best-effort basis from ``field_provenances``.

    BRIEF-FR-006 A1 defect fix: ``work_mode``, ``work_mode_source``,
    ``location_country``, ``location_city``, ``location_region``,
    ``remote_scope``, ``remote_scope_regions``, and the four
    ``compensation_*`` columns are read directly off ``record`` -- migration
    ``0004_founder_control`` (A1M) made these real ``opportunities`` columns
    and ``storage/repository.py::save_opportunity`` (A1M) writes them from
    exactly the keys ``opportunity/persistence.py::_build_opp_data`` (A1)
    produces -- so the column is the authoritative, always-in-sync source,
    not a re-derivation from ``field_provenances``.

    ``work_mode`` backward-compatibility decision: rows written by every
    adapter as of this fix persist their work-mode signal as a
    ``field_provenances`` row named ``"work_mode"`` (not ``"remote_policy"``
    -- see ``opportunity/adapters/*.py``), *and*, going forward, directly on
    ``record.work_mode``. Older rows written before this brief's adapters
    landed have neither: ``record.work_mode`` defaults to
    ``"unspecified"`` (migration 0004's column default) until a backfill
    (``reextract_all``) re-derives it, and their only surviving signal is a
    legacy ``field_provenances`` row still named ``"remote_policy"`` from the
    pre-FR-006 adapter code. Rather than silently reporting "unspecified" for
    those rows when better information already exists, this function keeps
    reading that legacy key as a fallback -- but ONLY when ``record.work_mode``
    is still at its unbackfilled default; it is never used to override a
    genuine (even if ``"unspecified"``-by-inference) value the column already
    holds. The ``field_provenances`` row itself is never renamed or rewritten
    by this read path -- only a new write (a fresh poll, or ``reextract_all``)
    would ever replace it with a ``"work_mode"``-named row.

    Known, honest limitation: ``opportunity.persistence`` (frozen for this
    deliverable) stores ``responsibilities``/``requirements`` provenance only
    as an item *count* (e.g. ``create_field_provenance("responsibilities",
    ..., f"{len(responsibilities)} items", ...)`` in every adapter under
    ``opportunity/adapters/``) -- the underlying requirement/responsibility
    text itself is not persisted anywhere the schema currently exposes. There
    is therefore no faithful way to recover it here, and this function
    deliberately leaves those two tuples empty rather than fabricate content
    (per this project's hard rule against fabricated claims). The
    qualification/scoring engines already treat missing fields as unknown
    rather than as a hard failure, so this degrades to more
    "gap"/"unknown"-flagged dimensions for a reconstructed opportunity, never
    a crash or a fabricated pass.
    """
    if archive_payload is None:
        prov = _first_field_provenance_map(session, record.id)
    else:
        prov = {
            item.get("field_name"): item.get("normalized_value")
            for item in archive_payload.get("provenance") or []
            if item.get("field_name") and item.get("normalized_value") is not None
        }

    source = record.source_id
    raw_payload_json = (
        archive_payload.get("raw_payload_json")
        if archive_payload is not None
        else record.raw_payload_json
    )
    description = (
        archive_payload.get("description") or ""
        if archive_payload is not None
        else record.description
    )
    if raw_payload_json:
        try:
            raw_provenance = json.loads(raw_payload_json)
            source = raw_provenance.get("source_id") or source
        except (TypeError, ValueError):
            pass

    skills_raw = prov.get("skills", "")
    skills = tuple(s.strip() for s in skills_raw.split(",") if s.strip())

    geo = None
    geo_status = prov.get("geographic_eligibility")
    if geo_status:
        geo = GeographicEligibility(status=geo_status, reason="")

    # --- work_mode: record column first, legacy "remote_policy" provenance
    # fallback only when the column is still at its unbackfilled default. ---
    record_work_mode = getattr(record, "work_mode", None)
    if record_work_mode and record_work_mode != "unspecified":
        work_mode = _enum_or_default(WorkMode, record_work_mode, WorkMode.UNSPECIFIED)
    else:
        legacy_remote_policy_to_work_mode = {
            "remote": WorkMode.REMOTE, "hybrid": WorkMode.HYBRID, "on_site": WorkMode.ONSITE,
        }
        work_mode = legacy_remote_policy_to_work_mode.get(prov.get("remote_policy", ""), WorkMode.UNSPECIFIED)
    work_mode_source = getattr(record, "work_mode_source", None) or "none"

    remote_scope = _enum_or_default(RemoteScope, getattr(record, "remote_scope", None), RemoteScope.UNSPECIFIED)
    remote_scope_regions_raw = getattr(record, "remote_scope_regions", None)
    try:
        remote_scope_regions = tuple(json.loads(remote_scope_regions_raw)) if remote_scope_regions_raw else ()
    except (TypeError, ValueError):
        remote_scope_regions = ()

    # --- compensation: record columns first (A1M-authoritative), falling
    # back to the pre-existing field_provenances-derived reconstruction for
    # rows the migration/backfill has not touched. ---
    record_comp_min = getattr(record, "compensation_min", None)
    record_comp_max = getattr(record, "compensation_max", None)
    record_comp_currency = getattr(record, "compensation_currency", None)
    record_comp_period = getattr(record, "compensation_period", None)
    compensation = None
    if record_comp_min is not None or record_comp_max is not None or record_comp_currency or record_comp_period:
        compensation = Compensation(
            min_amount=float(record_comp_min) if record_comp_min is not None else None,
            max_amount=float(record_comp_max) if record_comp_max is not None else None,
            currency=record_comp_currency,
            interval=_enum_or_default(CompensationInterval, record_comp_period, CompensationInterval.UNSPECIFIED),
        )
    else:
        comp_min_raw = prov.get("compensation.min_amount")
        comp_max_raw = prov.get("compensation.max_amount")
        comp_currency = prov.get("compensation.currency") or None
        comp_interval = _enum_or_default(
            CompensationInterval, prov.get("compensation.interval"), CompensationInterval.UNSPECIFIED
        )
        if comp_min_raw or comp_max_raw or comp_currency or comp_interval != CompensationInterval.UNSPECIFIED:
            try:
                compensation = Compensation(
                    min_amount=float(comp_min_raw) if comp_min_raw else None,
                    max_amount=float(comp_max_raw) if comp_max_raw else None,
                    currency=comp_currency,
                    interval=comp_interval,
                )
            except ValueError:
                compensation = None

    return Opportunity(
        id=record.id,
        track=_enum_or_default(Track, record.track, Track.EMPLOYMENT),
        source=source or "unknown",
        source_url=record.source_url,
        source_id=record.source_id,
        organization=record.organization,
        title=record.title,
        description=description,
        responsibilities=(),
        requirements=(),
        skills=skills,
        seniority=_enum_or_default(SeniorityLevel, prov.get("seniority"), SeniorityLevel.UNSPECIFIED),
        employment_type=_enum_or_default(EmploymentType, prov.get("employment_type"), EmploymentType.UNSPECIFIED),
        location_raw=prov.get("location_raw", ""),
        work_mode=work_mode,
        work_mode_source=work_mode_source,
        location_country=getattr(record, "location_country", None) or "",
        location_city=getattr(record, "location_city", None) or "",
        location_region=getattr(record, "location_region", None) or "",
        remote_scope=remote_scope,
        remote_scope_regions=remote_scope_regions,
        geographic_eligibility=geo,
        compensation=compensation,
        posted_date=record.posted_date,
        closing_date=record.deadline,
        content_hash=record.content_hash,
    )


def make_evaluate_new_handler(
    *,
    session_factory: Optional[SessionFactory] = None,
    truth_pack_path: Optional[Any] = None,
    pack_loader: Optional[PackLoader] = None,
    scorer: Optional[OpportunityScorer] = None,
) -> Callable[[dict], None]:
    """Build an ``evaluate_new`` handler bound to the given (injectable) dependencies.

    Evaluates every opportunity that has no ``match_evaluations`` or
    ``feed_projection`` row for the *current* founder truth-pack hash, via
    ``matching.evaluate_persist.evaluate_and_store``.

    ``pack_loader`` / ``truth_pack_path`` are the injectable pack source:
    production code should pass neither (defaults to
    ``truth.pack.load_founder_pack``, which reads
    ``private/truth_pack.yaml``); tests must inject a ``pack_loader`` (or a
    ``truth_pack_path`` pointing at a fixture file) so no test ever reads
    ``private/``.

    Refusal semantics: if no truth pack is present (``TruthPackMissing``) or
    the pack fails to load/validate (``TruthPackInvalid``), the handler logs
    a structured refusal line and returns -- it never raises for this
    condition. No database session is opened before this check, so a refusal
    here writes nothing at all (no partial evaluation rows). This mirrors
    ``poll_source``'s read-disabled refusal: the job is treated as handled
    (``WorkerRunner`` calls ``complete_job``, not ``fail_job``), because a
    missing/invalid truth pack is a founder-side condition retrying cannot
    fix -- dead-lettering it after ``max_retries`` would just be a slower way
    of doing nothing, and every subsequent ``poll_source`` run would keep
    re-enqueueing ``evaluate_new`` regardless of this job's outcome.
    """
    loader = pack_loader or load_founder_pack
    _session_factory_holder: list[Optional[SessionFactory]] = [session_factory]

    def _resolve_session_factory() -> SessionFactory:
        if _session_factory_holder[0] is None:
            _session_factory_holder[0] = _production_session_factory()
        return _session_factory_holder[0]

    def handler(payload: dict) -> None:
        try:
            pack = loader(truth_pack_path)
        except (TruthPackMissing, TruthPackInvalid) as exc:
            logger.warning(
                "worker.evaluate_new_refused",
                extra={
                    "component": "worker.handlers",
                    "extra_data": {"reason": type(exc).__name__, "detail": str(exc)},
                },
            )
            return

        truth_graph = pack.graph
        truth_pack_hash = pack.truth_pack_hash

        session = _resolve_session_factory()()
        try:
            repository = StorageRepository(session)

            # A committed evaluation without its projection is unfinished
            # publication. Retry it after a projection failure instead of
            # treating the evaluation row alone as successful completion.
            evaluated_for_pack = (
                session.query(MatchEvaluationRecord.opportunity_id)
                .filter(
                    MatchEvaluationRecord.opportunity_id == OpportunityRecord.id,
                    MatchEvaluationRecord.truth_pack_hash == truth_pack_hash,
                )
                .exists()
            )
            projected_for_pack = (
                session.query(FeedProjectionRecord.opportunity_id)
                .filter(
                    FeedProjectionRecord.opportunity_id == OpportunityRecord.id,
                    FeedProjectionRecord.truth_pack_hash == truth_pack_hash,
                )
                .exists()
            )
            pending_records = (
                session.query(OpportunityRecord)
                .filter(or_(~evaluated_for_pack, ~projected_for_pack))
                .order_by(OpportunityRecord.id.asc())
                .limit(EVALUATE_NEW_BATCH_SIZE)
                .all()
            )

            for record in pending_records:
                archive_payload = None
                if record.description == "[archived]":
                    # Truth-pack changes may make a cold terminal row
                    # eligible again. Verify and read its lossless archive in
                    # memory only. The hot row and its compact archive marker
                    # remain untouched after scoring.
                    archive_payload = repository.load_cold_opportunity_payload(
                        record.id, record=record
                    )
                opportunity = _reconstruct_opportunity(
                    session, record, archive_payload=archive_payload
                )
                evaluate_and_store(
                    opportunity,
                    truth_graph,
                    repository,
                    truth_pack_hash=truth_pack_hash,
                    evaluated_at=datetime.now(timezone.utc),
                    scorer=scorer,
                )

            # A bounded job may leave eligible rows.  Coalescing preserves a
            # single RUNNING evaluator plus one successor, so a poll committing
            # work while this job is running cannot strand that work or create a
            # global enqueue storm.
            remaining = (
                session.query(OpportunityRecord.id)
                .filter(or_(~evaluated_for_pack, ~projected_for_pack))
                .limit(1)
                .first()
            )
            if remaining is not None:
                BackgroundWorkerQueue(session).enqueue_evaluate_new_coalesced(commit=False)

            logger.info(
                "worker.evaluate_new_completed",
                extra={
                    "component": "worker.handlers",
                    "extra_data": {
                        "truth_pack_hash": truth_pack_hash,
                        "evaluated_count": len(pending_records),
                    },
                },
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return handler


#: Interface for the (as of this work order, not-yet-landed) founder-control
#: field extractor that the concurrent A1-extract work order is building:
#: ``(raw_payload: dict) -> Mapping[str, Any]`` mapping A1M column name (see
#: ``_A1M_COLUMNS`` below and ``storage/migrations/versions/
#: 0004_founder_control.py``) to its freshly extracted value. Injectable so a
#: test can supply a fake extractor without waiting on that concurrent order.
FounderControlExtractor = Callable[[dict], Mapping[str, Any]]

#: Every ``opportunities`` column this work order's migration
#: (``0004_founder_control``) added that ``reextract_all`` is responsible for
#: refreshing. ``search_tsv`` is deliberately excluded: it is a derived
#: search index, not a directly-extracted field, and is out of scope here.
_A1M_COLUMNS = (
    "work_mode", "work_mode_source", "location_country", "location_city",
    "location_region", "remote_scope", "remote_scope_regions", "employment_type",
    "seniority_level", "compensation_min", "compensation_max", "compensation_currency",
    "compensation_period", "title_family", "title_level", "family_key",
)


def reextract_all(
    session: Any,
    *,
    extractor: Optional[FounderControlExtractor] = None,
    batch_size: int = 200,
) -> dict:
    """Re-parse every stored ``raw_payload_json`` and update the A1M
    founder-control columns on ``opportunities`` in place.

    Batched: at most ``batch_size`` rows are loaded and committed per
    iteration, ordered by ``id`` ascending with a keyset (``id > last_id``)
    cursor, so an interrupted run can simply be re-invoked and makes forward
    progress from where the last committed batch left off, without an
    ``OFFSET`` skipping or re-scanning rows.

    Idempotent: a row is only written (and only counted in ``changed``) when
    at least one extracted column's value actually differs from what is
    already stored, so re-running against unchanged underlying data (and an
    unchanged extractor) always reports ``changed == 0`` on the second and
    every subsequent run.

    ``extractor`` is the injectable interface described by
    ``FounderControlExtractor`` above. If neither ``extractor`` nor the
    module-level default (populated only once the concurrent A1-extract work
    order's ``opportunity.extraction.extract_founder_control_fields`` exists
    on this branch) is available, this is a documented no-op: it scans zero
    rows, changes zero rows, and reports
    ``{"status": "extractor_unavailable", "scanned": 0, "changed": 0}``.
    Extraction logic itself is out of scope for this work order -- see
    ``reports/evidence/FR-006/orders/A1M-migration.md`` item 4.
    """
    extract_fn = extractor or _default_founder_control_extractor
    if extract_fn is None:
        logger.warning(
            "worker.reextract_all_extractor_unavailable",
            extra={"component": "worker.handlers", "extra_data": {"scanned": 0, "changed": 0}},
        )
        return {"status": "extractor_unavailable", "scanned": 0, "changed": 0}

    scanned = 0
    changed = 0
    last_id: Optional[str] = None
    while True:
        query = session.query(OpportunityRecord).order_by(OpportunityRecord.id.asc())
        if last_id is not None:
            query = query.filter(OpportunityRecord.id > last_id)
        batch = query.limit(batch_size).all()
        if not batch:
            break
        for record in batch:
            last_id = record.id
            scanned += 1
            if not record.raw_payload_json:
                continue
            try:
                raw_payload = json.loads(record.raw_payload_json)
            except (TypeError, ValueError):
                continue
            extracted = extract_fn(raw_payload)
            row_changed = False
            for column in _A1M_COLUMNS:
                if column not in extracted:
                    continue
                new_value = extracted[column]
                if getattr(record, column) != new_value:
                    setattr(record, column, new_value)
                    row_changed = True
            if row_changed:
                changed += 1
        session.commit()

    logger.info(
        "worker.reextract_all_completed",
        extra={"component": "worker.handlers", "extra_data": {"scanned": scanned, "changed": changed}},
    )
    return {"status": "ok", "scanned": scanned, "changed": changed}


def make_reextract_all_handler(
    *,
    session_factory: Optional[SessionFactory] = None,
    extractor: Optional[FounderControlExtractor] = None,
    batch_size: int = 200,
) -> Callable[[dict], None]:
    """Build the ``reextract_all`` job handler bound to the given (injectable) dependencies.

    See ``reextract_all`` (above) for the batching/idempotency/no-op
    contract this handler wraps in a single committed session per batch.
    """
    _session_factory_holder: list[Optional[SessionFactory]] = [session_factory]

    def _resolve_session_factory() -> SessionFactory:
        if _session_factory_holder[0] is None:
            _session_factory_holder[0] = _production_session_factory()
        return _session_factory_holder[0]

    def handler(payload: dict) -> None:
        session = _resolve_session_factory()()
        try:
            reextract_all(session, extractor=extractor, batch_size=batch_size)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return handler


def backfill_family_keys(session: Any, *, batch_size: int = 200) -> dict:
    """A2 (BRIEF-FR-006 clustering) backfill: compute and persist
    ``opportunities.family_key`` for every existing row.

    Unlike ``reextract_all`` above, this needs no raw-payload reconstruction
    and no injectable extractor: ``family_key`` (see
    ``opportunity.clustering.compute_family_key``) is a pure function of only
    ``organization`` and ``title``, both stored with full fidelity on
    ``OpportunityRecord`` itself.

    Batched (keyset cursor, ``id`` ascending, ``batch_size`` rows per
    committed iteration) and idempotent: a row is only written -- and only
    counted in ``changed`` -- when the freshly computed key differs from
    what is already stored, so re-running this against unchanged data
    reports ``changed == 0`` on the second and every subsequent run.
    """
    scanned = 0
    changed = 0
    last_id: Optional[str] = None
    while True:
        query = session.query(OpportunityRecord).order_by(OpportunityRecord.id.asc())
        if last_id is not None:
            query = query.filter(OpportunityRecord.id > last_id)
        batch = query.limit(batch_size).all()
        if not batch:
            break
        for record in batch:
            last_id = record.id
            scanned += 1
            computed_key = compute_family_key(record.organization, record.title)
            if record.family_key != computed_key:
                record.family_key = computed_key
                changed += 1
        session.commit()

    logger.info(
        "worker.backfill_family_keys_completed",
        extra={"component": "worker.handlers", "extra_data": {"scanned": scanned, "changed": changed}},
    )
    return {"status": "ok", "scanned": scanned, "changed": changed}


def make_backfill_family_keys_handler(
    *,
    session_factory: Optional[SessionFactory] = None,
    batch_size: int = 200,
) -> Callable[[dict], None]:
    """Build the ``backfill_family_keys`` job handler bound to the given
    (injectable) session factory. See ``backfill_family_keys`` (above) for
    the batching/idempotency contract this handler wraps in a single
    committed session per batch."""
    _session_factory_holder: list[Optional[SessionFactory]] = [session_factory]

    def _resolve_session_factory() -> SessionFactory:
        if _session_factory_holder[0] is None:
            _session_factory_holder[0] = _production_session_factory()
        return _session_factory_holder[0]

    def handler(payload: dict) -> None:
        session = _resolve_session_factory()()
        try:
            backfill_family_keys(session, batch_size=batch_size)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

def make_reverify_stale_handler(
    *,
    session_factory: Optional[SessionFactory] = None,
    registry: Optional[SourceRegistry] = None,
    rate_limiter: Optional[RateLimiter] = None,
    reverify_fn: Optional[Callable[[str], dict]] = None,
    stale_after_days: int = 14,
) -> Callable[[dict], None]:
    """Build the ``reverify_stale`` job handler bound to the given dependencies."""
    from opportunity.reverification import StaleOpportunityReverifier

    _session_factory_holder: list[Optional[SessionFactory]] = [session_factory]

    def _resolve_session_factory() -> SessionFactory:
        if _session_factory_holder[0] is None:
            _session_factory_holder[0] = _production_session_factory()
        return _session_factory_holder[0]

    def handler(payload: dict) -> None:
        session = _resolve_session_factory()()
        try:
            days = payload.get("stale_after_days", stale_after_days) if payload else stale_after_days
            board_result = StaleOpportunityReverifier.reverify_greenhouse_boards(
                session,
                registry=registry,
                rate_limiter=rate_limiter,
                request_fn=reverify_fn,
            )
            result = StaleOpportunityReverifier.reverify_stale_opportunities(
                session,
                registry=registry,
                rate_limiter=rate_limiter,
                reverify_fn=reverify_fn,
                stale_after_days=days,
            )
            result = {**result, **board_result}
            logger.info(
                "worker.reverify_stale_completed",
                extra={"component": "worker.handlers", "extra_data": result},
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return handler


def default_handler_registry(
    *,
    registry: Optional[SourceRegistry] = None,
    transport: Optional[BaseTransport] = None,
    adapters=None,
    refusal_sink: Optional[RefusalSink] = None,
    session_factory: Optional[SessionFactory] = None,
    truth_pack_path: Optional[Any] = None,
    pack_loader: Optional[PackLoader] = None,
    scorer: Optional[OpportunityScorer] = None,
) -> MutableMapping[str, Callable[[dict], None]]:
    """Build the default job_type -> handler mapping used by ``python -m worker``.

    Tests should call this with an injected ``transport`` (a ``MockTransport``),
    an injected ``session_factory`` (pointed at an isolated test database), and
    (for ``evaluate_new`` coverage) an injected ``pack_loader``/``truth_pack_path``
    rather than relying on the real-network, real-database, real-``private/``
    defaults.
    """
    return {
        "noop": noop,
        "poll_source": make_poll_source_handler(
            registry=registry,
            transport=transport,
            adapters=adapters,
            refusal_sink=refusal_sink,
            session_factory=session_factory,
            truth_pack_path=truth_pack_path,
            pack_loader=pack_loader,
            scorer=scorer,
        ),
        "evaluate_new": make_evaluate_new_handler(
            session_factory=session_factory,
            truth_pack_path=truth_pack_path,
            pack_loader=pack_loader,
            scorer=scorer,
        ),
        "reextract_all": make_reextract_all_handler(session_factory=session_factory),
        "backfill_family_keys": make_backfill_family_keys_handler(session_factory=session_factory),
        "reverify_stale": make_reverify_stale_handler(
            session_factory=session_factory,
            registry=registry,
        ),
        "refresh_feed_projections": make_refresh_feed_projections_handler(
            session_factory=session_factory,
            truth_pack_path=truth_pack_path,
            pack_loader=pack_loader,
        ),
    }


def make_refresh_feed_projections_handler(
    *,
    session_factory: Optional[SessionFactory] = None,
    truth_pack_path: Optional[Any] = None,
    pack_loader: Optional[PackLoader] = None,
) -> Callable[[dict], None]:
    """Build a handler for ``refresh_feed_projections`` background jobs.

    Asynchronously refreshes feed projections scoped to the authoritative
    loaded truth_pack_hash without blocking founder settings requests.
    """
    _session_factory_holder: list[Optional[SessionFactory]] = [session_factory]
    pack_loader_fn = pack_loader or load_founder_pack

    def _resolve_session_factory() -> SessionFactory:
        if _session_factory_holder[0] is None:
            _session_factory_holder[0] = _production_session_factory()
        return _session_factory_holder[0]

    def handler(payload: dict) -> None:
        target_hash = payload.get("truth_pack_hash") if payload else None
        if not target_hash:
            logger.warning(
                "worker.refresh_projections_no_hash",
                extra={"component": "worker.handlers"},
            )
            return

        try:
            pack = pack_loader_fn(truth_pack_path)
        except (TruthPackMissing, TruthPackInvalid) as exc:
            logger.warning(
                "worker.refresh_projections_skipped_no_pack",
                extra={"component": "worker.handlers", "extra_data": {"reason": type(exc).__name__}},
            )
            raise

        if pack.truth_pack_hash != target_hash:
            logger.info(
                "worker.refresh_projections_hash_mismatch",
                extra={
                    "component": "worker.handlers",
                    "extra_data": {"expected": target_hash, "current": pack.truth_pack_hash},
                },
            )
            return

        session = _resolve_session_factory()()
        try:
            from storage.feed_projection_service import refresh_existing_feed_projections

            count = refresh_existing_feed_projections(
                session,
                truth_graph=pack.graph,
                truth_pack_hash=target_hash,
            )
            session.commit()
            logger.info(
                "worker.refresh_projections_completed",
                extra={
                    "component": "worker.handlers",
                    "extra_data": {"refreshed_count": count, "truth_pack_hash": target_hash},
                },
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return handler


