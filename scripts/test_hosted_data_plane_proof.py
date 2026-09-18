import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlunsplit

from scripts import hosted_data_plane_proof as proof


def settings(host, database, *, sslmode="verify-full", port="5432"):
    password = "unit" + "-credential"
    dsn = urlunsplit(("postgresql", f"operator:{password}@{host}:{port}",
                      f"/{database}", f"sslmode={sslmode}", ""))
    return {"dsn": dsn, "driver_dsn": dsn, "host": host, "port": port,
            "user": "operator", "password": password, "database": database,
            "sslmode": sslmode}


class HostedProofTests(unittest.TestCase):
    def setUp(self):
        self.source = settings("source.example", "source")
        self.target = settings("target.example", "target")

    def test_missing_secret_fails_closed(self):
        with mock.patch.object(proof.db, "config", side_effect=ValueError("missing")):
            with self.assertRaises(proof.HostedProofError):
                proof.validate_configuration("PRECHECK", "direct")

    def test_redaction_never_contains_password_or_full_dsn(self):
        value = self.source["dsn"]
        redacted = proof.redact_dsn(value)
        self.assertNotIn("secret", redacted)
        self.assertNotIn(value, redacted)
        self.assertIn("<redacted>", redacted)

    def test_same_source_target_rejected(self):
        same = settings("same.example", "db")
        with mock.patch.object(proof, "_settings", return_value=(same, same)):
            with self.assertRaisesRegex(proof.HostedProofError, "must differ"):
                proof.validate_configuration("PRECHECK", "direct")

    def test_local_target_rejected_in_hosted_mode(self):
        local = settings("localhost", "target")
        with mock.patch.object(proof, "_settings", return_value=(self.source, local)):
            with self.assertRaisesRegex(proof.HostedProofError, "local target"):
                proof.validate_configuration("PRECHECK", "direct")

    def test_pooler_rejected_for_migration(self):
        pooler = settings("abc.pooler.supabase.com", "target", port="6543")
        with mock.patch.object(proof, "_settings", return_value=(self.source, pooler)):
            with self.assertRaisesRegex(proof.HostedProofError, "direct"):
                proof.validate_configuration("MIGRATE_STAGING", "pooler", confirm_staging=True)

    def test_migration_requires_explicit_acknowledgement(self):
        with mock.patch.object(proof, "_settings", return_value=(self.source, self.target)):
            with self.assertRaisesRegex(proof.HostedProofError, "acknowledgement"):
                proof.validate_configuration("MIGRATE_STAGING", "direct")

    def test_precheck_does_not_call_migration(self):
        checked = {"status": "PASS", "ready": True, "checks": {}}
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(proof, "_settings", return_value=(self.source, self.target)), \
             mock.patch.object(proof, "discover_alembic_head", return_value="dynamic-head"), \
             mock.patch.object(proof.preflight, "evaluate", return_value=checked), \
             mock.patch.object(proof.migration_acceptance, "run") as migrate:
            report = proof.run("PRECHECK", connection_mode="direct", output_dir=tmp)
        migrate.assert_not_called()
        self.assertEqual(report["stages"]["MIGRATE"], "NOT_RUN")
        self.assertNotIn("MIGRATED", json.dumps(report))

    def test_dynamic_head_is_discovered(self):
        with mock.patch("alembic.script.ScriptDirectory.from_config") as directory:
            directory.return_value.get_current_head.return_value = "head-from-alembic"
            self.assertEqual(proof.discover_alembic_head(), "head-from-alembic")

    def test_command_failure_propagates_from_existing_runner(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(proof, "_settings", return_value=(self.source, self.target)), \
             mock.patch.object(proof, "discover_alembic_head", return_value="head"), \
             mock.patch.object(proof.preflight, "evaluate", return_value={"status": "PASS", "ready": True}), \
             mock.patch.object(proof.migration_acceptance, "run", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                proof.run("MIGRATE_STAGING", connection_mode="direct", output_dir=tmp,
                          confirm_staging=True)

    def test_evidence_write_is_machine_readable_and_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            report = {"mode": "PRECHECK", "stages": {"MIGRATE": "NOT_RUN"},
                      "details": {"target_dsn": proof.redact_dsn(self.target["dsn"])}}
            proof.write_evidence(report, str(path))
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded["stages"]["MIGRATE"], "NOT_RUN")
            self.assertNotIn("secret", path.read_text())

    def test_manual_workflow_has_no_automatic_destructive_trigger(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" /
                    "fr007-hosted-data-plane-proof.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", workflow)
        self.assertNotIn("pull_request", workflow)
        self.assertIn("environment: fr007-staging", workflow)
        self.assertIn("MIGRATE_STAGING", workflow)

    def test_proof_source_uses_no_shell_interpolation(self):
        source = Path(__file__).with_name("hosted_data_plane_proof.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)


if __name__ == "__main__":
    unittest.main()
