from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from scripts.refresh_feed_projection_candidates import discover_current_candidates


class DiscoverCurrentCandidatesTests(TestCase):
    def test_selects_core_before_adjacent_and_skips_non_target_and_ineligible(self):
        rows = [
            (SimpleNamespace(id="adjacent", title="Software Engineer, LLM Platform", description="", posted_date="2026-09-28"), "uncertain"),
            (SimpleNamespace(id="old-core", title="Data Engineer", description="", posted_date="2026-08-01"), "uncertain"),
            (SimpleNamespace(id="new-core", title="Machine Learning Engineer", description="", posted_date="2026-09-27"), "uncertain"),
            (SimpleNamespace(id="bad-domain", title="Staff BESS Electrical Design Engineer, EPC", description="data engineering", posted_date="2026-09-28"), "uncertain"),
            (SimpleNamespace(id="ineligible", title="Data Analyst", description="", posted_date="2026-09-28"), "ineligible"),
        ]
        query = MagicMock()
        query.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
        session = MagicMock()
        session.query.return_value = query

        with patch("scripts.refresh_feed_projection_candidates._load_founder_behavior_signals", return_value=[]):
            self.assertEqual(
                discover_current_candidates(session, truth_pack_hash="truth-current", limit=2),
                ("new-core", "old-core"),
            )
        query.join.return_value.filter.return_value.order_by.return_value.limit.assert_called_once_with(500)

    def test_discovery_limit_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            discover_current_candidates(MagicMock(), truth_pack_hash="truth-current", limit=101)

