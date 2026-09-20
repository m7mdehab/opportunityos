from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import fr007_supabase_execution_bundle as bundle
from scripts import migration_baseline


class SupabaseExecutionBundleTests(unittest.TestCase):
    def test_revision_order_and_expected_head(self):
        chain = bundle.revisions()
        self.assertEqual([item["revision"] for item in chain], [
            "0001_baseline_schema", "0002_match_evaluations", "0003_provenance_identity",
            "0004_founder_control", "0005_widen_location_region", "0006_feed_projection",
            "0007_source_schedules", "0008_artifact_storage", "0009_hosted_founder_auth",
            "0010_hosted_runtime", "0011_hosted_api_surface", "0012_hosted_policy_alignment",
            "0013_hosted_poll_now_cadence", "0014_backup_heartbeat", "0015_hosted_founder_surface",
        ])
        self.assertEqual(chain[-1]["revision"], "0015_hosted_founder_surface")
        self.assertEqual(len({item["revision"] for item in chain}), len(chain))

    def test_generation_is_deterministic_and_hashes_match(self):
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            first = bundle.generate(Path(left))
            second = bundle.generate(Path(right))
            self.assertEqual(first, second)
            for path in Path(left).rglob("*"):
                if path.is_file():
                    other = Path(right) / path.relative_to(left)
                    self.assertEqual(path.read_bytes(), other.read_bytes(), path.name)
            self.assertEqual(bundle.verify_manifest(Path(left))["expected_final_revision"], "0015_hosted_founder_surface")
            manifest = json.loads((Path(left) / "migration-manifest.json").read_text(encoding="utf-8"))
            policy_alignment = next(item for item in manifest["migrations"] if item["revision"] == "0012_hosted_policy_alignment")
            self.assertTrue(policy_alignment["effects"]["touches_rls"])
            api_surface = next(item for item in manifest["migrations"] if item["revision"] == "0011_hosted_api_surface")
            self.assertIn("founder_cv_selections", api_surface["effects"]["tables_or_columns"])

    def test_provider_sql_has_no_shell_dsn_or_secret_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle.generate(Path(tmp))
            for path in Path(tmp).rglob("*.sql"):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(?i)(postgres(?:ql)?|mysql|redis)://")
                self.assertNotIn("\\connect", text)
                self.assertNotIn("\\set", text)
                self.assertNotRegex(text, r"(?i)(password|service[-_ ]role|secret|token)\s*[:=]\s*[^\s;]+")

    def test_manifest_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle.generate(root)
            target = root / "verify" / "rls.sql"
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(bundle.BundleError):
                bundle.verify_manifest(root)

    def test_storage_contract_is_private_and_evidence_starts_unexecuted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle.generate(root)
            storage = (root / "storage.sql").read_text(encoding="utf-8")
            self.assertIn("public)\nVALUES", storage)
            self.assertIn("false)", storage)
            evidence = json.loads((root / "evidence-template.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "NOT_EXECUTED")
            self.assertEqual(evidence["acceptance"]["A-10"], "NOT_EXECUTED")
            self.assertIsNone(evidence["executed_at_utc"])
            security = (root / "provider-security.sql").read_text(encoding="utf-8")
            self.assertIn("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY", security)
            self.assertIn("REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM anon", security)
            self.assertIn("REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM authenticated", security)
            with self.assertRaises(bundle.BundleError):
                bundle.validate_evidence_document({"status": "PASS"})

    def test_parity_fixture_pass_and_mismatch(self):
        tables = {name: None for name in migration_baseline.TABLES}
        tables.update({"opportunities": 1, "match_evaluations": 1})
        invariants = {name: 0 for name in set(migration_baseline.CHECKS) | set(migration_baseline.REFERENCES)}
        constraints = {name: True for name in migration_baseline.UNIQUE_CONSTRAINTS.values()}
        base = {
            "format": 2, "alembic_revision": "0009_hosted_founder_auth",
            "tables": tables, "evaluation_coverage": {}, "invariants": invariants,
            "opportunity_sample": [], "identity_digests": {"opportunities": "a", "evaluation_bindings": "b"},
            "decision_distributions": {}, "state_distributions": {},
            "null_counts": {}, "unique_constraints": constraints,
        }
        self.assertEqual(migration_baseline.compare(base, dict(base)), [])
        mismatch = dict(base)
        mismatch["tables"] = dict(base["tables"])
        mismatch["tables"]["opportunities"] = 2
        self.assertTrue(migration_baseline.compare(base, mismatch))


if __name__ == "__main__":
    unittest.main()
