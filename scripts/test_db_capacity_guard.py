from __future__ import annotations

import unittest

from scripts.db_capacity_guard import (
    BLOCK_BYTES,
    CapacityBlocked,
    HARD_STOP_BYTES,
    TARGET_BYTES,
    assert_heavy_work_allowed,
    inspect_connection,
)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Connection:
    def __init__(self, values):
        self.values = iter(values)

    def execute(self, _statement):
        return _Result(next(self.values))


class CapacityGuardTests(unittest.TestCase):
    def test_read_only_is_distinct_from_capacity_warning(self):
        snapshot = inspect_connection(_Connection([100, True, False]))
        self.assertEqual(snapshot.status, "READ_ONLY")
        self.assertTrue(snapshot.read_only)

    def test_at_or_above_w23_hard_ceiling_blocks_heavy_work(self):
        for size in (TARGET_BYTES, TARGET_BYTES + 1, HARD_STOP_BYTES + 1):
            with self.subTest(size=size):
                snapshot = inspect_connection(_Connection([size, False, False]))
                self.assertEqual(snapshot.status, "HARD_STOP_CAPACITY")
                with self.assertRaises(CapacityBlocked):
                    assert_heavy_work_allowed(_Connection([size, False, False]))

    def test_measured_review_band_below_ceiling_remains_allowed(self):
        snapshot = inspect_connection(_Connection([BLOCK_BYTES - 1, False, False]))
        self.assertEqual(snapshot.status, "STRONG_WARN_CAPACITY")
        allowed = assert_heavy_work_allowed(_Connection([BLOCK_BYTES - 1, False, False]))
        self.assertEqual(allowed.status, "STRONG_WARN_CAPACITY")

    def test_normal_budget_is_allowed_status(self):
        snapshot = inspect_connection(_Connection([10, False, False]))
        self.assertEqual(snapshot.status, "OK")


if __name__ == "__main__":
    unittest.main()
