"""Synthetic state-report tests for the one-command proof runner."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import live_portability_proof as proof


class ProofRunnerTests(unittest.TestCase):
    def test_restore_confirmation_is_required_and_other_stages_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            report = proof.run(directory, confirmed=False)
        self.assertEqual(report["stages"]["restore"], "FAIL")
        self.assertEqual(report["stages"]["backup_creation"], "NOT_RUN")
        self.assertEqual(report["status"], "FAIL")

    def test_partial_is_never_pass_even_with_ci_exit_override(self):
        partial = {"format": 1, "stages": {name: "PASS" for name in proof.STAGES},
                   "details": {}, "status": "PARTIAL", "summary": "synthetic partial"}
        partial["stages"]["structural_parity"] = "PARTIAL"
        with patch.object(proof, "run", return_value=partial):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(proof.main(["--output-dir", "unused", "--confirm-target-restore"]), 3)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "PARTIAL")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(proof.main(["--output-dir", "unused", "--confirm-target-restore",
                                             "--allow-partial"]), 0)

    def test_missing_configuration_fails_without_echoing_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = proof.main(["--output-dir", directory, "--confirm-target-restore"])
        self.assertEqual(code, 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["stages"]["backup_creation"], "FAIL")
        self.assertEqual(report["stages"]["restore"], "NOT_RUN")
        self.assertEqual(report["details"]["backup_creation"]["reason"], "configuration_or_preflight_failed")


if __name__ == "__main__":
    unittest.main()
