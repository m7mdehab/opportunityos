"""Acceptance report semantics without database credentials."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import migration_acceptance as acceptance
from scripts import production_migration_cutover as cutover


class AcceptanceTests(unittest.TestCase):
    def test_fingerprint_excludes_password_and_username(self):
        one = {"host": "DB.example.invalid", "port": "5432", "database": "main",
               "user": "private_user", "password": "secret_one"}
        two = {**one, "user": "other", "password": "secret_two"}
        self.assertEqual(acceptance.fingerprint(one), acceptance.fingerprint(two))
        self.assertNotIn("secret", acceptance.fingerprint(one))
        self.assertNotEqual(acceptance.fingerprint(one), acceptance.fingerprint({**one, "database": "other"}))

    def test_all_gate_ids_have_explicit_needs_and_no_invented_pass(self):
        self.assertEqual(set(acceptance.GATE_NEEDS), {f"A-{i}" for i in range(18)})
        stages = {name: "PASS" for name in cutover.STAGES}
        gates = acceptance._gate_statuses(stages)
        self.assertTrue(all(gate["status"] != "PASS" for gate in gates.values()))
        self.assertIn("elapsed_soak_time", gates["A-14"]["needs"])
        self.assertIn("artifact_store", gates["A-11"]["needs"])

    def test_dry_run_remains_rejected_and_reports_no_destructive_stage(self):
        settings = {"host": "localhost", "port": "5432", "database": "fixture"}
        with tempfile.TemporaryDirectory() as directory:
            with (mock.patch.object(acceptance.db, "config", return_value=settings),
                  mock.patch.object(acceptance.db, "target_config", return_value={**settings, "database": "target"}),
                  mock.patch.object(acceptance.preflight, "evaluate", return_value={
                      "status": "PARTIAL", "ready": False, "checks": {"target_empty": "BLOCKED"}}),
                  mock.patch.object(acceptance.cutover, "run") as destructive):
                result = acceptance.run(directory, dry_run=True, connection_mode="direct")
            destructive.assert_not_called()
            self.assertEqual(result["decision"], "REJECT")
            self.assertEqual(result["stages"]["restore_import"], "NOT_RUN")
            self.assertEqual(result["gates"]["A-12"]["status"], "NOT_RUN")
            self.assertEqual(json.loads((Path(directory) / "acceptance.json").read_text())["decision"], "REJECT")

    def test_blocked_or_failed_stage_rejects_and_redacts(self):
        raw = cutover.report_template()
        cutover.record(raw, "preflight", "BLOCKED", {"reason": "configuration_failed"})
        raw = cutover.finish(raw)
        with tempfile.TemporaryDirectory() as directory:
            report = acceptance.assemble(raw, Path(directory))
        self.assertEqual(report["decision"], "REJECT")
        self.assertEqual(report["gates"]["A-9"]["status"], "NOT_RUN")
        self.assertNotIn("OPOS_SOURCE_DB_URL", json.dumps(report))

    def test_reused_output_directory_cannot_replay_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "source-baseline.json").write_text('{"private":"marker"}', encoding="utf-8")
            report = acceptance.run(directory, connection_mode="direct")
        self.assertEqual(report["stages"]["preflight"], "BLOCKED")
        self.assertIsNone(report["alembic_revision"]["source"])
        self.assertNotIn("marker", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
