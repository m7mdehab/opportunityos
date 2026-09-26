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
ACTIVITY_CORRECTION = Path(__file__).parent / "migrations" / "versions" / "0017_founder_activity_correction.py"


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
        self.assertEqual(script.get_current_head(), "0026_fr008_live_actions")

    def test_founder_claim_compatibility_migration_accepts_postgrest_json_claims(self):
        migration = Path(__file__).parent / "migrations" / "versions" / "0024_founder_jwt_claim_compat.py"
        source = migration.read_text(encoding="utf-8")
        self.assertIn('revision: str = "0024_founder_jwt_claims"', source)
        self.assertIn('down_revision: Union[str, None] = "0023_alembic_access"', source)
        self.assertIn("request.jwt.claim.sub", source)
        self.assertIn("request.jwt.claims", source)
        self.assertIn("->> 'sub'", source)
        self.assertIn("SECURITY DEFINER", source)
        self.assertIn("founder.supabase_user_id = COALESCE", source)
        self.assertIn("def downgrade()", source)

    def test_current_feed_fast_path_uses_unique_storage_v2_projection(self):
        migration = Path(__file__).parent / "migrations" / "versions" / "0025_current_feed_projection_fast_path.py"
        source = migration.read_text(encoding="utf-8")
        self.assertIn('revision: str = "0025_current_feed_fast_path"', source)
        self.assertIn('down_revision: Union[str, None] = "0024_founder_jwt_claims"', source)
        self.assertIn("security_invoker = true", source)
        self.assertIn("JOIN public.opportunities o ON o.id = fp.opportunity_id", source)
        self.assertIn("one current feed_projection row per opportunity", source)
        self.assertNotIn("row_number() OVER", source.split("def downgrade()", 1)[0])
        downgrade = source.split("def downgrade()", 1)[1]
        self.assertIn("row_number() OVER", downgrade)
        self.assertIn("CREATE OR REPLACE VIEW public.founder_feed", downgrade)
        self.assertNotIn("DROP VIEW", downgrade)
        self.assertNotIn("founder_feed_activity", downgrade)
        config = Config("alembic.ini")
        self.assertEqual(ScriptDirectory.from_config(config).get_current_head(), "0026_fr008_live_actions")


    def test_fr008_live_actions_are_linear_after_current_feed_fast_path(self):
        migration = Path(__file__).parent / "migrations" / "versions" / "0026_fr008_live_actions.py"
        source = migration.read_text(encoding="utf-8")
        self.assertIn('revision: str = "0026_fr008_live_actions"', source)
        self.assertIn('down_revision: Union[str, None] = "0025_current_feed_fast_path"', source)
        for required in (
            "founder_restore_action",
            "'save','mark_applied','reject'",
            "founder_feed_fr008",
            "remote_rank",
            "security_invoker = true",
        ):
            self.assertIn(required, source)

    def test_capacity_revision_is_linear_after_activity_view_access(self):
        capacity = Path(__file__).parent / "migrations" / "versions" / "0020_capacity_archive.py"
        source = capacity.read_text(encoding="utf-8")
        self.assertIn('revision: str = "0020_capacity_archive"', source)
        self.assertIn('down_revision: Union[str, None] = "0019_activity_view_access"', source)
        self.assertIn('"opportunity_cold_archive"', source)

    def test_storage_v2_is_linear_and_object_backed(self):
        migration = Path(__file__).parent / "migrations" / "versions" / "0021_storage_v2.py"
        source = migration.read_text(encoding="utf-8")
        self.assertIn('revision: str = "0021_storage_v2"', source)
        self.assertIn('down_revision: Union[str, None] = "0020_capacity_archive"', source)
        for required in ("archive_object_key", "archive_sha256", "storage_backend", "object_key", "DROP INDEX IF EXISTS ix_feed_projection_search_tsv"):
            self.assertIn(required, source)

    def test_alembic_version_is_browser_denied_without_forcing_owner_rls(self):
        migration = Path(__file__).parent / "migrations" / "versions" / "0023_alembic_version_access_hardening.py"
        source = migration.read_text(encoding="utf-8")
        self.assertIn('revision: str = "0023_alembic_access"', source)
        self.assertLessEqual(len("0023_alembic_access"), 32)
        self.assertIn('down_revision: Union[str, None] = "0022_storage_v2_direct_tiering"', source)
        self.assertIn("REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM PUBLIC", source)
        self.assertIn("FROM anon", source)
        self.assertIn("FROM authenticated", source)
        self.assertIn("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY", source)
        self.assertNotIn("FORCE ROW LEVEL SECURITY", source)
        self.assertNotIn("CREATE POLICY", source.upper())
        self.assertIn("def downgrade()", source)
        self.assertIn("Keep it in force on downgrade", source)

    def test_activity_correction_matches_live_0016_contract(self):
        source = ACTIVITY_CORRECTION.read_text(encoding="utf-8")
        self.assertIn('revision: str = "0017_founder_activity_correction"', source)
        self.assertIn('down_revision: Union[str, None] = "0016_founder_activity"', source)
        for required in ("founder_activity_events", "founder_set_action", "founder_add_feedback", "founder_activity_detail", "has_activity", "CURRENT_DATE", "SECURITY DEFINER", "p_type='clear'", "action_type IN ('mark_applied','dismiss','snooze','clear')"):
            self.assertIn(required, source)
        self.assertNotIn("THEN CASE WHEN a.applied_at IS NOT NULL THEN 'submitted'", source)

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
            "make_interval(secs => sched.cadence_hours * 3600.0)",
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
