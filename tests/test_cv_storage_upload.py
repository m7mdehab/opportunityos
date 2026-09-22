from __future__ import annotations

import hashlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.upload_cv_storage_objects import UploadObject, prepare_objects, upload_objects


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TestCvStorageUpload(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        (self.root / "CVs").mkdir()
        self.source_path = self.root / "CVs" / "candidate.pdf"
        self.source_path.write_bytes(b"canonical candidate data")
        self.package_path = self.root / "package.zip"
        self.package_path.write_bytes(b"canonical package")
        self.manifest = {
            "project_ref": "sunjfepvdzfknglrjwhm",
            "bucket": "founder-cv-portfolio",
            "private": True,
            "object_count": 2,
            "total_bytes": self.source_path.stat().st_size + self.package_path.stat().st_size,
            "objects": [
                {
                    "object_key": "2026/candidate.pdf",
                    "source": "CVs/candidate.pdf",
                    "kind": "canonical-pdf",
                    "bytes": self.source_path.stat().st_size,
                    "sha256": hashlib.sha256(self.source_path.read_bytes()).hexdigest(),
                },
                {
                    "object_key": "2026/system/package.zip",
                    "source": "package.zip",
                    "kind": "canonical-source-package",
                    "bytes": self.package_path.stat().st_size,
                    "sha256": hashlib.sha256(self.package_path.read_bytes()).hexdigest(),
                },
            ],
        }
        self.base_url = "https://sunjfepvdzfknglrjwhm.supabase.co"

    def test_preflight_verifies_all_exact_sources_before_upload(self) -> None:
        prepared = prepare_objects(
            self.manifest,
            source_root=self.root,
            package_zip=self.package_path,
            base_url=self.base_url,
        )
        self.assertEqual([item.object_key for item in prepared], ["2026/candidate.pdf", "2026/system/package.zip"])
        self.assertEqual(prepared[0].content_type, "application/pdf")

    def test_checksum_mismatch_fails_preflight(self) -> None:
        self.manifest["objects"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            prepare_objects(
                self.manifest,
                source_root=self.root,
                package_zip=self.package_path,
                base_url=self.base_url,
            )

    def test_preflight_rejects_unsafe_source_path(self) -> None:
        self.manifest["objects"][0]["source"] = "../outside.pdf"
        with self.assertRaisesRegex(ValueError, "unsafe source path"):
            prepare_objects(
                self.manifest,
                source_root=self.root,
                package_zip=self.package_path,
                base_url=self.base_url,
            )

    def test_upload_uses_private_service_auth_and_resumable_upsert(self) -> None:
        item = UploadObject("2026/a file.pdf", b"payload", "application/pdf")
        captured = []

        def fake_urlopen(request, timeout):
            captured.append((request, timeout))
            return _FakeResponse()

        with patch("scripts.upload_cv_storage_objects.urlopen", fake_urlopen):
            result = upload_objects(
                [item],
                base_url=self.base_url,
                bucket="founder-cv-portfolio",
                service_key="do-not-log-this",
            )

        request, timeout = captured[0]
        self.assertEqual(request.full_url, f"{self.base_url}/storage/v1/object/founder-cv-portfolio/2026/a%20file.pdf")
        self.assertEqual(request.get_header("Authorization"), "Bearer do-not-log-this")
        self.assertEqual(request.get_header("X-upsert"), "true")
        self.assertEqual(request.data, b"payload")
        self.assertEqual(timeout, 60)
        self.assertEqual(result, {"objects_uploaded": 1, "bytes_uploaded": 7})

    def test_upload_error_is_sanitized(self) -> None:
        def fail_urlopen(_request, **_kwargs):
            body = json.dumps({"error": "StorageApiError", "message": "rejected do-not-log-this"}).encode()
            raise HTTPError("https://example.invalid", 403, "forbidden", {}, io.BytesIO(body))

        with patch("scripts.upload_cv_storage_objects.urlopen", fail_urlopen):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403") as context:
                upload_objects(
                    [UploadObject("x.pdf", b"x", "application/pdf")],
                    base_url=self.base_url,
                    bucket="founder-cv-portfolio",
                    service_key="do-not-log-this",
                )
        self.assertNotIn("do-not-log-this", str(context.exception))
        self.assertIn("rejected [redacted]", str(context.exception))

    def test_hosted_verifier_reads_public_url_from_environment_variables(self) -> None:
        workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "fr007-storage-v2-postgres.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("SUPABASE_URL: ${{ vars.SUPABASE_URL || secrets.SUPABASE_URL }}", workflow)
        self.assertIn("STORAGE_SERVICE_KEY: ${{ secrets.STORAGE_SERVICE_KEY }}", workflow)


if __name__ == "__main__":
    unittest.main()
