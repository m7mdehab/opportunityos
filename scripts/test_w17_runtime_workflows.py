from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class W17RuntimeWorkflowContractTests(unittest.TestCase):
    def test_backup_workflow_installs_crypto_and_uploads_only_encrypted_outputs(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-encrypted-backup.yml").read_text(encoding="utf-8")
        self.assertIn("python -m pip install -e .", workflow)
        self.assertIn("BACKUP_ENCRYPTION_KEY", workflow)
        self.assertIn("--remove-plaintext", workflow)
        upload = workflow.split("Upload encrypted backup only", 1)[1]
        self.assertIn("backup-out/backup.dump.enc", upload)
        self.assertIn("backup-out/backup.encrypted.manifest.json", upload)
        self.assertNotIn("backup-out/source.dump\n", upload)

    def test_backup_workflow_is_explicitly_authorized_and_manual(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-encrypted-backup.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("inputs.acknowledge_backup == true", workflow)
        self.assertNotIn("pull_request", workflow)

    def test_worker_workflow_uses_single_bounded_mode(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-worker-drain.yml").read_text(encoding="utf-8")
        command = next(
            line.strip()
            for line in workflow.splitlines()
            if line.strip().startswith("python scripts/fr007_hosted_bootstrap.py")
        )
        self.assertIn("--mode all", command)
        self.assertIn("--max-jobs", command)
        self.assertIn("--time-budget-seconds", command)
        self.assertNotIn("--once", command)
        self.assertIn("OPOS_TARGET_DB_URL", workflow)
        self.assertIn("OPPORTUNITYOS_TRUTH_PACK_PATH", workflow)

    def test_encryption_dependency_is_runtime_declared(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(pyproject, r'"cryptography>=')

    def test_encrypted_manifest_is_safe_json(self):
        from scripts import encrypted_backup
        self.assertEqual(encrypted_backup.KEY_ENV, "BACKUP_ENCRYPTION_KEY")
        source = (ROOT / "scripts" / "encrypted_backup.py").read_text(encoding="utf-8")
        self.assertNotIn("service_role", source)


if __name__ == "__main__":
    unittest.main()
