import unittest
import os
import tempfile
from storage.engine import get_engine, init_db, get_session_factory
from storage.repository import StorageRepository
from storage.models import OpportunityRecord, FounderFeedbackRecord
from scripts.backup_restore import dump_database, restore_database

class TestBackupRestore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.src_db = os.path.join(self.temp_dir.name, "src.db")
        self.dst_db = os.path.join(self.temp_dir.name, "dst.db")
        self.dump_file = os.path.join(self.temp_dir.name, "backup.json")

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_full_backup_and_restore_cycle(self):
        # 1. Populate source db
        engine = get_engine(f"sqlite:///{self.src_db}")
        init_db(engine)
        session_factory = get_session_factory(engine)
        session = session_factory()
        repo = StorageRepository(session)
        
        repo.save_opportunity({
            "id": "OPP-BACKUP-1",
            "track": "EMPLOYMENT",
            "title": "Principal Distributed Systems Engineer",
            "organization": "Alexandria Cloud Labs",
            "description": "Distributed systems",
            "source_id": "greenhouse:alexandria",
            "source_url": "https://boards.greenhouse.io/alexandria/1",
            "content_hash": "hash999",
        }, [{"field_name": "title", "derivation_type": "EXACT_EXTRACTION", "record_checksum": "hash999"}])
        
        repo.record_feedback("OPP-BACKUP-1", "good_match", None, "Perfect role fit")
        session.close()
        engine.dispose()

        # 2. Dump
        dump_database(f"sqlite:///{self.src_db}", self.dump_file)
        self.assertTrue(os.path.exists(self.dump_file))

        # 3. Restore to new target db
        restore_database(self.dump_file, f"sqlite:///{self.dst_db}")

        # 4. Verify target db contents
        dst_engine = get_engine(f"sqlite:///{self.dst_db}")
        dst_session = get_session_factory(dst_engine)()
        
        opp = dst_session.query(OpportunityRecord).filter_by(id="OPP-BACKUP-1").first()
        self.assertIsNotNone(opp)
        self.assertEqual(opp.title, "Principal Distributed Systems Engineer")
        self.assertEqual(len(opp.provenances), 1)

        fb = dst_session.query(FounderFeedbackRecord).filter_by(opportunity_id="OPP-BACKUP-1").first()
        self.assertIsNotNone(fb)
        self.assertEqual(fb.feedback_label, "good_match")

        dst_session.close()
        dst_engine.dispose()

if __name__ == "__main__":
    unittest.main()
