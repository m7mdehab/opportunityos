import unittest

from recon.audit import build_audit_item
from recon.models import Record


class AuditSerializationTests(unittest.TestCase):
    def test_audit_serialization_populates_extracted_geo_allow(self):
        record = Record(
            source="test_source",
            track="employment",
            title="Senior Data Engineer",
            organization="Acme Corp",
            location_text="Worldwide",
            url="https://example.test/jobs/1",
            posted_date="2026-08-28",
            description="We are hiring anywhere across the globe.",
            raw_payload_pointer="fixtures/test.json",
        )
        self.assertEqual((), record.geo_allow)
        self.assertEqual((), record.geo_deny)

        eligibility, item = build_audit_item(record)
        self.assertEqual("eligible", eligibility)
        self.assertEqual("eligible", item["derived_verdict"])
        self.assertGreater(len(item["geo_allow"]), 0)
        self.assertIn(("WORLDWIDE", "Worldwide"), item["geo_allow"])
        self.assertEqual([], item["geo_deny"])

    def test_audit_serialization_populates_extracted_geo_deny(self):
        record = Record(
            source="test_source",
            track="employment",
            title="Backend Engineer",
            organization="Acme Corp",
            location_text="Remote",
            url="https://example.test/jobs/2",
            posted_date="2026-08-28",
            description="Must be authorized to work in the United States.",
            raw_payload_pointer="fixtures/test.json",
        )
        self.assertEqual((), record.geo_allow)
        self.assertEqual((), record.geo_deny)

        eligibility, item = build_audit_item(record)
        self.assertEqual("excluded", eligibility)
        self.assertEqual("excluded", item["derived_verdict"])
        self.assertEqual([], item["geo_allow"])
        self.assertGreater(len(item["geo_deny"]), 0)
        self.assertTrue(any("WORK_AUTH_REQUIRED:US" in token for token, _ in item["geo_deny"]))

    def test_audit_serialization_reflects_both_allow_and_deny_evidence(self):
        record = Record(
            source="test_source",
            track="employment",
            title="Full Stack Developer",
            organization="Acme Corp",
            location_text="Worldwide",
            url="https://example.test/jobs/3",
            posted_date="2026-08-28",
            description="Worldwide remote. No visa sponsorship is available.",
            raw_payload_pointer="fixtures/test.json",
        )
        eligibility, item = build_audit_item(record)
        self.assertEqual("excluded", eligibility)
        self.assertIn(("WORLDWIDE", "Worldwide"), item["geo_allow"])
        self.assertTrue(any(token == "NO_SPONSORSHIP" for token, _ in item["geo_deny"]))
