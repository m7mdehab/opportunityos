"""Tests for scripts/generate_readiness_matrix.py and the matrix data it renders.

Runnable both as a direct script (``python scripts/test_readiness_matrix.py -v``,
today) and, once ``scripts/__init__.py`` lands, as a discovered package module
(``python -m unittest scripts.test_readiness_matrix -v``). The import guard
below picks whichever form resolves.
"""
from __future__ import annotations

import copy
import json
import re
import unittest
from collections import Counter
from pathlib import Path

try:
    from scripts import generate_readiness_matrix as grm
except ImportError:  # running as a direct script before scripts/__init__.py exists
    import generate_readiness_matrix as grm


ALLOWED_STATUSES = {
    "DONE",
    "PARTIAL",
    "MISSING",
    "INTENTIONALLY_DEFERRED",
    "REQUIRES_LIVE_INTEGRATION_OR_CREDENTIALS",
}

REQ_ID_PATTERN = re.compile(r"REQ-[A-Z0-9]+-\d+")

TOTALS_HEADING_PATTERN = re.compile(
    r"(?ims)^###\s+Primary Status Counts\s*\(Total = (\d+)\)\s*:\s*$\n(.*?)(?=^###|\Z)"
)
TOTALS_LINE_PATTERN = re.compile(r"-\s+\*\*`([A-Z0-9_]+)`:\*\*\s*(\d+)")


class ReadinessMatrixDataTest(unittest.TestCase):
    """Invariants over reports/FOUNDER_READINESS_MATRIX.json itself."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows: list[dict] = grm.load_rows()

    def test_req_ids_are_unique(self) -> None:
        req_ids = [row["req_id"] for row in self.rows]
        duplicates = [req_id for req_id, count in Counter(req_ids).items() if count > 1]
        self.assertEqual(duplicates, [], f"duplicate req_id values: {duplicates}")

    def test_every_status_is_in_allowed_set(self) -> None:
        offenders = {
            row["req_id"]: row["status"]
            for row in self.rows
            if row["status"] not in ALLOWED_STATUSES
        }
        self.assertEqual(offenders, {}, f"rows with disallowed status: {offenders}")


class ReadinessMatrixRenderTest(unittest.TestCase):
    """Invariants over the generated Markdown, compared against the JSON."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows: list[dict] = grm.load_rows()
        cls.rendered: str = grm.render(cls.rows)

    def test_rendered_totals_equal_json_counts(self) -> None:
        expected = Counter(row["status"] for row in self.rows)

        match = TOTALS_HEADING_PATTERN.search(self.rendered)
        self.assertIsNotNone(match, "Primary Status Counts section not found in rendered output")
        rendered_total = int(match.group(1))
        body = match.group(2)

        observed: dict[str, int] = {}
        for status, count in TOTALS_LINE_PATTERN.findall(body):
            observed[status] = int(count)

        self.assertEqual(rendered_total, sum(expected.values()))
        self.assertEqual(observed, dict(expected))

    def test_req_ids_mentioned_in_reports_exist_in_matrix(self) -> None:
        known_ids = {row["req_id"] for row in self.rows}
        for report_name in ("REPORT-FR-002.md", "REPORT-FR-003.md"):
            report_path = grm.ROOT / "reports" / report_name
            if not report_path.exists():
                # REPORT-FR-003.md does not exist yet as of this brief; treated
                # as nothing to check until it lands.
                continue
            text = report_path.read_text(encoding="utf-8")
            mentioned = set(REQ_ID_PATTERN.findall(text))
            missing = sorted(mentioned - known_ids)
            self.assertEqual(
                missing,
                [],
                f"{report_name} mentions REQ- IDs absent from "
                f"{grm.JSON_PATH.relative_to(grm.ROOT)}: {missing}",
            )

    def test_rendered_output_matches_committed_markdown(self) -> None:
        self.assertTrue(
            grm.MD_PATH.exists(),
            f"{grm.MD_PATH.relative_to(grm.ROOT)} does not exist; run "
            "scripts/generate_readiness_matrix.py",
        )
        on_disk = grm.MD_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            on_disk,
            self.rendered,
            f"{grm.MD_PATH.relative_to(grm.ROOT)} is stale relative to "
            f"{grm.JSON_PATH.relative_to(grm.ROOT)}; regenerate it with "
            "scripts/generate_readiness_matrix.py",
        )

    def test_status_history_is_tolerated_but_not_rendered(self) -> None:
        rows_with_history = copy.deepcopy(self.rows)
        for row in rows_with_history:
            row["status_history"] = [
                {"brief": "BRIEF-FR-003", "from": "MISSING", "to": row["status"], "date": "2026-09-02"}
            ]
        rendered = grm.render(rows_with_history)  # must not raise
        self.assertNotIn("status_history", rendered)


if __name__ == "__main__":
    unittest.main()
