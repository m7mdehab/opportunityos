"""Unit tests for two-layer deduplication and conservative false-merge prevention."""
import unittest

from opportunity.dedupe import deduplicate_opportunities
from opportunity.models import (
    GeographicEligibility,
    Opportunity,
    SeniorityLevel,
    Track,
)


class DeduplicationTests(unittest.TestCase):
    def test_exact_hash_deduplication(self):
        opp1 = Opportunity(
            id="opp-exact-1",
            track=Track.EMPLOYMENT,
            source="greenhouse:stripe",
            source_url="https://stripe.com/jobs/1",
            source_id="1",
            organization="Stripe",
            title="Senior Infrastructure Engineer",
            description="Build scalable distributed telemetry.",
            location_raw="Remote - Worldwide",
        )
        opp2 = Opportunity(
            id="opp-exact-2",
            track=Track.EMPLOYMENT,
            source="remote_ok",
            source_url="https://remoteok.com/jobs/99",
            source_id="99",
            organization="Stripe",
            title="Senior Infrastructure Engineer",
            description="Build scalable distributed telemetry.",
            location_raw="Remote - Worldwide",
        )
        result = deduplicate_opportunities([opp1, opp2])

        self.assertEqual(1, len(result.unique_opportunities))
        self.assertEqual(1, result.exact_duplicates_count)
        self.assertEqual(1, len(result.clusters))
        self.assertEqual("exact", result.clusters[0].dedup_layer)
        self.assertEqual(2, result.clusters[0].cluster_size)

    def test_cross_source_deduplication(self):
        # Slightly different descriptions but same organization, title, location, and seniority
        opp1 = Opportunity(
            id="opp-cs-1",
            track=Track.EMPLOYMENT,
            source="greenhouse:datadog",
            source_url="https://datadog.com/1",
            source_id="1",
            organization="Datadog",
            title="Senior Systems Engineer",
            description="Detailed job description from ATS with full benefits list.",
            location_raw="Remote",
            seniority=SeniorityLevel.SENIOR,
            geographic_eligibility=GeographicEligibility("eligible", "worldwide"),
        )
        opp2 = Opportunity(
            id="opp-cs-2",
            track=Track.EMPLOYMENT,
            source="we_work_remotely",
            source_url="https://weworkremotely.com/2",
            source_id="2",
            organization="Datadog",
            title="Senior Systems Engineer",
            description="Short summary on job board.",
            location_raw="Remote",
            seniority=SeniorityLevel.SENIOR,
            geographic_eligibility=GeographicEligibility("eligible", "worldwide"),
        )
        result = deduplicate_opportunities([opp1, opp2])

        self.assertEqual(1, len(result.unique_opportunities))
        self.assertEqual(1, result.cross_source_duplicates_count)
        self.assertEqual(1, len(result.clusters))
        self.assertEqual("cross_source", result.clusters[0].dedup_layer)

    def test_different_organizations_never_merge(self):
        opp_stripe = Opportunity(
            id="opp-stripe",
            track=Track.EMPLOYMENT,
            source="greenhouse:stripe",
            source_url="https://stripe.com/1",
            source_id="1",
            organization="Stripe",
            title="Senior Backend Engineer",
            description="Build payments.",
            location_raw="Remote",
            seniority=SeniorityLevel.SENIOR,
        )
        opp_twilio = Opportunity(
            id="opp-twilio",
            track=Track.EMPLOYMENT,
            source="greenhouse:twilio",
            source_url="https://twilio.com/1",
            source_id="1",
            organization="Twilio",
            title="Senior Backend Engineer",
            description="Build messaging.",
            location_raw="Remote",
            seniority=SeniorityLevel.SENIOR,
        )
        result = deduplicate_opportunities([opp_stripe, opp_twilio])

        self.assertEqual(2, len(result.unique_opportunities))
        self.assertEqual(0, result.exact_duplicates_count)
        self.assertEqual(0, result.cross_source_duplicates_count)

    def test_distinct_seniority_never_merges(self):
        opp_sr = Opportunity(
            id="opp-sr",
            track=Track.EMPLOYMENT,
            source="greenhouse:stripe",
            source_url="https://stripe.com/sr",
            source_id="sr",
            organization="Stripe",
            title="Senior Backend Engineer",
            description="Build platform.",
            location_raw="Remote",
            seniority=SeniorityLevel.SENIOR,
        )
        opp_jr = Opportunity(
            id="opp-jr",
            track=Track.EMPLOYMENT,
            source="greenhouse:stripe",
            source_url="https://stripe.com/jr",
            source_id="jr",
            organization="Stripe",
            title="Junior Backend Engineer",
            description="Build platform.",
            location_raw="Remote",
            seniority=SeniorityLevel.ENTRY,
        )
        result = deduplicate_opportunities([opp_sr, opp_jr])

        self.assertEqual(2, len(result.unique_opportunities))
        self.assertEqual(0, result.exact_duplicates_count)
        self.assertEqual(0, result.cross_source_duplicates_count)

    def test_distinct_geographic_eligibility_never_merges(self):
        opp_eligible = Opportunity(
            id="opp-el",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.com/1",
            source_id="1",
            organization="Cloudflare",
            title="Systems Engineer",
            description="Remote worldwide.",
            location_raw="Remote - Worldwide",
            geographic_eligibility=GeographicEligibility("eligible", "worldwide"),
        )
        opp_ineligible = Opportunity(
            id="opp-inel",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url="https://cloudflare.com/2",
            source_id="2",
            organization="Cloudflare",
            title="Systems Engineer",
            description="Remote US only.",
            location_raw="Remote - US Only",
            geographic_eligibility=GeographicEligibility("ineligible", "us only"),
        )
        result = deduplicate_opportunities([opp_eligible, opp_ineligible])

        self.assertEqual(2, len(result.unique_opportunities))
        self.assertEqual(0, result.cross_source_duplicates_count)

    def test_distinct_tracks_never_merge(self):
        opp_emp = Opportunity(
            id="opp-emp",
            track=Track.EMPLOYMENT,
            source="greenhouse:un",
            source_url="https://un.org/1",
            source_id="1",
            organization="United Nations",
            title="Data Architect",
            description="Full-time staff role.",
        )
        opp_proc = Opportunity(
            id="opp-proc",
            track=Track.PROCUREMENT,
            source="ungm",
            source_url="https://ungm.org/1",
            source_id="1",
            organization="United Nations",
            title="Data Architect",
            description="RFP consulting contract.",
        )
        result = deduplicate_opportunities([opp_emp, opp_proc])

        self.assertEqual(2, len(result.unique_opportunities))
        self.assertEqual(0, result.cross_source_duplicates_count)


if __name__ == "__main__":
    unittest.main()
