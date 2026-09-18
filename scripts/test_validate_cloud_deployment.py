import json
from pathlib import Path
import tempfile
import unittest

from scripts import validate_cloud_deployment as validator


class CloudDeploymentValidatorTests(unittest.TestCase):
    def test_repository_package_passes_with_immutable_image(self):
        root = Path(__file__).parents[1]
        self.assertEqual(validator.validate_package(root), [])
        self.assertEqual(validator.validate_image(
            "registry.example/opportunityos@sha256:" + "a" * 64), [])

    def test_mutable_and_missing_images_fail_closed(self):
        self.assertTrue(validator.validate_image("registry.example/opportunityos:latest"))
        self.assertTrue(validator.validate_image("registry.example/opportunityos:release"))

    def test_exact_four_roles_and_scheduler_singleton(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            (copy / "infra" / "azure").mkdir(parents=True)
            for relative in ("main.bicep", "modules/container-app.bicep", "modules/container-job.bicep"):
                source = root / "infra" / "azure" / relative
                destination = copy / "infra" / "azure" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            contract = json.loads((root / "infra/azure/contract.json").read_text(encoding="utf-8"))
            contract["roles"].pop("scheduler")
            (copy / "infra/azure/contract.json").write_text(json.dumps(contract), encoding="utf-8")
            (copy / ".github" / "workflows").mkdir(parents=True)
            workflow = root.joinpath(".github/workflows/fr007-azure-staging-deploy.yml")
            (copy / ".github/workflows/fr007-azure-staging-deploy.yml").write_text(
                workflow.read_text(encoding="utf-8"), encoding="utf-8")
            errors = validator.validate_package(copy)
            self.assertTrue(any("exactly" in error for error in errors))

    def test_forbidden_foundational_resource_is_rejected(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for source_relative in ("infra/azure", ".github/workflows"):
                destination = copy / source_relative
                destination.mkdir(parents=True)
                for source in (root / source_relative).glob("**/*"):
                    if source.is_file():
                        target = destination / source.relative_to(root / source_relative)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            main = copy / "infra/azure/main.bicep"
            main.write_text(main.read_text(encoding="utf-8") + "\nresource registry 'Microsoft.ContainerRegistry/registries@2023-01-01' = {}\n", encoding="utf-8")
            self.assertTrue(any("foundational" in error for error in validator.validate_package(copy)))

    def test_job_secret_and_migration_success_gate_are_required(self):
        root = Path(__file__).parents[1]
        self.assertEqual(validator.validate_package(root), [])
        job = root / "infra/azure/modules/container-job.bicep"
        workflow = root / ".github/workflows/fr007-azure-staging-deploy.yml"
        self.assertIn("secrets:", job.read_text(encoding="utf-8"))
        self.assertIn("manualTriggerConfig:", job.read_text(encoding="utf-8"))
        self.assertIn("job execution list", workflow.read_text(encoding="utf-8"))
        self.assertIn("Succeeded) exit 0", workflow.read_text(encoding="utf-8"))

    def test_truth_pack_uri_is_secret_ref_backed(self):
        root = Path(__file__).parents[1]
        main = (root / "infra/azure/main.bicep").read_text(encoding="utf-8")
        app = (root / "infra/azure/modules/container-app.bicep").read_text(encoding="utf-8")
        self.assertRegex(main, r"@secure\(\)\s*\nparam truthPackUri string")
        self.assertIn("{ name: 'truth-pack-uri'; value: truthPackUri }", app)
        self.assertIn("{ name: 'OPPORTUNITYOS_TRUTH_PACK_URI'; secretRef: 'truth-pack-uri' }", app)


if __name__ == "__main__":
    unittest.main()
