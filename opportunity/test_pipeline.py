"""End-to-end integration and pipeline tests for OpportunityOS."""
from pathlib import Path
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
from opportunity.models import SourceHealthStatus
from opportunity.pipeline import OpportunityPipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.adapters = [
            GreenhouseAdapter("cloudflare"),
            LeverAdapter("shyftlabs"),
            HimalayasAdapter(),
            RemotiveAdapter(),
            RemoteOKAdapter(),
            WeWorkRemotelyAdapter(),
            UNGMAdapter(),
            WorldBankAdapter(),
            EUTEDAdapter(),
        ]
        self.pipeline = OpportunityPipeline(self.adapters)

    def test_full_pipeline_multi_source_ingestion(self):
        payload_map = {
            "greenhouse:cloudflare": read_fixture("greenhouse_cloudflare.json"),
            "lever:shyftlabs": read_fixture("lever_shyftlabs.json"),
            "himalayas": read_fixture("himalayas.json"),
            "remotive": read_fixture("remotive.json"),
            "remote_ok": read_fixture("remote_ok.json"),
            "we_work_remotely": read_fixture("we_work_remotely.xml"),
            "ungm": read_fixture("ungm.json"),
            "world_bank": read_fixture("world_bank.json"),
            "eu_ted": read_fixture("eu_ted.json"),
        }

        batch = self.pipeline.process_payloads(payload_map, fetched_at="2026-08-30")

        self.assertEqual(11, batch.total_raw_opportunities)
        self.assertTrue(len(batch.unique_opportunities) >= 9)
        self.assertEqual(9, len(batch.health_reports))
        self.assertTrue(batch.is_clean)

        # Check track distribution
        track_dict = dict(batch.tracks_summary)
        self.assertIn("employment", track_dict)
        self.assertIn("procurement", track_dict)
        self.assertEqual(8, track_dict["employment"])
        self.assertEqual(3, track_dict["procurement"])

        # Check geographic distribution
        geo_dict = dict(batch.geographic_summary)
        self.assertTrue(geo_dict.get("eligible", 0) > 0)
        self.assertTrue(geo_dict.get("excluded", 0) > 0)

    def test_pipeline_deterministic_replay(self):
        payload_map = {
            "greenhouse:cloudflare": read_fixture("greenhouse_cloudflare.json"),
            "himalayas": read_fixture("himalayas.json"),
            "eu_ted": read_fixture("eu_ted.json"),
        }

        batch1 = self.pipeline.process_payloads(payload_map, fetched_at="2026-08-30")
        batch2 = self.pipeline.process_payloads(payload_map, fetched_at="2026-08-30")

        self.assertEqual(batch1.total_raw_opportunities, batch2.total_raw_opportunities)
        self.assertEqual(len(batch1.unique_opportunities), len(batch2.unique_opportunities))
        
        # Compare opportunity IDs and content hashes
        hashes1 = [o.content_hash for o in batch1.unique_opportunities]
        hashes2 = [o.content_hash for o in batch2.unique_opportunities]
        self.assertEqual(hashes1, hashes2)

    def test_pipeline_handles_schema_drift_and_empty_payloads(self):
        payload_map = {
            "greenhouse:cloudflare": read_fixture("greenhouse_cloudflare.json"),
            "himalayas": '{"invalid": "schema without jobs key"}',
            "remotive": '{"jobs": []}',
        }

        batch = self.pipeline.process_payloads(payload_map, fetched_at="2026-08-30")

        # Greenhouse is healthy
        # Himalayas has empty list / 0 records -> EMPTY_RESULTS
        # Remotive has empty list -> EMPTY_RESULTS
        self.assertEqual(2, batch.total_raw_opportunities)
        report_himalayas = next(r for r in batch.health_reports if r.source_id == "himalayas")
        self.assertEqual(SourceHealthStatus.EMPTY_RESULTS, report_himalayas.status)


if __name__ == "__main__":
    unittest.main()
