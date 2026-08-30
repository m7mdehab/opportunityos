"""Comprehensive Unit & Regression Tests for Conservative Two-Layer Deduplication."""
import unittest

from opportunity.dedupe import deduplicate_opportunities
from opportunity.models import (
    GeographicEligibility,
    Opportunity,
    RemotePolicy,
    SeniorityLevel,
    Track,
)


class DeduplicationTests(unittest.TestCase):
    def test_exact_hash_deduplication(self) -> None:
        opp1 = Opportunity(
            id="himalayas:1",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/1",
            source_id="1",
            organization="Stripe",
            title="Software Engineer",
            description="Build economic infrastructure.",
            location_raw="Worldwide",
        )
        opp2 = Opportunity(
            id="himalayas:1-copy",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/1",
            source_id="1",
            organization="Stripe",
            title="Software Engineer",
            description="Build economic infrastructure.",
            location_raw="Worldwide",
        )
        result = deduplicate_opportunities([opp1, opp2])
        self.assertEqual(len(result.unique_opportunities), 1)
        self.assertEqual(result.exact_duplicates_count, 1)
        self.assertEqual(len(result.clusters), 1)
        self.assertEqual(result.clusters[0].cluster_size, 2)

    def test_invariant_a_same_org_title_loc_diff_req_ids_diff_desc_never_merges(self) -> None:
        """Regression A: Same org + title + location, different requisition IDs, different descriptions -> MUST NOT MERGE."""
        opp_a = Opportunity(
            id="greenhouse:cloudflare:101",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url="https://boards.greenhouse.io/cloudflare/jobs/101",
            source_id="101",
            organization="Cloudflare",
            title="Systems Engineer",
            description="Focus on edge routing and DDoS mitigation pipelines.",
            location_raw="Remote",
            seniority=SeniorityLevel.MID,
        )
        opp_b = Opportunity(
            id="greenhouse:cloudflare:102",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url="https://boards.greenhouse.io/cloudflare/jobs/102",
            source_id="102",
            organization="Cloudflare",
            title="Systems Engineer",
            description="Focus on internal developer platform and build tooling infrastructure.",
            location_raw="Remote",
            seniority=SeniorityLevel.MID,
        )
        result = deduplicate_opportunities([opp_a, opp_b])
        self.assertEqual(len(result.unique_opportunities), 2)
        self.assertEqual(result.cross_source_duplicates_count, 0)

    def test_invariant_b_same_source_two_distinct_req_ids_identical_text_never_merges(self) -> None:
        """Regression B: Same source, two distinct requisition IDs, identical text -> MUST NOT MERGE."""
        opp_a = Opportunity(
            id="greenhouse:datadog:req-alpha",
            track=Track.EMPLOYMENT,
            source="greenhouse:datadog",
            source_url="https://boards.greenhouse.io/datadog/jobs/req-alpha",
            source_id="req-alpha",
            organization="Datadog",
            title="Software Engineer, Core Observability",
            description="Build scalable telemetry platforms across Kubernetes.",
            location_raw="Remote",
            seniority=SeniorityLevel.MID,
        )
        opp_b = Opportunity(
            id="greenhouse:datadog:req-beta",
            track=Track.EMPLOYMENT,
            source="greenhouse:datadog",
            source_url="https://boards.greenhouse.io/datadog/jobs/req-beta",
            source_id="req-beta",
            organization="Datadog",
            title="Software Engineer, Core Observability",
            description="Build scalable telemetry platforms across Kubernetes.",
            location_raw="Remote",
            seniority=SeniorityLevel.MID,
        )
        result = deduplicate_opportunities([opp_a, opp_b])
        # Preserves both distinct open headcount requisitions
        self.assertEqual(len(result.unique_opportunities), 2)
        self.assertEqual(result.cross_source_duplicates_count, 0)

    def test_invariant_c_ats_direct_and_aggregator_same_outbound_url_merges(self) -> None:
        """Regression C: ATS direct listing + aggregator copy with common outbound ATS URL -> SHOULD MERGE."""
        ats_direct = Opportunity(
            id="greenhouse:cloudflare:5512301",
            track=Track.EMPLOYMENT,
            source="greenhouse:cloudflare",
            source_url="https://boards.greenhouse.io/cloudflare/jobs/5512301",
            source_id="5512301",
            organization="Cloudflare",
            title="Senior Systems Engineer",
            description="Build edge computing infrastructure.",
            location_raw="Remote",
            seniority=SeniorityLevel.SENIOR,
            canonical_outbound_url="https://boards.greenhouse.io/cloudflare/jobs/5512301",
        )
        aggregator_copy = Opportunity(
            id="himalayas:cloudflare-systems-senior-5512301",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/cloudflare-systems-senior-5512301",
            source_id="cloudflare-systems-senior-5512301",
            organization="Cloudflare",
            title="Senior Systems Engineer (Edge)",
            description="<p>Build edge computing infrastructure with high reliability.</p>",
            location_raw="Remote - Worldwide",
            seniority=SeniorityLevel.SENIOR,
            canonical_outbound_url="https://boards.greenhouse.io/cloudflare/jobs/5512301?gh_jid=5512301&utm_source=himalayas",
        )
        result = deduplicate_opportunities([ats_direct, aggregator_copy])
        self.assertEqual(len(result.unique_opportunities), 1)
        self.assertEqual(result.cross_source_duplicates_count, 1)
        self.assertEqual(result.clusters[0].primary_opportunity.id, "greenhouse:cloudflare:5512301")
        self.assertIn("himalayas", result.clusters[0].sources)

    def test_invariant_d_same_ats_job_remote_vs_remote_worldwide_merges_with_identity(self) -> None:
        """Regression D: Same canonical ATS job, 'Remote' vs 'Remote - Worldwide' -> SHOULD MERGE."""
        opp_a = Opportunity(
            id="lever:shyftlabs:job-1",
            track=Track.EMPLOYMENT,
            source="lever:shyftlabs",
            source_url="https://jobs.lever.co/shyftlabs/job-1",
            source_id="job-1",
            organization="ShyftLabs",
            title="Staff Python Engineer",
            description="Architect core distributed data services.",
            location_raw="Remote",
            seniority=SeniorityLevel.PRINCIPAL,
            canonical_outbound_url="https://jobs.lever.co/shyftlabs/job-1",
        )
        opp_b = Opportunity(
            id="remote_ok:shyftlabs-job-1",
            track=Track.EMPLOYMENT,
            source="remote_ok",
            source_url="https://remoteok.com/l/shyftlabs-job-1",
            source_id="shyftlabs-job-1",
            organization="ShyftLabs",
            title="Staff Python Engineer",
            description="Architect core distributed data services.",
            location_raw="Remote - Worldwide",
            seniority=SeniorityLevel.PRINCIPAL,
            canonical_outbound_url="https://jobs.lever.co/shyftlabs/job-1",
        )
        result = deduplicate_opportunities([opp_a, opp_b])
        self.assertEqual(len(result.unique_opportunities), 1)
        self.assertEqual(result.cross_source_duplicates_count, 1)

    def test_invariant_e_same_company_similar_title_no_stable_identity_remains_separate(self) -> None:
        """Regression E: Same company + similar title without stable identity proof -> MUST remain separate or possible_duplicate."""
        opp_a = Opportunity(
            id="himalayas:acme-eng-1",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/acme-eng-1",
            source_id="acme-eng-1",
            organization="Acme Corp",
            title="Data Platform Engineer",
            description="Manage Kafka clusters and data pipelines.",
            location_raw="Worldwide",
            seniority=SeniorityLevel.MID,
        )
        opp_b = Opportunity(
            id="remotive:acme-eng-2",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.com/jobs/acme-eng-2",
            source_id="acme-eng-2",
            organization="Acme Corp",
            title="Data Analytics Engineer",
            description="Build dbt models and dashboard telemetry.",
            location_raw="Worldwide",
            seniority=SeniorityLevel.MID,
        )
        result = deduplicate_opportunities([opp_a, opp_b])
        self.assertEqual(len(result.unique_opportunities), 2)
        self.assertEqual(result.cross_source_duplicates_count, 0)

    def test_distinct_seniority_never_merges(self) -> None:
        opp_jr = Opportunity(
            id="himalayas:1",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/1",
            source_id="1",
            organization="Acme Corp",
            title="Junior Software Engineer",
            description="Build web applications.",
            seniority=SeniorityLevel.ENTRY,
        )
        opp_sr = Opportunity(
            id="remotive:2",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.com/jobs/2",
            source_id="2",
            organization="Acme Corp",
            title="Senior Software Engineer",
            description="Build web applications.",
            seniority=SeniorityLevel.SENIOR,
        )
        result = deduplicate_opportunities([opp_jr, opp_sr])
        self.assertEqual(len(result.unique_opportunities), 2)

    def test_distinct_geographic_eligibility_never_merges(self) -> None:
        opp_worldwide = Opportunity(
            id="himalayas:1",
            track=Track.EMPLOYMENT,
            source="himalayas",
            source_url="https://himalayas.app/jobs/1",
            source_id="1",
            organization="Acme Corp",
            title="Software Engineer",
            description="Build web applications.",
            geographic_eligibility=GeographicEligibility(status="eligible", reason="Worldwide"),
        )
        opp_us_only = Opportunity(
            id="remotive:2",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.com/jobs/2",
            source_id="2",
            organization="Acme Corp",
            title="Software Engineer",
            description="Build web applications.",
            geographic_eligibility=GeographicEligibility(status="excluded", reason="US Only"),
        )
        result = deduplicate_opportunities([opp_worldwide, opp_us_only])
        self.assertEqual(len(result.unique_opportunities), 2)

    def test_distinct_tracks_never_merge(self) -> None:
        opp_emp = Opportunity(
            id="remotive:1",
            track=Track.EMPLOYMENT,
            source="remotive",
            source_url="https://remotive.com/jobs/1",
            source_id="1",
            organization="United Nations",
            title="Data Consultant",
            description="Support data modeling.",
        )
        opp_proc = Opportunity(
            id="ungm:2",
            track=Track.PROCUREMENT,
            source="ungm",
            source_url="https://ungm.org/notices/2",
            source_id="2",
            organization="United Nations",
            title="Data Consultant",
            description="Support data modeling.",
        )
        result = deduplicate_opportunities([opp_emp, opp_proc])
        self.assertEqual(len(result.unique_opportunities), 2)


if __name__ == "__main__":
    unittest.main()
