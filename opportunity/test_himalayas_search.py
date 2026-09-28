import json
import unittest
from urllib.parse import parse_qs, urlparse

from opportunity.discovery.himalayas import (
    HIMALAYAS_TARGET_QUERIES,
    merge_search_payloads,
    targeted_search_urls,
)


class HimalayasSearchTests(unittest.TestCase):
    def test_search_plan_targets_egypt_and_worldwide_recently(self):
        urls = targeted_search_urls()
        self.assertEqual(len(HIMALAYAS_TARGET_QUERIES), len(urls))
        self.assertEqual(len(set(urls)), len(urls))
        parsed = [urlparse(url) for url in urls]
        self.assertTrue(all(item.path == "/jobs/api/search" for item in parsed))
        params = parse_qs(parsed[0].query)
        self.assertEqual(["data engineer"], params["q"])
        self.assertEqual(["Egypt"], params["country"])
        self.assertEqual(["true"], params["worldwide"])
        self.assertEqual(["Mid-level,Senior,Manager,Director"], params["seniority"])
        self.assertEqual(["Full Time,Contractor"], params["employment_type"])
        self.assertEqual(["recent"], params["sort"])
        self.assertEqual(["1"], params["page"])

    def test_page_builder_supports_documented_page_based_search_pagination(self):
        page_two = targeted_search_urls(queries=("data engineer",), page=2)
        self.assertEqual(["2"], parse_qs(urlparse(page_two[0]).query)["page"])
        with self.assertRaises(ValueError):
            targeted_search_urls(page=0)

    def test_merge_deduplicates_overlapping_results_and_reports_raw_count(self):
        first = {"jobs": [
            {"guid": "job-1", "title": "Data Engineer", "companyName": "Acme"},
            {"guid": "job-2", "title": "Analyst", "companyName": "Example"},
        ]}
        second = {"jobs": [
            {"guid": "job-1", "title": "Data Engineer", "companyName": "Acme"},
            {"guid": "job-3", "title": "ML Engineer", "companyName": "Other"},
        ]}
        merged, raw_count = merge_search_payloads([json.dumps(first), json.dumps(second)])
        self.assertEqual(4, raw_count)
        self.assertEqual(["job-1", "job-2", "job-3"], [job["guid"] for job in json.loads(merged)["jobs"]])

    def test_malformed_search_page_fails_closed(self):
        with self.assertRaises(ValueError):
            merge_search_payloads([json.dumps({"unexpected": []})])


if __name__ == "__main__":
    unittest.main()
