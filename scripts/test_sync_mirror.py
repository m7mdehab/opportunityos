from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from scripts import sync_mirror
except ImportError:  # running as `python scripts/test_sync_mirror.py` directly
    import sync_mirror


class SyncMirrorTest(unittest.TestCase):
    def test_fr008_private_paths_are_excluded_and_safe_docs_remain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            (source / ".git").mkdir(parents=True)
            (destination / ".git").mkdir(parents=True)
            (source / ".mirror-allowlist").write_text(
                (Path(__file__).resolve().parents[1] / ".mirror-allowlist").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            paths = [
                "briefs/BRIEF-SAFE-001.md",
                "reports/REPORT-SAFE-001.md",
                "briefs/BRIEF-FR-008.md",
                "briefs/FR-008-FOLLOW-UP.md",
                "reports/REPORT-FR-008.md",
                "reports/evidence/FR-008/orders/example.txt",
            ]
            for relative in paths:
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("synthetic mirror fixture\n", encoding="utf-8")

            tracked = subprocess.CompletedProcess(
                args=["git", "ls-files", "-z"],
                returncode=0,
                stdout=("\0".join(paths) + "\0").encode("utf-8"),
                stderr=b"",
            )
            argv = [
                "sync_mirror.py",
                str(source),
                str(destination),
                "--source-sha",
                "test-sha",
                "--sync-time",
                "2026-09-25T00:00:00Z",
            ]

            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                sync_mirror.subprocess, "run", return_value=tracked
            ):
                sync_mirror.main()

            self.assertTrue((destination / "briefs/BRIEF-SAFE-001.md").is_file())
            self.assertTrue((destination / "reports/REPORT-SAFE-001.md").is_file())
            for relative in paths[2:]:
                self.assertFalse((destination / relative).exists(), relative)

    def test_workflow_uses_original_source_path_when_remapped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            workflow = source / ".github" / "workflows" / "foo.yml"

            (source / ".git").mkdir(parents=True)
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: test\n", encoding="utf-8")
            (source / ".mirror-allowlist").write_text(
                ".github/workflows/**\n", encoding="utf-8"
            )
            (destination / ".git").mkdir(parents=True)

            tracked = subprocess.CompletedProcess(
                args=["git", "ls-files", "-z"],
                returncode=0,
                stdout=b".github/workflows/foo.yml\0",
                stderr=b"",
            )
            argv = [
                "sync_mirror.py",
                str(source),
                str(destination),
                "--source-sha",
                "test-sha",
                "--sync-time",
                "2026-08-29T00:00:00Z",
            ]

            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                sync_mirror.subprocess, "run", return_value=tracked
            ):
                sync_mirror.main()

            copied = destination / "ci-reference" / "workflows" / "foo.yml"
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.read_text(encoding="utf-8"), "name: test\n")

    def test_pii_patterns_uses_original_source_path_when_remapped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            pii_file = source / ".github" / "pii-patterns.txt"

            (source / ".git").mkdir(parents=True)
            pii_file.parent.mkdir(parents=True)
            pii_file.write_text("pattern1\n", encoding="utf-8")
            (source / ".mirror-allowlist").write_text(
                ".github/pii-patterns.txt\n", encoding="utf-8"
            )
            (destination / ".git").mkdir(parents=True)

            tracked = subprocess.CompletedProcess(
                args=["git", "ls-files", "-z"],
                returncode=0,
                stdout=b".github/pii-patterns.txt\0",
                stderr=b"",
            )
            argv = [
                "sync_mirror.py",
                str(source),
                str(destination),
                "--source-sha",
                "test-sha",
                "--sync-time",
                "2026-08-29T00:00:00Z",
            ]

            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                sync_mirror.subprocess, "run", return_value=tracked
            ):
                sync_mirror.main()

            copied = destination / "ci-reference" / "pii-patterns.txt"
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.read_text(encoding="utf-8"), "pattern1\n")


if __name__ == "__main__":
    unittest.main()
