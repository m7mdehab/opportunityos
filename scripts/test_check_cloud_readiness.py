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
    check_authentication,
    check_database_and_schema,
    check_pc_independence,
    check_queue_durability,
    check_secrets_and_config,
    check_single_role_autonomy,
    check_truth_pack,
    main,
    run_preflight_checks,
)


class CheckCloudReadinessTest(unittest.TestCase):

    def setUp(self) -> None:
        self.valid_env = {
            "CLOUD_DATABASE_URL": "postgresql+psycopg2" + "://user:pass" + "@" + "db.cloud.invalid:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "valid-founder-password",
            "OPPORTUNITYOS_SESSION_SECRET": "valid-32-byte-session-secret-key",
            "OPPORTUNITYOS_TRUTH_PACK_URI": "https://storage.supabase.co/truth/pack.yaml",
            "OPPORTUNITYOS_TRUTH_PACK_HASH": "a" * 64,
        }

    def _mock_inspector(self):
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = [
            "alembic_version",
            "worker_jobs",
            "feed_projection",
            "source_poll_runs",
            "opportunities",
        ]
        mock_inspector.get_columns.return_value = [
            {"name": col} for col in (
                "id", "job_type", "payload_json", "status", "lease_owner",
                "lease_expires_at", "retry_count", "max_retries", "run_after"
            )
        ]
        return mock_inspector

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

        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspect.return_value = self._mock_inspector()

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
            mock_inspect.return_value = self._mock_inspector()

            results = run_preflight_checks("all", environ=self.valid_env, engine=mock_engine)
            # Preflight must execute without failures
            self.assertFalse(any(r.status == "FAIL" for r in results))

            # Verify no SQL queries touch opportunities table
            for call_item in mock_conn.execute.call_args_list:
                sql_text = str(call_item[0][0]).lower()
                self.assertNotIn("select * from opportunities", sql_text)
                self.assertNotIn("match_evaluations", sql_text)

    def test_cli_exit_code_zero_when_role_passes(self) -> None:
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspect.return_value = self._mock_inspector()

            with unittest.mock.patch.dict("os.environ", self.valid_env, clear=True):
                # All autonomous roles (api, worker, scheduler, migrate, all) have zero launch blockers and pass
                for r in ("migrate", "worker", "scheduler", "api", "all"):
                    code = main(["--role", r, "--quiet"], engine=mock_engine)
                    self.assertEqual(code, 0, f"Role '{r}' expected exit code 0, got {code}")

    def test_cli_exit_code_two_when_role_has_unresolved_blockers(self) -> None:
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspect.return_value = self._mock_inspector()

            web_env = {
                "NEXT_PUBLIC_DATA_API_URL": "https://api.cloud.invalid",
                "NEXT_PUBLIC_DATA_ANON_KEY": "synthetic-public-key",
            }
            with unittest.mock.patch.dict("os.environ", web_env, clear=True):
                # Web role has unwired cloud dependencies and returns BLOCKED (exit 2)
                code = main(["--role", "web", "--quiet"], engine=mock_engine)
                self.assertEqual(code, 2)

    def test_cli_exit_code_two_when_worker_missing_truth_pack(self) -> None:
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        env_without_truth = {
            "CLOUD_DATABASE_URL": "postgresql+psycopg2" + "://user:pass" + "@" + "db.cloud.invalid:5432/opportunityos",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "valid-founder-password",
            "OPPORTUNITYOS_SESSION_SECRET": "valid-32-byte-session-secret-key",
        }
        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspect.return_value = self._mock_inspector()

            with unittest.mock.patch.dict("os.environ", env_without_truth, clear=True):
                # Worker and all without truth pack must return BLOCKED (exit code 2)
                code_worker = main(["--role", "worker", "--quiet"], engine=mock_engine)
                self.assertEqual(code_worker, 2, "worker without truth pack must exit 2 (BLOCKED)")

                code_all = main(["--role", "all", "--quiet"], engine=mock_engine)
                self.assertEqual(code_all, 2, "all without truth pack must exit 2 (BLOCKED)")

    def test_cli_exit_code_one_when_prerequisite_fails(self) -> None:
        empty_env = {}
        with unittest.mock.patch.dict("os.environ", empty_env, clear=True):
            code = main(["--role", "api", "--quiet"])
            self.assertEqual(code, 1)

    def test_check_authentication_founder_and_jwks(self) -> None:
        # Founder credentials pass
        res_founder = check_authentication(self.valid_env)
        self.assertTrue(res_founder.passed)
        self.assertIn("Founder", res_founder.name)

        # JWKS credentials pass
        jwks_env = {"AUTH_JWKS_URL": "https://auth.invalid/jwks", "AUTH_SERVICE_KEY": "syn-key"}
        res_jwks = check_authentication(jwks_env)
        self.assertTrue(res_jwks.passed)
        self.assertIn("JWKS", res_jwks.name)

        # Missing credentials return BLOCKED
        res_missing = check_authentication({})
        self.assertEqual("BLOCKED", res_missing.status)

    def test_check_truth_pack_remote_and_local(self) -> None:
        # Remote URL with hash passes
        res_remote = check_truth_pack({
            "OPPORTUNITYOS_TRUTH_PACK_URI": "https://bucket.s3.invalid/pack.yaml",
            "OPPORTUNITYOS_TRUTH_PACK_HASH": "a" * 64,
        })
        self.assertTrue(res_remote.passed)
        self.assertIn("Remote HTTPS", res_remote.message)

        # Remote URL without hash returns BLOCKED
        res_no_hash = check_truth_pack({"OPPORTUNITYOS_TRUTH_PACK_URI": "https://bucket.s3.invalid/pack.yaml"})
        self.assertEqual("BLOCKED", res_no_hash.status)
        self.assertIn("Missing required OPPORTUNITYOS_TRUTH_PACK_HASH", res_no_hash.message)

        # Unset returns BLOCKED for worker
        res_unset_worker = check_truth_pack({}, role="worker")
        self.assertEqual("BLOCKED", res_unset_worker.status)

        # Unset passes for api (not required)
        res_unset_api = check_truth_pack({}, role="api")
        self.assertTrue(res_unset_api.passed)

        # Plain http returns FAIL
        res_http = check_truth_pack({"OPPORTUNITYOS_TRUTH_PACK_URI": "http://insecure.invalid/pack.yaml"})
        self.assertEqual("FAIL", res_http.status)

        # Data URI returns FAIL in production check
        res_data = check_truth_pack({"OPPORTUNITYOS_TRUTH_PACK_URI": "data:text/yaml,hello"})
        self.assertEqual("FAIL", res_data.status)

        # Forbidden local machine path fails
        res_forbidden = check_truth_pack({"OPPORTUNITYOS_TRUTH_PACK_URI": "C:\\Users\\founder\\pack.yaml"})
        self.assertEqual("FAIL", res_forbidden.status)
        self.assertIn("Forbidden", res_forbidden.message)

    def test_check_queue_durability(self) -> None:
        mock_engine = MagicMock()
        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspect.return_value = self._mock_inspector()
            res = check_queue_durability(engine=mock_engine)
            self.assertTrue(res.passed)
            self.assertIn("worker_jobs", res.message)

        # Fails when table missing
        with unittest.mock.patch("sqlalchemy.inspect") as mock_inspect:
            insp = MagicMock()
            insp.get_table_names.return_value = []
            mock_inspect.return_value = insp
            res_missing = check_queue_durability(engine=mock_engine)
            self.assertFalse(res_missing.passed)
            self.assertIn("Missing required 'worker_jobs'", res_missing.message)

    def test_check_single_role_autonomy(self) -> None:
        for role in ("api", "worker", "scheduler", "migrate"):
            res = check_single_role_autonomy(role, self.valid_env)
            self.assertTrue(res.passed, f"Role '{role}' expected autonomous pass, got: {res.message}")


if __name__ == "__main__":
    unittest.main()
