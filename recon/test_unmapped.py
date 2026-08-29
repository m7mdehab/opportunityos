import unittest

from recon.geography import extract
from recon.models import Record


class UnmappedPhraseTrackingTests(unittest.TestCase):
    def test_newly_mapped_location_is_not_captured_as_unmapped(self):
        record = Record(
            source="test_source",
            track="employment",
            title="Software Engineer",
            organization="Acme Corp",
            location_text="Singapore",
            url="https://example.test/jobs/1",
            posted_date="2026-08-28",
            description="Looking for an engineer based in Singapore office.",
            raw_payload_pointer="fixtures/test.json",
        )
        extracted = extract(record)
        self.assertNotIn("Singapore", extracted.unmapped)
        self.assertIn(("SG", "Singapore"), extracted.geo_allow)

    def test_mapped_locations_are_not_marked_unmapped(self):
        record = Record(
            source="test_source",
            track="employment",
            title="Remote Developer",
            organization="Acme Corp",
            location_text="Worldwide",
            url="https://example.test/jobs/2",
            posted_date="2026-08-28",
            description="Hiring globally anywhere.",
            raw_payload_pointer="fixtures/test.json",
        )
        extracted = extract(record)
        self.assertEqual((), extracted.unmapped)
        self.assertIn(("WORLDWIDE", "Worldwide"), extracted.geo_allow)

    def test_compound_mapped_location_has_no_unmapped_segment(self):
        record = Record(
            source="test_source",
            track="employment",
            title="DevOps Engineer",
            organization="Acme Corp",
            location_text="Remote - Singapore, Japan",
            url="https://example.test/jobs/3",
            posted_date="2026-08-28",
            description="We hire in Singapore and Japan.",
            raw_payload_pointer="fixtures/test.json",
        )
        extracted = extract(record)
        self.assertNotIn("Singapore", extracted.unmapped)
        self.assertNotIn("Japan", extracted.unmapped)
        self.assertTrue(any(token == "JP" for token, _ in extracted.geo_allow))

    def test_generic_work_modes_are_not_marked_unmapped(self):
        record = Record(
            source="test_source",
            track="employment",
            title="Frontend Engineer",
            organization="Acme Corp",
            location_text="Remote / Hybrid",
            url="https://example.test/jobs/4",
            posted_date="2026-08-28",
            description="Flexible work environment.",
            raw_payload_pointer="fixtures/test.json",
        )
        extracted = extract(record)
        self.assertEqual((), extracted.unmapped)
