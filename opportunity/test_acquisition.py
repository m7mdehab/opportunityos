"""Unit and Authority Tests for SourceRegistry and Acquisition Transport."""
from __future__ import annotations

import unittest
from opportunity.models import SourceHealthStatus
from opportunity.pipeline import OpportunityPipeline
from opportunity.registry import SourceRegistry
from opportunity.transport import (
    AcquisitionService,
    DiscoveryRequest,
    HttpTransport,
    MockTransport,
    RateLimiter,
    TransportResponse,
)


class TestAcquisitionAndRegistryAuthority(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SourceRegistry()
        self.transport = MockTransport()
        self.service = AcquisitionService(registry=self.registry, transport=self.transport)

    def test_unregistered_source_refused_preflight(self) -> None:
        authorized, reason = self.registry.validate_preflight("unregistered_source", "https://example.com/api")
        self.assertFalse(authorized)
        self.assertIn("not registered", reason)

        res = self.service.acquire("unregistered_source", "https://example.com/api")
        self.assertFalse(res.authorized)
        self.assertEqual(res.response.status_code, 403)

    def test_disabled_source_refused_preflight(self) -> None:
        # jobicy is disabled in docs/SOURCE_REGISTRY.yaml
        authorized, reason = self.registry.validate_preflight("jobicy", "https://jobicy.com/api/v2/remote-jobs")
        self.assertFalse(authorized)
        self.assertIn("disabled by policy", reason)

        res = self.service.acquire("jobicy", "https://jobicy.com/api/v2/remote-jobs")
        self.assertFalse(res.authorized)
        self.assertEqual(res.response.status_code, 403)

    def test_mutating_methods_strictly_forbidden(self) -> None:
        for method in ("PUT", "PATCH", "DELETE"):
            authorized, reason = self.registry.validate_preflight(
                "himalayas", "https://himalayas.app/jobs/api", method=method
            )
            self.assertFalse(authorized)
            self.assertIn("forbidden", reason.lower())

    def test_arbitrary_host_get_refused_preflight(self) -> None:
        # A registered source ID is NOT permission to GET arbitrary URLs
        authorized, reason = self.registry.validate_preflight(
            "himalayas", "https://evil.example/jobs", method="GET"
        )
        self.assertFalse(authorized)
        self.assertIn("unauthorized", reason.lower())

        # Greenhouse arbitrary host
        authorized, reason = self.registry.validate_preflight(
            "greenhouse:cloudflare", "https://example.com/v1/boards/cloudflare/jobs", method="GET"
        )
        self.assertFalse(authorized)
        self.assertIn("unauthorized", reason.lower())

    def test_ted_endpoint_and_substring_bypass_rejection(self) -> None:
        # TED must require exact host and path
        authorized, reason = self.registry.validate_preflight(
            "eu_ted", "https://api.ted.europa.eu/v3/notices/search", method="POST"
        )
        self.assertTrue(authorized)

        # Substring bypass in query parameter MUST FAIL
        authorized, reason = self.registry.validate_preflight(
            "eu_ted", "https://evil.example/?x=api.ted.europa.eu/v3/notices/search", method="POST"
        )
        self.assertFalse(authorized)
        self.assertIn("unauthorized", reason.lower())

        # GET to TED search MUST FAIL
        authorized, reason = self.registry.validate_preflight(
            "eu_ted", "https://api.ted.europa.eu/v3/notices/search", method="GET"
        )
        self.assertFalse(authorized)

        # POST to non-search TED endpoint MUST FAIL
        authorized, reason = self.registry.validate_preflight(
            "eu_ted", "https://api.ted.europa.eu/v3/notices/publish", method="POST"
        )
        self.assertFalse(authorized)

    def test_pacing_rate_limiter_injectable_clock(self) -> None:
        current_time = 1000.0

        def mock_clock() -> float:
            nonlocal current_time
            return current_time

        limiter = RateLimiter(clock=mock_clock, default_min_interval_s=2.0)

        # First request at t=1000: 0 wait (recorded finish at 1000.0)
        wait1 = limiter.acquire("himalayas")
        self.assertEqual(wait1, 0.0)

        # Immediate second request at t=1000: 2.0s wait (recorded finish at 1002.0)
        wait2 = limiter.acquire("himalayas")
        self.assertEqual(wait2, 2.0)

        # Advance clock to t=1005.0 (> 1002.0 + 2.0s)
        current_time = 1005.0
        wait3 = limiter.acquire("himalayas")
        self.assertEqual(wait3, 0.0)

    def test_exact_latency_telemetry_preserved(self) -> None:
        # Response with 187 ms latency
        self.transport.set_response(
            "himalayas",
            TransportResponse(
                status_code=200,
                body='{"jobs": []}',
                latency_ms=187,
            ),
        )
        pipeline = OpportunityPipeline(transport=self.transport)
        batch = pipeline.execute_discovery(source_ids=["himalayas"])

        report = next(r for r in batch.health_reports if r.source_id == "himalayas")
        self.assertEqual(report.fetch_latency_ms, 187)


if __name__ == "__main__":
    unittest.main()
