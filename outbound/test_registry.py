"""Tests for AdapterRegistry dynamic graduation evidence validation and runtime invalidation."""
import json
import tempfile
import unittest
from pathlib import Path
from outbound.models import AdapterLifecycleState, GraduationRecord
from outbound.registry import AdapterRegistry


class RegistryTests(unittest.TestCase):
    def test_production_default_adapters_are_assisted_verified(self) -> None:
        reg = AdapterRegistry()
        gh_rec = reg.get_graduation_record("greenhouse")
        self.assertIsNotNone(gh_rec)
        self.assertEqual(gh_rec.lifecycle_state, AdapterLifecycleState.ASSISTED_VERIFIED)
        self.assertEqual(gh_rec.evidence_hash, "")

    def test_evidence_deleted_after_initialization_invalidates_submit_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ev_dir = Path(temp_dir)
            gh_file = ev_dir / "greenhouse_graduation_evidence.json"
            gh_file.write_text(json.dumps({"test_run_id": "run-101", "success": True}), encoding="utf-8")

            reg = AdapterRegistry(evidence_dir=ev_dir)
            rec = reg.get_graduation_record("greenhouse")
            self.assertIsNotNone(rec)
            self.assertEqual(rec.lifecycle_state, AdapterLifecycleState.SUBMIT_ELIGIBLE)
            self.assertTrue(len(rec.evidence_hash) > 0)

            # Enable submit while evidence is valid
            reg.enable_submit("greenhouse")
            self.assertEqual(reg.get_graduation_record("greenhouse").lifecycle_state, AdapterLifecycleState.SUBMIT_ENABLED)

            # Delete evidence file on disk AFTER initialization
            gh_file.unlink()

            # Dynamic check on get_graduation_record must downgrade to ASSISTED_VERIFIED
            downgraded = reg.get_graduation_record("greenhouse")
            self.assertEqual(downgraded.lifecycle_state, AdapterLifecycleState.ASSISTED_VERIFIED)
            self.assertEqual(downgraded.evidence_hash, "")
            self.assertFalse(downgraded.submit_enabled_by_founder)

            # Subsequent enable_submit must fail
            with self.assertRaises(ValueError):
                reg.enable_submit("greenhouse")

    def test_evidence_corrupted_after_initialization_invalidates_submit_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ev_dir = Path(temp_dir)
            gh_file = ev_dir / "greenhouse_graduation_evidence.json"
            gh_file.write_text(json.dumps({"test_run_id": "run-101", "success": True}), encoding="utf-8")

            reg = AdapterRegistry(evidence_dir=ev_dir)
            self.assertEqual(reg.get_graduation_record("greenhouse").lifecycle_state, AdapterLifecycleState.SUBMIT_ELIGIBLE)

            # Corrupt evidence file
            gh_file.write_text("NOT_VALID_JSON_CORRUPTED", encoding="utf-8")

            downgraded = reg.get_graduation_record("greenhouse")
            self.assertEqual(downgraded.lifecycle_state, AdapterLifecycleState.ASSISTED_VERIFIED)

    def test_evidence_modified_after_initialization_invalidates_submit_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ev_dir = Path(temp_dir)
            gh_file = ev_dir / "greenhouse_graduation_evidence.json"
            gh_file.write_text(json.dumps({"test_run_id": "run-101", "success": True}), encoding="utf-8")

            reg = AdapterRegistry(evidence_dir=ev_dir)
            reg.enable_submit("greenhouse")
            self.assertEqual(reg.get_graduation_record("greenhouse").lifecycle_state, AdapterLifecycleState.SUBMIT_ENABLED)

            # Modify evidence content (changes SHA digest without updating record)
            gh_file.write_text(json.dumps({"test_run_id": "run-102_modified", "success": True}), encoding="utf-8")

            downgraded = reg.get_graduation_record("greenhouse")
            self.assertEqual(downgraded.lifecycle_state, AdapterLifecycleState.ASSISTED_VERIFIED)


if __name__ == "__main__":
    unittest.main()
