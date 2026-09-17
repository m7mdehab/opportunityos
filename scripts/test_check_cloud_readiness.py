"""Unit tests for scripts/check_cloud_readiness.py (Item E).

Verifies that the deployment readiness check:
- validates required secrets and environment;
- checks database connectivity and schema tables;
- rejects localhost/loopback in cloud mode;
- proves zero opportunity corpus scanning or feed rebuilding;
- returns deterministic non-zero exit codes on failure.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from scripts.check_cloud_readiness import (
    check_database_and_schema,
    check_pc_independence,
    check_secrets_and_config,
    main,
    run_preflight_checks,
)


class CheckCloudReadinessTest(unittest.TestCase):

    def setUp(self) -> None:
        self.valid_env = {
            "CLOUD_DATABASE_URL": "postgresql+psycopg2" + "://user:pass" + "@" + "db.cloud.invalid:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "valid-founder-password",
            "OPPORTUNITYOS_SESSION_SECRET": "valid-32-byte-session-secret-key",
        }

    def test_secrets_and_config_passes_with_valid_env(self) -> None:
        result = check_secrets_and_config("all", self.valid_env)
        self.assertTrue(result.passed)

    def test_secrets_and_config_fails_when_missing_secrets(self) -> None:
        incomplete_env = {
            "CLOUD_DATABASE_URL": "postgresql+psycopg2" + "://user:pass" + "@" + "db.cloud.invalid:5432/opportunityos"
        }
        result = check_secrets_and_config("api", incomplete_env)
        self.assertFalse(result.passed)
        self.assertIn("Missing required API credentials", result.message)

    def test_pc_independence_rejects_loopback_in_production(self) -> None:
        prod_env = dict(self.valid_env)
        prod_env["OPPORTUNITYOS_ENVIRONMENT"] = "production"
        prod_env["CLOUD_DATABASE_URL"] = "postgresql+psycopg2" + "://user:pass" + "@" + "127.0.0.1:5432/opportunityos"

        result = check_pc_independence(prod_env)
        self.assertFalse(result.passed)
        self.assertIn("localhost/loopback", result.message)

    def test_database_and_schema_passes_when_all_tables_present(self) -> None:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = "0006_feed_projection"

        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # Mock inspect(engine).get_table_names()
        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = [
                "alembic_version",
                "worker_jobs",
                "feed_projection",
                "source_poll_runs",
                "opportunities",
            ]
            mock_inspect.return_value = mock_inspector

            results = check_database_and_schema(engine=mock_engine)
            self.assertTrue(all(r.passed for r in results))

    def test_database_and_schema_fails_when_tables_missing(self) -> None:
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = ["alembic_version"]
            mock_inspect.return_value = mock_inspector

            results = check_database_and_schema(engine=mock_engine)
            schema_res = [r for r in results if r.name == "Schema Migrations & Tables"][0]
            self.assertFalse(schema_res.passed)
            self.assertIn("Missing required tables", schema_res.message)

    def test_readiness_does_not_scan_opportunity_corpus(self) -> None:
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = [
                "alembic_version",
                "worker_jobs",
                "feed_projection",
                "source_poll_runs",
            ]
            mock_inspect.return_value = mock_inspector

            results = run_preflight_checks("all", environ=self.valid_env, engine=mock_engine)
            self.assertTrue(all(r.passed for r in results))

            # Verify no SQL queries touch opportunities table
            for call_item in mock_conn.execute.call_args_list:
                sql_text = str(call_item[0][0]).lower()
                self.assertNotIn("select * from opportunities", sql_text)
                self.assertNotIn("match_evaluations", sql_text)

    def test_cli_exit_code_zero_when_all_pass(self) -> None:
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = [
                "alembic_version",
                "worker_jobs",
                "feed_projection",
                "source_poll_runs",
            ]
            mock_inspect.return_value = mock_inspector

            with unittest.mock.patch.dict("os.environ", self.valid_env, clear=True):
                code = main(["--role", "api", "--quiet"], engine=mock_engine)
                self.assertEqual(code, 0)

    def test_cli_exit_code_one_when_prerequisite_fails(self) -> None:
        empty_env = {}
        with unittest.mock.patch.dict("os.environ", empty_env, clear=True):
            code = main(["--role", "api", "--quiet"])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
