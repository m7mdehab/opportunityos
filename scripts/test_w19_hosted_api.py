from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]

class HostedApiW19ContractTests(unittest.TestCase):
    def test_browser_never_persists_auth_tokens(self):
        source = (ROOT / "web/lib/supabase/browser.ts").read_text(encoding="utf-8")
        self.assertNotIn("localStorage", source)
        self.assertIn("/api/auth/login", source)
        self.assertIn("credentials: \"same-origin\"", source)

    def test_edge_route_uses_http_only_cookies_and_refresh(self):
        source = (ROOT / "web/app/api/[...path]/route.ts").read_text(encoding="utf-8")
        self.assertIn("httpOnly: true", source)
        self.assertIn("__Host-opos_access", source)
        self.assertIn("grant_type=refresh_token", source)
        self.assertIn("NEXT_PUBLIC_SUPABASE_URL", source)
        self.assertNotIn("STORAGE_SERVICE_KEY", source)
        self.assertNotIn("OPOS_TARGET_DB_URL", source)

    def test_route_has_exact_total_and_poll_shape(self):
        source = (ROOT / "web/app/api/[...path]/route.ts").read_text(encoding="utf-8")
        self.assertIn("Prefer: \"count=exact\"", source)
        self.assertIn("const enqueued", source)
        self.assertIn("source_id", source)
        self.assertIn("job_id", source)

    def test_migration_adds_durable_cv_and_exact_rpc(self):
        source = (ROOT / "storage/migrations/versions/0011_hosted_api_surface.py").read_text(encoding="utf-8")
        self.assertIn('revision: str = "0011_hosted_api_surface"', source)
        self.assertIn('"founder_cv_selections"', source)
        self.assertIn("RETURNS jsonb", source)
        self.assertIn("already_queued", source)
        self.assertIn("not_due", source)
        self.assertIn("founder_source_health", (ROOT / "storage/migrations/versions/0010_hosted_runtime.py").read_text(encoding="utf-8"))

    def test_bootstrap_is_bounded_and_manual_workflow_only(self):
        script = (ROOT / "scripts/fr007_hosted_bootstrap.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/fr007-hosted-bootstrap.yml").read_text(encoding="utf-8")
        self.assertIn("queue-empty", script)
        self.assertIn("--max-jobs", script)
        self.assertIn("workflow_dispatch", workflow)
        self.assertNotIn("push:", workflow)

if __name__ == "__main__":
    unittest.main()
