"""Tests for AdapterRegistry and SourceActionRegistry graduation and evidence authority."""
import tempfile
import unittest
from pathlib import Path
from outbound.models import AdapterLifecycleState, SourceActionPolicy
from outbound.registry import AdapterRegistry, SourceActionRegistry


class RegistryTests(unittest.TestCase):
    def test_missing_graduation_evidence_caps_lifecycle_at_assisted_verified(self) -> None:
        with tempfile.TemporaryDirectory() as empty_dir:
            reg = AdapterRegistry(evidence_dir=Path(empty_dir))
            gh_rec = reg.get_graduation_record("greenhouse")
            self.assertIsNotNone(gh_rec)
            # Without evidence file, Greenhouse cannot be SUBMIT_ELIGIBLE
            self.assertEqual(gh_rec.lifecycle_state, AdapterLifecycleState.ASSISTED_VERIFIED)
            self.assertEqual(gh_rec.evidence_hash, "")

            # Attempting to enable submit without valid evidence raises ValueError
            with self.assertRaises(ValueError):
                reg.enable_submit("greenhouse")

    def test_valid_graduation_evidence_allows_submit_enable(self) -> None:
        reg = AdapterRegistry()  # Uses real fixtures/graduation directory
        gh_rec = reg.get_graduation_record("greenhouse")
        self.assertIsNotNone(gh_rec)
        self.assertEqual(gh_rec.lifecycle_state, AdapterLifecycleState.SUBMIT_ELIGIBLE)
        self.assertTrue(len(gh_rec.evidence_hash) > 0)

        reg.enable_submit("greenhouse")
        updated = reg.get_graduation_record("greenhouse")
        self.assertEqual(updated.lifecycle_state, AdapterLifecycleState.SUBMIT_ENABLED)
        self.assertTrue(updated.submit_enabled_by_founder)


if __name__ == "__main__":
    unittest.main()
