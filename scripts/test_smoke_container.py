"""Unit tests for scripts/smoke_container.py.

Verifies the OCI smoke automation logic:
- runtime engine detection;
- per-command bounded timeout and container tracking/cleanup;
- build, non-root, liveness, readiness, role separation, dry-run command construction;
- live DB migration, post-migration readiness, detached API SIGTERM shutdown;
- worker/scheduler cloud dependencies BLOCKED handling;
- structured evidence markers and zero false-green invariants.
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

    def test_exec_timeout_handling(self) -> None:
        mock_runner = MagicMock(side_effect=subprocess.TimeoutExpired(cmd=["test"], timeout=1.0))
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)
        res = runner._exec(["test"], timeout=1.0, container_name="test-cont")
        self.assertEqual(res.returncode, -1)
        self.assertIn("timed out after 1.0s", res.stderr)

    def test_smoke_build_image_success_and_failure(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        res = runner.smoke_build_image()
        self.assertTrue(res.passed)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.marker, "IMAGE_BUILD_PASS")

        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="build error")
        res = runner.smoke_build_image()
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAIL")
        self.assertIsNone(res.marker)

    def test_smoke_non_root_user_verifies_uid_1000(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        # UID 1000 (appuser) -> pass
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="1000\n", stderr="")
        res = runner.smoke_non_root_user()
        self.assertTrue(res.passed)
        self.assertEqual(res.marker, "NON_ROOT_USER_PASS")

        # UID 0 (root) -> fail
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="0\n", stderr="")
        res = runner.smoke_non_root_user()
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAIL")

    def test_smoke_liveness_probe(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="liveness probe: ok\n", stderr=""
        )
        res = runner.smoke_liveness_probe()
        self.assertTrue(res.passed)
        self.assertEqual(res.marker, "LIVENESS_PROBE_PASS")

    def test_smoke_readiness_fails_without_db(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="readiness probe: failed (no db)"
        )
        res = runner.smoke_readiness_fails_without_db()
        self.assertTrue(res.passed)
        self.assertEqual(res.marker, "READINESS_FAIL_CLOSED_PASS")

    def test_smoke_role_separation_worker(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Role separation violation: '--schedule' cannot be used"
        )
        res = runner.smoke_role_separation_worker()
        self.assertTrue(res.passed)
        self.assertEqual(res.marker, "ROLE_SEPARATION_PASS")

    def test_smoke_invalid_role_fails_closed(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error: Invalid role 'definitely-not-a-role'."
        )
        res = runner.smoke_invalid_role_fails_closed()
        self.assertTrue(res.passed)
        self.assertEqual(res.marker, "INVALID_ROLE_FAIL_CLOSED_PASS")

    def test_smoke_command_construction_contracts(self) -> None:
        mock_runner = MagicMock()
        runner = OCIContainerSmokeRunner(engine="mock-docker", runner_fn=mock_runner)

        mock_runner.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='DRY_RUN_COMMAND: ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "9090"]\n',
            stderr="",
        )
        res = runner.smoke_command_construction_contracts()
        # With mock returning api stdout for all 4, worker will fail missing 'worker', testing failure detection
        self.assertFalse(res.passed)

        # Now mock exact outputs for each role
        def side_effect(cmd, **kwargs):
            if "api" in cmd:
                out = 'DRY_RUN_COMMAND: ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "9090"]'
            elif "worker" in cmd:
                out = 'DRY_RUN_COMMAND: ["python", "-m", "worker"]'
            elif "scheduler" in cmd:
                out = 'DRY_RUN_COMMAND: ["python", "scripts/container_entrypoint.py", "_scheduler_loop"]'
            elif "migrate" in cmd:
                out = 'DRY_RUN_COMMAND: ["python", "-m", "alembic", "upgrade", "head"]'
            else:
                out = ""
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=out, stderr="")

        runner.run_cmd = side_effect
        res_ok = runner.smoke_command_construction_contracts()
        self.assertTrue(res_ok.passed)
        self.assertEqual(res_ok.marker, "COMMAND_CONSTRUCTION_PASS")

    def test_smoke_migrations_execute_db(self) -> None:
        # Without DB -> BLOCKED
        runner_no_db = OCIContainerSmokeRunner(engine="mock-docker", db_url=None)
        res_no_db = runner_no_db.smoke_migrations_execute_db()
        self.assertEqual(res_no_db.status, "BLOCKED")

        # With DB -> PASS
        mock_runner = MagicMock()
        runner_with_db = OCIContainerSmokeRunner(
            engine="mock-docker",
            db_url="postgresql+psycopg2://user:pass@db:5432/test",
            runner_fn=mock_runner,
        )
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="Running upgrade -> head", stderr="")
        res_with_db = runner_with_db.smoke_migrations_execute_db()
        self.assertTrue(res_with_db.passed)
        self.assertEqual(res_with_db.status, "PASS")
        self.assertEqual(res_with_db.marker, "MIGRATION_EXECUTION_PASS")

    def test_smoke_readiness_post_migration(self) -> None:
        # Without DB -> BLOCKED
        runner_no_db = OCIContainerSmokeRunner(engine="mock-docker", db_url=None)
        res_no_db = runner_no_db.smoke_readiness_post_migration()
        self.assertEqual(res_no_db.status, "BLOCKED")

        # With DB -> PASS
        mock_runner = MagicMock()
        runner_with_db = OCIContainerSmokeRunner(
            engine="mock-docker",
            db_url="postgresql+psycopg2://user:pass@db:5432/test",
            runner_fn=mock_runner,
        )
        mock_runner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="readiness probe: ok\n", stderr="")
        res_with_db = runner_with_db.smoke_readiness_post_migration()
        self.assertTrue(res_with_db.passed)
        self.assertEqual(res_with_db.status, "PASS")
        self.assertEqual(res_with_db.marker, "READINESS_POST_MIGRATION_PASS")

    def test_smoke_detached_api_startup_and_sigterm(self) -> None:
        # Without DB -> BLOCKED
        runner_no_db = OCIContainerSmokeRunner(engine="mock-docker", db_url=None)
        res_no_db = runner_no_db.smoke_detached_api_startup_and_sigterm()
        self.assertEqual(res_no_db.status, "BLOCKED")

        # With DB -> runs detached, polls logs, stops with SIGTERM
        mock_runner = MagicMock()
        runner_with_db = OCIContainerSmokeRunner(
            engine="mock-docker",
            db_url="postgresql+psycopg2://user:pass@db:5432/test",
            runner_fn=mock_runner,
        )
        def side_effect(cmd, **kwargs):
            if "logs" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Uvicorn running on http://0.0.0.0:9099", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mock_runner.side_effect = side_effect
        res_with_db = runner_with_db.smoke_detached_api_startup_and_sigterm()
        self.assertTrue(res_with_db.passed)
        self.assertEqual(res_with_db.status, "PASS")
        self.assertEqual(res_with_db.marker, "API_GRACEFUL_SHUTDOWN_PASS")

    def test_smoke_worker_scheduler_cloud_dependencies_is_explicitly_blocked(self) -> None:
        runner = OCIContainerSmokeRunner(engine="mock-docker")
        res = runner.smoke_worker_scheduler_cloud_dependencies()
        self.assertEqual(res.status, "BLOCKED")
        self.assertIn("ROLE_LIVE_PROOF_BLOCKED", res.message)

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
