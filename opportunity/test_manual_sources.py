"""BRIEF-FR-006 E23: every manual_only/platform_application catalogue entry must have
a resolvable deep link, and tutoring platform cards must never claim to be postings."""
from __future__ import annotations

import unittest
from urllib.parse import urlparse

from opportunity.manual_sources import (
    FOUNDER_SEARCH_QUERY,
    MANUAL_SOURCES,
    tutoring_platform_cards,
)
from opportunity.models import Track


class ManualSourceCatalogueTests(unittest.TestCase):
    def test_every_entry_has_a_resolvable_deep_link(self):
        self.assertTrue(MANUAL_SOURCES, "catalogue must not be empty")
        for entry in MANUAL_SOURCES:
            link = entry.deep_link(FOUNDER_SEARCH_QUERY)
            with self.subTest(source_id=entry.source_id):
                self.assertNotIn("{query}", link, "unsubstituted template placeholder")
                parsed = urlparse(link)
                self.assertEqual("https", parsed.scheme)
                self.assertTrue(parsed.netloc, "deep link must have a host")

    def test_opportunity_type_is_manual_only_or_platform_application(self):
        for entry in MANUAL_SOURCES:
            with self.subTest(source_id=entry.source_id):
                self.assertIn(entry.opportunity_type, ("manual_only", "platform_application"))

    def test_tutoring_platforms_are_platform_application_under_tutoring_track(self):
        cards = tutoring_platform_cards()
        expected = {"preply", "superprof", "wyzant", "tutor_com", "chegg", "cambly"}
        self.assertEqual(expected, {card.source_id for card in cards})
        for card in cards:
            with self.subTest(source_id=card.source_id):
                self.assertEqual(Track.TUTORING, card.track)
                self.assertEqual("platform_application", card.opportunity_type)
                self.assertTrue(card.readiness_checklist, "tutoring cards need a readiness checklist")

    def test_no_duplicate_source_ids(self):
        ids = [entry.source_id for entry in MANUAL_SOURCES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_reddit_routes_are_registered_and_blocked(self):
        reddit_ids = {entry.source_id for entry in MANUAL_SOURCES if entry.source_id.startswith("reddit_")}
        self.assertEqual(
            {"reddit_forhire", "reddit_remotejobs", "reddit_machinelearningjobs",
             "reddit_datajobs", "reddit_hiring", "reddit_jobbit", "reddit_bigdatajobs"},
            reddit_ids,
        )
        for entry in MANUAL_SOURCES:
            if entry.source_id.startswith("reddit_"):
                with self.subTest(source_id=entry.source_id):
                    self.assertEqual("manual_only", entry.opportunity_type)
                    self.assertIn("403", entry.policy_note)


if __name__ == "__main__":
    unittest.main()
