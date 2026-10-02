from __future__ import annotations

import unittest
import subprocess
import sys
from pathlib import Path

from scripts.db_capacity_guard import PROVIDER_LIMIT_BYTES
from scripts.db_capacity_maintenance import (
    PROVIDER_REWRITE_SAFETY_MARGIN_BYTES,
    relation_rewrite_fits_provider,
    relation_rewrite_peak_estimate,
)


class RelationRewriteHeadroomTests(unittest.TestCase):
    def test_maintenance_cli_imports_when_run_as_a_script(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/db_capacity_maintenance.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hot-dimensions-apply", result.stdout)

    def test_estimate_includes_database_relation_and_safety_margin(self):
        self.assertEqual(
            relation_rewrite_peak_estimate(400_000_000, 50_000_000),
            450_000_000 + PROVIDER_REWRITE_SAFETY_MARGIN_BYTES,
        )

    def test_large_relation_rewrite_is_deferred_before_provider_boundary(self):
        database_bytes = 405_294_227
        relation_bytes = 124_149_760
        self.assertGreaterEqual(
            relation_rewrite_peak_estimate(database_bytes, relation_bytes),
            PROVIDER_LIMIT_BYTES,
        )
        self.assertFalse(relation_rewrite_fits_provider(database_bytes, relation_bytes))

    def test_medium_relation_rewrite_retains_transient_provider_headroom(self):
        database_bytes = 405_294_227
        relation_bytes = 76_275_712
        self.assertLess(
            relation_rewrite_peak_estimate(database_bytes, relation_bytes),
            PROVIDER_LIMIT_BYTES,
        )
        self.assertTrue(relation_rewrite_fits_provider(database_bytes, relation_bytes))


if __name__ == "__main__":
    unittest.main()
