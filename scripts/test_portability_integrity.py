"""Synthetic portability, artifact retrieval, and checksum tests."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
import hashlib

from scripts import artifact_integrity as ai
from scripts import db_migration_restore as db
from scripts import portability_bundle as pb


class Reader:
    def __init__(self, rows):
        self.rows = rows

    def inventory(self):
        return self.rows


class PortabilityTests(unittest.TestCase):
    def test_postgres_payload_reader_fetches_bytes_read_only(self):
        class Cursor:
            def __init__(self):
                self.sql = []
                self.rows = []
                self.done = False

            def execute(self, sql):
                self.sql.append(sql)
                self.done = False
                if "information_schema.columns" in sql:
                    self.rows = [("cache_key",), ("payload",)]
                elif "SELECT cache_key, payload" in sql:
                    self.rows = [("a" * 64, b"private synthetic body"), ("b" * 64, None)]

            def fetchall(self):
                return self.rows

            def fetchmany(self, size):
                if self.done:
                    return []
                self.done = True
                return self.rows

            def close(self):
                pass

        class Connection:
            def __init__(self):
                self.query = Cursor()
                self.closed = False

            def cursor(self):
                return self.query

            def close(self):
                self.closed = True

            def rollback(self):
                pass

        connection = Connection()
        with patch.object(db, "connect", return_value=connection):
            rows = ai.PostgresPayloadReader({}).inventory()
        self.assertEqual(rows[0]["sha256"], hashlib.sha256(b"private synthetic body").hexdigest())
        self.assertEqual(rows[1]["body_status"], "metadata_only")
        self.assertTrue(connection.closed)
        self.assertTrue(connection.query.sql[0].endswith("READ ONLY"))
        self.assertEqual(connection.query.sql[-1], "ROLLBACK")
        self.assertNotIn("private synthetic body", str(rows))

    def test_artifact_manifest_distinguishes_body_from_metadata(self):
        key1, key2 = "a" * 64, "b" * 64
        source = ai.manifest(Reader([
            {"cache_key": key1, "sha256": "c" * 64, "size_bytes": 10, "body_status": "retrievable"},
            {"cache_key": key2, "sha256": None, "size_bytes": None, "body_status": "metadata_only"},
        ]))
        self.assertEqual((source["referenced"], source["retrievable"], source["metadata_only"]), (2, 1, 1))
        self.assertEqual(ai.verify(source, Reader(source["artifacts"]))["metadata_only"], 1)
        self.assertEqual(ai.verify(source, Reader([]))["missing"], 2)
        wrong = [{"cache_key": key1, "sha256": "d" * 64, "size_bytes": 10,
                  "body_status": "retrievable"}]
        self.assertEqual(ai.verify(source, Reader(wrong))["checksum_mismatch"], 1)
        with self.assertRaises(db.HarnessError):
            ai.verify({**source, "artifacts": [source["artifacts"][0]] * 2}, Reader([]))

    def test_artifact_external_backend_is_explicitly_unsupported(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(ai.main(["manifest", "--role", "source", "--output", "unused.json",
                                      "--backend", "external"]), 3)
        self.assertIn("unsupported", stderr.getvalue())

    def test_bundle_round_trip_and_corruption_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup = root / "source.dump"
            backup.write_bytes(b"PGDMP synthetic")
            info = db.backup_manifest(backup, "0006_feed_projection",
                                      version="pg_dump (PostgreSQL) 17.0",
                                      commit="a" * 40,
                                      created_at="2026-09-17T00:00:00+00:00")
            manifest = db.write_backup_manifest(backup, info)
            artifacts = root / "artifacts.json"
            artifacts.write_text(json.dumps(ai.manifest(Reader([]))), encoding="utf-8")
            bundle_path = root / "bundle.json"
            created = pb.create(backup, manifest, artifacts, bundle_path)
            self.assertEqual(created["alembic_revision"], "0006_feed_projection")
            self.assertEqual(pb.verify(bundle_path)["application_commit"], "a" * 40)
            self.assertNotIn("synthetic_secret_value", json.dumps(created).lower())
            backup.write_bytes(b"PGDMP corrupted")
            with self.assertRaises(db.HarnessError):
                pb.verify(bundle_path)

    def test_bundle_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bundle.json"
            path.write_text(json.dumps({"format": 1, "config_contract": pb.CONFIG_CONTRACT,
                                        "files": {"postgres_backup": {"name": "../outside"},
                                                  "backup_manifest": {}, "artifact_manifest": {}}}),
                            encoding="utf-8")
            with self.assertRaises(db.HarnessError):
                pb.verify(path)


if __name__ == "__main__":
    unittest.main()
