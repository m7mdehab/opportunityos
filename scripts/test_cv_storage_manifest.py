from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts.verify_cv_storage_objects import verify_objects


class CVStorageManifestTests(TestCase):
    def test_checked_in_manifest_covers_the_exact_canonical_portfolio(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "founder" / "cv_storage_objects.json").read_text(encoding="utf-8"))
        objects = manifest["objects"]
        self.assertEqual(manifest["project_ref"], "sunjfepvdzfknglrjwhm")
        self.assertTrue(manifest["private"])
        self.assertEqual(manifest["object_count"], 31)
        self.assertEqual(len(objects), 31)
        self.assertEqual(len({item["object_key"] for item in objects}), 31)
        self.assertEqual(sum(item["kind"] == "canonical-pdf" for item in objects), 9)
        self.assertEqual(sum(item["kind"] == "canonical-editable-docx" for item in objects), 9)
        self.assertEqual(sum(item["kind"] == "supporting-document" for item in objects), 11)
        self.assertEqual(sum(item["kind"] == "canonical-source-package" for item in objects), 1)
        self.assertEqual(manifest["total_bytes"], sum(item["bytes"] for item in objects))
        self.assertTrue(all(len(item["sha256"]) == 64 for item in objects))

    def test_private_download_verifier_checks_exact_bytes_and_hash(self) -> None:
        payload = b"canonical private object"
        manifest = {
            "bucket": "founder-cv-portfolio",
            "objects": [{
                "object_key": "2026/system/example.bin",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }],
        }

        with patch("scripts.verify_cv_storage_objects.urlopen", return_value=io.BytesIO(payload)):
            result = verify_objects(manifest, base_url="https://example.supabase.co", service_key="not-logged")

        self.assertEqual(result, {"objects_verified": 1, "bytes_downloaded": len(payload)})

    def test_private_download_verifier_fails_closed_on_checksum_mismatch(self) -> None:
        payload = b"wrong bytes"
        manifest = {
            "bucket": "founder-cv-portfolio",
            "objects": [{"object_key": "2026/file", "bytes": len(payload), "sha256": "0" * 64}],
        }

        with patch("scripts.verify_cv_storage_objects.urlopen", return_value=io.BytesIO(payload)):
            with self.assertRaisesRegex(RuntimeError, "integrity mismatch"):
                verify_objects(manifest, base_url="https://example.supabase.co", service_key="not-logged")
