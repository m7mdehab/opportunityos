from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import generate_state


class ReportDecisionSemanticsTest(unittest.TestCase):
    def test_inline_pass_with_not_closed_is_non_terminal(self) -> None:
        report = "**Decision: `PASS_WITH_NOT_CLOSED`.**\n"
        decision = generate_state.decision_line(report)
        self.assertEqual(decision, "PASS_WITH_NOT_CLOSED")
        self.assertFalse(generate_state.is_terminal_pass(decision))

    def test_historical_final_pass_remains_terminal(self) -> None:
        report = "## Decision\n\n**FINAL / PASS**\n"
        decision = generate_state.decision_line(report)
        self.assertEqual(decision, "FINAL / PASS")
        self.assertTrue(generate_state.is_terminal_pass(decision))


class ReportOpenAcceptanceItemsTest(unittest.TestCase):
    def test_named_not_closed_rows_are_exposed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "REPORT-FR-006.md"
            report.write_text(
                "**Decision: `PASS_WITH_NOT_CLOSED`.**\n\n"
                "| Claim | Result |\n"
                "|---|---|\n"
                "| A-1 full suite | **PASS** |\n"
                "| A-12 extraction | **NOT_CLOSED** — work mode below gate |\n"
                "| A-13 scoring | **NOT_CLOSED** — title family below gate |\n"
                "| A-21 cards | **PASS** |\n",
                encoding="utf-8",
            )
            items = generate_state.report_open_acceptance_items(report)

        self.assertEqual(
            items,
            [
                "A-12 extraction — unresolved in latest report",
                "A-13 scoring — unresolved in latest report",
            ],
        )

    def test_non_terminal_report_without_table_never_becomes_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "REPORT-FR-006.md"
            report.write_text("**Decision: `PASS_WITH_NOT_CLOSED`.**\n", encoding="utf-8")
            items = generate_state.report_open_acceptance_items(report)

        self.assertEqual(items, ["Latest report decision is PASS_WITH_NOT_CLOSED"])


class ActiveStateReportTruthTest(unittest.TestCase):
    def test_fr006_pass_with_not_closed_stays_active_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs" / "adr").mkdir(parents=True)
            (root / "briefs").mkdir(parents=True)
            (root / "reports").mkdir(parents=True)
            state_path = root / "docs" / "STATE.md"

            (root / "briefs" / "BRIEF-FR-006.md").write_text(
                "# BRIEF-FR-006\n", encoding="utf-8"
            )
            (root / "reports" / "REPORT-FR-006.md").write_text(
                "**Date:** 2026-09-04\n\n"
                "**Decision: `PASS_WITH_NOT_CLOSED`.**\n\n"
                "| Claim | Result |\n"
                "|---|---|\n"
                "| A-12 extraction | **NOT_CLOSED** — below target |\n"
                "| A-23 breadth | **NOT_CLOSED** — below target |\n",
                encoding="utf-8",
            )

            with mock.patch.object(generate_state, "ROOT", root), mock.patch.object(
                generate_state, "STATE_PATH", state_path
            ):
                generate_state.main()

            state = state_path.read_text(encoding="utf-8")

        self.assertIn("Active work: BRIEF-FR-006.", state)
        self.assertIn("Phase status: in progress.", state)
        self.assertIn("Open acceptance items:** 2", state)
        self.assertIn("A-12 extraction — unresolved in latest report", state)
        self.assertIn("A-23 breadth — unresolved in latest report", state)
        self.assertNotIn("BRIEF-FR-006 — 2026-09-04", state)

    def test_latest_fr_brief_wins_over_superseded_partial_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs" / "adr").mkdir(parents=True)
            (root / "briefs").mkdir(parents=True)
            (root / "reports").mkdir(parents=True)
            state_path = root / "docs" / "STATE.md"

            for tag in ("004", "006"):
                (root / "briefs" / f"BRIEF-FR-{tag}.md").write_text(
                    f"# BRIEF-FR-{tag}\n", encoding="utf-8"
                )
            (root / "reports" / "REPORT-FR-004.md").write_text(
                "**Date:** 2026-09-02\n\n**Decision: `PASS_WITH_NOT_CLOSED`.**\n",
                encoding="utf-8",
            )
            (root / "reports" / "REPORT-FR-006.md").write_text(
                "**Date:** 2026-09-04\n\n"
                "**Decision: `PASS_WITH_NOT_CLOSED`.**\n\n"
                "| Claim | Result |\n|---|---|\n"
                "| A-23 breadth | **NOT_CLOSED** — below target |\n",
                encoding="utf-8",
            )

            with mock.patch.object(generate_state, "ROOT", root), mock.patch.object(
                generate_state, "STATE_PATH", state_path
            ):
                generate_state.main()

            state = state_path.read_text(encoding="utf-8")

        self.assertIn("Active work: BRIEF-FR-006.", state)
        self.assertNotIn("Active work: BRIEF-FR-004.", state)
        self.assertIn("A-23 breadth — unresolved in latest report", state)


if __name__ == "__main__":
    unittest.main()
