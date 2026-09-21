from __future__ import annotations

import unittest

from scripts.db_capacity_guard import (
    BLOCK_BYTES,
    CapacityBlocked,
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

    def test_over_budget_blocks(self):
        snapshot = inspect_connection(_Connection([BLOCK_BYTES + 1, False, False]))
        self.assertEqual(snapshot.status, "BLOCKED_CAPACITY")

    def test_normal_budget_is_allowed_status(self):
        snapshot = inspect_connection(_Connection([10, False, False]))
        self.assertEqual(snapshot.status, "OK")


if __name__ == "__main__":
    unittest.main()
