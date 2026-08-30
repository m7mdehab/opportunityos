"""Source Health & Diagnostics Engine for OpportunityOS Ingestion."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Sequence

from .models import SourceHealthReport, SourceHealthStatus


class SourceHealthMonitor:
    """Tracks ingestion status, diagnostics, and schema drift across sources."""

    def __init__(self) -> None:
        self._reports: dict[str, SourceHealthReport] = {}

    def record_run(
        self,
        source_id: str,
        records_fetched: int,
        records_parsed: int,
        records_valid: int,
        fetch_latency_ms: int = 0,
        status_code: int = 200,
        error_message: str | None = None,
        has_schema_drift: bool = False,
        now_iso: str | None = None,
    ) -> SourceHealthReport:
        """Record an ingestion run and evaluate deterministic health status."""
        timestamp = now_iso or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        diag_list: list[tuple[str, str]] = [
            ("status_code", str(status_code)),
            ("records_fetched", str(records_fetched)),
            ("records_parsed", str(records_parsed)),
            ("records_valid", str(records_valid)),
        ]

        if status_code == 429:
            health_status = SourceHealthStatus.RATE_LIMITED
        elif status_code in {401, 403}:
            health_status = SourceHealthStatus.POLICY_RESTRICTION
        elif status_code in {500, 502, 503, 504} or "timeout" in (error_message or "").casefold():
            health_status = SourceHealthStatus.TRANSIENT_FAILURE
        elif error_message and ("parse" in error_message.casefold() or "json" in error_message.casefold() or "xml" in error_message.casefold()):
            health_status = SourceHealthStatus.PERSISTENT_FAILURE
        elif has_schema_drift or (records_fetched > 0 and records_parsed == 0):
            health_status = SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED
            diag_list.append(("drift_note", "Non-empty payload yielded 0 valid opportunities"))
        elif records_fetched == 0 and records_parsed == 0:
            health_status = SourceHealthStatus.EMPTY_RESULTS
            diag_list.append(("empty_note", "Feed returned zero records"))
        elif records_valid > 0:
            health_status = SourceHealthStatus.HEALTHY
        else:
            health_status = SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED

        last_success = timestamp if health_status is SourceHealthStatus.HEALTHY else (
            self._reports[source_id].last_successful_ingestion if source_id in self._reports else None
        )

        report = SourceHealthReport(
            source_id=source_id,
            status=health_status,
            records_fetched=records_fetched,
            records_parsed=records_parsed,
            records_valid=records_valid,
            fetch_latency_ms=fetch_latency_ms,
            last_successful_ingestion=last_success,
            error_message=error_message,
            diagnostics=tuple(diag_list),
        )

        self._reports[source_id] = report
        return report

    def get_report(self, source_id: str) -> SourceHealthReport | None:
        return self._reports.get(source_id)

    @property
    def all_reports(self) -> tuple[SourceHealthReport, ...]:
        return tuple(self._reports.values())

    @property
    def healthy_sources(self) -> tuple[str, ...]:
        return tuple(r.source_id for r in self._reports.values() if r.status is SourceHealthStatus.HEALTHY)

    @property
    def degraded_sources(self) -> tuple[str, ...]:
        return tuple(r.source_id for r in self._reports.values() if r.status is not SourceHealthStatus.HEALTHY)
