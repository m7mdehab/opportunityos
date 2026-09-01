import unittest
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from storage.engine import get_engine, init_db, get_session_factory
from storage.migration import LegacySqliteToPostgresMigrator
from storage.models import (
    OutboundActionRecord,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
)

class TestLegacyMigration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_db_path = os.path.join(self.temp_dir.name, "target.db")
        self.engine = get_engine(f"sqlite:///{self.target_db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()
        self.migrator = LegacySqliteToPostgresMigrator(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_migrate_inbox_sqlite(self):
        sqlite_path = os.path.join(self.temp_dir.name, "legacy_inbox.db")
        conn = sqlite3.connect(sqlite_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE inbound_evidence (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                sender TEXT NOT NULL,
                subject TEXT NOT NULL,
                body_hash TEXT NOT NULL,
                received_at TEXT NOT NULL,
                processing_status TEXT,
                processed_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE pipeline_events (
                id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                signal_category TEXT NOT NULL,
                source_timestamp TEXT NOT NULL,
                confidence REAL NOT NULL,
                provenance_hash TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE notifications (
                id TEXT PRIMARY KEY,
                notification_key TEXT UNIQUE NOT NULL,
                opportunity_id TEXT NOT NULL,
                priority TEXT NOT NULL,
                headline TEXT NOT NULL,
                body TEXT NOT NULL,
                action_required INTEGER,
                deadline TEXT
            )
        """)
        cur.execute("""
            INSERT INTO inbound_evidence VALUES (
                'EVID-1', 'MSG-1', 'GMAIL', 'recruiter@cairo.com', 'Interview Invitation', 'hashbody1', '2026-08-31T12:00:00', 'PROCESSED', '2026-08-31T12:05:00'
            )
        """)
        cur.execute("""
            INSERT INTO pipeline_events VALUES (
                'EVT-1', 'OPP-100', 'SIG-1', 'INTERVIEW_REQUEST', '2026-08-31T12:00:00', 1.0, 'hashprov1'
            )
        """)
        cur.execute("""
            INSERT INTO notifications VALUES (
                'NOTIF-1', 'KEY-1', 'OPP-100', 'URGENT', 'Interview Request', 'Founder interview scheduled', 1, '2026-09-02'
            )
        """)
        conn.commit()
        conn.close()

        stats = self.migrator.migrate_inbox_sqlite(sqlite_path)
        self.assertEqual(stats["evidence"], 1)
        self.assertEqual(stats["events"], 1)
        self.assertEqual(stats["notifications"], 1)

        ev = self.session.query(InboundEvidenceRecord).filter_by(id="EVID-1").first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.processing_status, "PROCESSED")

        evt = self.session.query(PipelineEventRecord).filter_by(id="EVT-1").first()
        self.assertIsNotNone(evt)
        self.assertEqual(evt.signal_category, "INTERVIEW_REQUEST")

        notif = self.session.query(NotificationRecord).filter_by(id="NOTIF-1").first()
        self.assertIsNotNone(notif)
        self.assertTrue(notif.action_required)


if __name__ == "__main__":
    unittest.main()
