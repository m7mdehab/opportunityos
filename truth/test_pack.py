"""Tests for truth.pack: founder truth pack loading and reporting.

All tests use explicit temporary paths. None of these tests read, write, or
list anything under private/ -- the DEFAULT_TRUTH_PACK_PATH constant is
exercised only as a value, never dereferenced against the real filesystem.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from truth.pack import (
    DEFAULT_TRUTH_PACK_PATH,
    LoadedPack,
    TruthPackInvalid,
    TruthPackMissing,
    load_founder_pack,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "docs" / "templates" / "truth_pack.template.yaml"
TRUTH_CHECK_SCRIPT = REPO_ROOT / "scripts" / "truth_check.py"

# Distinctive, obviously-synthetic values that appear in the shipped
# template. If any of these ever show up in truth_check.py's output, the
# script is leaking field values.
TEMPLATE_DISTINCTIVE_VALUES = (
    "Jane Q. Example",
    "Example Industries Ltd",
    "Senior Widget Engineer",
    "Certified Widget Professional",
    "Widget Design",
    "Example State University",
)


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def _minimal_pack_yaml(*, reason: str = "keep it honest", key_order: str = "forward") -> str:
    """A small, self-contained pack that loads cleanly.

    `key_order` == "reversed" reorders mapping keys (but not list contents)
    relative to "forward", to prove the truth_pack_hash does not depend on
    incidental key ordering.
    """
    if key_order == "forward":
        evidence_block = (
            '  - id: ev-role\n'
            '    content: "Example Engineer at Example Org from 2024-01-01"\n'
            '    source: "fixture"\n'
            '    locator: "employment.0"\n'
            '    metadata: {"organization": "Example Org", "title": "Example Engineer"}\n'
        )
        employment_block = (
            '    - id: job-example\n'
            '      organization: "Example Org"\n'
            '      title: "Example Engineer"\n'
            '      start_date: "2024-01-01"\n'
            '      evidence_ids: ["ev-role"]\n'
        )
    else:
        evidence_block = (
            '  - id: ev-role\n'
            '    locator: "employment.0"\n'
            '    source: "fixture"\n'
            '    metadata: {"title": "Example Engineer", "organization": "Example Org"}\n'
            '    content: "Example Engineer at Example Org from 2024-01-01"\n'
        )
        employment_block = (
            '    - id: job-example\n'
            '      evidence_ids: ["ev-role"]\n'
            '      start_date: "2024-01-01"\n'
            '      title: "Example Engineer"\n'
            '      organization: "Example Org"\n'
        )

    return (
        "evidence:\n"
        f"{evidence_block}"
        "career_profile:\n"
        "  id: career-example\n"
        "  employment:\n"
        f"{employment_block}"
        "  red_lines:\n"
        "    - id: redline-1\n"
        '      pattern: "test pattern"\n'
        f'      reason: "{reason}"\n'
    )


class LoadFounderPackMissingTest(unittest.TestCase):
    def test_missing_file_raises_truth_pack_missing(self):
        with TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "does-not-exist.yaml"
            with self.assertRaises(TruthPackMissing):
                load_founder_pack(missing_path)


class LoadFounderPackInvalidTest(unittest.TestCase):
    def test_invalid_pack_raises_truth_pack_invalid_with_findings(self):
        with TemporaryDirectory() as tmp:
            path = _write(
                Path(tmp), "broken.yaml",
                "evidence:\n"
                "  - id: ev-role\n"
                '    content: "Example Engineer at Example Org from 2024-01-01"\n'
                '    source: "fixture"\n'
                '    locator: "employment.0"\n'
                "career_profile:\n"
                "  id: career-example\n"
                "  employment:\n"
                "    - id: job-example\n"
                '      organization: "Example Org"\n'
                '      title: "Example Engineer"\n'
                '      start_date: "2024-01-01"\n'
                '      evidence_ids: ["ev-nonexistent"]\n',
            )
            with self.assertRaises(TruthPackInvalid) as ctx:
                load_founder_pack(path)
            self.assertTrue(ctx.exception.findings)
            self.assertIn("ev-nonexistent", ctx.exception.findings[0])


class LoadFounderPackDefaultPathTest(unittest.TestCase):
    def test_default_path_constant_is_private_truth_pack(self):
        self.assertEqual(Path("private/truth_pack.yaml"), DEFAULT_TRUTH_PACK_PATH)


class LoadFounderPackHashTest(unittest.TestCase):
    def test_hash_stable_across_two_loads_of_same_file(self):
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "pack.yaml", _minimal_pack_yaml())
            first = load_founder_pack(path)
            second = load_founder_pack(path)
            self.assertEqual(first.truth_pack_hash, second.truth_pack_hash)

    def test_hash_stable_across_key_ordering(self):
        with TemporaryDirectory() as tmp:
            forward = _write(Path(tmp), "forward.yaml", _minimal_pack_yaml(key_order="forward"))
            reversed_ = _write(Path(tmp), "reversed.yaml", _minimal_pack_yaml(key_order="reversed"))
            forward_pack = load_founder_pack(forward)
            reversed_pack = load_founder_pack(reversed_)
            self.assertEqual(forward_pack.truth_pack_hash, reversed_pack.truth_pack_hash)

    def test_hash_changes_when_content_changes(self):
        with TemporaryDirectory() as tmp:
            path_a = _write(Path(tmp), "a.yaml", _minimal_pack_yaml(reason="keep it honest"))
            path_b = _write(Path(tmp), "b.yaml", _minimal_pack_yaml(reason="a materially different reason"))
            pack_a = load_founder_pack(path_a)
            pack_b = load_founder_pack(path_b)
            self.assertNotEqual(pack_a.truth_pack_hash, pack_b.truth_pack_hash)


class LoadFounderPackReportTest(unittest.TestCase):
    def test_report_and_loaded_pack_shape(self):
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "pack.yaml", _minimal_pack_yaml())
            loaded = load_founder_pack(path)
            self.assertIsInstance(loaded, LoadedPack)
            self.assertTrue(loaded.report.valid)
            self.assertEqual((), loaded.report.findings)
            counts = dict(loaded.report.section_counts)
            self.assertEqual(1, counts["evidence"])
            self.assertEqual(1, counts["career_profile"])
            self.assertEqual(1, counts["career_profile.employment"])
            self.assertEqual(0, counts["career_profile.education"])
            self.assertIn("career_profile.education", loaded.report.empty_sections())


class TruthPackTemplateTest(unittest.TestCase):
    """The shipped template must load cleanly, as-is, with zero errors."""

    def test_template_loads_with_zero_validator_errors(self):
        self.assertTrue(TEMPLATE_PATH.exists(), f"template missing at {TEMPLATE_PATH}")
        loaded = load_founder_pack(TEMPLATE_PATH)
        self.assertTrue(loaded.report.valid)
        self.assertEqual((), loaded.report.findings)
        self.assertTrue(loaded.truth_pack_hash)

    def test_template_covers_every_documented_section(self):
        loaded = load_founder_pack(TEMPLATE_PATH)
        counts = dict(loaded.report.section_counts)
        self.assertEqual(1, counts["career_profile"])
        self.assertEqual(1, counts["capability_profile"])
        for name, count in counts.items():
            self.assertGreater(count, 0, f"template section {name} is unexpectedly empty")


class TruthCheckScriptTest(unittest.TestCase):
    def _run(self, path: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TRUTH_CHECK_SCRIPT), "--path", str(path)],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )

    def test_template_copy_exits_zero(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tp.yaml"
            path.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            result = self._run(path)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_broken_copy_exits_one_with_findings(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tp.yaml"
            broken = TEMPLATE_PATH.read_text(encoding="utf-8").replace(
                'state: "completed"', 'state: "bogus_state"'
            )
            self.assertIn('state: "bogus_state"', broken)
            path.write_text(broken, encoding="utf-8")
            result = self._run(path)
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("INVALID", result.stdout)
            self.assertIn("finding:", result.stdout)

    def test_output_contains_no_template_field_values(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tp.yaml"
            path.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            result = self._run(path)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for value in TEMPLATE_DISTINCTIVE_VALUES:
                self.assertNotIn(value, result.stdout)
                self.assertNotIn(value.lower(), result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
