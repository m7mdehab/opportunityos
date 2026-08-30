"""Unit tests for OpportunityOS data models and typing invariants."""
import unittest

from opportunity.models import (
    Compensation,
    CompensationInterval,
    EmploymentType,
    GeographicEligibility,
    Opportunity,
    OpportunityCluster,
    ProcurementMetadata,
    RemotePolicy,
    SeniorityLevel,
    SourceHealthReport,
    SourceHealthStatus,
    SourceProvenance,
    Track,
)


class OpportunityModelTests(unittest.TestCase):
    def test_models_are_immutable(self):
        comp = Compensation(100.0, 150.0, "USD", CompensationInterval.HOURLY)
        with self.assertRaises(Exception):
            comp.min_amount = 200.0  # type: ignore

        prov = SourceProvenance("greenhouse:cloudflare", "https://example.com", "https://example.com/feed", "2026-08-30")
        with self.assertRaises(Exception):
            prov.source_id = "other"  # type: ignore

        opp = Opportunity(
            id="opp-1",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url="https://example.com",
            source_id="123",
            organization="Cloudflare",
            title="Senior Systems Engineer",
            description="Build systems",
            compensation=comp,
            raw_provenance=prov,
        )
        with self.assertRaises(Exception):
            opp.title = "New Title"  # type: ignore

    def test_compensation_invariants(self):
        # min cannot exceed max
        with self.assertRaises(ValueError):
            Compensation(200.0, 100.0, "USD")

        # currency cannot be empty string
        with self.assertRaises(ValueError):
            Compensation(100.0, 200.0, "   ")

        # valid compensation
        c = Compensation(120000.0, 150000.0, "USD", CompensationInterval.YEARLY)
        self.assertEqual(120000.0, c.min_amount)
        self.assertEqual("USD", c.currency)

    def test_geographic_eligibility_invariants(self):
        with self.assertRaises(ValueError):
            GeographicEligibility("maybe_eligible", "no reason")

        geo = GeographicEligibility("eligible", "worldwide remote", "individual_ok", "individual permitted")
        self.assertEqual("eligible", geo.status)
        self.assertEqual("individual_ok", geo.individual_eligibility)

    def test_content_hash_and_dedup_key_computed_automatically(self):
        opp = Opportunity(
            id="opp-test",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.com/1",
            source_id="1",
            organization="Acme Corp",
            title="Data Engineer",
            description="Work with SQL and Python.",
            location_raw="Worldwide",
        )
        self.assertTrue(len(opp.content_hash) > 20)
        self.assertTrue(len(opp.dedup_key) > 20)

    def test_opportunity_cluster_invariants(self):
        opp1 = Opportunity("opp-1", Track.EMPLOYMENT, "greenhouse:stripe", "https://stripe.com/1", "1", "Stripe", "Backend Engineer", "Desc")
        opp2 = Opportunity("opp-2", Track.EMPLOYMENT, "remote_ok", "https://remoteok.com/2", "2", "Stripe", "Backend Engineer", "Desc")
        cluster = OpportunityCluster(
            canonical_id=opp1.id,
            primary_opportunity=opp1,
            duplicate_opportunities=(opp2,),
            dedup_layer="cross_source",
        )
        self.assertEqual(2, cluster.cluster_size)
        self.assertIn("greenhouse:stripe", cluster.sources)
        self.assertIn("remote_ok", cluster.sources)


if __name__ == "__main__":
    unittest.main()
