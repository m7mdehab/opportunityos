"""Integration and parsing tests for all opportunity feed adapters."""
import json
from pathlib import Path
import unittest

from opportunity.adapters import (
    EUTEDAdapter,
    GreenhouseAdapter,
    HackerNewsWhoIsHiringAdapter,
    HimalayasAdapter,
    LeverAdapter,
    RemoteOKAdapter,
    RemotiveAdapter,
    UNGMAdapter,
    WeWorkRemotelyAdapter,
    WorldBankAdapter,
)
from opportunity.models import (
    EmploymentType,
    RemotePolicy,
    RemoteScope,
    SeniorityLevel,
    Track,
    WorkMode,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class AdapterTests(unittest.TestCase):
    def test_greenhouse_adapter(self):
        adapter = GreenhouseAdapter("cloudflare")
        payload = read_fixture("greenhouse_cloudflare.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:greenhouse", fetched_at="2026-08-30")

        self.assertEqual(2, len(opportunities))
        opp1 = opportunities[0]
        self.assertEqual("greenhouse:cloudflare", opp1.source)
        self.assertEqual("Cloudflare", opp1.organization)
        self.assertEqual("Senior Systems Engineer - Distributed Caching", opp1.title)
        self.assertEqual(SeniorityLevel.SENIOR, opp1.seniority)
        self.assertEqual(RemotePolicy.REMOTE, opp1.remote_policy)
        self.assertEqual("eligible", opp1.geographic_eligibility.status)  # Worldwide
        self.assertIsNotNone(opp1.compensation)
        self.assertEqual(160000.0, opp1.compensation.min_amount)  # type: ignore
        self.assertEqual(210000.0, opp1.compensation.max_amount)  # type: ignore
        self.assertTrue(len(opp1.skills) > 0)
        self.assertIn("Rust", opp1.skills)

        opp2 = opportunities[1]
        self.assertEqual("Data Analyst - Product Insights", opp2.title)
        self.assertEqual("excluded", opp2.geographic_eligibility.status)  # US Only

    def test_lever_adapter(self):
        adapter = LeverAdapter("shyftlabs")
        payload = read_fixture("lever_shyftlabs.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:lever", fetched_at="2026-08-30")

        self.assertEqual(2, len(opportunities))
        opp1 = opportunities[0]
        self.assertEqual("lever:shyftlabs", opp1.source)
        self.assertEqual("Senior Machine Learning Engineer", opp1.title)
        self.assertEqual(SeniorityLevel.SENIOR, opp1.seniority)
        self.assertEqual(EmploymentType.FULL_TIME, opp1.employment_type)
        self.assertEqual("eligible", opp1.geographic_eligibility.status)

        opp2 = opportunities[1]
        self.assertEqual("Junior Frontend Developer", opp2.title)
        self.assertEqual(SeniorityLevel.ENTRY, opp2.seniority)
        self.assertEqual(EmploymentType.CONTRACT, opp2.employment_type)
        self.assertEqual("excluded", opp2.geographic_eligibility.status)  # Canada Only

    def test_himalayas_adapter(self):
        adapter = HimalayasAdapter()
        payload = read_fixture("himalayas.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:himalayas", fetched_at="2026-08-30")

        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("himalayas", opp.source)
        self.assertEqual("CloudScale Inc", opp.organization)
        self.assertEqual("Principal Backend Architect", opp.title)
        self.assertEqual(SeniorityLevel.PRINCIPAL, opp.seniority)
        self.assertEqual("eligible", opp.geographic_eligibility.status)
        self.assertIsNotNone(opp.compensation)
        self.assertEqual(180000.0, opp.compensation.min_amount)  # type: ignore

    def test_remotive_adapter(self):
        adapter = RemotiveAdapter()
        payload = read_fixture("remotive.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:remotive", fetched_at="2026-08-30")

        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("remotive", opp.source)
        self.assertEqual("InfraStack Ltd", opp.organization)
        self.assertEqual("Lead DevOps Engineer", opp.title)
        self.assertEqual(SeniorityLevel.LEAD, opp.seniority)
        self.assertEqual(EmploymentType.FULL_TIME, opp.employment_type)
        self.assertEqual("eligible", opp.geographic_eligibility.status)
        self.assertIn("Kubernetes", opp.skills)
        self.assertIn("Terraform", opp.skills)

    def test_remote_ok_adapter(self):
        adapter = RemoteOKAdapter()
        payload = read_fixture("remote_ok.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:remote_ok", fetched_at="2026-08-30")

        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("remote_ok", opp.source)
        self.assertEqual("NextWave Labs", opp.organization)
        self.assertEqual("Senior Fullstack Engineer", opp.title)
        self.assertEqual(SeniorityLevel.SENIOR, opp.seniority)
        self.assertEqual(130000.0, opp.compensation.min_amount)  # type: ignore

    def test_we_work_remotely_adapter(self):
        adapter = WeWorkRemotelyAdapter()
        payload = read_fixture("we_work_remotely.xml")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:wwr", fetched_at="2026-08-30")

        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("we_work_remotely", opp.source)
        self.assertEqual("Datadog", opp.organization)
        self.assertEqual("Senior Backend Systems Engineer", opp.title)
        self.assertEqual(SeniorityLevel.SENIOR, opp.seniority)
        self.assertEqual("eligible", opp.geographic_eligibility.status)

    def test_ungm_adapter(self):
        adapter = UNGMAdapter()
        payload = read_fixture("ungm.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:ungm", fetched_at="2026-08-30")

        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("ungm", opp.source)
        self.assertEqual(Track.PROCUREMENT, opp.track)
        self.assertEqual("United Nations Development Programme (UNDP)", opp.organization)
        self.assertIn("Climate Adaptation", opp.title)
        self.assertIsNotNone(opp.procurement_metadata)
        self.assertEqual("2026-09-30", opp.closing_date)
        self.assertEqual("Egypt", opp.procurement_metadata.buyer_country)  # type: ignore

    def test_world_bank_adapter(self):
        adapter = WorldBankAdapter()
        payload = read_fixture("world_bank.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:world_bank", fetched_at="2026-08-30")

        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("world_bank", opp.source)
        self.assertEqual(Track.PROCUREMENT, opp.track)
        self.assertEqual("Ministry of Communications and Information Technology", opp.organization)
        self.assertIn("Digital Transformation", opp.title)
        self.assertIsNotNone(opp.procurement_metadata)
        self.assertEqual("2026-10-15", opp.closing_date)

    def test_eu_ted_adapter(self):
        adapter = EUTEDAdapter()
        self.assertEqual("POST", adapter.method)
        payload = read_fixture("eu_ted.json")
        opportunities = adapter.parse_payload(payload, raw_pointer="fixture:eu_ted", fetched_at="2026-08-30")

        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("eu_ted", opp.source)
        self.assertEqual(Track.PROCUREMENT, opp.track)
        self.assertIn("Cybersecurity", opp.organization)
        self.assertIn("Modernization", opp.title)
        self.assertIsNotNone(opp.procurement_metadata)
        self.assertIn("72000000", opp.procurement_metadata.cpv_codes)  # type: ignore

    def test_hacker_news_who_is_hiring_adapter(self):
        # Inline fixture (not opportunity/fixtures/**, which A1 owns this wave): a minimal,
        # already-assembled Hacker News Firebase payload matching HackerNewsWhoIsHiringAdapter's
        # documented PAYLOAD SHAPE (see opportunity/adapters/hacker_news.py).
        payload = json.dumps({
            "thread_id": 99999999,
            "thread_title": "Ask HN: Who is hiring? (September 2026)",
            "comments": [
                {
                    "id": 111111,
                    "by": "hn_recruiter",
                    "time": 1767225600,
                    "text": (
                        "NimbusData | Remote (Worldwide) | Full-time | $140k-$180k<p>"
                        "We are hiring a Senior Machine Learning Engineer to build our "
                        "recommendation platform. Python, PyTorch, Kubernetes required."
                    ),
                },
                {
                    "id": 222222,
                    "by": "another_recruiter",
                    "time": 1767225700,
                    "text": "",  # empty text should be skipped, not raise
                },
            ],
        })
        adapter = HackerNewsWhoIsHiringAdapter()
        result = adapter.parse_payload(payload, raw_pointer="fixture:hn", fetched_at="2026-09-03")

        self.assertEqual(2, result.records_raw_count)
        opportunities = result.opportunities
        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        self.assertEqual("hacker_news_who_is_hiring", opp.source)
        self.assertEqual("NimbusData", opp.organization)
        self.assertIn("NimbusData", opp.title)
        self.assertEqual("https://news.ycombinator.com/item?id=111111", opp.source_url)
        self.assertIn("Python", opp.description)
        # BRIEF-FR-006 A1 defect fix: HN "who is hiring" comments carry no native
        # structured work-mode field -- "Remote (Worldwide)" is free text, so this
        # must be inference, and work_mode_source must say so (never silently
        # "adapter" for a fact the adapter never actually mapped).
        self.assertEqual(WorkMode.REMOTE, opp.work_mode)
        self.assertEqual("inference", opp.work_mode_source)
        self.assertEqual(RemoteScope.WORLDWIDE, opp.remote_scope)
        self.assertEqual(RemotePolicy.REMOTE, opp.remote_policy)


if __name__ == "__main__":
    unittest.main()
