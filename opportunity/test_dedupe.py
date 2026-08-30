"""Unit Tests for Conservative Two-Layer Deduplication Engine."""
from __future__ import annotations

import unittest

from opportunity.dedupe import (
    _canonicalize_url,
    _evaluate_deduplication,
    deduplicate_opportunities,
)
from opportunity.models import (
    GeographicEligibility,
    Opportunity,
    SeniorityLevel,
    Track,
)


class TestDeduplicationRegressions(unittest.TestCase):
    def test_source_id_substring_matching_rejected(self) -> None:
        """source_id in other.source_url (e.g. '1' in '.../jobs/12345') MUST NEVER MERGE."""
        opp_a = Opportunity(
            id="himalayas:1",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/1",
            source_id="1",
            organization="Stripe",
            title="Senior Backend Engineer",
            description="Stripe backend role building payment infrastructure",
            canonical_outbound_url="https://himalayas.app/jobs/1",
        )
        opp_b = Opportunity(
            id="remotive:abc",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.example/jobs/12345",
            source_id="abc",
            organization="Twilio",
            title="Senior Backend Engineer",
            description="Twilio communications backend role",
            canonical_outbound_url="https://remotive.example/jobs/12345",
        )

        can_merge, is_ambiguous = _evaluate_deduplication(opp_a, opp_b)
        self.assertFalse(can_merge)
        self.assertFalse(is_ambiguous)

        result = deduplicate_opportunities([opp_a, opp_b])
        self.assertEqual(len(result.unique_opportunities), 2)
        self.assertEqual(result.cross_source_duplicates_count, 0)

    def test_similarity_without_identity_proof_does_not_merge(self) -> None:
        """Same org, same exact title, near-identical description without stable identity -> preserve both."""
        opp_a = Opportunity(
            id="source_a:101",
            track=Track.EMPLOYMENT,
            source="source_a",
            source_url="https://source-a.example/jobs/101",
            source_id="101",
            organization="Acme Corp",
            title="Senior Python Engineer",
            description="Build scalable distributed backend systems with Python and AWS.",
            seniority=SeniorityLevel.SENIOR,
            canonical_outbound_url="https://source-a.example/jobs/101",
        )
        opp_b = Opportunity(
            id="source_b:202",
            track=Track.EMPLOYMENT,
            source="source_b",
            source_url="https://source-b.example/jobs/202",
            source_id="202",
            organization="Acme Corp",
            title="Senior Python Engineer",
            description="Build scalable distributed backend systems with Python and AWS.",
            seniority=SeniorityLevel.SENIOR,
            canonical_outbound_url="https://source-b.example/jobs/202",
        )

        can_merge, is_ambiguous = _evaluate_deduplication(opp_a, opp_b)
        self.assertFalse(can_merge)
        self.assertTrue(is_ambiguous)

        result = deduplicate_opportunities([opp_a, opp_b])
        self.assertEqual(len(result.unique_opportunities), 2)
        self.assertEqual(result.cross_source_duplicates_count, 0)
        self.assertEqual(result.ambiguous_duplicates_count, 1)

    def test_ats_direct_plus_aggregator_with_same_canonical_url_merges(self) -> None:
        """ATS direct + aggregator with exact same canonical ATS URL -> MERGES cleanly."""
        canonical_url = "https://boards.greenhouse.io/cloudflare/jobs/456789"
        opp_ats = Opportunity(
            id="greenhouse:cloudflare:456789",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url=canonical_url,
            source_id="456789",
            organization="Cloudflare",
            title="Systems Engineer - Cloudflare Workers",
            description="Work on edge compute infrastructure.",
            canonical_outbound_url=canonical_url,
        )
        opp_agg = Opportunity(
            id="himalayas:cf-workers",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/cloudflare-workers",
            source_id="cf-workers",
            organization="Cloudflare",
            title="Systems Engineer - Cloudflare Workers",
            description="Work on edge compute infrastructure.",
            canonical_outbound_url=canonical_url,
        )

        can_merge, is_ambiguous = _evaluate_deduplication(opp_ats, opp_agg)
        self.assertTrue(can_merge)
        self.assertFalse(is_ambiguous)

        result = deduplicate_opportunities([opp_ats, opp_agg])
        self.assertEqual(len(result.unique_opportunities), 1)
        self.assertEqual(result.cross_source_duplicates_count, 1)

    def test_same_source_distinct_requisition_ids_never_merge(self) -> None:
        """Distinct requisition IDs from same source never merge (preserving headcount)."""
        opp_req1 = Opportunity(
            id="greenhouse:stripe:1001",
            track=Track.EMPLOYMENT,
            source="greenhouse:stripe",
            source_url="https://boards.greenhouse.io/stripe/jobs/1001",
            source_id="1001",
            organization="Stripe",
            title="Software Engineer - Payments",
            description="Identical description for open headcount 1",
        )
        opp_req2 = Opportunity(
            id="greenhouse:stripe:1002",
            track=Track.EMPLOYMENT,
            source="greenhouse:stripe",
            source_url="https://boards.greenhouse.io/stripe/jobs/1002",
            source_id="1002",
            organization="Stripe",
            title="Software Engineer - Payments",
            description="Identical description for open headcount 1",
        )

        can_merge, is_ambiguous = _evaluate_deduplication(opp_req1, opp_req2)
        self.assertFalse(can_merge)

        result = deduplicate_opportunities([opp_req1, opp_req2])
        self.assertEqual(len(result.unique_opportunities), 2)
        self.assertEqual(result.exact_duplicates_count, 0)
        self.assertEqual(result.cross_source_duplicates_count, 0)


if __name__ == "__main__":
    unittest.main()
