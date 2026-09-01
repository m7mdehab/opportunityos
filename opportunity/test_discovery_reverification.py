import unittest
from opportunity.adapters.ashby import AshbyAdapter
from opportunity.schema_org import SchemaOrgJobPostingExtractor
from opportunity.reverification import StaleOpportunityReverifier
from opportunity.models import Track

class TestStructuredDiscoveryAndReverification(unittest.TestCase):
    def test_ashby_adapter_parsing(self):
        job_payload = {
            "id": "12345-abc",
            "title": "Principal AI Systems Engineer",
            "descriptionPlain": "Develop high-throughput inference engines.",
            "locationName": "Remote - MENA",
            "jobUrl": "https://jobs.ashbyhq.com/openai/12345-abc",
        }
        opp = AshbyAdapter.parse_job_posting("openai", job_payload, "2026-08-31T20:00:00Z")
        self.assertEqual(opp.id, "ashby:openai:12345-abc")
        self.assertEqual(opp.title, "Principal AI Systems Engineer")
        self.assertEqual(opp.organization, "openai")
        self.assertEqual(opp.location_raw, "Remote - MENA")
        self.assertEqual(opp.track, Track.EMPLOYMENT)
        self.assertEqual(len(opp.field_provenances), 3)

    def test_schema_org_json_ld_extraction(self):
        json_ld = {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Lead Backend Engineer",
            "description": "High performance microservices in Python & Go.",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "Alexandria Tech Hub"
            }
        }
        opp = SchemaOrgJobPostingExtractor.extract_from_json_ld(json_ld, "https://company.com/jobs/1", "2026-08-31T20:00:00Z")
        self.assertIsNotNone(opp)
        self.assertEqual(opp.title, "Lead Backend Engineer")
        self.assertEqual(opp.organization, "Alexandria Tech Hub")

    def test_reverification_mock(self):
        # Reverifier test with mock response logic
        res = StaleOpportunityReverifier.reverify_url("http://invalid.domain.that.does.not.exist.internal", timeout_seconds=1)
        self.assertFalse(res["is_stale"])
        self.assertIn("Transient network failure", res["reason"])


if __name__ == "__main__":
    unittest.main()
