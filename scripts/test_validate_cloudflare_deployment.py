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
            ignore=shutil.ignore_patterns("node_modules", ".next", "playwright-report*", "test-results"),
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


if __name__ == "__main__":
    unittest.main()