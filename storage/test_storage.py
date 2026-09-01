import unittest
import os
import tempfile
from datetime import datetime, timezone
from storage.engine import get_engine, init_db, get_session_factory
from storage.repository import StorageRepository
from storage.models import Base


class TestStorageRepository(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_storage.db")
        self.engine = get_engine(f"sqlite:///{self.db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()
        self.repo = StorageRepository(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_save_and_get_opportunity(self):
        opp_data = {
            "id": "OPP-001",
            "track": "EMPLOYMENT",
            "title": "Lead Platform Engineer",
            "organization": "Cairo Cloud Systems",
            "description": "Building next-generation cloud infra.",
            "source_id": "greenhouse:cairocloud",
            "source_url": "https://boards.greenhouse.io/cairocloud/jobs/123",
            "content_hash": "hash123456",
            "country": "Egypt",
            "region": "MENA",
            "geographic_scope": "COUNTRY_ONLY",
            "posted_date": "2026-08-31",
            "is_stale": False,
        }
        provenances = [
            {
                "field_name": "title",
                "raw_value": "Lead Platform Engineer",
                "normalized_value": "Lead Platform Engineer",
                "derivation_type": "EXACT_EXTRACTION",
                "record_checksum": "hash123456",
            }
        ]
        saved = self.repo.save_opportunity(opp_data, provenances)
        self.assertEqual(saved.id, "OPP-001")

        retrieved = self.repo.get_opportunity("OPP-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Lead Platform Engineer")
        self.assertEqual(len(retrieved.provenances), 1)
        self.assertEqual(retrieved.provenances[0].field_name, "title")

    def test_founder_feedback(self):
        self.repo.save_opportunity({
            "id": "OPP-002",
            "track": "EMPLOYMENT",
            "title": "Senior AI Architect",
            "organization": "Nile AI",
            "description": "AI systems",
            "source_id": "lever:nileai",
            "source_url": "https://jobs.lever.co/nileai/123",
            "content_hash": "hash222",
        }, [])

        fb = self.repo.record_feedback("OPP-002", "bad_match", "seniority_wrong", "Too junior")
        self.assertEqual(fb.opportunity_id, "OPP-002")
        self.assertEqual(fb.feedback_label, "bad_match")

        feedback_list = self.repo.list_feedback_for_opportunity("OPP-002")
        self.assertEqual(len(feedback_list), 1)
        self.assertEqual(feedback_list[0].structured_reason, "seniority_wrong")


if __name__ == "__main__":
    unittest.main()
