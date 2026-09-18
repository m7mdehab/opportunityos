"""Synthetic regression checks for the FR-007 current-runtime bridge."""

import unittest

from scripts.cloud_runtime_bridge import (
    CompatibilityError, build_runtime_environment, plan_runtime_environment,
)


DB = "postgresql+psycopg2" + "://db.cloud.invalid/opos"
WORKER = {
    "CLOUD_DATABASE_URL": DB,
    "QUEUE_NAMESPACE": "jobs",
    "STORAGE_SERVICE_KEY": "synthetic-private-storage-key",
    "STORAGE_PRIVATE_BUCKET": "artifacts",
}
WEB = {
    "NEXT_PUBLIC_DATA_API_URL": "https://api.cloud.invalid",
    "NEXT_PUBLIC_DATA_ANON_KEY": "synthetic-public-key",
}


class BridgeTests(unittest.TestCase):
    def test_unconfigured_roles_have_explicit_blockers(self):
        # Web has unwired blockers
        self.assertTrue(plan_runtime_environment("web", WEB).blockers)
        with self.assertRaisesRegex(CompatibilityError, "Unsupported role"):
            plan_runtime_environment("unknown", {})

    def test_neutral_database_maps_to_existing_consumer(self):
        plan = plan_runtime_environment("worker", WORKER)
        self.assertEqual(plan.aliases, {"OPPORTUNITYOS_DB_URL": DB})

    def test_missing_cloud_config_fails_closed(self):
        with self.assertRaisesRegex(CompatibilityError, "CLOUD_DATABASE_URL"):
            plan_runtime_environment("worker", {k: v for k, v in WORKER.items() if k != "CLOUD_DATABASE_URL"})

    def test_conflicting_legacy_database_fails_closed_without_values(self):
        with self.assertRaises(CompatibilityError) as caught:
            plan_runtime_environment("worker", dict(WORKER, OPPORTUNITYOS_DB_URL="postgresql" + "://other.invalid/other"))
        self.assertIn("OPPORTUNITYOS_DB_URL", str(caught.exception))
        self.assertNotIn("other.invalid", str(caught.exception))

    def test_diagnostics_redact_secrets(self):
        with self.assertRaises(CompatibilityError) as caught:
            plan_runtime_environment("worker", dict(WORKER, QUEUE_NAMESPACE="REPLACE_ME"))
        self.assertIn("QUEUE_NAMESPACE", str(caught.exception))
        self.assertNotIn("REPLACE_ME", str(caught.exception))
        self.assertNotIn("synthetic-private-storage-key", str(caught.exception))

    def test_web_does_not_inherit_worker_secrets(self):
        plan = plan_runtime_environment("web", WEB)
        self.assertEqual(plan.aliases, {})
        self.assertNotIn("STORAGE_SERVICE_KEY", plan.blockers)

    def test_production_never_enables_mock_or_local_fallback(self):
        for key, value in (("NEXT_PUBLIC_USE_MOCK_API", "1"),
                           ("OPPORTUNITYOS_TRUTH_PACK_PATH", "private/local.yaml"),
                           ("CLOUD_DATABASE_URL", "postgresql" + "://127.0.0.2/opos")):
            with self.subTest(key=key), self.assertRaises(CompatibilityError):
                plan_runtime_environment("worker", dict(WORKER, **{key: value}))

    def test_privileged_values_never_become_public(self):
        plan = plan_runtime_environment("worker", WORKER)
        self.assertFalse(any(key.startswith("NEXT_PUBLIC_") for key in plan.aliases))
        self.assertNotIn(WORKER["STORAGE_SERVICE_KEY"], plan.aliases.values())
        with self.assertRaises(CompatibilityError):
            build_runtime_environment("web", WEB)

    def test_unwired_dependencies_are_explicit_and_block_launch(self):
        # Web has unwired blockers and refuses to build
        plan = plan_runtime_environment("web", WEB)
        self.assertIn("NEXT_PUBLIC_DATA_API_URL", plan.blockers)
        with self.assertRaisesRegex(CompatibilityError, "NEXT_PUBLIC_DATA_API_URL"):
            build_runtime_environment("web", WEB)

    def test_matching_legacy_alias_is_accepted(self):
        self.assertEqual(plan_runtime_environment("worker", dict(WORKER, OPPORTUNITYOS_DB_URL=DB)).aliases,
                         {"OPPORTUNITYOS_DB_URL": DB})

    def test_founder_auth_accepted_with_zero_blockers(self):
        api_env = {
            "CLOUD_DATABASE_URL": DB,
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "valid-founder-password",
            "OPPORTUNITYOS_SESSION_SECRET": "valid-session-secret-32-chars",
        }
        plan = plan_runtime_environment("api", api_env)
        self.assertEqual(plan.aliases["OPPORTUNITYOS_FOUNDER_PASSWORD"], "valid-founder-password")
        self.assertEqual(plan.aliases["OPPORTUNITYOS_SESSION_SECRET"], "valid-session-secret-32-chars")
        # Single-founder production auth clears all blockers in FR-007
        self.assertEqual(plan.blockers, ())
        env = build_runtime_environment("api", api_env)
        self.assertEqual(env["OPPORTUNITYOS_DB_URL"], DB)
        self.assertEqual(env["OPPORTUNITYOS_FOUNDER_PASSWORD"], "valid-founder-password")

    def test_remote_truth_pack_uri_accepted_and_aliased(self):
        env = {
            "CLOUD_DATABASE_URL": DB,
            "OPPORTUNITYOS_TRUTH_PACK_URI": "https://storage.supabase.co/truth/pack.yaml",
            "OPPORTUNITYOS_TRUTH_PACK_HASH": "a" * 64,
        }
        plan = plan_runtime_environment("worker", env)
        self.assertEqual(plan.aliases["OPPORTUNITYOS_TRUTH_PACK_PATH"], "https://storage.supabase.co/truth/pack.yaml")
        self.assertEqual(plan.aliases["OPPORTUNITYOS_TRUTH_PACK_URI"], "https://storage.supabase.co/truth/pack.yaml")
        self.assertEqual(plan.aliases["OPPORTUNITYOS_TRUTH_PACK_HASH"], "a" * 64)

    def test_worker_role_unconfigured_has_truth_pack_blocker(self):
        plan = plan_runtime_environment("worker", WORKER)
        self.assertIn("OPPORTUNITYOS_TRUTH_PACK_URI", plan.blockers)
        with self.assertRaisesRegex(CompatibilityError, "OPPORTUNITYOS_TRUTH_PACK_URI"):
            build_runtime_environment("worker", WORKER)

    def test_worker_role_with_truth_pack_has_zero_blockers_and_builds_cleanly(self):
        configured_worker = dict(
            WORKER,
            OPPORTUNITYOS_TRUTH_PACK_URI="https://storage.supabase.co/truth/pack.yaml",
            OPPORTUNITYOS_TRUTH_PACK_HASH="a" * 64,
        )
        plan = plan_runtime_environment("worker", configured_worker)
        self.assertEqual(plan.blockers, ())
        env = build_runtime_environment("worker", configured_worker)
        self.assertEqual(env["OPPORTUNITYOS_DB_URL"], DB)
        self.assertEqual(env["OPPORTUNITYOS_TRUTH_PACK_URI"], "https://storage.supabase.co/truth/pack.yaml")

    def test_scheduler_role_has_zero_blockers_and_builds_cleanly(self):
        sched_env = {"CLOUD_DATABASE_URL": DB}
        plan = plan_runtime_environment("scheduler", sched_env)
        self.assertEqual(plan.blockers, ())
        env = build_runtime_environment("scheduler", sched_env)
        self.assertEqual(env["OPPORTUNITYOS_DB_URL"], DB)

    def test_migrate_role_has_zero_blockers_and_builds_cleanly(self):
        migrate_env = {"CLOUD_DATABASE_URL": DB}
        plan = plan_runtime_environment("migrate", migrate_env)
        self.assertEqual(plan.blockers, ())
        env = build_runtime_environment("migrate", migrate_env)
        self.assertEqual(env["OPPORTUNITYOS_DB_URL"], DB)

    def test_api_jwks_alone_does_not_clear_blockers(self):
        jwks_env = {
            "CLOUD_DATABASE_URL": DB,
            "AUTH_JWKS_URL": "https://auth.invalid/jwks",
            "AUTH_SERVICE_KEY": "synthetic-auth-key",
            "OPPORTUNITYOS_FOUNDER_PASSWORD": "valid-founder-password",
            "OPPORTUNITYOS_SESSION_SECRET": "valid-session-secret-32-chars",
        }
        # With founder secrets it passes
        self.assertEqual(plan_runtime_environment("api", jwks_env).blockers, ())

        # Without founder secrets, JWKS alone fails to validate or leaves blockers
        jwks_only = {
            "CLOUD_DATABASE_URL": DB,
            "AUTH_JWKS_URL": "https://auth.invalid/jwks",
            "AUTH_SERVICE_KEY": "synthetic-auth-key",
        }
        with self.assertRaises(CompatibilityError) as caught:
            plan_runtime_environment("api", jwks_only)
        self.assertIn("OPPORTUNITYOS_FOUNDER_PASSWORD", str(caught.exception))

    def test_worker_role_local_container_truth_pack_is_blocked(self):
        local_worker = dict(
            WORKER,
            OPPORTUNITYOS_TRUTH_PACK_PATH="/app/truth/founder.yaml",
        )
        plan = plan_runtime_environment("worker", local_worker)
        self.assertIn("OPPORTUNITYOS_TRUTH_PACK_URI", plan.blockers)

    def test_worker_role_https_without_hash_has_hash_blocker(self):
        worker_no_hash = dict(
            WORKER,
            OPPORTUNITYOS_TRUTH_PACK_URI="https://storage.supabase.co/truth/pack.yaml",
        )
        plan = plan_runtime_environment("worker", worker_no_hash)
        self.assertIn("OPPORTUNITYOS_TRUTH_PACK_HASH", plan.blockers)

    def test_liveness_role_has_zero_blockers(self):
        plan = plan_runtime_environment("liveness", {})
        self.assertEqual(plan.blockers, ())
        env = build_runtime_environment("liveness", {})
        self.assertEqual(env, {})


if __name__ == "__main__":
    unittest.main()


