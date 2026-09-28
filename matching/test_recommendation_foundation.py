from __future__ import annotations

import unittest

from matching.recommendation_foundation import (
    classify_application_access,
    classify_founder_geography,
    classify_role_relevance,
)


class RecommendationFoundationTests(unittest.TestCase):
    def test_role_relevance_uses_existing_families_and_requires_adjacent_evidence(self):
        self.assertEqual(classify_role_relevance("Senior Data Engineer").classification, "core")
        self.assertEqual(
            classify_role_relevance("Backend Engineer", "Build a data platform with SQL pipelines").classification,
            "non_target",
        )
        self.assertEqual(
            classify_role_relevance("Backend Engineer - Data Platform").classification,
            "core",
        )
        self.assertEqual(
            classify_role_relevance("Backend Engineer - AI Tooling").classification,
            "adjacent",
        )
        self.assertEqual(
            classify_role_relevance(
                "Backend Engineer",
                "Build distributed services. About Us: We are leaders in machine learning and AI data platforms.",
            ).classification,
            "non_target",
        )
        self.assertEqual(
            classify_role_relevance(
                "Staff BESS Electrical Design Engineer, EPC",
                "Design electrical battery storage systems for construction projects.",
            ).classification,
            "non_target",
        )
        self.assertEqual(classify_role_relevance("Risk Analyst", "Our company builds AI tools").classification, "non_target")
        self.assertEqual(classify_role_relevance("Associate Demo Engineer", "About Us: AI analytics platform").classification, "non_target")
        self.assertEqual(
            classify_role_relevance("Backend Engineer", "Build distributed services").classification,
            "non_target",
        )
        self.assertEqual(classify_role_relevance("Gardener").classification, "non_target")

    def test_us_employer_or_office_is_not_an_applicant_restriction(self):
        state, _ = classify_founder_geography(
            description="Remote role for a US company, USD compensation.",
            location_country="US",
            work_mode="remote",
        )
        self.assertEqual(state, "review")

    def test_explicit_egypt_scope_and_restrictions_are_distinguished(self):
        self.assertEqual(classify_founder_geography(
            description="We hire worldwide.", work_mode="remote"
        )[0], "likely_eligible")
        self.assertEqual(classify_founder_geography(
            description="US applicants only; must have US work authorization."
        )[0], "ineligible")
        self.assertEqual(classify_founder_geography(
            description="Eligible countries: United States and Canada."
        )[0], "ineligible")
        self.assertEqual(classify_founder_geography(
            description="Eligible countries: Egypt, United States."
        )[0], "likely_eligible")
        self.assertEqual(classify_founder_geography(
            description="Must be based in US Eastern time zone."
        )[0], "review")
        self.assertEqual(classify_founder_geography(
            description="On-site role", location_country="US", work_mode="onsite"
        )[0], "ineligible")

    def test_public_ats_url_overrides_aggregator_route(self):
        result = classify_application_access(
            "we_work_remotely",
            "https://weworkremotely.com/remote-jobs/example",
            "https://boards.greenhouse.io/example/jobs/123",
        )
        self.assertEqual((result.route, result.access), ("ats", "direct_free"))
        self.assertEqual(result.application_url, "https://boards.greenhouse.io/example/jobs/123")

    def test_unverified_application_access_remains_unknown(self):
        result = classify_application_access(
            "himalayas", "https://himalayas.app/jobs/data-engineer"
        )
        self.assertEqual(result.access, "unknown")


if __name__ == "__main__":
    unittest.main()
