from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class W17RuntimeWorkflowContractTests(unittest.TestCase):
    def test_backup_workflow_installs_crypto_and_uploads_only_encrypted_outputs(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-encrypted-backup.yml").read_text(encoding="utf-8")
        self.assertIn("python -m pip install -e .", workflow)
        self.assertIn("BACKUP_ENCRYPTION_KEY", workflow)
        self.assertIn("--remove-plaintext", workflow)
        founder_upload = workflow.split("Upload short-lived encrypted Founder-state backup", 1)[1].split(
            "Upload monthly encrypted integrity backup", 1
        )[0]
        integrity_upload = workflow.split("Upload monthly encrypted integrity backup", 1)[1]
        self.assertIn("backup-out/backup.founder_state.enc", founder_upload)
        self.assertIn("backup-out/backup.founder_state.manifest.json", founder_upload)
        self.assertNotIn("source.dump", founder_upload)
        self.assertIn("backup-out/backup.integrity.enc", integrity_upload)
        self.assertIn("backup-out/backup.integrity.manifest.json", integrity_upload)
        self.assertIn("backup-out/source.dump.manifest.json", integrity_upload)
        self.assertNotIn("backup-out/source.dump\n", integrity_upload)

    def test_backup_workflow_is_explicitly_authorized_and_manual(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-encrypted-backup.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("inputs.acknowledge_backup == true", workflow)
        self.assertNotIn("pull_request", workflow)
        self.assertNotIn("\n  push:", workflow)

    def test_backup_workflow_separates_daily_founder_state_from_monthly_integrity(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-encrypted-backup.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 2 * * *"', workflow)
        self.assertIn('cron: "47 2 1 * *"', workflow)
        self.assertIn("backup_class:", workflow)
        self.assertIn("founder_state", workflow)
        self.assertIn("integrity", workflow)
        self.assertIn("scripts/founder_state_backup.py export", workflow)
        self.assertIn("--backup-class integrity", workflow)
        self.assertIn("retention-days: 7", workflow)
        self.assertIn("retention-days: 30", workflow)
        self.assertIn("source.dump.manifest.json", workflow)
        self.assertIn("secrets.CLOUD_DATABASE_URL || secrets.OPOS_TARGET_DB_URL", workflow)

    def test_worker_drain_five_shard_matrix_and_structure(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-worker-drain.yml").read_text(encoding="utf-8")
        # Enqueue phase exists and executes once (no matrix)
        self.assertIn("enqueue:", workflow)
        enqueue_section = workflow.split("enqueue:", 1)[1].split("drain:", 1)[0]
        self.assertIn("--mode enqueue", enqueue_section)
        self.assertNotIn("matrix:", enqueue_section)

        # Drain phase exists with 5 parallel shards
        self.assertIn("drain:", workflow)
        drain_section = workflow.split("drain:", 1)[1]
        self.assertIn("needs: [enqueue]", drain_section)
        self.assertIn("shard: [1, 2, 3, 4, 5]", drain_section)
        self.assertIn("--mode drain", drain_section)

        # Concurrency protection
        self.assertIn("cancel-in-progress: false", workflow)

    def test_worker_drain_schedule_and_defaults(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-worker-drain.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "*/15 * * * *"', workflow)
        # Scheduled/default per-shard parameters: 30 jobs, 480 seconds
        self.assertIn('default: "30"', workflow)
        self.assertIn('default: "480"', workflow)
        self.assertIn("RAW_MAX > 150 ? 150", workflow)
        self.assertIn("RAW_BUDGET > 540 ? 540", workflow)

    def test_worker_drain_unique_worker_id_per_shard(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-worker-drain.yml").read_text(encoding="utf-8")
        self.assertIn('OPOS_WORKER_ID: "hosted-bootstrap-${{ github.run_id }}-${{ matrix.shard }}"', workflow)
        self.assertIn('--worker-id "${OPOS_WORKER_ID}"', workflow)

    def test_worker_drain_timeout_headroom(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-worker-drain.yml").read_text(encoding="utf-8")
        drain_section = workflow.split("drain:", 1)[1]
        self.assertIn("timeout-minutes: 35", drain_section)

    def test_final_closure_fails_closed_on_piped_failures_and_direct_script_imports(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-final-runtime-closure.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("set -o pipefail"), 4)
        bootstrap = (ROOT / "scripts" / "fr007_hosted_bootstrap.py").read_text(encoding="utf-8")
        closure = (ROOT / "scripts" / "fr007_capacity_closure.py").read_text(encoding="utf-8")
        self.assertIn("REPOSITORY_ROOT = Path(__file__).resolve().parents[1]", bootstrap)
        self.assertIn("REPOSITORY_ROOT = Path(__file__).resolve().parents[1]", closure)


    def test_worker_drain_mode_conditions(self):
        workflow = (ROOT / ".github" / "workflows" / "fr007-worker-drain.yml").read_text(encoding="utf-8")
        enqueue_section = workflow.split("enqueue:", 1)[1].split("drain:", 1)[0]
        drain_section = workflow.split("drain:", 1)[1]
        # Enqueue runs on all / enqueue, skipped on drain
        self.assertIn("inputs.mode == 'enqueue'", enqueue_section)
        # Drain runs on all / drain, skipped on enqueue
        self.assertIn("inputs.mode == 'drain'", drain_section)

    def test_hosted_bootstrap_worker_id_contract(self):
        import os
        from unittest.mock import patch, MagicMock
        from scripts import fr007_hosted_bootstrap

        parser = fr007_hosted_bootstrap.build_parser()
        args = parser.parse_args(["--worker-id", "test-shard-3"])
        self.assertEqual(args.worker_id, "test-shard-3")

        # Fallback to OPOS_WORKER_ID
        with patch.dict(os.environ, {"OPOS_WORKER_ID": "env-worker-4"}):
            with patch("scripts.fr007_hosted_bootstrap.WorkerRunner") as mock_runner:
                mock_runner.return_value.run_once.return_value = False
                fr007_hosted_bootstrap._drain(MagicMock(), max_jobs=1, budget=10.0)
                mock_runner.assert_called_once()
                self.assertEqual(mock_runner.call_args[1]["worker_id"], "env-worker-4")

        # Explicit argument overrides env
        with patch.dict(os.environ, {"OPOS_WORKER_ID": "env-worker-4"}):
            with patch("scripts.fr007_hosted_bootstrap.WorkerRunner") as mock_runner:
                mock_runner.return_value.run_once.return_value = False
                fr007_hosted_bootstrap._drain(MagicMock(), max_jobs=1, budget=10.0, worker_id="explicit-worker-2")
                self.assertEqual(mock_runner.call_args[1]["worker_id"], "explicit-worker-2")

        # Default fallback
        with patch.dict(os.environ, {}, clear=True):
            with patch("scripts.fr007_hosted_bootstrap.WorkerRunner") as mock_runner:
                mock_runner.return_value.run_once.return_value = False
                fr007_hosted_bootstrap._drain(MagicMock(), max_jobs=1, budget=10.0)
                self.assertEqual(mock_runner.call_args[1]["worker_id"], "hosted-bootstrap")

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
