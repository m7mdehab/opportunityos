"""Unit tests for source health monitoring and schema drift detection."""
import unittest

from opportunity.health import SourceHealthMonitor
from opportunity.models import SourceHealthStatus


class HealthMonitorTests(unittest.TestCase):
    def setUp(self):
        self.monitor = SourceHealthMonitor()

    def test_healthy_run(self):
        report = self.monitor.record_run(
            source_id="greenhouse:cloudflare",
            records_fetched=10,
            records_parsed=10,
            records_valid=10,
            status_code=200,
        )
        self.assertEqual(SourceHealthStatus.HEALTHY, report.status)
        self.assertTrue(report.is_healthy)
        self.assertIn("greenhouse:cloudflare", self.monitor.healthy_sources)

    def test_empty_results_not_silently_healthy(self):
        report = self.monitor.record_run(
            source_id="himalayas",
            records_fetched=0,
            records_parsed=0,
            records_valid=0,
            status_code=200,
        )
        self.assertEqual(SourceHealthStatus.EMPTY_RESULTS, report.status)
        self.assertFalse(report.is_healthy)
        self.assertIn("himalayas", self.monitor.degraded_sources)

    def test_schema_drift_detection(self):
        report = self.monitor.record_run(
            source_id="remotive",
            records_fetched=5,
            records_parsed=0,
            records_valid=0,
            has_schema_drift=True,
        )
        self.assertEqual(SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED, report.status)
        self.assertFalse(report.is_healthy)

    def test_policy_restriction_and_rate_limiting(self):
        r_403 = self.monitor.record_run("jobicy", 0, 0, 0, status_code=403)
        self.assertEqual(SourceHealthStatus.POLICY_RESTRICTION, r_403.status)

        r_429 = self.monitor.record_run("remote_ok", 0, 0, 0, status_code=429)
        self.assertEqual(SourceHealthStatus.RATE_LIMITED, r_429.status)

    def test_transient_and_persistent_failures(self):
        r_503 = self.monitor.record_run("we_work_remotely", 0, 0, 0, status_code=503)
        self.assertEqual(SourceHealthStatus.TRANSIENT_FAILURE, r_503.status)

        r_timeout = self.monitor.record_run("ungm", 0, 0, 0, error_message="Connection timeout")
        self.assertEqual(SourceHealthStatus.TRANSIENT_FAILURE, r_timeout.status)

        r_parse = self.monitor.record_run("eu_ted", 0, 0, 0, error_message="JSON parse error on malformed token")
        self.assertEqual(SourceHealthStatus.PERSISTENT_FAILURE, r_parse.status)


if __name__ == "__main__":
    unittest.main()
