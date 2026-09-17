"""Synthetic-only contract tests for the W5 database harness."""

import io
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout, nullcontext
from unittest.mock import Mock, patch

from scripts import db_migration_restore as db


SOURCE_URL = ("postgresql+psycopg2://" + "source_user:source_secret" +
              "@source.example:5433/source_db?sslmode=require")
TARGET_URL = ("postgresql+psycopg2://" + "target_user:target_secret" +
              "@target.example:5434/target_db?sslmode=require")


class Cursor:
    def __init__(self, tables=1, revision="0006_feed_projection"):
        self.sql = []
        self.tables = tables
        self.revision = revision
        self.value = None

    def execute(self, sql):
        self.sql.append(sql)
        if sql == "SELECT 1":
            self.value = (1,)
        elif "information_schema.tables" in sql:
            self.value = (self.tables,)
        elif "to_regclass" in sql:
            self.value = ("alembic_version" if self.revision else None,)
        elif "version_num" in sql:
            self.value = (self.revision,)

    def fetchone(self):
        return self.value

    def fetchall(self):
        return [self.value]

    def close(self):
        pass


class Connection:
    def __init__(self, tables=1, revision="0006_feed_projection"):
        self.query = Cursor(tables, revision)
        self.closed = False

    def cursor(self):
        return self.query

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.env = {db.SOURCE: SOURCE_URL, db.TARGET: TARGET_URL}

    def test_source_target_configuration_is_separate(self):
        source = db.config("source", self.env)
        target = db.config("target", self.env)
        self.assertEqual((source["host"], source["database"]), ("source.example", "source_db"))
        self.assertEqual((target["host"], target["database"]), ("target.example", "target_db"))
        self.assertNotEqual(source["password"], target["password"])
        child = db.pg_environment(target, self.env)
        self.assertNotIn(db.SOURCE, child)
        self.assertNotIn(db.TARGET, child)
        self.assertEqual(child["PGPASSWORD"], "target_secret")
        self.assertEqual(db.target_config(self.env)["database"], "target_db")
        with self.assertRaises(db.HarnessError):
            db.target_config({db.SOURCE: SOURCE_URL, db.TARGET: SOURCE_URL})

    def test_missing_configuration_and_tool_fail_closed(self):
        with self.assertRaises(db.HarnessError):
            db.config("target", {})
        with self.assertRaises(db.HarnessError):
            db.config("source", {db.SOURCE: "sqlite:///local"})
        with patch.object(db.shutil, "which", return_value=None):
            with self.assertRaises(db.HarnessError):
                db.require_tool("pg_dump")

    def test_backup_command_is_deterministic_and_secret_free(self):
        commands = []

        def fake_run(argv, env):
            commands.append((argv, env))
            Path(argv[argv.index("--file") + 1]).write_bytes(b"PGDMP")

        with tempfile.TemporaryDirectory() as temp, \
             patch.object(db, "require_tool", return_value="pg_dump"), \
             patch.object(db, "run_command", side_effect=fake_run):
            destination = Path(temp) / "backup.dump"
            db.backup(db.config("source", self.env), destination)
            argv, env = commands[0]
            self.assertEqual(argv, ["pg_dump", "--format=custom", "--schema=public", "--no-owner",
                                    "--no-privileges", "--file", str(destination),
                                    "--dbname", "source_db"])
            self.assertNotIn("source_secret", " ".join(argv))
            self.assertNotIn(SOURCE_URL, " ".join(argv))
            self.assertEqual(env["PGHOST"], "source.example")
            self.assertEqual(env["PGPASSWORD"], "source_secret")
            with self.assertRaises(db.HarnessError):
                db.backup(db.config("source", self.env), destination)

    def test_restore_requires_flag_and_empty_target(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "backup.dump"
            archive.write_bytes(b"PGDMP")
            with patch.object(db, "run_command") as run:
                with self.assertRaises(db.HarnessError):
                    db.restore(db.config("target", self.env), archive)
                run.assert_not_called()
            with patch.object(db, "inspect", side_effect=db.HarnessError("target schema is not empty")), \
                 patch.object(db, "verify_backup"), \
                 patch.object(db, "run_command") as run:
                with self.assertRaises(db.HarnessError):
                    db.restore(db.config("target", self.env), archive, manifest="manifest.json", confirmed=True)
                run.assert_not_called()
            with patch.object(db, "inspect", return_value={"ready": True}), \
                 patch.object(db, "verify_backup"), \
                 patch.object(db, "require_tool", return_value="pg_restore"), \
                 patch.object(db, "restore_toc", return_value=nullcontext("toc.list")), \
                 patch.object(db, "run_command") as run:
                db.restore(db.config("target", self.env), archive, manifest="manifest.json", confirmed=True)
                argv, env = run.call_args.args
                self.assertEqual(argv[-3:], ["--dbname", "target_db", str(archive)])
                self.assertNotIn("--clean", argv)
                self.assertEqual(argv[argv.index("--use-list") + 1], "toc.list")
                self.assertNotIn("target_secret", " ".join(argv))
                self.assertEqual(env["PGPASSWORD"], "target_secret")

    def test_restore_toc_filters_only_default_public_schema_creation(self):
        listing = ("; archive header\n"
                   "1; 2615 2200 SCHEMA - public fixture\n"
                   "2; 1259 900 TABLE public opportunities fixture\n"
                   "3; 0 0 COMMENT - SCHEMA public fixture\n")
        filtered = db.filter_existing_public_schema_toc(listing)
        self.assertNotIn("SCHEMA - public", filtered)
        self.assertIn("TABLE public opportunities", filtered)
        self.assertIn("COMMENT - SCHEMA public", filtered)

    def test_backup_manifest_detects_corruption_before_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "source.dump"
            archive.write_bytes(b"PGDMP synthetic data")
            manifest = db.backup_manifest(
                archive, "0006_feed_projection", version="pg_dump (PostgreSQL) 17.0",
                commit="a" * 40, created_at="2026-09-17T00:00:00+00:00")
            manifest_path = db.write_backup_manifest(archive, manifest)
            self.assertEqual(db.verify_backup(archive, manifest_path)["sha256"], db.file_sha256(archive))
            archive.write_bytes(b"PGDMP altered data")
            with patch.object(db, "inspect") as inspect, patch.object(db, "run_command") as run:
                with self.assertRaisesRegex(db.HarnessError, "integrity mismatch"):
                    db.restore(db.config("target", self.env), archive,
                               manifest=manifest_path, confirmed=True)
                inspect.assert_not_called()
                run.assert_not_called()

    def test_migration_targets_only_supplied_target(self):
        target = db.config("target", self.env)
        with patch.object(db, "run_command") as run:
            db.migrate(target)
            argv, env = run.call_args.args
            self.assertEqual(argv[-4:], ["-c", "alembic.ini", "upgrade", "head"])
            self.assertEqual(env["OPPORTUNITYOS_DB_URL"], TARGET_URL)
            self.assertNotIn(db.SOURCE, env)
            self.assertNotIn(db.TARGET, env)
            self.assertNotIn("target_secret", " ".join(argv))

    def test_inspection_is_read_only(self):
        connection = Connection()
        with patch.object(db, "connect", return_value=connection):
            result = db.inspect(db.config("target", self.env))
        self.assertEqual(result["alembic_revision"], "0006_feed_projection")
        self.assertTrue(connection.closed)
        self.assertEqual(connection.query.sql[0], "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        self.assertTrue(all(sql.startswith(("SET TRANSACTION", "SELECT", "ROLLBACK"))
                            for sql in connection.query.sql))
        self.assertEqual(connection.query.sql[-1], "ROLLBACK")

    def test_baseline_handoff_is_explicit_when_missing(self):
        with patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(db.HarnessError, "baseline module unavailable"):
                db.baseline_handoff("compare", baseline="a.json", candidate="b.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(db.main(["parity", "--baseline", "a.json", "--candidate", "b.json"]), 3)
            self.assertIn('"status": "error"', stderr.getvalue())

    def test_parity_mismatch_has_distinct_exit_status(self):
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(db.subprocess, "run", return_value=Mock(returncode=1)) as run:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(db.main(["parity", "--baseline", "a.json", "--candidate", "b.json"]), 1)
            self.assertIn('"status": "mismatch"', stderr.getvalue())
            self.assertIs(run.call_args.kwargs["shell"], False)

    def test_live_parity_uses_two_connections_and_reports_mismatch(self):
        from scripts import migration_baseline as baseline
        first, second = Mock(), Mock()
        with patch.object(db, "connect", side_effect=[first, second]) as connect, \
             patch.object(baseline, "inspect", side_effect=[{"format": 2}, {"format": 2}]), \
             patch.object(baseline, "compare", return_value=["tables.opportunities: mismatch"]), \
             patch.object(baseline, "unsupported", return_value=[]):
            result = db.parity_live(db.config("source", self.env), db.target_config(self.env))
        self.assertEqual(result["differences"], ["tables.opportunities: mismatch"])
        self.assertEqual(connect.call_count, 2)
        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_live_parity_partial_is_not_pass(self):
        with patch.dict(os.environ, self.env), \
             patch.object(db, "parity_live", return_value={
                 "differences": [], "unsupported": ["tables.source_states"]}):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(db.main(["parity-live"]), 3)
        self.assertIn('"status": "partial"', output.getvalue())

    def test_subprocess_never_uses_shell_or_leaks_error(self):
        with patch.object(db.subprocess, "run", return_value=Mock(returncode=1)) as run:
            with self.assertRaises(db.HarnessError):
                db.run_command(["pg_dump", "--dbname", "source_db"], {"PGPASSWORD": "source_secret"})
            self.assertIs(run.call_args.kwargs["shell"], False)
            self.assertEqual(run.call_args.kwargs["stderr"], db.subprocess.PIPE)
            self.assertEqual(run.call_args.kwargs["stdout"], db.subprocess.DEVNULL)
        with patch.dict(os.environ, self.env):
            stderr = io.StringIO()
            with redirect_stderr(stderr), patch.object(db, "inspect", side_effect=RuntimeError(TARGET_URL)):
                self.assertEqual(db.main(["verify"]), 2)
            self.assertNotIn(TARGET_URL, stderr.getvalue())
            self.assertNotIn("target_secret", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
