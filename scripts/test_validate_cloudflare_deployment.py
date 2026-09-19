from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import validate_cloudflare_deployment as validator


class CloudflareDeploymentValidatorTests(unittest.TestCase):
    def test_repository_package_passes(self):
        root = Path(__file__).parents[1]
        errors = validator.validate_cloudflare_package(root)
        self.assertEqual(errors, [], f"Expected zero errors, got: {errors}")


    def _copy_package(self, destination: Path) -> None:
        root = Path(__file__).parents[1]
        shutil.copytree(
            root / "web",
            destination / "web",
            ignore=shutil.ignore_patterns("node_modules", ".next", ".open-next"),
        )
        (destination / ".github" / "workflows").mkdir(parents=True)
        shutil.copy2(
            root / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml",
            destination / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml",
        )

    def test_missing_cloud_edge_guard_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            route = root / "web" / "app" / "api" / "[...path]" / "route.ts"
            text = route.read_text(encoding="utf-8-sig").replace(
                'process.env.OPPORTUNITYOS_CLOUD_EDGE === "1"',
                'false',
            )
            route.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("distinguish cloud edge" in error for error in errors))

    def test_automatic_workflow_trigger_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            workflow = root / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml"
            text = workflow.read_text(encoding="utf-8-sig").replace(
                "on:\n  workflow_dispatch:",
                "on:\n  push:\n  workflow_dispatch:",
            )
            workflow.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("automatic trigger forbidden" in error for error in errors))

    def test_missing_deploy_acknowledgement_failure_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            workflow = root / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml"
            text = workflow.read_text(encoding="utf-8-sig").replace(
                "DEPLOY_STAGING requires explicit acknowledgement.",
                "deployment acknowledgement omitted",
            )
            workflow.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("must fail, not silently skip" in error for error in errors))

    def test_foundational_resource_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            wrangler = root / "web" / "wrangler.jsonc"
            text = wrangler.read_text(encoding="utf-8-sig").rstrip()
            text = text[:-1] + ',\n  "r2_buckets": []\n}\n'
            wrangler.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("forbidden foundational" in error for error in errors))

    def test_wrong_worker_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            wrangler = root / "web" / "wrangler.jsonc"
            text = wrangler.read_text(encoding="utf-8-sig").replace(
                '"name": "opportunityos-web-staging"',
                '"name": "opportunityos-wrong-worker"',
            )
            wrangler.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("opportunityos-web-staging" in error for error in errors))

    def test_secret_in_wrangler_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            wrangler = root / "web" / "wrangler.jsonc"
            text = wrangler.read_text(encoding="utf-8-sig").replace(
                '"OPPORTUNITYOS_CLOUD_EDGE": "1"',
                '"OPPORTUNITYOS_CLOUD_EDGE": "1", "SUPABASE_SERVICE_ROLE_KEY": "secret"',
            )
            wrangler.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("forbidden secret embedded in wrangler.jsonc" in error for error in errors))

    def test_missing_supabase_browser_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            sb = root / "web" / "lib" / "supabase" / "browser.ts"
            sb.unlink()
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("missing Supabase browser client" in error for error in errors))

    def test_obsolete_truth_pack_in_web_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            route = root / "web" / "app" / "api" / "[...path]" / "route.ts"
            text = route.read_text(encoding="utf-8-sig") + '\n// bucket = "founder-truth-pack"\n'
            route.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("founder-truth-pack" in error for error in errors))

    def test_missing_ref_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            workflow = root / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml"
            text = workflow.read_text(encoding="utf-8-sig").replace("      ref:", "      target_sha:")
            workflow.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("support explicit ref input" in error for error in errors))

    def test_missing_token_verification_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            workflow = root / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml"
            text = workflow.read_text(encoding="utf-8-sig").replace("tokens/verify", "tokens/disabled")
            workflow.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("verify Cloudflare API token" in error for error in errors))

    def test_missing_smoke_email_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            workflow = root / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml"
            text = workflow.read_text(encoding="utf-8-sig").replace("E2E_FOUNDER_EMAIL", "NO_EMAIL")
            workflow.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("Founder email secret" in error for error in errors))

    def test_secret_in_worker_deploy_vars_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_package(root)
            workflow = root / ".github" / "workflows" / "fr007-cloudflare-staging-deploy.yml"
            text = workflow.read_text(encoding="utf-8-sig").replace(
                'VAR_ARGS=()',
                'VAR_ARGS=(--var "SUPABASE_SERVICE_ROLE_KEY:fake")',
            )
            workflow.write_text(text, encoding="utf-8")
            errors = validator.validate_cloudflare_package(root)
            self.assertTrue(any("forbidden secret passed to Worker deploy vars" in error for error in errors))


if __name__ == "__main__":
    unittest.main()