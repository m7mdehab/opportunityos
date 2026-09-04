#!/usr/bin/env python3
"""Unit tests for scripts/truth_check.py (BRIEF-FR-006 F1).

Runs both standalone (python scripts/test_truth_check.py -v) and, once
scripts/__init__.py exists, as a package module
(python -m unittest scripts.test_truth_check -v).

F1.3/F1.4 acceptance: a pack with a distinctive sentinel string in every
field -- including the new `identity` and `approved_phrases` sections --
must produce stdout that never contains that sentinel, and the command must
exit 0. This is load-bearing: it is the only way the founder can validate a
pack without an agent reading it (see F1-identity.md).
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
try:
    from scripts.truth_check import main
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from truth_check import main

SENTINEL = "SENTINEL_VALUE_TEXT_9f3c2"

_LEAK_PACK = f"""
evidence:
  - id: ev-employment
    content: "{SENTINEL} worked as {SENTINEL} at {SENTINEL} from 2021-01-01 to 2022-01-01."
    source: "{SENTINEL}"
    locator: "employment.0"
    metadata: {{"organization": "{SENTINEL}", "title": "{SENTINEL}"}}
  - id: ev-identity
    content: "{SENTINEL} contact {SENTINEL}@example.com {SENTINEL} linkedin {SENTINEL} github {SENTINEL} website {SENTINEL} city {SENTINEL} country {SENTINEL}"
    source: "self_reported"
    locator: "identity"
  - id: ev-phrase
    content: "{SENTINEL} phrase text"
    source: "self_reported"
    locator: "approved_phrases.0"

identity:
  name: "{SENTINEL}"
  evidence_ids: ["ev-identity"]
  headline: "{SENTINEL}"
  email: "{SENTINEL}@example.com"
  phone: "{SENTINEL}"
  linkedin: "{SENTINEL}"
  github: "{SENTINEL}"
  website: "{SENTINEL}"
  location_city: "{SENTINEL}"
  location_country: "{SENTINEL}"

approved_phrases:
  - id: phrase-1
    text: "{SENTINEL} phrase text"
    evidence_ids: ["ev-phrase"]
    tags: ["{SENTINEL}"]

career_profile:
  id: career-1
  employment:
    - id: job-1
      organization: "{SENTINEL}"
      title: "{SENTINEL}"
      start_date: "2021-01-01"
      end_date: "2022-01-01"
      evidence_ids: ["ev-employment"]

assertions: []
relations: []
metrics: []
"""


class TruthCheckLeakTests(unittest.TestCase):
    def _write_pack(self, text: str) -> pathlib.Path:
        tmp_dir = pathlib.Path(tempfile.mkdtemp())
        pack_path = tmp_dir / "pack.yaml"
        pack_path.write_text(text, encoding="utf-8")
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return pack_path

    def test_exit_zero_and_reports_identity_and_approved_phrases_counts(self) -> None:
        pack_path = self._write_pack(_LEAK_PACK)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(["--path", str(pack_path)])
        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("identity: 1", output)
        self.assertIn("approved_phrases: 1", output)

    def test_no_value_text_leaks_for_any_field(self) -> None:
        pack_path = self._write_pack(_LEAK_PACK)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(["--path", str(pack_path)])
        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            output.count(SENTINEL), 0,
            "scripts/truth_check.py must never print evidence/field value text",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
