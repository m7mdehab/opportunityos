"""No live database is needed for these state and redaction checks."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from unittest import TestCase, mock

from scripts import production_db_preflight as preflight
from scripts import production_migration_cutover as cutover
from scripts import db_migration_restore as db


class FakeCursor:
    def __init__(self, *, nonempty=False):
        self.calls = []
        self.nonempty = nonempty
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = sql
        self.calls.append(sql)

    def fetchone(self):
        sql = self.sql
        if "server_version_num" in sql:
            return (160000, "fixture_db", "fixture", 42)
        if "pg_stat_ssl" in sql:
            return (True,)
        if "has_database_privilege" in sql:
            return (True, True, True)
        if "pg_get_userbyid" in sql:
            return (True,)
        if "count(*) FROM pg_class" in sql:
            return (1 if self.nonempty else 0,)
        if "to_regclass" in sql:
            return (False,)
        if "current_schemas" in sql:
            return (["public"], "UTC", "on", "on", "off")
        if "pg_database_size" in sql:
            return (1024,)
        raise AssertionError("unhandled query")

    def fetchall(self):
        if "pg_extension" in self.sql:
            return [("plpgsql",)]
        if "pg_settings" in self.sql:
            return [("lock_timeout", "0", "ms"), ("statement_timeout", "0", "ms")]
        raise AssertionError("unhandled query")

    def close(self):
        pass


class FakeConnection:
    def __init__(self, *, nonempty=False):
        self.fake_cursor = FakeCursor(nonempty=nonempty)
        self.rollbacks = 0

    def cursor(self):
        return self.fake_cursor

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class PreflightTests(TestCase):
    settings = {"host": "db.example.invalid", "sslmode": "verify-full"}

    def test_read_only_queries_and_ready_state(self):
        connection = FakeConnection()
        result = preflight.evaluate(self.settings, connection_mode="direct",
                                    connection_factory=lambda _: connection)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["ready"])
        self.assertEqual(connection.rollbacks, 1)
        for sql in connection.fake_cursor.calls:
            self.assertFalse(any(word in sql.upper() for word in
                             ("INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE", "ALTER TABLE", "DROP ")))
        self.assertIn("READ ONLY", connection.fake_cursor.calls[0])

    def test_nonempty_pooler_and_tls_fail_closed(self):
        nonempty = preflight.evaluate(self.settings, connection_mode="direct",
                                      connection_factory=lambda _: FakeConnection(nonempty=True))
        self.assertEqual(nonempty["checks"]["target_empty"], "BLOCKED")
        self.assertFalse(nonempty["ready"])
        pooler = preflight.evaluate(self.settings, connection_mode="pooler",
                                    connection_factory=lambda _: FakeConnection())
        self.assertEqual(pooler["checks"]["connection_mode"], "BLOCKED")
        plain = preflight.evaluate({**self.settings, "sslmode": "prefer"}, connection_mode="direct",
                                   connection_factory=lambda _: FakeConnection())
        self.assertEqual(plain["checks"]["tls"], "BLOCKED")

    def test_local_override_cannot_apply_to_remote(self):
        result = preflight.evaluate(self.settings, connection_mode="direct", allow_insecure_local=True,
                                    connection_factory=lambda _: FakeConnection())
        self.assertEqual(result["checks"]["tls"], "BLOCKED")

    def test_driver_error_is_redacted(self):
        marker = "private_fixture_password"
        with mock.patch.object(db, "target_config", side_effect=ValueError(marker)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(preflight.main(["--connection-mode", "direct"]), 2)
        self.assertNotIn(marker, output.getvalue())


class CutoverTests(TestCase):
    def test_unsupported_artifact_backend_blocks_before_backup_or_restore(self):
        with (mock.patch.object(db, "config", return_value={"host": "source"}),
              mock.patch.object(db, "target_config", return_value={"host": "target"}),
              mock.patch.object(preflight, "evaluate", return_value={"ready": True, "status": "PASS"}),
              mock.patch.object(db, "backup") as backup):
            report = cutover.run("unused", connection_mode="direct", artifact_backend="object_store",
                                 confirm_restore=True, source_writes_paused=True, target_writes_disabled=True)
        self.assertEqual(report["stages"]["artifact_body"], "BLOCKED")
        self.assertEqual(report["stages"]["backup"], "NOT_RUN")
        backup.assert_not_called()

    def test_missing_configuration_and_confirmation_block(self):
        with mock.patch.object(db, "config", side_effect=ValueError("private_fixture_password")):
            report = cutover.run("unused", connection_mode="direct")
        self.assertEqual(report["stages"]["preflight"], "BLOCKED")
        self.assertNotIn("private_fixture_password", json.dumps(report))
        with (mock.patch.object(db, "config", return_value={"host": "source"}),
              mock.patch.object(db, "target_config", return_value={"host": "target"}),
              mock.patch.object(preflight, "evaluate", return_value={"ready": True, "status": "PASS"})):
            report = cutover.run("unused", connection_mode="direct")
        self.assertEqual(report["stages"]["source_baseline"], "BLOCKED")
        self.assertEqual(report["stages"]["restore_import"], "NOT_RUN")

    def test_rollback_state_machine_never_claims_cutover(self):
        blocked = {"status": "BLOCKED"}
        self.assertEqual(cutover.rollback_decision(blocked)["decision"], "KEEP_SOURCE_AUTHORITATIVE")
        self.assertEqual(cutover.rollback_decision(blocked, traffic_cutover_occurred=True)["decision"],
                         "REVERSE_TRAFFIC_TO_SOURCE")
        partial = {"status": "PARTIAL"}
        self.assertEqual(cutover.rollback_decision(partial)["decision"], "AWAIT_OWNER_CUTOVER")

    def test_final_status_keeps_partial_distinct(self):
        report = cutover.report_template()
        for name in cutover.STAGES:
            if name != "final_acceptance":
                cutover.record(report, name, "PASS")
        cutover.record(report, "artifact_body", "PARTIAL")
        self.assertEqual(cutover.finish(report)["status"], "PARTIAL")


if __name__ == "__main__":
    import unittest
    unittest.main()
