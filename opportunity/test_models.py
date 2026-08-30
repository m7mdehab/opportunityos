"""Unit tests for OpportunityOS domain models and schemas."""
import unittest

from opportunity.models import (
    Compensation,
    CompensationInterval,
    DerivationType,
    EmploymentType,
    FieldProvenance,
    GeographicEligibility,
    Opportunity,
    OpportunityCluster,
    ProcurementMetadata,
    RemotePolicy,
    SeniorityLevel,
    SourceProvenance,
    Track,
    compute_canonical_content_hash,
    compute_dedup_key,
    compute_deterministic_id,
)


class OpportunityModelTests(unittest.TestCase):
    def test_models_are_immutable(self) -> None:
        comp = Compensation(min_amount=100000.0, max_amount=150000.0, currency="USD", interval=CompensationInterval.YEARLY)
        with self.assertRaises(Exception):
            comp.min_amount = 90000.0  # type: ignore

        geo = GeographicEligibility(status="eligible", reason="Worldwide remote allowed")
        with self.assertRaises(Exception):
            geo.status = "excluded"  # type: ignore

        prov = SourceProvenance(
            source_id="himalayas",
            source_url="https://himalayas.app/jobs/123",
            feed_url="https://himalayas.app/jobs/api",
            fetched_at="2026-08-30",
        )
        with self.assertRaises(Exception):
            prov.source_id = "lever"  # type: ignore

        field_prov = FieldProvenance(
            field_name="title",
            raw_value="Senior Software Engineer",
            normalized_value="Senior Software Engineer",
            derivation_type=DerivationType.RAW_EXTRACTION.value,
            raw_pointer="jobs[0].title",
            record_checksum="abc123sha",
            rule_id="clean_text",
        )
        with self.assertRaises(Exception):
            field_prov.raw_value = "Staff Engineer"  # type: ignore

    def test_content_hash_and_dedup_key_computed_automatically(self) -> None:
        opp = Opportunity(
            id="himalayas:123",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/123",
            source_id="123",
            organization="Acme Corp",
            title="Senior Backend Engineer",
            description="Build scalable distributed systems with Python.",
            seniority=SeniorityLevel.SENIOR,
            location_raw="Worldwide",
            remote_policy=RemotePolicy.REMOTE,
        )
        self.assertTrue(opp.content_hash)
        self.assertTrue(opp.dedup_key)

        # Deterministic check
        expected_content_hash = compute_canonical_content_hash(
            "Acme Corp", "Senior Backend Engineer", "Worldwide", "Build scalable distributed systems with Python."
        )
        self.assertEqual(opp.content_hash, expected_content_hash)

        expected_dedup_key = compute_dedup_key(
            "Acme Corp", "Senior Backend Engineer", "Worldwide"
        )
        self.assertEqual(opp.dedup_key, expected_dedup_key)

    def test_deterministic_id_computation(self) -> None:
        id1 = compute_deterministic_id("greenhouse:cloudflare", "5512301", "Senior Engineer", "Cloudflare", "feed:jobs[0]")
        self.assertEqual(id1, "greenhouse:cloudflare:5512301")

        # Without remote_id, derives stable sha256
        id2 = compute_deterministic_id("world_bank", "", "Consulting Notice", "World Bank", "feed:html_link[0]")
        self.assertTrue(id2.startswith("world_bank:"))
        self.assertGreater(len(id2), 15)

    def test_compensation_invariants(self) -> None:
        # min > max should raise ValueError
        with self.assertRaises(ValueError):
            Compensation(min_amount=200000.0, max_amount=100000.0, currency="USD")

    def test_geographic_eligibility_invariants(self) -> None:
        # Invalid status should raise ValueError
        with self.assertRaises(ValueError):
            GeographicEligibility(status="invalid_status", reason="test")

    def test_four_real_tracks_instantiation(self) -> None:
        for t in (Track.EMPLOYMENT, Track.CONTRACT, Track.FREELANCE, Track.PROCUREMENT):
            opp = Opportunity(
                id=f"test:{t.value}",
                track=t,
                source="test",
                source_url="https://example.com",
                source_id="1",
                organization="Org",
                title=f"{t.value} title",
                description="desc",
            )
            self.assertEqual(opp.track, t)

    def test_opportunity_cluster_invariants(self) -> None:
        opp_primary = Opportunity(
            id="himalayas:1",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/1",
            source_id="1",
            organization="Acme Corp",
            title="Senior Backend Engineer",
            description="Build scalable systems.",
        )
        opp_duplicate = Opportunity(
            id="remotive:2",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.com/jobs/2",
            source_id="2",
            organization="Acme Corp",
            title="Senior Backend Engineer",
            description="Build scalable systems.",
        )
        cluster = OpportunityCluster(
            canonical_id=opp_primary.id,
            primary_opportunity=opp_primary,
            duplicate_opportunities=(opp_duplicate,),
            dedup_layer="cross_source",
        )
        self.assertEqual(cluster.cluster_size, 2)
        self.assertEqual(cluster.sources, ("himalayas", "remotive"))


if __name__ == "__main__":
    unittest.main()
