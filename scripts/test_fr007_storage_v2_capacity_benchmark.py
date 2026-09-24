from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from scripts.fr007_storage_v2_capacity_benchmark import (
    SUCCESSFUL_CORPUS_SOURCE_ID,
    _remaining_capacity_projection,
    _shape,
    _source_scope,
)


def _mapping_result(values):
    result = MagicMock()
    result.mappings.return_value.one.return_value = values
    return result


class StorageV2CapacityBenchmarkTests(unittest.TestCase):
    def test_corpus_scope_is_limited_to_sources_with_successful_polls(self):
        state = {
            "database_role": "postgres",
            "transaction_read_only": "off",
            "in_recovery": False,
            "revision": "0025_current_feed_fast_path",
            "opportunities": 826,
            "hot": 13,
            "cold": 813,
            "protected": 0,
            "successful_source_count": 5,
            "poll_status": "ok",
            "poll_unique": 826,
        }
        opportunity = {
            "hot": 13, "cold": 813, "protected": 0,
            "hot_title": 50, "hot_org": 25, "hot_url": 60, "hot_description": 1000,
            "hot_raw": 1400, "hot_city": 20, "hot_region": 30, "hot_remote_regions": 24,
            "cold_title": 45, "cold_org": 24, "cold_url": 58, "cold_city": 18,
            "cold_region": 25, "cold_remote_regions": 20,
        }
        evaluation = {"hot_reasons": 140, "hot_dimensions": 320, "hot_detail": 800, "cold_reasons": 94}
        provenance = {"rows": 150, "raw_value": 25, "normalized_value": 24, "raw_pointer": 25, "rule_id": 12}
        archive = {"rows": 813, "compressed_bytes": 8060, "original_bytes": 18000, "object_key_length": 100}
        poll = {"raw_ingested": 135, "unique_opportunities": 128}
        storage = {
            "rows": 813, "tuple_bytes": 400, "metadata_bytes": 180,
            "object_key_length": 100, "path_segments": 4, "version_length": 36,
        }
        connection = MagicMock()
        connection.execute.side_effect = [
            _mapping_result(state), _mapping_result(opportunity), _mapping_result(evaluation),
            _mapping_result(provenance), _mapping_result(archive), _mapping_result(storage), _mapping_result(poll),
        ]

        shape = _shape(connection, SUCCESSFUL_CORPUS_SOURCE_ID)

        self.assertEqual(shape["sample_scope"], "successful-source-corpus")
        self.assertEqual(shape["sample_source_count"], 5)
        self.assertEqual(shape["sample_opportunities"], 826)
        self.assertEqual(shape["sample_hot"], 13)
        self.assertEqual(shape["sample_cold"], 813)
        self.assertIn("source_id IN (SELECT DISTINCT source_id", _source_scope(SUCCESSFUL_CORPUS_SOURCE_ID))
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        for statement in statements[:5] + statements[6:]:
            self.assertIn("source_id IN (SELECT DISTINCT source_id", statement)

    def test_remaining_capacity_uses_real_corpus_and_reserves_source_and_row_growth(self):
        projection = _remaining_capacity_projection(
            live_database_bytes=18_738_323,
            benchmark_growth_bytes=170_000_000,
            source_growth_bytes=720_896,
            current_opportunities=826,
            current_sources=5,
            target_opportunities=26_000,
            target_sources=343,
        )

        self.assertEqual(projection["remaining_sources"], 338)
        self.assertEqual(projection["remaining_opportunities"], 25_621)
        self.assertGreater(projection["remaining_projected_bytes"], 0)
        self.assertEqual(
            projection["projected_final_database_bytes"],
            18_738_323 + projection["remaining_projected_bytes"],
        )

    def test_capacity_projection_rejects_source_overhead_that_consumes_entire_measurement(self):
        with self.assertRaisesRegex(ValueError, "invalid measured population bounds"):
            _remaining_capacity_projection(
                live_database_bytes=10,
                benchmark_growth_bytes=20,
                source_growth_bytes=20,
                current_opportunities=1,
                current_sources=1,
                target_opportunities=26_000,
                target_sources=343,
            )


if __name__ == "__main__":
    unittest.main()
