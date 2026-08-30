"""Unified Ingestion Pipeline for OpportunityOS.

Coordinates multi-source feed ingestion, normalization, geographic classification,
two-layer deduplication, and health diagnostics into an immutable IngestionBatch.
"""
from __future__ import annotations

import datetime
import uuid
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


@dataclass(frozen=True, slots=True)
class IngestionBatch:
    batch_id: str
    ingested_at: str
    total_raw_opportunities: int
    unique_opportunities: tuple[Opportunity, ...]
    clusters: tuple[OpportunityCluster, ...]
    health_reports: tuple[SourceHealthReport, ...]
    tracks_summary: tuple[tuple[str, int], ...]
    geographic_summary: tuple[tuple[str, int], ...]

    @property
    def is_clean(self) -> bool:
        return all(r.status is SourceHealthStatus.HEALTHY for r in self.health_reports)


class OpportunityPipeline:
    """Orchestrates multi-source opportunity discovery, normalization, and deduplication."""

    def __init__(
        self,
        adapters: Sequence[BaseAdapter] | None = None,
        health_monitor: SourceHealthMonitor | None = None,
    ) -> None:
        self.adapters = list(adapters or get_all_standard_adapters())
        self.health_monitor = health_monitor or SourceHealthMonitor()

    def process_payloads(
        self,
        payload_map: Mapping[str, str],
        fetched_at: str | None = None,
    ) -> IngestionBatch:
        """Process a mapping of source_id -> raw payload string into an IngestionBatch."""
        now_iso = fetched_at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        batch_id = str(uuid.uuid4())[:8]

        all_raw_opportunities: list[Opportunity] = []
        adapter_by_id = {adapter.source_id: adapter for adapter in self.adapters}

        for source_id, payload in payload_map.items():
            adapter = adapter_by_id.get(source_id)
            if not adapter:
                # Unregistered adapter payload
                continue

            try:
                opportunities = adapter.parse_payload(
                    payload=payload,
                    raw_pointer=f"fixture:{source_id}",
                    fetched_at=now_iso,
                )
                valid_opportunities = [o for o in opportunities if isinstance(o, Opportunity)]
                all_raw_opportunities.extend(valid_opportunities)

                self.health_monitor.record_run(
                    source_id=source_id,
                    records_fetched=len(opportunities),
                    records_parsed=len(opportunities),
                    records_valid=len(valid_opportunities),
                    fetch_latency_ms=10,
                    status_code=200,
                    now_iso=now_iso,
                )
            except Exception as e:
                self.health_monitor.record_run(
                    source_id=source_id,
                    records_fetched=0,
                    records_parsed=0,
                    records_valid=0,
                    fetch_latency_ms=0,
                    status_code=500,
                    error_message=str(e),
                    has_schema_drift=True,
                    now_iso=now_iso,
                )

        # Execute two-layer deduplication
        dedup_result = deduplicate_opportunities(all_raw_opportunities)

        # Compute summary statistics
        track_counts: dict[str, int] = {}
        geo_counts: dict[str, int] = {"eligible": 0, "ineligible": 0, "unclear": 0}

        for opp in dedup_result.unique_opportunities:
            track_counts[opp.track.value] = track_counts.get(opp.track.value, 0) + 1
            if opp.geographic_eligibility:
                status = opp.geographic_eligibility.status
                geo_counts[status] = geo_counts.get(status, 0) + 1

        tracks_summary = tuple(sorted(track_counts.items()))
        geographic_summary = tuple(sorted(geo_counts.items()))

        return IngestionBatch(
            batch_id=batch_id,
            ingested_at=now_iso,
            total_raw_opportunities=len(all_raw_opportunities),
            unique_opportunities=dedup_result.unique_opportunities,
            clusters=dedup_result.clusters,
            health_reports=self.health_monitor.all_reports,
            tracks_summary=tracks_summary,
            geographic_summary=geographic_summary,
        )
