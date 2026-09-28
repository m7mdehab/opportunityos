from __future__ import annotations

import unittest

from scripts.db_capacity_guard import (
    BLOCK_BYTES,
    HARD_STOP_BYTES,
    PREFERRED_BYTES,
    PROVIDER_LIMIT_BYTES,
    WARN_BYTES,
    CapacityBlocked,
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


def _snapshot(size, *, read_only=False, in_recovery=False):
    return inspect_connection(_Connection([size, read_only, in_recovery]))


class CapacityGuardTests(unittest.TestCase):
    def test_provider_limit_uses_decimal_megabytes(self):
        self.assertEqual(PROVIDER_LIMIT_BYTES, 500_000_000)

    def test_thresholds_classify_normal_monitor_warning_pause_and_hard_stop(self):
        cases = (
            (PREFERRED_BYTES - 1, "NORMAL", False),
            (PREFERRED_BYTES, "MONITOR_CAPACITY", False),
            (WARN_BYTES, "WARN_CAPACITY", False),
            (BLOCK_BYTES, "HEAVY_WORK_PAUSED", True),
            (HARD_STOP_BYTES, "HARD_STOP_CAPACITY", True),
        )
        for size, status, paused in cases:
            with self.subTest(size=size):
                snapshot = _snapshot(size)
                self.assertEqual(snapshot.status, status)
                self.assertEqual(snapshot.pauses_heavy_work, paused)

    def test_normal_and_monitor_ranges_allow_heavy_work(self):
        for size in (PREFERRED_BYTES - 1, PREFERRED_BYTES, WARN_BYTES - 1):
            with self.subTest(size=size):
                self.assertEqual(assert_heavy_work_allowed(_Connection([size, False, False])).database_size_bytes, size)

    def test_warning_range_allows_work_but_reports_warning(self):
        snapshot = _snapshot(WARN_BYTES)
        self.assertEqual(snapshot.status, "WARN_CAPACITY")
        self.assertFalse(snapshot.pauses_heavy_work)

    def test_pause_and_hard_stop_block_heavy_work(self):
        for size in (BLOCK_BYTES, HARD_STOP_BYTES, PROVIDER_LIMIT_BYTES):
            with self.subTest(size=size):
                with self.assertRaises(CapacityBlocked):
                    assert_heavy_work_allowed(_Connection([size, False, False]))

    def test_read_only_always_blocks(self):
        snapshot = inspect_connection(_Connection([1, True, False]))
        self.assertEqual(snapshot.status, "READ_ONLY")
        self.assertTrue(snapshot.pauses_heavy_work)
        with self.assertRaises(CapacityBlocked):
            assert_heavy_work_allowed(_Connection([1, True, False]))

    def test_recovery_mode_always_blocks(self):
        snapshot = inspect_connection(_Connection([1, False, True]))
        self.assertEqual(snapshot.status, "IN_RECOVERY")
        self.assertTrue(snapshot.pauses_heavy_work)
        with self.assertRaises(CapacityBlocked):
            assert_heavy_work_allowed(_Connection([1, False, True]))


if __name__ == "__main__":
    unittest.main()
