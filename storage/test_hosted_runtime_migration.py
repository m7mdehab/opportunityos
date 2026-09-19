"""Contract tests for migration 0010 hosted runtime closure.

These tests intentionally inspect the repository-owned migration without a live
provider.  The PostgreSQL execution proof remains in the disposable provider
suite and the Overseer hosted run.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION = Path(__file__).parent / "migrations" / "versions" / "0010_hosted_runtime.py"


class HostedRuntimeMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MIGRATION.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_revision_is_after_hosted_auth(self):
        namespace: dict[str, object] = {}
        exec(compile(self.tree, str(MIGRATION), "exec"), namespace)
        self.assertEqual(namespace["revision"], "0010_hosted_runtime")
        self.assertEqual(namespace["down_revision"], "0009_hosted_founder_auth")

        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        self.assertEqual(script.get_current_head(), "0011_hosted_api_surface")

    def test_durable_founder_binding_and_browser_boundary(self):
        for required in (
            '"founder_identity"',
            "supabase_user_id",
            "request.jwt.claim.sub",
            "opos_is_founder",
            "founder_feed",
            "founder_source_health",
            "founder_artifact_metadata",
            "security_invoker",
            "REVOKE ALL ON public.founder_identity FROM PUBLIC",
        ):
            self.assertIn(required, self.source)
        self.assertIn("GRANT SELECT ON public.{view} TO authenticated", self.source)
        self.assertNotIn("app.founder_auth_uid", self.source)
        self.assertIn("founder_private_cv_select", self.source)
        self.assertIn("founder_private_artifact_select", self.source)
        self.assertIn("founder-cv-portfolio", self.source)
        self.assertIn("opportunity-artifacts", self.source)

    def test_poll_now_is_due_only_and_scheduler_safe(self):
        for required in (
            "next_due_at <= now()",
            "cooldown_until IS NULL OR s.cooldown_until <= now()",
            "FOR UPDATE SKIP LOCKED",
            "status IN ('PENDING', 'RETRY', 'RUNNING')",
            "payload_json::jsonb ->> 'source_id'",
            "make_interval(hours => sched.cadence_hours)",
            "json_build_object('source_id', sched.source_id)",
        ):
            self.assertIn(required, self.source)
        # No force bypass or generic empty payload may creep back into the
        # hosted boundary. The Python scheduler remains the source policy.
        self.assertNotIn("p_force", self.source)
        self.assertNotIn("'{}'::text", self.source)
        self.assertNotIn("'poll_source', p_source_id", self.source)

    def test_security_definer_functions_are_restricted(self):
        self.assertGreaterEqual(self.source.count("SECURITY DEFINER"), 3)
        self.assertGreaterEqual(self.source.count("REVOKE ALL ON FUNCTION"), 4)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated", self.source)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.poll_job_status(text) TO authenticated", self.source)
        self.assertNotIn("service_role", self.source.lower())
        self.assertNotIn("postgresql://", self.source)
        self.assertNotIn("password", self.source.lower())

    def test_downgrade_removes_runtime_objects_and_reinstates_deny_policy(self):
        for required in (
            "DROP FUNCTION IF EXISTS public.enqueue_poll_now(text)",
            "DROP FUNCTION IF EXISTS public.poll_job_status(text)",
            "DROP FUNCTION IF EXISTS public.opos_is_founder()",
            "DROP VIEW IF EXISTS public.founder_feed",
            "DROP VIEW IF EXISTS public.founder_source_health",
            "DROP VIEW IF EXISTS public.founder_artifact_metadata",
            "founder_identity DISABLE ROW LEVEL SECURITY",
            "browser_deny_authenticated",
        ):
            self.assertIn(required, self.source)


if __name__ == "__main__":
    unittest.main()
