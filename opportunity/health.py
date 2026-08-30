"""Source Health & Diagnostics Engine for OpportunityOS Ingestion."""
from __future__ import annotations

import datetime
from typing import Sequence

from .models import SourceHealthReport, SourceHealthStatus


class SourceHealthMonitor:
    """Tracks ingestion status, diagnostics, and schema drift across sources."""

    def __init__(self) -> None:
        self._reports: dict[str, SourceHealthReport] = {}

    def record_run(
        self,
        source_id: str,
        transport_status_code: int = 200,
        transport_error: str | None = None,
        records_raw_count: int = 0,
        records_parsed: int = 0,
        records_valid: int = 0,
        fetch_latency_ms: int = 0,
        has_schema_drift: bool = False,
        parser_error: str | None = None,
        now_iso: str | None = None,
    ) -> SourceHealthReport:
        """Record an acquisition and ingestion run with separated transport and parser diagnostics."""
        timestamp = now_iso or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        # 1. Determine transport status
        if transport_status_code == 429:
            transport_status = "RATE_LIMITED"
            overall_status = SourceHealthStatus.RATE_LIMITED
        elif transport_status_code in {401, 403}:
            transport_status = "POLICY_RESTRICTION"
            overall_status = SourceHealthStatus.POLICY_RESTRICTION
        elif transport_status_code in {500, 502, 503, 504} or (transport_error and "timeout" in transport_error.casefold()):
            transport_status = "TRANSIENT_FAILURE"
            overall_status = SourceHealthStatus.TRANSIENT_FAILURE
        elif transport_status_code >= 400:
            transport_status = f"HTTP_{transport_status_code}"
            overall_status = SourceHealthStatus.TRANSIENT_FAILURE
        else:
            transport_status = f"OK_{transport_status_code}"
            overall_status = None

        # 2. Determine parser status
        if parser_error:
            parser_status = "PARSE_SYNTAX_ERROR"
            if overall_status is None:
                overall_status = SourceHealthStatus.PERSISTENT_FAILURE
        elif has_schema_drift or (records_raw_count > 0 and records_parsed == 0):
            parser_status = "SCHEMA_DRIFT_SUSPECTED"
            if overall_status is None:
                overall_status = SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED
        elif records_raw_count == 0 and records_parsed == 0 and transport_status.startswith("OK_"):
            parser_status = "EMPTY_PAYLOAD"
            if overall_status is None:
                overall_status = SourceHealthStatus.EMPTY_RESULTS
        else:
            parser_status = "PARSED_OK"
            if overall_status is None:
                overall_status = SourceHealthStatus.HEALTHY if records_valid > 0 else SourceHealthStatus.EMPTY_RESULTS

        # Final health status fallback
        if overall_status is None:
            overall_status = SourceHealthStatus.HEALTHY if records_valid > 0 else SourceHealthStatus.EMPTY_RESULTS

        diag_list: list[tuple[str, str]] = [
            ("transport_status", transport_status),
            ("parser_status", parser_status),
            ("status_code", str(transport_status_code)),
            ("records_raw_count", str(records_raw_count)),
            ("records_parsed", str(records_parsed)),
            ("records_valid", str(records_valid)),
        ]
        if transport_error:
            diag_list.append(("transport_error", transport_error))
        if parser_error:
            diag_list.append(("parser_error", parser_error))

        last_success = timestamp if overall_status is SourceHealthStatus.HEALTHY else (
            self._reports[source_id].last_successful_ingestion if source_id in self._reports else None
        )

        report = SourceHealthReport(
            source_id=source_id,
            status=overall_status,
            transport_status=transport_status,
            parser_status=parser_status,
            records_raw_count=records_raw_count,
            records_parsed=records_parsed,
            records_valid=records_valid,
            fetch_latency_ms=fetch_latency_ms,
            last_successful_ingestion=last_success,
            error_message=parser_error or transport_error,
            diagnostics=tuple(diag_list),
        )
        self._reports[source_id] = report
        return report

    def get_report(self, source_id: str) -> SourceHealthReport | None:
        return self._reports.get(source_id)

    @property
    def all_reports(self) -> tuple[SourceHealthReport, ...]:
        return tuple(self._reports.values())
