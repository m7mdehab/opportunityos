"""Opportunity Ingestion Pipeline Orchestrator."""
from __future__ import annotations

import collections
import datetime
import hashlib
from dataclasses import dataclass
from typing import Mapping, Sequence

from .adapters import BaseAdapter, get_all_standard_adapters
from .dedupe import DeduplicationResult, deduplicate_opportunities
from .health import SourceHealthMonitor
from .models import (
    Opportunity,
    OpportunityCluster,
    SourceHealthReport,
    SourceHealthStatus,
    Track,
)
from .registry import SourceRegistry
from .transport import AcquisitionResult, AcquisitionService, BaseTransport, MockTransport


@dataclass(frozen=True, slots=True)
class IngestionBatch:
    batch_id: str
    run_id: str
    ingested_at: str
    opportunities: tuple[Opportunity, ...]
    clusters: tuple[OpportunityCluster, ...]
    health_reports: tuple[SourceHealthReport, ...]
    total_raw_ingested: int
    total_unique_opportunities: int
    exact_duplicates_removed: int
    cross_source_duplicates_clustered: int
    ambiguous_duplicates_count: int
    track_counts: tuple[tuple[str, int], ...]
    eligibility_counts: tuple[tuple[str, int], ...]

    @property
    def is_clean(self) -> bool:
        """A batch is clean only if at least one source was ingested and ALL sources are HEALTHY."""
        if not self.health_reports:
            return False
        return all(r.status is SourceHealthStatus.HEALTHY for r in self.health_reports)


class OpportunityPipeline:
    """Orchestrates authorized multi-source opportunity discovery, normalization, deduplication, and health."""

    def __init__(
        self,
        adapters: Sequence[BaseAdapter] | None = None,
        registry: SourceRegistry | None = None,
        transport: BaseTransport | None = None,
    ) -> None:
        self.registry = registry or SourceRegistry()
        self.acquisition = AcquisitionService(registry=self.registry, transport=transport or MockTransport())
        self._adapters: dict[str, BaseAdapter] = {}
        adapter_list = adapters if adapters is not None else get_all_standard_adapters()
        for adapter in adapter_list:
            self._adapters[adapter.source_id] = adapter
        self.health_monitor = SourceHealthMonitor()

    def register_adapter(self, adapter: BaseAdapter) -> None:
        self._adapters[adapter.source_id] = adapter

    def process_payloads(
        self,
        payload_map: Mapping[str, str],
        now_iso: str | None = None,
        run_id: str = "run_default",
    ) -> IngestionBatch:
        """Process pre-fetched or offline test payloads across registered adapters."""
        timestamp = now_iso or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        all_raw_opportunities: list[Opportunity] = []
        total_raw = 0

        for source_id, payload in payload_map.items():
            adapter = self._adapters.get(source_id)
            if not adapter:
                self.health_monitor.record_run(
                    source_id=source_id,
                    transport_status_code=400,
                    transport_error=f"Unregistered adapter for payload source '{source_id}'",
                    records_raw_count=0,
                    records_parsed=0,
                    records_valid=0,
                    now_iso=timestamp,
                )
                continue

            # Verify registry policy
            authorized, reason = self.registry.validate_preflight(source_id, adapter.feed_url, adapter.method)
            if not authorized:
                self.health_monitor.record_run(
                    source_id=source_id,
                    transport_status_code=403,
                    transport_error=reason,
                    records_raw_count=0,
                    records_parsed=0,
                    records_valid=0,
                    now_iso=timestamp,
                )
                continue

            try:
                parsed = adapter.parse_payload(payload, raw_pointer=f"payload:{source_id}", fetched_at=timestamp)
                total_raw += len(parsed)
                all_raw_opportunities.extend(parsed)

                # Schema drift detection
                is_drift = bool(payload.strip() and len(payload) > 50 and len(parsed) == 0)

                self.health_monitor.record_run(
                    source_id=source_id,
                    transport_status_code=200,
                    records_raw_count=len(parsed),
                    records_parsed=len(parsed),
                    records_valid=len(parsed),
                    fetch_latency_ms=10,
                    has_schema_drift=is_drift,
                    now_iso=timestamp,
                )
            except Exception as e:
                self.health_monitor.record_run(
                    source_id=source_id,
                    transport_status_code=200,
                    records_raw_count=0,
                    records_parsed=0,
                    records_valid=0,
                    parser_error=f"Parser exception: {str(e)}",
                    now_iso=timestamp,
                )

        # Conservative Deduplication
        dedup_result = deduplicate_opportunities(all_raw_opportunities)

        # Track summaries
        track_counter: collections.Counter[str] = collections.Counter()
        for opp in dedup_result.unique_opportunities:
            track_counter[opp.track.value] += 1
        track_counts = tuple(sorted(track_counter.items()))

        # Eligibility summaries
        geo_counter: collections.Counter[str] = collections.Counter()
        for opp in dedup_result.unique_opportunities:
            if opp.geographic_eligibility:
                geo_counter[opp.geographic_eligibility.status] += 1
            else:
                geo_counter["unspecified"] += 1
        eligibility_counts = tuple(sorted(geo_counter.items()))

        # Deterministic batch ID (derived from sorted unique opportunity IDs)
        if dedup_result.unique_opportunities:
            id_str = ",".join(sorted(o.id for o in dedup_result.unique_opportunities))
            batch_id = hashlib.sha256(f"batch:{id_str}".encode("utf-8")).hexdigest()[:16]
        else:
            batch_id = hashlib.sha256(f"batch:empty:{timestamp}".encode("utf-8")).hexdigest()[:16]

        return IngestionBatch(
            batch_id=batch_id,
            run_id=run_id,
            ingested_at=timestamp,
            opportunities=dedup_result.unique_opportunities,
            clusters=dedup_result.clusters,
            health_reports=self.health_monitor.all_reports,
            total_raw_ingested=total_raw,
            total_unique_opportunities=len(dedup_result.unique_opportunities),
            exact_duplicates_removed=dedup_result.exact_duplicates_count,
            cross_source_duplicates_clustered=dedup_result.cross_source_duplicates_count,
            ambiguous_duplicates_count=dedup_result.ambiguous_duplicates_count,
            track_counts=track_counts,
            eligibility_counts=eligibility_counts,
        )

    def execute_discovery(
        self,
        source_ids: Sequence[str] | None = None,
        now_iso: str | None = None,
        run_id: str = "run_default",
    ) -> IngestionBatch:
        """Execute authorized network acquisition and pipeline ingestion."""
        timestamp = now_iso or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        target_ids = source_ids if source_ids is not None else list(self._adapters.keys())
        payload_map: dict[str, str] = {}

        for source_id in target_ids:
            adapter = self._adapters.get(source_id)
            if not adapter:
                self.health_monitor.record_run(
                    source_id=source_id,
                    transport_status_code=400,
                    transport_error=f"Unregistered adapter '{source_id}'",
                    now_iso=timestamp,
                )
                continue

            acq_res = self.acquisition.acquire(
                source_id=source_id,
                url=adapter.feed_url,
                method=adapter.method,
            )

            if not acq_res.authorized:
                self.health_monitor.record_run(
                    source_id=source_id,
                    transport_status_code=acq_res.response.status_code,
                    transport_error=acq_res.refusal_reason,
                    fetch_latency_ms=acq_res.response.latency_ms,
                    now_iso=timestamp,
                )
            elif not acq_res.response.is_success:
                self.health_monitor.record_run(
                    source_id=source_id,
                    transport_status_code=acq_res.response.status_code,
                    transport_error=acq_res.response.error_message,
                    fetch_latency_ms=acq_res.response.latency_ms,
                    now_iso=timestamp,
                )
            else:
                payload_map[source_id] = acq_res.response.body

        return self.process_payloads(payload_map, now_iso=timestamp, run_id=run_id)
