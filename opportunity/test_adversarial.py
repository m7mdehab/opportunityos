"""Adversarial and Invariant Tests for Discovery, Normalization, Provenance, and Health."""
from __future__ import annotations

import unittest

from opportunity.adapters import (
    EUTEDAdapter,
    GreenhouseAdapter,
    HimalayasAdapter,
    LeverAdapter,
    RemoteOKAdapter,
    RemotiveAdapter,
    UNGMAdapter,
    WeWorkRemotelyAdapter,
    WorldBankAdapter,
)
from opportunity.models import (
    SeniorityLevel,
    SourceHealthStatus,
    Track,
    validate_opportunity_provenance,
)
from opportunity.pipeline import OpportunityPipeline
from opportunity.transport import MockTransport, TransportResponse


class TestAdversarialInvariants(unittest.TestCase):
    def test_ted_concrete_description_laundering_bug_fixed(self) -> None:
        """Notice has title but no description -> description MUST NOT silently become title."""
        payload = """{
            "results": [
                {
                    "publication-number": "2026/S 001-000001",
                    "notice-title": "Supply of Enterprise IT Hardware",
                    "buyer-name": "Ministry of Transport",
                    "buyer-country": "EGY"
                }
            ]
        }"""
        adapter = EUTEDAdapter()
        result = adapter.parse_payload(payload)
        self.assertEqual(len(result.opportunities), 1)
        opp = result.opportunities[0]
        self.assertEqual(opp.title, "Supply of Enterprise IT Hardware")
        self.assertEqual(opp.description, "")
        
        # Provenance for description must not claim title
        desc_prov = next(fp for fp in opp.field_provenances if fp.field_name == "description")
        self.assertEqual(desc_prov.raw_value, "")
        self.assertEqual(desc_prov.normalized_value, "")
        self.assertEqual(desc_prov.derivation_type, "unasserted_absent")

    def test_minimal_records_zero_fabrication_across_all_adapters(self) -> None:
        """Sparse records across all 9 adapters must not fabricate placeholder values."""
        prohibited_placeholders = {
            "EU Contracting Authority",
            "EU",
            "Tender Notice",
            "Services",
            "United Nations",
            "RFP",
            "Consulting Services",
            "Himalayas Employer",
            "Remotive Employer",
            "Remote OK Employer",
            "We Work Remotely Employer",
            "Anywhere in the World",
        }

        sparse_payloads = [
            (GreenhouseAdapter("cloudflare"), '{"jobs": [{"id": 1, "title": "Dev"}]}'),
            (LeverAdapter("stripe"), '[{"id": "abc", "text": "Dev"}]'),
            (HimalayasAdapter(), '{"jobs": [{"slug": "dev", "title": "Dev"}]}'),
            (RemotiveAdapter(), '{"jobs": [{"id": 1, "title": "Dev"}]}'),
            (RemoteOKAdapter(), '[{"id": "1", "position": "Dev"}]'),
            (WeWorkRemotelyAdapter(), '<rss><channel><item><title>Dev</title><link>https://weworkremotely.com/remote-jobs/1-dev</link></item></channel></rss>'),
            (UNGMAdapter(), '{"notices": [{"id": "1", "title": "Procurement Notice"}]}'),
            (WorldBankAdapter(), '{"notices": [{"id": "1", "title": "Consulting Notice"}]}'),
            (EUTEDAdapter(), '{"results": [{"publication-number": "1", "notice-title": "Notice"}]}'),
        ]

        for adapter, payload in sparse_payloads:
            result = adapter.parse_payload(payload)
            self.assertGreater(len(result.opportunities), 0, f"Adapter {adapter.source_id} failed to parse sparse payload")
            opp = result.opportunities[0]

            for ph in prohibited_placeholders:
                self.assertNotEqual(opp.organization, ph, f"Fabricated organization '{ph}' in {adapter.source_id}")
                self.assertNotEqual(opp.location_raw, ph, f"Fabricated location '{ph}' in {adapter.source_id}")
                self.assertNotEqual(opp.description, ph, f"Fabricated description '{ph}' in {adapter.source_id}")

            valid, err = validate_opportunity_provenance(opp)
            self.assertTrue(valid, f"Provenance validation failed for {adapter.source_id}: {err}")

    def test_health_telemetry_a_mock_response_latency(self) -> None:
        """A. Mock response latency=187 ms -> final SourceHealthReport.fetch_latency_ms == 187."""
        transport = MockTransport()
        transport.set_response(
            "himalayas",
            TransportResponse(
                status_code=200,
                body='{"jobs": [{"slug": "1", "title": "Engineer"}]}',
                latency_ms=187,
            ),
        )
        pipeline = OpportunityPipeline(transport=transport)
        batch = pipeline.execute_discovery(source_ids=["himalayas"])
        report = next(r for r in batch.health_reports if r.source_id == "himalayas")
        self.assertEqual(report.fetch_latency_ms, 187)

    def test_health_telemetry_b_valid_empty_payload(self) -> None:
        """B. Valid source payload containing exactly 0 source records -> EMPTY_RESULTS."""
        transport = MockTransport()
        transport.set_response(
            "himalayas",
            TransportResponse(
                status_code=200,
                body='{"jobs": []}',
                latency_ms=25,
            ),
        )
        pipeline = OpportunityPipeline(transport=transport)
        batch = pipeline.execute_discovery(source_ids=["himalayas"])
        report = next(r for r in batch.health_reports if r.source_id == "himalayas")
        self.assertEqual(report.status, SourceHealthStatus.EMPTY_RESULTS)
        self.assertEqual(report.records_raw_count, 0)
        self.assertEqual(report.parser_status, "EMPTY_PAYLOAD")

    def test_health_telemetry_c_nonempty_json_missing_expected_collection(self) -> None:
        """C. Nonempty JSON with expected collection missing -> SCHEMA_DRIFT_SUSPECTED."""
        transport = MockTransport()
        transport.set_response(
            "himalayas",
            TransportResponse(
                status_code=200,
                body='{"unexpected_key": "drifted_data"}',
                latency_ms=30,
            ),
        )
        pipeline = OpportunityPipeline(transport=transport)
        batch = pipeline.execute_discovery(source_ids=["himalayas"])
        report = next(r for r in batch.health_reports if r.source_id == "himalayas")
        self.assertEqual(report.status, SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED)
        self.assertEqual(report.parser_status, "SCHEMA_DRIFT_SUSPECTED")

    def test_health_telemetry_d_raw_parsed_valid_accuracy(self) -> None:
        """D. Collection has 3 raw records, 2 normalize successfully -> raw=3, parsed=2, valid=2."""
        payload = """{
            "jobs": [
                {"slug": "1", "title": "Valid Job 1"},
                {"slug": "2", "title": ""},
                {"slug": "3", "title": "Valid Job 2"}
            ]
        }"""
        pipeline = OpportunityPipeline()
        batch = pipeline.process_payloads({"himalayas": payload}, latencies_ms={"himalayas": 45})
        report = next(r for r in batch.health_reports if r.source_id == "himalayas")
        self.assertEqual(report.records_raw_count, 3)
        self.assertEqual(report.records_parsed, 2)
        self.assertEqual(report.records_valid, 2)

    def test_health_telemetry_e_parser_exception_after_http_200(self) -> None:
        """E. Parser exception after HTTP 200 -> HTTP transport remains 200 and parser error is independently recorded."""
        transport = MockTransport()
        transport.set_response(
            "himalayas",
            TransportResponse(
                status_code=200,
                body="<not-valid-json>corrupt",
                latency_ms=20,
            ),
        )
        pipeline = OpportunityPipeline(transport=transport)
        batch = pipeline.execute_discovery(source_ids=["himalayas"])
        report = next(r for r in batch.health_reports if r.source_id == "himalayas")
        self.assertEqual(report.status, SourceHealthStatus.PERSISTENT_FAILURE)
        self.assertEqual(report.transport_status, "OK_200")
        self.assertEqual(report.parser_status, "PARSE_SYNTAX_ERROR")
        self.assertTrue(bool(report.error_message))


if __name__ == "__main__":
    unittest.main()
