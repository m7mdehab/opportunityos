"""Job handlers for the background worker runner.

Exactly two job types are supported:
  - ``noop``: does nothing; used for smoke tests / queue plumbing checks.
  - ``poll_source``: invokes the governed opportunity acquisition path for one
    source, after checking the SourceRegistry read policy. A source whose read
    automation is disabled is refused (never fetched) and the refusal is
    recorded via a structured log line and, when provided, an injectable
    refusal sink -- this is the mechanism the end-to-end test observes. A
    source that is allowed is fetched, normalized, and persisted (via
    ``opportunity.persistence.persist_batch``) to the ``opportunities`` /
    ``field_provenances`` tables.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, MutableMapping, Optional

from core.logging import get_logger, redact_data
from opportunity.persistence import persist_batch
from opportunity.pipeline import OpportunityPipeline
from opportunity.registry import SourceRegistry
from opportunity.transport import BaseTransport, HttpTransport
from storage.repository import StorageRepository

logger = get_logger("opportunityos.worker.handlers")

#: Reason code recorded when poll_source refuses a read-disabled source.
REFUSAL_REASON_READ_DISABLED = "read_disabled_by_policy"

RefusalSink = Callable[[Mapping[str, str]], None]
#: A zero-arg callable returning a new SQLAlchemy ``Session`` (i.e. a
#: ``sessionmaker``/``storage.engine.get_session_factory(engine)`` result).
SessionFactory = Callable[[], Any]


def noop(payload: dict) -> None:
    """Smoke-test handler: accepts any payload and does nothing."""
    return None


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


def make_poll_source_handler(
    *,
    registry: Optional[SourceRegistry] = None,
    transport: Optional[BaseTransport] = None,
    adapters=None,
    refusal_sink: Optional[RefusalSink] = None,
    session_factory: Optional[SessionFactory] = None,
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
    read-disabled refusal path never calls ``session_factory`` at all: no
    session is opened and no persistence code runs for a refused source.
    """
    reg = registry or SourceRegistry()
    fetch_transport = transport or HttpTransport()
    _session_factory_holder: list[Optional[SessionFactory]] = [session_factory]

    def _resolve_session_factory() -> SessionFactory:
        if _session_factory_holder[0] is None:
            _session_factory_holder[0] = _production_session_factory()
        return _session_factory_holder[0]

    def handler(payload: dict) -> None:
        source_id = payload.get("source_id") if payload else None
        if not source_id:
            raise ValueError("poll_source payload requires a non-empty 'source_id'")

        if not reg.is_read_allowed(source_id):
            _record_refusal(source_id, refusal_sink)
            return

        logger.info(
            "worker.poll_source_fetching",
            extra={"component": "worker.handlers", "extra_data": {"source_id": source_id}},
        )
        pipeline = OpportunityPipeline(adapters=adapters, registry=reg, transport=fetch_transport)
        batch = pipeline.execute_discovery(source_ids=[source_id])

        session = _resolve_session_factory()()
        try:
            repository = StorageRepository(session)
            result = persist_batch(batch, repository)
            session.commit()
            logger.info(
                "worker.poll_source_persisted",
                extra={
                    "component": "worker.handlers",
                    "extra_data": {
                        "source_id": source_id,
                        "inserted": result.inserted_count,
                        "unchanged": result.unchanged_count,
                        "updated": result.updated_count,
                    },
                },
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
) -> MutableMapping[str, Callable[[dict], None]]:
    """Build the default job_type -> handler mapping used by ``python -m worker``.

    Tests should call this with an injected ``transport`` (a ``MockTransport``)
    and an injected ``session_factory`` (pointed at an isolated test database)
    rather than relying on the real-network, real-database defaults.
    """
    return {
        "noop": noop,
        "poll_source": make_poll_source_handler(
            registry=registry,
            transport=transport,
            adapters=adapters,
            refusal_sink=refusal_sink,
            session_factory=session_factory,
        ),
    }
