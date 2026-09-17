"""Unit tests for scripts/smoke_container.py (Item A).

Verifies the OCI smoke automation logic:
- runtime engine detection;
- build, non-root, invalid-role, probe, and role separation step handlers;
- argument parsing and exit code contracts.
"""
from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from scripts.smoke_container import (
    OCIContainerSmokeRunner,
    find_oci_runtime,
    main,
)


class SmokeContainerUnitTest(unittest.TestCase):

    def test_find_oci_runtime_returns_path(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"):
            engine = find_oci_runtime("auto")
            self.assertEqual(engine, "/usr/bin/docker")

    def test_find_oci_runtime_returns_none_when_missing(self) -> None:
        with patch("shutil.which", return_value=None):
            engine = find_oci_runtime("auto")
            self.assertIsNone(engine)

    def test_smoke_build_image_success_and_failure(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        # Success case
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        res = runner.smoke_build_image()
        self.assertTrue(res.passed)

        # Failure case
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="build error")
        res = runner.smoke_build_image()
        self.assertFalse(res.passed)
        self.assertIn("build error", res.message)

    def test_smoke_non_root_user_verifies_uid_1000(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        # UID 1000 (appuser) -> pass
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="1000\n", stderr="")
        res = runner.smoke_non_root_user()
        self.assertTrue(res.passed)

        # UID 0 (root) -> fail
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="0\n", stderr="")
        res = runner.smoke_non_root_user()
        self.assertFalse(res.passed)

    def test_smoke_invalid_role_fails_closed(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error: Invalid role 'definitely-not-a-role'."
        )
        res = runner.smoke_invalid_role_fails_closed()
        self.assertTrue(res.passed)

    def test_smoke_liveness_probe(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="liveness probe: ok\n", stderr=""
        )
        res = runner.smoke_liveness_probe()
        self.assertTrue(res.passed)

    def test_smoke_worker_role_separation(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Role separation violation: '--schedule' cannot be used"
        )
        res = runner.smoke_role_separation_worker()
        self.assertTrue(res.passed)

    def test_run_all_smoke_tests_stops_if_build_fails(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        # Build fails
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")
        results = runner.run_all_smoke_tests(skip_build=False)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].passed)

    def test_main_exits_zero_when_no_engine_and_not_required(self) -> None:
        with patch("scripts.smoke_container.find_oci_runtime", return_value=None):
            code = main([])
            self.assertEqual(code, 0)

    def test_main_exits_two_when_no_engine_and_required(self) -> None:
        with patch("scripts.smoke_container.find_oci_runtime", return_value=None):
            code = main(["--require-engine"])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
