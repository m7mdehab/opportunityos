"""Adversarial and security tests for OpportunityOS Discovery & Ingestion."""
import unittest

from opportunity.adapters import (
    EUTEDAdapter,
    GreenhouseAdapter,
    HimalayasAdapter,
    LeverAdapter,
    RemoteOKAdapter,
    RemotiveAdapter,
    UNGMAdapter,
    WeWorkRemotelyAdapter,
    WorldBankAdapter,
    get_all_standard_adapters,
)
from opportunity.dedupe import deduplicate_opportunities
from opportunity.health import SourceHealthMonitor
from opportunity.models import (
    GeographicEligibility,
    Opportunity,
    SeniorityLevel,
    SourceHealthStatus,
    Track,
)
from opportunity.normalization import (
    derive_geographic_eligibility,
    extract_compensation,
    extract_seniority,
)


class AdversarialIngestionTests(unittest.TestCase):
    def test_external_action_safety_and_verbs(self):
        """Invariant 1: All adapters must be strictly read-only; mutations are forbidden."""
        adapters = get_all_standard_adapters()
        for adapter in adapters:
            if adapter.source_id == "eu_ted":
                self.assertEqual("POST", adapter.method)
                self.assertEqual("https://api.ted.europa.eu/v3/notices/search", adapter.feed_url)
            else:
                self.assertEqual("GET", adapter.method)

            # Ensure no mutating verbs exist in adapter definitions
            self.assertNotIn(adapter.method, {"PUT", "PATCH", "DELETE"})

    def test_no_fabricated_normalized_fields(self):
        """Invariant 2: Missing fields must remain None / UNSPECIFIED; never invent data."""
        # Minimal payload with only title
        gh = GreenhouseAdapter("testcorp")
        opps = gh.parse_payload('{"jobs": [{"id": 1, "title": "Software Engineer"}]}')
        self.assertEqual(1, len(opps))
        opp = opps[0]

        self.assertEqual(SeniorityLevel.UNSPECIFIED, opp.seniority)
        self.assertIsNone(opp.compensation)
        self.assertEqual("", opp.location_raw)
        self.assertEqual((), opp.responsibilities)
        self.assertEqual((), opp.requirements)
        self.assertEqual((), opp.skills)
        self.assertIsNone(opp.posted_date)

    def test_geographic_safety_and_no_false_eligibility(self):
        """Invariant 3: Restricted postings must NEVER be classified as eligible."""
        test_cases = [
            ("Must reside in the United States", "US Only", "excluded"),
            ("Canadian citizens only", "Canada", "excluded"),
            ("UK based applicants only", "London, UK", "excluded"),
            ("European Union residents only", "Germany / France", "excluded"),
            ("Work from anywhere in the world", "Remote - Worldwide", "eligible"),
            ("100% remote for candidates globally", "Global Remote", "eligible"),
        ]
        for desc, loc, expected_status in test_cases:
            geo = derive_geographic_eligibility("Engineer", loc, desc)
            self.assertEqual(
                expected_status,
                geo.status,
                f"Failed for description '{desc}' and location '{loc}'",
            )

    def test_near_duplicate_false_merge_attacks(self):
        """Invariant 4: Opportunities with distinct organizations, seniorities, or geographic scopes MUST NOT merge."""
        # Attack A: Same title, different company
        opp_a = Opportunity("1", Track.EMPLOYMENT, "greenhouse:stripe", "https://stripe.com/1", "1", "Stripe", "Staff Engineer", "Build infra", location_raw="Remote")
        opp_b = Opportunity("2", Track.EMPLOYMENT, "greenhouse:square", "https://square.com/2", "2", "Square", "Staff Engineer", "Build infra", location_raw="Remote")
        res_ab = deduplicate_opportunities([opp_a, opp_b])
        self.assertEqual(2, len(res_ab.unique_opportunities))

        # Attack B: Same company, different seniority
        opp_sr = Opportunity("3", Track.EMPLOYMENT, "greenhouse:stripe", "https://stripe.com/3", "3", "Stripe", "Senior Engineer", "Build infra", seniority=SeniorityLevel.SENIOR)
        opp_jr = Opportunity("4", Track.EMPLOYMENT, "greenhouse:stripe", "https://stripe.com/4", "4", "Stripe", "Junior Engineer", "Build infra", seniority=SeniorityLevel.ENTRY)
        res_sr_jr = deduplicate_opportunities([opp_sr, opp_jr])
        self.assertEqual(2, len(res_sr_jr.unique_opportunities))

        # Attack C: Same company & title, different geographic restriction
        opp_ww = Opportunity("5", Track.EMPLOYMENT, "greenhouse:stripe", "https://stripe.com/5", "5", "Stripe", "Security Engineer", "Global", geographic_eligibility=GeographicEligibility("eligible", "worldwide"))
        opp_us = Opportunity("6", Track.EMPLOYMENT, "greenhouse:stripe", "https://stripe.com/6", "6", "Stripe", "Security Engineer", "US Only", geographic_eligibility=GeographicEligibility("ineligible", "us only"))
        res_geo = deduplicate_opportunities([opp_ww, opp_us])
        self.assertEqual(2, len(res_geo.unique_opportunities))

    def test_schema_drift_is_never_silently_ignored(self):
        """Invariant 5: Malformed feeds and unexpected schemas must raise drift or failure status."""
        monitor = SourceHealthMonitor()

        # Non-empty payload that yields 0 records
        rep1 = monitor.record_run(
            source_id="himalayas",
            records_fetched=10,
            records_parsed=0,
            records_valid=0,
            has_schema_drift=True,
        )
        self.assertEqual(SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED, rep1.status)

        # Corrupt JSON / syntax error
        rep2 = monitor.record_run(
            source_id="remotive",
            records_fetched=0,
            records_parsed=0,
            records_valid=0,
            error_message="JSONDecodeError: Unterminated string",
        )
        self.assertEqual(SourceHealthStatus.PERSISTENT_FAILURE, rep2.status)

    def test_zero_results_not_falsely_reported_as_healthy(self):
        """Invariant 6: Feed returning 0 records must be marked EMPTY_RESULTS, never HEALTHY."""
        monitor = SourceHealthMonitor()
        report = monitor.record_run(
            source_id="we_work_remotely",
            records_fetched=0,
            records_parsed=0,
            records_valid=0,
            status_code=200,
        )
        self.assertEqual(SourceHealthStatus.EMPTY_RESULTS, report.status)
        self.assertFalse(report.is_healthy)

    def test_procurement_metadata_preserved_without_employment_mangling(self):
        """Invariant 7: Procurement notices must preserve procurement metadata rather than forcing into employment fields."""
        ted = EUTEDAdapter()
        payload = """{
            "notices": [{
                "publication-number": "2026/S 999-123456",
                "notice-title": {"ENG": ["EU Cloud Framework Tender"]},
                "buyer-name": {"ENG": ["European Commission"]},
                "buyer-country": "BE",
                "category": "Advisory Services",
                "notice-type": "Prior Information Notice",
                "cpv": ["72000000", "79400000"]
            }]
        }"""
        opps = ted.parse_payload(payload)
        self.assertEqual(1, len(opps))
        opp = opps[0]

        self.assertEqual(Track.PROCUREMENT, opp.track)
        self.assertIsNotNone(opp.procurement_metadata)
        self.assertEqual("European Commission", opp.procurement_metadata.buyer_name)  # type: ignore
        self.assertEqual("Prior Information Notice", opp.procurement_metadata.notice_type)  # type: ignore
        self.assertEqual(("72000000", "79400000"), opp.procurement_metadata.cpv_codes)  # type: ignore


if __name__ == "__main__":
    unittest.main()
