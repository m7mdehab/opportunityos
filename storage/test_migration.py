import unittest
import os
import sqlite3
import json
import tempfile
from datetime import datetime, timezone
from storage.engine import get_engine, init_db, get_session_factory
from storage.migration import LegacySqliteToPostgresMigrator
from storage.models import (
    OutboundActionRecordModel,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    InboxCheckpointRecord,
    ReconciliationRecordModel,
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
                message_content_hash TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_message_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                sender_email TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                snippet TEXT NOT NULL,
                body_text TEXT NOT NULL,
                body_html TEXT NOT NULL,
                received_at TEXT NOT NULL,
                headers_json TEXT NOT NULL,
                attachment_names_json TEXT NOT NULL,
                processing_status TEXT NOT NULL DEFAULT 'FETCHED',
                processed_at TEXT
            )
        """)
        cur.execute("""
            INSERT INTO inbound_evidence (
                message_content_hash, provider, provider_message_id, thread_id,
                sender_email, sender_name, recipient_email, subject, snippet,
                body_text, body_html, received_at, headers_json, attachment_names_json,
                processing_status, processed_at
            ) VALUES (
                'hash_msg_1', 'gmail', 'msg_1', 'th_1',
                'hiring@techcorp.com', 'TechCorp Hiring', 'candidate@example.com',
                'Invitation to Technical Interview', 'We would like to invite you...',
                'Full email text...', '<p>Full email text...</p>', '2026-08-31T12:00:00Z',
                '[["From", "hiring@techcorp.com"]]', '["schedule.ics"]',
                'PROCESSED', '2026-08-31T12:05:00Z'
            )
        """)
        conn.commit()
        conn.close()

        stats = self.migrator.migrate_inbox_sqlite(sqlite_path)
        self.assertEqual(stats["inbound_evidence"], 1)

        migrated = self.session.query(InboundEvidenceRecord).filter_by(message_content_hash="hash_msg_1").first()
        self.assertIsNotNone(migrated)
        self.assertEqual(migrated.sender_email, "hiring@techcorp.com")
        self.assertEqual(migrated.processing_status, "PROCESSED")

    def test_migrate_outbound_sqlite(self):
        sqlite_path = os.path.join(self.temp_dir.name, "legacy_outbound.db")
        conn = sqlite3.connect(sqlite_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE idempotency_ledger (
                idempotency_key TEXT PRIMARY KEY,
                action_id TEXT NOT NULL,
                workspace TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                opportunity_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_status TEXT NOT NULL,
                record_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        rec_json = json.dumps({
            "action_id": "act_101",
            "opportunity_id": "opp_101",
            "opportunity_content_hash": "opp_hash_1",
            "workspace": "default",
            "candidate_id": "founder",
            "track": "EMPLOYMENT",
            "source": "ashby",
            "adapter_name": "ashby_outbound",
            "adapter_version": "1.0.0",
            "execution_mode": "CONTROLLED_SUBMIT",
            "qualification_decision": "QUALIFIED",
            "match_score_snapshot": 95.0,
            "artifact_ids": ["art_1"],
            "artifact_hashes": ["ahash_1"],
            "manifest_hash": "man_hash_1",
            "action_status": "CONFIRMED",
            "idempotency_key": "idemp_101",
            "created_at": "2026-08-31T10:00:00Z",
            "updated_at": "2026-08-31T10:05:00Z",
            "confirmation_evidence": {
                "confirmed": True,
                "confirmation_text": "Application received",
                "application_id": "app_99",
                "receipt_reference": "ASHBY-99",
                "final_url": "https://jobs.ashbyhq.com/thanks",
                "detected_at": "2026-08-31T10:05:00Z",
                "evidence_checksum": "chk_99"
            },
            "external_reference_id": "ASHBY-99"
        })

        cur.execute("""
            INSERT INTO idempotency_ledger (
                idempotency_key, action_id, workspace, candidate_id, opportunity_id,
                action_type, action_status, record_json, created_at, updated_at
            ) VALUES (
                'idemp_101', 'act_101', 'default', 'founder', 'opp_101',
                'submit', 'CONFIRMED', ?, '2026-08-31T10:00:00Z', '2026-08-31T10:05:00Z'
            )
        """, (rec_json,))
        conn.commit()
        conn.close()

        stats = self.migrator.migrate_outbound_sqlite(sqlite_path)
        self.assertEqual(stats["idempotency_reservations"], 1)
        self.assertEqual(stats["outbound_actions"], 1)

        migrated_act = self.session.query(OutboundActionRecordModel).filter_by(id="act_101").first()
        self.assertIsNotNone(migrated_act)
        self.assertEqual(migrated_act.action_status, "CONFIRMED")
        self.assertEqual(migrated_act.receipt_reference, "ASHBY-99")


if __name__ == "__main__":
    unittest.main()
