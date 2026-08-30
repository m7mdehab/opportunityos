"""Deterministic Replay Test across distinct PYTHONHASHSEED environments."""
import json
import os
import pathlib
import subprocess
import sys
import unittest

FIXTURES_DIR = pathlib.Path(__file__).resolve().parent / "fixtures"

_SUBPROCESS_SCRIPT = """
import json
import pathlib
import sys
from opportunity.pipeline import OpportunityPipeline

fixtures_dir = pathlib.Path(sys.argv[1])
fixtures = {}
for path in fixtures_dir.glob("*.*"):
    if path.name.endswith(".json") or path.name.endswith(".xml"):
        key = path.stem.replace("_cloudflare", "").replace("_shyftlabs", "")
        if "greenhouse" in path.name:
            key = "greenhouse:cloudflare"
        elif "lever" in path.name:
            key = "lever:shyftlabs"
        fixtures[key] = path.read_text(encoding="utf-8")

pipeline = OpportunityPipeline()
batch = pipeline.process_payloads(fixtures, now_iso="2026-08-30")

summary = {
    "batch_id": batch.batch_id,
    "total_raw": batch.total_raw_ingested,
    "total_unique": batch.total_unique_opportunities,
    "exact_dupes": batch.exact_duplicates_removed,
    "cross_source_dupes": batch.cross_source_duplicates_clustered,
    "track_counts": list(batch.track_counts),
    "eligibility_counts": list(batch.eligibility_counts),
    "opportunity_ids": [opp.id for opp in batch.opportunities],
    "content_hashes": [opp.content_hash for opp in batch.opportunities],
    "dedup_keys": [opp.dedup_key for opp in batch.opportunities],
    "cluster_ids": [c.canonical_id for c in batch.clusters],
    "field_provenances": [
        [(fp.field_name, fp.derivation_type, fp.record_checksum, fp.rule_id) for fp in opp.field_provenances]
        for opp in batch.opportunities
    ],
}

print(json.dumps(summary, sort_keys=True))
"""


class DeterministicReplayTests(unittest.TestCase):
    def test_canonical_serialization_identical_across_pythonhashseeds(self) -> None:
        outputs: list[str] = []
        seeds = ("0", "42", "12345", "999999")

        for seed in seeds:
            env = os.environ.copy()
            env["PYTHONHASHSEED"] = seed
            result = subprocess.run(
                [sys.executable, "-c", _SUBPROCESS_SCRIPT, str(FIXTURES_DIR)],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            outputs.append(result.stdout.strip())

        # Verify all subprocess outputs are byte-for-byte identical
        for i in range(1, len(outputs)):
            self.assertEqual(
                outputs[0],
                outputs[i],
                f"Mismatch in canonical serialization between seed {seeds[0]} and {seeds[i]}",
            )

        # Parse JSON and verify integrity
        data = json.loads(outputs[0])
        self.assertTrue(data["batch_id"])
        self.assertGreater(data["total_unique"], 0)
        self.assertGreater(len(data["opportunity_ids"]), 0)


if __name__ == "__main__":
    unittest.main()
