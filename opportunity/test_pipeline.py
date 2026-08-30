"""Integration tests for OpportunityPipeline with mock transport."""
import pathlib
import unittest

from opportunity.acquisition import MockTransport, TransportResponse
from opportunity.pipeline import OpportunityPipeline
from opportunity.registry import SourceRegistry

FIXTURES_DIR = pathlib.Path(__file__).resolve().parent / "fixtures"


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixtures: dict[str, str] = {}
        for path in FIXTURES_DIR.glob("*.*"):
            if path.name.endswith(".json") or path.name.endswith(".xml"):
                key = path.stem.replace("_cloudflare", "").replace("_shyftlabs", "")
                if "greenhouse" in path.name:
                    key = "greenhouse:cloudflare"
                elif "lever" in path.name:
                    key = "lever:shyftlabs"
                self.fixtures[key] = path.read_text(encoding="utf-8")

    def test_full_pipeline_multi_source_ingestion(self) -> None:
        pipeline = OpportunityPipeline()
        batch = pipeline.process_payloads(self.fixtures, now_iso="2026-08-30")

        self.assertGreater(batch.total_raw_ingested, 0)
        self.assertGreater(batch.total_unique_opportunities, 0)
        self.assertTrue(batch.batch_id)

        # Check track counts presence
        track_dict = dict(batch.track_counts)
        self.assertIn("employment", track_dict)
        self.assertIn("procurement", track_dict)

        # Check all sources healthy
        self.assertTrue(batch.is_clean)

    def test_empty_batch_not_clean(self) -> None:
        pipeline = OpportunityPipeline()
        empty_batch = pipeline.process_payloads({}, now_iso="2026-08-30")
        self.assertEqual(empty_batch.total_raw_ingested, 0)
        self.assertFalse(empty_batch.is_clean)

    def test_pipeline_with_mock_transport_discovery(self) -> None:
        transport = MockTransport({
            "greenhouse:cloudflare": self.fixtures["greenhouse:cloudflare"],
            "himalayas": self.fixtures["himalayas"],
            "ungm": self.fixtures["ungm"],
        })
        pipeline = OpportunityPipeline(transport=transport)
        batch = pipeline.execute_discovery(
            source_ids=["greenhouse:cloudflare", "himalayas", "ungm"],
            now_iso="2026-08-30",
        )
        self.assertGreater(batch.total_unique_opportunities, 0)
        self.assertTrue(batch.is_clean)

    def test_pipeline_handles_unregistered_and_disabled_sources(self) -> None:
        pipeline = OpportunityPipeline()
        batch = pipeline.process_payloads({
            "jobicy": '{"jobs": [{"title": "Remote Engineer"}]}',  # disabled
            "unregistered_xyz": '{"data": []}',                   # unregistered
        })
        self.assertEqual(batch.total_unique_opportunities, 0)
        self.assertFalse(batch.is_clean)
        self.assertEqual(len(batch.health_reports), 2)


if __name__ == "__main__":
    unittest.main()
