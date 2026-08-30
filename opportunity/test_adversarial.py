"""Adversarial and Robustness Tests for Opportunity Ingestion Pipeline."""
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
    CompensationInterval,
    DerivationType,
    Opportunity,
    RemotePolicy,
    SeniorityLevel,
    SourceHealthStatus,
    Track,
)
from opportunity.normalization import derive_geographic_eligibility


class AdversarialIngestionTests(unittest.TestCase):
    def test_external_action_safety_and_verbs(self) -> None:
        """Invariant 1: All adapters must be strictly read-only; mutations are forbidden."""
        adapters = get_all_standard_adapters()
        for adapter in adapters:
            self.assertIn(
                adapter.method,
                {"GET", "POST"},
                f"Adapter {adapter.source_id} uses unapproved method {adapter.method}",
            )
            if adapter.method == "POST":
                self.assertEqual(
                    adapter.source_id,
                    "eu_ted",
                    f"Only EU TED is permitted read-only POST queries, got {adapter.source_id}",
                )
                self.assertIn(
                    "api.ted.europa.eu/v3/notices/search",
                    adapter.feed_url,
                    f"EU TED adapter points to unauthorized endpoint: {adapter.feed_url}",
                )

    def test_minimal_record_zero_fabrication_all_adapters(self) -> None:
        """Invariant 2: Minimal/sparse records MUST NOT fabricate default strings or values."""
        forbidden_strings = {
            "EU Contracting Authority",
            "EU",
            "Tender Notice",
            "Services",
            "United Nations",
            "RFP",
            "Consulting Services",
            "Himalayas Employer",
            "Remotive Employer",
            "Remote OK Employer",
            "We Work Remotely Employer",
            "Anywhere in the World",
        }

        # 1. Himalayas minimal
        him_adapter = HimalayasAdapter()
        him_opps = him_adapter.parse_payload('{"jobs": [{"title": "Minimal Engineer"}]}')
        self.assertEqual(len(him_opps), 1)
        self.assertEqual(him_opps[0].organization, "")
        self.assertEqual(him_opps[0].location_raw, "")
        self.assertEqual(him_opps[0].remote_policy, RemotePolicy.UNSPECIFIED)
        self.assertIsNone(him_opps[0].compensation)

        # 2. Remotive minimal
        rem_adapter = RemotiveAdapter()
        rem_opps = rem_adapter.parse_payload('{"jobs": [{"title": "Minimal Developer"}]}')
        self.assertEqual(len(rem_opps), 1)
        self.assertEqual(rem_opps[0].organization, "")
        self.assertEqual(rem_opps[0].location_raw, "")
        self.assertIsNone(rem_opps[0].compensation)

        # 3. Remote OK minimal
        rok_adapter = RemoteOKAdapter()
        rok_opps = rok_adapter.parse_payload('[{"position": "Minimal Worker"}]')
        self.assertEqual(len(rok_opps), 1)
        self.assertEqual(rok_opps[0].organization, "")
        self.assertEqual(rok_opps[0].location_raw, "")
        self.assertIsNone(rok_opps[0].compensation)

        # 4. We Work Remotely minimal
        wwr_adapter = WeWorkRemotelyAdapter()
        wwr_xml = "<rss><channel><item><title>Minimal Position</title></item></channel></rss>"
        wwr_opps = wwr_adapter.parse_payload(wwr_xml)
        self.assertEqual(len(wwr_opps), 1)
        self.assertEqual(wwr_opps[0].organization, "")
        self.assertEqual(wwr_opps[0].location_raw, "")

        # 5. UNGM minimal
        ungm_adapter = UNGMAdapter()
        ungm_opps = ungm_adapter.parse_payload('{"notices": [{"title": "Minimal Notice"}]}')
        self.assertEqual(len(ungm_opps), 1)
        self.assertEqual(ungm_opps[0].organization, "")
        self.assertEqual(ungm_opps[0].procurement_metadata.notice_type, "")
        self.assertEqual(ungm_opps[0].procurement_metadata.buyer_name, "")

        # 6. World Bank minimal
        wb_adapter = WorldBankAdapter()
        wb_opps = wb_adapter.parse_payload('{"notices": [{"title": "Minimal Project"}]}')
        self.assertEqual(len(wb_opps), 1)
        self.assertEqual(wb_opps[0].organization, "")
        self.assertEqual(wb_opps[0].procurement_metadata.buyer_name, "")

        # 7. EU TED minimal
        ted_adapter = EUTEDAdapter()
        ted_opps = ted_adapter.parse_payload('{"notices": [{"title": "Minimal Notice"}]}')
        self.assertEqual(len(ted_opps), 1)
        self.assertEqual(ted_opps[0].organization, "")
        self.assertEqual(ted_opps[0].procurement_metadata.buyer_name, "")
        self.assertEqual(ted_opps[0].procurement_metadata.buyer_country, "")

        # Verify no forbidden default string in any parsed minimal opportunity
        all_minimal_opps = him_opps + rem_opps + rok_opps + wwr_opps + ungm_opps + wb_opps + ted_opps
        for opp in all_minimal_opps:
            for forbidden in forbidden_strings:
                self.assertNotEqual(opp.organization, forbidden)
                self.assertNotEqual(opp.location_raw, forbidden)
                if opp.procurement_metadata:
                    self.assertNotEqual(opp.procurement_metadata.buyer_name, forbidden)
                    self.assertNotEqual(opp.procurement_metadata.notice_type, forbidden)

    def test_four_real_tracks_emission(self) -> None:
        """Invariant 3: Ingestion pipeline must emit distinct opportunities for all 4 tracks."""
        rem_adapter = RemotiveAdapter()
        
        # 1. Employment
        opp_emp = rem_adapter.parse_payload('{"jobs": [{"title": "Staff Backend Engineer", "job_type": "full_time"}]}')
        self.assertEqual(opp_emp[0].track, Track.EMPLOYMENT)

        # 2. Contract
        opp_contract = rem_adapter.parse_payload('{"jobs": [{"title": "Cloud Architect (Contract)", "job_type": "contract"}]}')
        self.assertEqual(opp_contract[0].track, Track.CONTRACT)

        # 3. Freelance
        opp_freelance = rem_adapter.parse_payload('{"jobs": [{"title": "Freelance Technical Writer", "job_type": "freelance"}]}')
        self.assertEqual(opp_freelance[0].track, Track.FREELANCE)

        # 4. Procurement
        ungm_adapter = UNGMAdapter()
        opp_proc = ungm_adapter.parse_payload('{"notices": [{"title": "Consulting RFP on Solar Grid Feasibility"}]}')
        self.assertEqual(opp_proc[0].track, Track.PROCUREMENT)

    def test_geographic_safety_and_no_false_eligibility(self) -> None:
        """Invariant 4: Restricted postings must NEVER be classified as eligible."""
        us_only = derive_geographic_eligibility("Senior Engineer", "US Only (Remote)", "US work authorization required.")
        self.assertEqual(us_only.status, "excluded")

        uk_only = derive_geographic_eligibility("DevOps Engineer", "United Kingdom Remote", "Must be UK resident.")
        self.assertEqual(uk_only.status, "excluded")

        eu_only = derive_geographic_eligibility("Frontend Lead", "EU / EEA Only", "Must reside in European Union.")
        self.assertEqual(eu_only.status, "excluded")

        worldwide = derive_geographic_eligibility("Python Architect", "Worldwide Remote", "Work from anywhere.")
        self.assertEqual(worldwide.status, "eligible")

    def test_schema_drift_is_never_silently_ignored(self) -> None:
        """Invariant 5: Corrupt payloads or unexpected schema structures must be flagged."""
        monitor = SourceHealthMonitor()
        
        # Corrupt JSON
        report_parse = monitor.record_run(
            source_id="himalayas",
            transport_status_code=200,
            parser_error="JSONDecodeError: invalid format",
        )
        self.assertEqual(report_parse.status, SourceHealthStatus.PERSISTENT_FAILURE)
        self.assertFalse(report_parse.is_healthy)

        # Non-empty payload with zero parsed records -> schema drift
        report_drift = monitor.record_run(
            source_id="lever:shyftlabs",
            transport_status_code=200,
            records_raw_count=50,
            records_parsed=0,
            has_schema_drift=True,
        )
        self.assertEqual(report_drift.status, SourceHealthStatus.SCHEMA_DRIFT_SUSPECTED)
        self.assertFalse(report_drift.is_healthy)


if __name__ == "__main__":
    unittest.main()
