import unittest

from recon.external_policy import READ_ONLY_QUERY, permits
from recon.sources import INDEPENDENT_SOURCES
from recon.sources import ATS_WATCHLIST


TED_SEARCH = "https://api.ted.europa.eu/v3/notices/search"


class ExternalPolicyTests(unittest.TestCase):
    def test_ted_search_post_is_permitted(self):
        self.assertTrue(permits("POST", TED_SEARCH, READ_ONLY_QUERY))

    def test_other_ted_post_is_rejected(self):
        self.assertFalse(permits("POST", "https://api.ted.europa.eu/v3/notices/submit", READ_ONLY_QUERY))

    def test_arbitrary_post_is_rejected(self):
        self.assertFalse(permits("POST", "https://example.test/v3/notices/search", READ_ONLY_QUERY))

    def test_mutating_verbs_are_rejected(self):
        for method in ("PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertFalse(permits(method, TED_SEARCH, READ_ONLY_QUERY))

    def test_ted_adapter_has_only_documented_search_fields(self):
        source = next(item for item in INDEPENDENT_SOURCES if item.source_id == "eu_ted")
        self.assertEqual("POST", source.method)
        self.assertEqual(READ_ONLY_QUERY, source.action_classification)
        self.assertTrue(set(source.request_body or {}).issubset({"query", "fields", "page", "limit", "scope", "checkQuerySyntax", "paginationMode", "iterationNextToken"}))

    def test_watchlist_has_25_unique_configured_boards(self):
        self.assertGreaterEqual(len(ATS_WATCHLIST), 25)
        self.assertEqual(len(ATS_WATCHLIST), len({(kind, board) for kind, board in ATS_WATCHLIST.values()}))
