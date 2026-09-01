import unittest
import tempfile
import os
from storage.engine import get_engine, init_db, get_session_factory
from storage.repository import StorageRepository
from feedback.models import FeedbackLabel
from feedback.service import FounderFeedbackService

class TestFounderFeedbackService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "fb.db")
        self.engine = get_engine(f"sqlite:///{self.db_path}")
        init_db(self.engine)
        self.session = get_session_factory(self.engine)()
        self.repo = StorageRepository(self.session)
        self.service = FounderFeedbackService(self.repo)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_submit_and_query_feedback(self):
        self.repo.save_opportunity({
            "id": "OPP-FB-1",
            "track": "EMPLOYMENT",
            "title": "Software Engineer",
            "organization": "Cairo Tech",
            "description": "Tech job",
            "source_id": "test:source",
            "source_url": "https://example.com/job/1",
            "content_hash": "hash11",
        }, [])

        evt = self.service.submit_feedback(
            opportunity_id="OPP-FB-1",
            label=FeedbackLabel.BAD_MATCH,
            reason="seniority_wrong",
            notes="Requires 15 years, candidate is mid-level",
        )
        self.assertEqual(evt.opportunity_id, "OPP-FB-1")
        self.assertEqual(evt.feedback_label, FeedbackLabel.BAD_MATCH)

        records = self.repo.list_feedback_for_opportunity("OPP-FB-1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].feedback_label, "bad_match")


if __name__ == "__main__":
    unittest.main()
