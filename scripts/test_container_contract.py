"""Unit tests for OpportunityOS OCI Container Role Runtime and Entrypoint Contract.

Covers W4 requirements:
- Explicit role dispatch (api, worker, scheduler, migrate, readiness, liveness)
- Invalid role fail-closed behavior
- Cloud-compatible host binding (0.0.0.0) and port configurability
- Strict role separation (API does not start scheduler/worker, worker rejects --schedule)
- Lightweight readiness/liveness probes (no corpus traversal, no feed rebuild)
- Secret isolation (no secrets baked into Dockerfile/entrypoint, strict .dockerignore)
- Non-root user in Dockerfile
- Database URL bridging and fail-closed validation
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from scripts.container_entrypoint import (
    ConfigurationError,
    InvalidRoleError,
    RoleSeparationError,
    build_role_command,
    main,
    resolve_environment,
    run_liveness,
    run_readiness,
    run_scheduler,
)

ROOT = Path(__file__).resolve().parents[1]


class ContainerRoleDispatchTest(unittest.TestCase):
    """Test deterministic role command construction and parameters."""

    def setUp(self) -> None:
        self.base_env = {
            "OPPORTUNITYOS_DB_URL": "postgresql+psycopg2://user:pass@cloud-pg:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "test-password",
            "OPPORTUNITYOS_SESSION_SECRET": "test-session-secret",
        }

    def test_role_dispatch_api_defaults(self) -> None:
        cmd = build_role_command("api", environ=self.base_env)
        self.assertEqual(cmd[0], sys.executable)
        self.assertIn("-m", cmd)
        self.assertIn("uvicorn", cmd)
        self.assertIn("api.app:app", cmd)
        self.assertIn("--host", cmd)
        host_idx = cmd.index("--host")
        self.assertEqual(cmd[host_idx + 1], "0.0.0.0")
        self.assertIn("--port", cmd)
        port_idx = cmd.index("--port")
        self.assertEqual(cmd[port_idx + 1], "8000")

    def test_role_dispatch_api_custom_host_and_port(self) -> None:
        custom_env = dict(self.base_env)
        custom_env["HOST"] = "0.0.0.0"
        custom_env["PORT"] = "9090"
        cmd = build_role_command("api", environ=custom_env)
        self.assertEqual(cmd[cmd.index("--host") + 1], "0.0.0.0")
        self.assertEqual(cmd[cmd.index("--port") + 1], "9090")

    def test_role_dispatch_api_respects_opportunityos_port_var(self) -> None:
        custom_env = dict(self.base_env)
        custom_env["OPPORTUNITYOS_API_PORT"] = "10000"
        cmd = build_role_command("api", environ=custom_env)
        self.assertEqual(cmd[cmd.index("--port") + 1], "10000")

    def test_role_dispatch_worker(self) -> None:
        cmd = build_role_command("worker", extra_args=["--once"], environ=self.base_env)
        self.assertEqual(cmd[0], sys.executable)
        self.assertIn("-m", cmd)
        self.assertIn("worker", cmd)
        self.assertIn("--once", cmd)

    def test_role_dispatch_scheduler(self) -> None:
        cmd = build_role_command("scheduler", environ=self.base_env)
        self.assertEqual(cmd[0], sys.executable)
        self.assertIn("scripts", cmd[1])

    def test_role_dispatch_migrate(self) -> None:
        cmd = build_role_command("migrate", environ=self.base_env)
        self.assertEqual(cmd[0], sys.executable)
        self.assertIn("-m", cmd)
        self.assertIn("alembic", cmd)
        self.assertIn("upgrade", cmd)
        self.assertIn("head", cmd)

    def test_invalid_role_fails_closed(self) -> None:
        with self.assertRaises(InvalidRoleError):
            build_role_command("definitely-not-a-role", environ=self.base_env)

        with self.assertRaises(InvalidRoleError):
            build_role_command("root", environ=self.base_env)


class RoleSeparationContractTest(unittest.TestCase):
    """Test that roles do not silently start other roles."""

    def setUp(self) -> None:
        self.base_env = {
            "OPPORTUNITYOS_DB_URL": "postgresql+psycopg2://user:pass@cloud-pg:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "test-password",
            "OPPORTUNITYOS_SESSION_SECRET": "test-session-secret",
        }

    def test_api_role_does_not_invoke_scheduler_or_migrations(self) -> None:
        cmd = build_role_command("api", environ=self.base_env)
        cmd_str = " ".join(cmd)
        self.assertNotIn("alembic", cmd_str)
        self.assertNotIn("scheduler", cmd_str)
        self.assertNotIn("--schedule", cmd_str)

    def test_worker_role_rejects_schedule_flag(self) -> None:
        with self.assertRaises(RoleSeparationError):
            build_role_command("worker", extra_args=["--schedule"], environ=self.base_env)

    def test_scheduler_role_does_not_invoke_worker_or_api(self) -> None:
        cmd = build_role_command("scheduler", environ=self.base_env)
        cmd_str = " ".join(cmd)
        self.assertNotIn("uvicorn", cmd_str)
        self.assertNotIn("api.app", cmd_str)

    def test_migrate_role_does_not_invoke_api_or_worker(self) -> None:
        cmd = build_role_command("migrate", environ=self.base_env)
        cmd_str = " ".join(cmd)
        self.assertNotIn("uvicorn", cmd_str)
        self.assertNotIn("api.app", cmd_str)
        self.assertNotIn("worker", cmd_str)


class EnvironmentAndConfigBridgeTest(unittest.TestCase):
    """Test fail-closed configuration and CLOUD_DATABASE_URL aliasing."""

    def test_cloud_database_url_aliases_to_opportunityos_db_url(self) -> None:
        env = {
            "CLOUD_DATABASE_URL": "postgresql+psycopg2://user:pass@cloud-pg:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "password",
            "OPPORTUNITYOS_SESSION_SECRET": "secret",
        }
        resolved = resolve_environment("api", env)
        self.assertEqual(resolved["OPPORTUNITYOS_DB_URL"], env["CLOUD_DATABASE_URL"])

    def test_conflicting_database_urls_fail_closed(self) -> None:
        env = {
            "CLOUD_DATABASE_URL": "postgresql+psycopg2://user:pass@db1:5432/opportunityos",
            "OPPORTUNITYOS_DB_URL": "postgresql+psycopg2://user:pass@db2:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "password",
            "OPPORTUNITYOS_SESSION_SECRET": "secret",
        }
        with self.assertRaises(ConfigurationError) as ctx:
            resolve_environment("api", env)
        self.assertIn("Conflicting", str(ctx.exception))

    def test_missing_database_url_fails_closed(self) -> None:
        env = {
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "password",
            "OPPORTUNITYOS_SESSION_SECRET": "secret",
        }
        for role in ("api", "worker", "scheduler", "migrate", "readiness"):
            with self.assertRaises(ConfigurationError):
                resolve_environment(role, env)

    def test_missing_api_credentials_fail_closed(self) -> None:
        env = {
            "OPPORTUNITYOS_DB_URL": "postgresql+psycopg2://user:pass@cloud-pg:5432/opportunityos"
        }
        with self.assertRaises(ConfigurationError) as ctx:
            resolve_environment("api", env)
        self.assertIn("OPPORTUNITYOS_FOUNDER_PASSWORD", str(ctx.exception))
        self.assertIn("OPPORTUNITYOS_SESSION_SECRET", str(ctx.exception))

    def test_malformed_database_scheme_fails_closed(self) -> None:
        env = {
            "OPPORTUNITYOS_DB_URL": "sqlite:///local.db",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "password",
            "OPPORTUNITYOS_SESSION_SECRET": "secret",
        }
        with self.assertRaises(ConfigurationError) as ctx:
            resolve_environment("api", env)
        self.assertIn("scheme must be one of", str(ctx.exception))

    def test_placeholder_values_fail_closed(self) -> None:
        env = {
            "OPPORTUNITYOS_DB_URL": "postgresql+psycopg2://user:pass@cloud-pg:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "REPLACE_ME",
            "OPPORTUNITYOS_SESSION_SECRET": "secret",
        }
        with self.assertRaises(ConfigurationError) as ctx:
            resolve_environment("api", env)
        self.assertIn("placeholder", str(ctx.exception))

    def test_production_loopback_rejection(self) -> None:
        env = {
            "OPPORTUNITYOS_ENVIRONMENT": "production",
            "CLOUD_DATABASE_URL": "postgresql+psycopg2://user:pass@localhost:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "password",
            "OPPORTUNITYOS_SESSION_SECRET": "secret",
        }
        with self.assertRaises(ConfigurationError) as ctx:
            resolve_environment("api", env)
        self.assertIn("loopback host rejected", str(ctx.exception))

    def test_local_dev_allows_loopback(self) -> None:
        env = {
            "CLOUD_DATABASE_URL": "postgresql+psycopg2://user:pass@127.0.0.1:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "password",
            "OPPORTUNITYOS_SESSION_SECRET": "secret",
        }
        resolved = resolve_environment("api", env)
        self.assertEqual(resolved["OPPORTUNITYOS_DB_URL"], env["CLOUD_DATABASE_URL"])


class HealthAndReadinessContractTest(unittest.TestCase):
    """Test that readiness/liveness probes do not scan corpus or rebuild feed."""

    def test_readiness_probe_executes_lightweight_queries_only(self) -> None:
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)

        code = run_readiness(session_factory=mock_factory)
        self.assertEqual(code, 0)
        self.assertTrue(mock_session.execute.called)

        # Inspect all executed query statements
        calls = [str(c[0][0]) for c in mock_session.execute.call_args_list]
        for query in calls:
            self.assertTrue(
                "SELECT 1" in query or "alembic_version" in query,
                f"Unexpected query in lightweight readiness probe: {query}",
            )
            # Guarantee no opportunity scanning or feed rebuild
            self.assertNotIn("opportunities", query.lower())
            self.assertNotIn("feed_projection", query.lower())

    def test_readiness_probe_fails_on_db_error(self) -> None:
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("database unreachable")
        mock_factory = MagicMock(return_value=mock_session)

        code = run_readiness(session_factory=mock_factory)
        self.assertEqual(code, 1)

    def test_liveness_probe_succeeds(self) -> None:
        self.assertEqual(run_liveness(), 0)


class SecretIsolationAndPackagingTest(unittest.TestCase):
    """Verify no credentials baked into files and Dockerfile/dockerignore invariants."""

    def test_dockerignore_excludes_secrets_and_caches(self) -> None:
        dockerignore_path = ROOT / ".dockerignore"
        self.assertTrue(dockerignore_path.exists(), ".dockerignore must exist")
        content = dockerignore_path.read_text(encoding="utf-8")

        required_patterns = [
            ".env*",
            "private",
            ".git",
            "*.db",
            "*.dump",
            "*.sql",
            "__pycache__",
            ".venv",
        ]
        for pattern in required_patterns:
            self.assertIn(
                pattern,
                content,
                f".dockerignore must contain '{pattern}' to prevent secret/state leakage",
            )

    def test_dockerfile_runs_as_non_root(self) -> None:
        dockerfile_path = ROOT / "Dockerfile"
        self.assertTrue(dockerfile_path.exists(), "Dockerfile must exist")
        content = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("USER appuser", content, "Dockerfile must set non-root USER appuser")
        self.assertIn("ENTRYPOINT", content, "Dockerfile must define ENTRYPOINT")
        self.assertIn("scripts/container_entrypoint.py", content)

    def test_no_secrets_baked_into_entrypoint_or_dockerfile(self) -> None:
        for file_name in ("Dockerfile", "scripts/container_entrypoint.py", ".dockerignore"):
            path = ROOT / file_name
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("postgres://", text)
            self.assertNotIn("postgresql://", text)
            self.assertNotIn("password123", text)
            self.assertNotIn("secret_key", text)


class GracefulInvocationTest(unittest.TestCase):
    """Test graceful shutdown signal handling."""

    def test_scheduler_graceful_stop_event(self) -> None:
        stop_event = threading.Event()
        mock_factory = MagicMock()
        mock_scheduler = MagicMock()

        with unittest.mock.patch("worker.scheduler.PollScheduler", return_value=mock_scheduler):
            # Set stop_event before run_forever to simulate stop immediately
            stop_event.set()
            run_scheduler(session_factory=mock_factory, stop_event=stop_event)
            self.assertTrue(mock_scheduler.run_forever.called)

    def test_cli_dispatch_via_subprocess(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "container_entrypoint.py"), "definitely-not-a-role"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Invalid role", proc.stderr)

    def test_cli_empty_role_fails(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "container_entrypoint.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("No role specified", proc.stderr)


if __name__ == "__main__":
    unittest.main()
