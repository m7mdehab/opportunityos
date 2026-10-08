from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from scripts.db_capacity_guard import (
    BLOCK_BYTES, HARD_STOP_BYTES, PROVIDER_LIMIT_BYTES,
)
from scripts.fr007_storage_reclamation import (
    INDEX_TARGETS, REINDEX_RESERVE_BYTES, REINDEX_EXTRA_MULTIPLIER,
    REINDEX_PROVIDER_RESERVE_BYTES, index_rebuild_estimate, reindex_one,
)


class StorageReclamationSafetyTests(unittest.TestCase):
    def test_live_provenance_index_does_not_fit_internal_safety_boundary(self):
        # Read-only measurements from the 2026-10-08 staging database.
        result = index_rebuild_estimate(409_128_083, 27_893_760)
        self.assertFalse(result.permitted)
        self.assertEqual(result.reason, "insufficient_temporary_headroom")
        self.assertGreater(result.estimated_peak_bytes, HARD_STOP_BYTES)

    def test_small_index_is_eligible_only_under_both_limits(self):
        result = index_rebuild_estimate(409_128_083, 1_875_968)
        self.assertTrue(result.permitted)
        self.assertLess(result.estimated_peak_bytes, HARD_STOP_BYTES)
        self.assertLess(
            result.estimated_peak_bytes,
            PROVIDER_LIMIT_BYTES - REINDEX_PROVIDER_RESERVE_BYTES,
        )
        self.assertEqual(
            result.estimated_peak_bytes,
            409_128_083 + REINDEX_EXTRA_MULTIPLIER * 1_875_968
            + REINDEX_RESERVE_BYTES,
        )

    def test_queue_and_readonly_fail_closed(self):
        for opts, reason in [
            ({"active_jobs": 1}, "worker_queue_not_idle"),
            ({"read_only": True}, "database_unwritable"),
            ({"in_recovery": True}, "database_unwritable"),
        ]:
            with self.subTest(opts=opts):
                estimate = index_rebuild_estimate(200 * 1024 * 1024, 1_000_000, **opts)
                self.assertFalse(estimate.permitted)
                self.assertEqual(estimate.reason, reason)

    def test_pause_boundary_is_never_relaxed(self):
        e = index_rebuild_estimate(BLOCK_BYTES, 1)
        self.assertFalse(e.permitted)
        self.assertEqual(e.reason, "heavy_work_pause_boundary")

    def test_negative_measurements_fail_closed(self):
        with self.assertRaises(ValueError):
            index_rebuild_estimate(-1, 100)
        with self.assertRaises(ValueError):
            index_rebuild_estimate(100, -1)
        with self.assertRaises(ValueError):
            index_rebuild_estimate(100, 1, active_jobs=-1)

    def test_index_allowlist_is_fixed_and_specific(self):
        self.assertIn("provenance_identity", INDEX_TARGETS)
        self.assertEqual(INDEX_TARGETS["provenance_identity"][2], "uq_field_provenances_identity")
        for item in INDEX_TARGETS.values():
            self.assertEqual(item[0], "public")
            self.assertEqual(len(item), 3)

    def test_reindex_cannot_execute_without_dual_approval(self):
        db = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "requires --confirm"):
                reindex_one(db, "provenance_identity", confirm=False)
            with self.assertRaisesRegex(RuntimeError, "requires --confirm"):
                reindex_one(db, "provenance_identity", confirm=True)
        db.exec_driver_sql.assert_not_called()

    def test_reindex_rejects_untrusted_index_identifier(self):
        with self.assertRaisesRegex(ValueError, "allowlist"):
            reindex_one(MagicMock(), 'x; DROP TABLE opportunities;', confirm=True)


if __name__ == "__main__":
    unittest.main()
