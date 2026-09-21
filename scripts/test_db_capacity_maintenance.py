from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from scripts.db_capacity_maintenance import archive_payload, verify_archive


class CapacityMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.connection = self.engine.connect()
        self.connection.execute(text("CREATE TABLE opportunities (id TEXT PRIMARY KEY, content_hash TEXT, description TEXT, raw_payload_json TEXT, search_tsv TEXT)"))
        self.connection.execute(text("CREATE TABLE field_provenances (id INTEGER PRIMARY KEY, opportunity_id TEXT, field_name TEXT, raw_value TEXT, normalized_value TEXT, derivation_type TEXT, raw_pointer TEXT, record_checksum TEXT, rule_id TEXT)"))
        self.connection.execute(text("CREATE TABLE opportunity_cold_archive (opportunity_id TEXT PRIMARY KEY, content_hash TEXT, payload_zlib BLOB, payload_sha256 TEXT, original_size_bytes INTEGER, archive_version TEXT, archived_at TEXT)"))
        self.connection.execute(
            text("INSERT INTO opportunities VALUES (:id,:hash,:description,:payload,NULL)"),
            {"id": "o1", "hash": "h1", "description": "source description", "payload": '{"x":1}'},
        )
        self.connection.execute(text("INSERT INTO field_provenances VALUES (1,'o1','title','raw','norm','RULE',NULL,'c','r')"))
        self.connection.commit()

    def tearDown(self):
        self.connection.close()
        self.engine.dispose()

    def test_archive_is_lossless_and_idempotently_verifiable(self):
        result = archive_payload(
            self.connection,
            {"id": "o1", "content_hash": "h1", "description": "source description", "raw_payload_json": '{"x":1}'},
            now=datetime.now(timezone.utc),
        )
        self.connection.commit()
        self.assertEqual(result["opportunity_id"], "o1")
        self.assertTrue(verify_archive(self.connection, "o1"))
        self.assertEqual(self.connection.execute(text("SELECT description FROM opportunities WHERE id='o1'")).scalar_one(), "[archived]")
        self.assertEqual(self.connection.execute(text("SELECT count(*) FROM field_provenances WHERE opportunity_id='o1'")).scalar_one(), 0)
        # A second verification never exposes or duplicates the payload.
        self.assertTrue(verify_archive(self.connection, "o1"))


if __name__ == "__main__":
    unittest.main()
