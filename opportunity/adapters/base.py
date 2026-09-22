"""Base Adapter Interface for OpportunityOS Feeds."""
from __future__ import annotations

import abc
import datetime
import hashlib
from typing import Any

from opportunity.models import (
    Opportunity,
    ParseResult,
    SourceProvenance,
    Track,
    serialize_source_record,
)


class BaseAdapter(abc.ABC):
    """Abstract base class for all opportunity source adapters."""

    def __init__(
        self,
        source_id: str,
        track: Track,
        feed_url: str,
        policy_url: str,
        rate_limit_rpm: int = 60,
        method: str = "GET",
        default_body: dict[str, Any] | None = None,
    ) -> None:
        self.source_id = source_id
        self.track = track
        self.feed_url = feed_url
        self.policy_url = policy_url
        self.rate_limit_rpm = rate_limit_rpm
        self.method = method
        self.default_body = default_body

    @abc.abstractmethod
    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> ParseResult:
        """Parse raw feed payload into a structured ParseResult containing Opportunities and raw count."""
        raise NotImplementedError

    def create_provenance(
        self,
        source_url: str,
        raw_pointer: str = "",
        fetched_at: str = "",
        payload: str = "",
        fetch_latency_ms: int = 0,
        feed_checksum: str = "",
    ) -> SourceProvenance:
        """Create deterministic SourceProvenance."""
        now_iso = fetched_at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest() if payload else ""
        return SourceProvenance(
            source_id=self.source_id,
            source_url=source_url,
            feed_url=self.feed_url,
            fetched_at=now_iso,
            fetch_latency_ms=fetch_latency_ms,
            raw_pointer=raw_pointer,
            payload_checksum=checksum,
            feed_checksum=feed_checksum or checksum,
        )

    @staticmethod
    def serialize_source_record(value: Any) -> str:
        """Keep the exact source record recoverable outside PostgreSQL."""
        return serialize_source_record(value)
