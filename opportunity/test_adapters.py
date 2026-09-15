"""Integration and parsing tests for all opportunity feed adapters."""
import json
import tempfile
from pathlib import Path
import unittest

from opportunity.acquisition import AcquisitionService
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
from opportunity.adapters.hacker_news import SourceReadRefused, fetch_who_is_hiring_payload
from opportunity.models import (
    EmploymentType,
    RemotePolicy,
    RemoteScope,
    SeniorityLevel,
    Track,
    WorkMode,
)
from opportunity.registry import SourceRegistry
from opportunity.transport import MockTransport, TransportResponse

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

    def test_himalayas_missing_native_id_uses_stable_url_across_reordering(self):
        adapter = HimalayasAdapter()
        target = json.loads(read_fixture("himalayas.json"))["jobs"][0]
        target.pop("id")
        target.pop("slug")

        original = adapter.parse_payload(
            json.dumps({"jobs": [target]}),
            raw_pointer="fixture:himalayas",
            fetched_at="2026-08-30",
        ).opportunities[0]
        dummy = {
            "id": "short-id",
            "title": "Example Role",
            "companyName": "Example Co",
            "applicationLink": "https://himalayas.app/jobs/example-role",
        }
        reordered = adapter.parse_payload(
            json.dumps({"jobs": [dummy, target]}),
            raw_pointer="fixture:himalayas",
            fetched_at="2026-08-30",
        ).opportunities[1]

        self.assertEqual(original.source_url, reordered.source_url)
        self.assertEqual(original.source_id, original.source_url)
        self.assertEqual(original.id, reordered.id)

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

    def test_we_work_remotely_long_guid_survives_feed_reordering(self):
        adapter = WeWorkRemotelyAdapter()
        payload = read_fixture("we_work_remotely.xml")
        original = adapter.parse_payload(
            payload, raw_pointer="fixture:wwr", fetched_at="2026-08-30"
        )

        dummy = """
    <item>
      <title>Example Co: Short Test Role</title>
      <link>https://weworkremotely.com/remote-jobs/example-short-role</link>
      <guid>example-short-role</guid>
      <pubDate>Sun, 28 Aug 2026 09:00:00 GMT</pubDate>
      <description>Example posting.</description>
      <region>Anywhere in the World</region>
    </item>
"""
        reordered_payload = payload.replace("    <item>", dummy + "    <item>", 1)
        reordered = adapter.parse_payload(
            reordered_payload, raw_pointer="fixture:wwr", fetched_at="2026-08-30"
        )

        original_datadog = next(o for o in original if o.organization == "Datadog")
        reordered_datadog = next(o for o in reordered if o.organization == "Datadog")
        self.assertEqual(original_datadog.source_url, reordered_datadog.source_url)
        self.assertEqual(
            original_datadog.id, reordered_datadog.id,
            "RSS item reordering must not mint a new identity for the same WWR posting",
        )

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


_HN_DISABLED_REGISTRY_YAML = """
sources:
  - source_id: hacker_news_who_is_hiring
    name: "hacker_news_who_is_hiring"
    category: employment
    access:
      discovery: public_get
      detail: public_get_or_unknown
      submit: prohibited_or_unknown
    attribution:
      required: review_required
    rate_limits:
      documented: unknown
    commercial_use:
      status: review_required
    automation:
      read: disabled
      prepare: disabled
      submit: disabled
    policy_status: manual_only
    observed:
      status: allowed_ok
      detail: "test fixture: disabled for E5.2"
      request_metadata: "method=GET; endpoint=/v0/item/1.json"
      latency_ms: 0
      record_count: 0
    last_policy_reviewed: 2026-09-03
    policy_evidence:
      - https://github.com/HackerNews/API
"""


class HackerNewsGovernedFetchTests(unittest.TestCase):
    """Council review 4, finding 10: ``fetch_who_is_hiring_payload`` must route every
    GET through ``AcquisitionService.acquire`` and refuse -- not fetch -- when the
    registry entry is ``read: disabled``."""

    def test_flipping_registry_to_disabled_refuses_not_fetches(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry_path = Path(tmp_dir) / "registry.yaml"
            registry_path.write_text(_HN_DISABLED_REGISTRY_YAML, encoding="utf-8")
            registry = SourceRegistry(registry_path)

            class CountingTransport(MockTransport):
                def __init__(self):
                    super().__init__()
                    self.calls = 0

                def fetch(self, request):
                    self.calls += 1
                    return TransportResponse(status_code=200, body='{"submitted": [1]}', latency_ms=5)

            transport = CountingTransport()
            service = AcquisitionService(registry=registry, transport=transport)

            with self.assertRaises(SourceReadRefused):
                fetch_who_is_hiring_payload(service)

            # The registry gate must refuse before transport is ever touched --
            # this is what makes it "refuse, not fetch".
            self.assertEqual(0, transport.calls)

    def test_read_allowed_fetches_through_acquisition_service(self):
        registry = SourceRegistry()  # real, committed docs/SOURCE_REGISTRY.yaml: read-allowed
        transport = MockTransport()
        transport.set_response(
            "hacker_news_who_is_hiring",
            TransportResponse(status_code=200, body=json.dumps({"submitted": []}), latency_ms=5),
        )
        service = AcquisitionService(registry=registry, transport=transport)

        payload = fetch_who_is_hiring_payload(service)
        data = json.loads(payload)
        self.assertEqual([], data["comments"])

    def test_403_mid_orchestration_stops_and_returns_partial_not_raise(self):
        registry = SourceRegistry()

        class SequencedTransport(MockTransport):
            def __init__(self):
                super().__init__()
                self._calls = 0

            def fetch(self, request):
                self._calls += 1
                if self._calls == 1:
                    return TransportResponse(status_code=200, body=json.dumps({"submitted": [42]}), latency_ms=5)
                return TransportResponse(status_code=403, body="", latency_ms=5)

        transport = SequencedTransport()
        service = AcquisitionService(registry=registry, transport=transport)

        payload = fetch_who_is_hiring_payload(service)
        data = json.loads(payload)
        self.assertEqual([], data["comments"])
        self.assertEqual(2, transport._calls)

    def test_hacker_news_long_title_clamped_and_provenance_preserved(self):
        adapter = HackerNewsWhoIsHiringAdapter()
        long_line = "Acme Corp | Remote | " + ("Very Long Title Word " * 25)
        payload = json.dumps({
            "thread_id": 99999,
            "thread_title": "Ask HN: Who is hiring? (Test)",
            "comments": [{
                "id": 12345,
                "by": "test_user",
                "time": 1700000000,
                "text": f"{long_line}\nWe are hiring engineers to build distributed systems in Python and Go.",
            }],
        })
        opportunities = adapter.parse_payload(payload, raw_pointer="test:hn", fetched_at="2026-09-08")
        self.assertEqual(1, len(opportunities))
        opp = opportunities[0]
        # Title must be clamped to 255 for database schema VARCHAR(255) safety
        self.assertLessEqual(len(opp.title), 255)
        self.assertLessEqual(len(opp.organization), 255)
        # Field provenance must retain the full un-truncated string in raw_value
        title_prov = next(p for p in opp.field_provenances if p.field_name == "title")
        self.assertGreater(len(title_prov.raw_value), 255)
        self.assertIn("Acme Corp", title_prov.raw_value)


if __name__ == "__main__":
    unittest.main()
