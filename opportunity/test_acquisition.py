"""Tests for OpportunityOS Authorized Acquisition, Registry Policy, and Transport."""
import unittest

from opportunity.acquisition import AcquisitionService, MockTransport, TransportResponse
from opportunity.registry import SourcePolicy, SourceRegistry


class AcquisitionAndRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SourceRegistry()
        self.transport = MockTransport()
        self.service = AcquisitionService(registry=self.registry, transport=self.transport)

    def test_registry_loads_and_verifies_authoritative_sources(self) -> None:
        # Check standard registered sources
        self.assertTrue(self.registry.is_source_registered("greenhouse:cloudflare"))
        self.assertTrue(self.registry.is_source_registered("lever:shyftlabs"))
        self.assertTrue(self.registry.is_source_registered("himalayas"))
        self.assertTrue(self.registry.is_source_registered("remotive"))
        self.assertTrue(self.registry.is_source_registered("remote_ok"))
        self.assertTrue(self.registry.is_source_registered("we_work_remotely"))
        self.assertTrue(self.registry.is_source_registered("ungm"))
        self.assertTrue(self.registry.is_source_registered("world_bank"))
        self.assertTrue(self.registry.is_source_registered("eu_ted"))

        # Verify read permission states
        self.assertTrue(self.registry.is_read_allowed("himalayas"))
        self.assertFalse(self.registry.is_read_allowed("jobicy"))  # read: disabled
        self.assertFalse(self.registry.is_read_allowed("afdb"))    # read: disabled

    def test_unregistered_source_refused_before_transport(self) -> None:
        result = self.service.acquire(
            source_id="unregistered_feed_xyz",
            url="https://example.com/jobs",
            method="GET",
        )
        self.assertFalse(result.authorized)
        self.assertEqual(result.response.status_code, 403)
        self.assertIn("not registered", result.refusal_reason or "")
        self.assertEqual(result.feed_checksum, "")

    def test_disabled_source_refused_before_transport(self) -> None:
        result = self.service.acquire(
            source_id="jobicy",
            url="https://jobicy.com/api/v2/remote-jobs",
            method="GET",
        )
        self.assertFalse(result.authorized)
        self.assertEqual(result.response.status_code, 403)
        self.assertIn("disabled by policy", result.refusal_reason or "")

    def test_forbidden_mutating_methods_blocked_before_transport(self) -> None:
        for forbidden in ("PUT", "PATCH", "DELETE"):
            result = self.service.acquire(
                source_id="himalayas",
                url="https://himalayas.app/jobs/api",
                method=forbidden,
            )
            self.assertFalse(result.authorized)
            self.assertIn(forbidden, result.refusal_reason or "")

    def test_unauthorized_post_blocked_before_transport(self) -> None:
        # POST is forbidden for standard GET discovery feeds
        result = self.service.acquire(
            source_id="himalayas",
            url="https://himalayas.app/jobs/api",
            method="POST",
            body={"query": "test"},
        )
        self.assertFalse(result.authorized)
        self.assertIn("forbidden for source", result.refusal_reason or "")

    def test_allowlisted_eu_ted_post_search_authorized(self) -> None:
        self.transport.set_response(
            "eu_ted",
            TransportResponse(
                status_code=200,
                body='{"notices": []}',
                latency_ms=25,
            ),
        )
        result = self.service.acquire(
            source_id="eu_ted",
            url="https://api.ted.europa.eu/v3/notices/search",
            method="POST",
            body={"query": "ND=2026"},
        )
        self.assertTrue(result.authorized)
        self.assertEqual(result.response.status_code, 200)
        self.assertNotEqual(result.feed_checksum, "")

    def test_unallowlisted_post_to_other_ted_endpoint_refused(self) -> None:
        result = self.service.acquire(
            source_id="eu_ted",
            url="https://api.ted.europa.eu/v3/notices/publish",
            method="POST",
            body={"data": "test"},
        )
        self.assertFalse(result.authorized)
        self.assertIn("not an authorized read-only search endpoint", result.refusal_reason or "")

    def test_mock_transport_latency_and_error_capture(self) -> None:
        self.transport.set_response(
            "remotive",
            TransportResponse(
                status_code=503,
                body="",
                latency_ms=120,
                error_message="Service Temporarily Unavailable",
            ),
        )
        result = self.service.acquire(
            source_id="remotive",
            url="https://remotive.com/api/remote-jobs",
            method="GET",
        )
        self.assertTrue(result.authorized)
        self.assertEqual(result.response.status_code, 503)
        self.assertEqual(result.response.latency_ms, 120)
        self.assertEqual(result.response.error_message, "Service Temporarily Unavailable")


if __name__ == "__main__":
    unittest.main()
