"""Job handlers for the background worker runner.

Exactly two job types are supported:
  - ``noop``: does nothing; used for smoke tests / queue plumbing checks.
  - ``poll_source``: invokes the governed opportunity acquisition path for one
    source, after checking the SourceRegistry read policy. A source whose read
    automation is disabled is refused (never fetched) and the refusal is
    recorded via a structured log line and, when provided, an injectable
    refusal sink -- this is the mechanism the end-to-end test observes.
"""
from __future__ import annotations

from typing import Callable, Mapping, MutableMapping, Optional

from core.logging import get_logger, redact_data
from opportunity.pipeline import OpportunityPipeline
from opportunity.registry import SourceRegistry
from opportunity.transport import BaseTransport, HttpTransport

logger = get_logger("opportunityos.worker.handlers")

#: Reason code recorded when poll_source refuses a read-disabled source.
REFUSAL_REASON_READ_DISABLED = "read_disabled_by_policy"

RefusalSink = Callable[[Mapping[str, str]], None]


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


def make_poll_source_handler(
    *,
    registry: Optional[SourceRegistry] = None,
    transport: Optional[BaseTransport] = None,
    adapters=None,
    refusal_sink: Optional[RefusalSink] = None,
) -> Callable[[dict], None]:
    """Build a ``poll_source`` handler bound to the given (injectable) dependencies.

    ``transport`` is the injectable fetcher: production code should pass nothing
    (defaults to the real ``HttpTransport``); tests must inject a ``MockTransport``
    with fixture data so no network I/O occurs.
    """
    reg = registry or SourceRegistry()
    fetch_transport = transport or HttpTransport()

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
        pipeline.execute_discovery(source_ids=[source_id])

    return handler


def default_handler_registry(
    *,
    registry: Optional[SourceRegistry] = None,
    transport: Optional[BaseTransport] = None,
    adapters=None,
    refusal_sink: Optional[RefusalSink] = None,
) -> MutableMapping[str, Callable[[dict], None]]:
    """Build the default job_type -> handler mapping used by ``python -m worker``.

    Tests should call this with an injected ``transport`` (a ``MockTransport``)
    and/or ``refusal_sink`` rather than relying on the real-network default.
    """
    return {
        "noop": noop,
        "poll_source": make_poll_source_handler(
            registry=registry,
            transport=transport,
            adapters=adapters,
            refusal_sink=refusal_sink,
        ),
    }
