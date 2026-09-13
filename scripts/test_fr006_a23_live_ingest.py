#!/usr/bin/env python3
from __future__ import annotations

import unittest

from opportunity.registry import SourceRegistry
from scripts.fr006_a23_live_ingest import SOURCE_IDS, validate_bindings


class A23LiveIngestConfigurationTests(unittest.TestCase):
    def test_exactly_eight_distinct_new_sources_are_bound_and_read_allowed(self) -> None:
        self.assertEqual(8, len(SOURCE_IDS))
        self.assertEqual(8, len(set(SOURCE_IDS)))
        validate_bindings(SourceRegistry())


if __name__ == "__main__":
    unittest.main()
