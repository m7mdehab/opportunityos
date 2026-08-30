"""Unit tests for Source Health monitoring and failure semantics."""
import unittest

from opportunity.health import SourceHealthMonitor
from opportunity.models import SourceHealthStatus


class HealthMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.monitor = SourceHealthMonitor()

    def test_healthy_run(self) -> None:
        report = self.monitor.record_run(
            source_id="himalayas",
            transport_status_code=200,
            records_raw_count=20,
            records_parsed=20,
            records_valid=20,
            fetch_latency_ms=150,
            now_iso="2026-08-30",
        )
        self.assertTrue(report.is_healthy)
        self.assertEqual(report.status, SourceHealthStatus.HEALTHY)
        self.assertEqual(report.transport_status, "OK_200")
        self.assertEqual(report.parser_status, "PARSED_OK")
        self.assertEqual(report.last_successful_ingestion, "2026-08-30")

    def test_empty_results_not_silently_healthy(self) -> None:
        report = self.monitor.record_run(
            source_id="remotive",
            transport_status_code=200,
            records_raw_count=0,
            records_parsed=0,
            records_valid=0,
        )
        self.assertFalse(report.is_healthy)
        self.assertEqual(report.status, SourceHealthStatus.EMPTY_RESULTS)
        self.assertEqual(report.parser_status, "EMPTY_PAYLOAD")

    def test_schema_drift_detection(self) -> None:
        report = self.monitor.record_run(
            source_id="remote_ok",
            transport_status_code=200,
            records_raw_count=50,
            records_parsed=0,
            records_valid=0,
            has_schema_drift=True,
        )
        self.assertFalse(report.is_healthy)
        self.assertEqual(report.status, SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED)
        self.assertEqual(report.parser_status, "SCHEMA_DRIFT_SUSPECTED")

    def test_policy_restriction_and_rate_limiting(self) -> None:
        report_403 = self.monitor.record_run(
            source_id="ungm",
            transport_status_code=403,
            transport_error="Access Denied by WAF",
        )
        self.assertEqual(report_403.status, SourceHealthStatus.POLICY_RESTRICTION)
        self.assertEqual(report_403.transport_status, "POLICY_RESTRICTION")

        report_429 = self.monitor.record_run(
            source_id="lever:shyftlabs",
            transport_status_code=429,
            transport_error="Too Many Requests",
        )
        self.assertEqual(report_429.status, SourceHealthStatus.RATE_LIMITED)
        self.assertEqual(report_429.transport_status, "RATE_LIMITED")

    def test_transient_and_persistent_failures(self) -> None:
        report_500 = self.monitor.record_run(
            source_id="world_bank",
            transport_status_code=500,
            transport_error="Internal Server Error",
        )
        self.assertEqual(report_500.status, SourceHealthStatus.TRANSIENT_FAILURE)
        self.assertEqual(report_500.transport_status, "TRANSIENT_FAILURE")

        report_parse_err = self.monitor.record_run(
            source_id="eu_ted",
            transport_status_code=200,
            records_raw_count=0,
            parser_error="JSONDecodeError: Unterminated string",
        )
        self.assertEqual(report_parse_err.status, SourceHealthStatus.PERSISTENT_FAILURE)
        self.assertEqual(report_parse_err.parser_status, "PARSE_SYNTAX_ERROR")
        self.assertIn("JSONDecodeError", report_parse_err.error_message or "")


if __name__ == "__main__":
    unittest.main()
