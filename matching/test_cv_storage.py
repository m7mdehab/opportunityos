"""Unit tests for immutable fixed-CV storage integrity."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from matching.cv_selector import CVVariant
from matching.cv_storage import CVStorageError, fetch_cv_bytes, verify_cv_bytes


class FixedCVStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = b"%PDF-1.7\nfixed-cv-test\n%%EOF\n"
        self.variant = CVVariant(
            variant="fixture",
            filename="fixture.pdf",
            object_path="2026/fixture.pdf",
            sha256=hashlib.sha256(self.payload).hexdigest(),
        )

    def test_local_exact_bytes_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, self.variant.filename).write_bytes(self.payload)
            result = fetch_cv_bytes(self.variant, environ={"OPPORTUNITYOS_CV_DIR": temp})
        self.assertEqual(result, self.payload)

    def test_hash_mismatch_fails_closed(self) -> None:
        bad = CVVariant("fixture", "fixture.pdf", "2026/fixture.pdf", "0" * 64)
        with self.assertRaises(CVStorageError):
            verify_cv_bytes(bad, self.payload)

    def test_non_pdf_fails_closed(self) -> None:
        payload = b"not a PDF"
        variant = CVVariant(
            "fixture", "fixture.pdf", "2026/fixture.pdf",
            hashlib.sha256(payload).hexdigest(),
        )
        with self.assertRaises(CVStorageError):
            verify_cv_bytes(variant, payload)

    def test_missing_hosted_config_fails_closed(self) -> None:
        with self.assertRaises(CVStorageError):
            fetch_cv_bytes(self.variant, environ={})

    def test_no_generated_fallback_when_local_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(CVStorageError):
                fetch_cv_bytes(self.variant, environ={"OPPORTUNITYOS_CV_DIR": temp})


if __name__ == "__main__":
    unittest.main()
