from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import generate_state
except ImportError:  # running as `python -m unittest scripts.test_generate_state`
    from scripts import generate_state


class GenerateStateTest(unittest.TestCase):
    def test_state_generation_recognizes_gate_fr_001_and_blocks_brief_007(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            docs.mkdir(parents=True)
            state_path = docs / "STATE.md"
            
            reports = root / "reports"
            reports.mkdir(parents=True)
            gate_report = reports / "REPORT-FR-001.md"
            gate_report.write_text(
                "# Gate Report: GATE-FR-001\n\n"
                "## 6. Final Recommendation\n\n"
                "**FINAL RECOMMENDATION: ORDERED SEQUENCE (C + A) -> B -> D**\n"
                "- **Immediate Next Phase: PHASE 0/1 FOUNDATION & WEB INTEGRATION**\n\n"
                "**PRIVATE FAMILY ALPHA (BRIEF-007) REMAINS STRICTLY BLOCKED** until the single-user Founder Web Alpha is fully integrated.\n\n"
                "## 7. Decision\n\n"
                "**FINAL / PASS**\n",
                encoding="utf-8"
            )
            
            briefs = root / "briefs"
            briefs.mkdir(parents=True)
            (briefs / "BRIEF-006.md").write_text("## Decision\nPASS\n", encoding="utf-8")
            (reports / "REPORT-006.md").write_text("**Date:** 2026-08-31\n## Decision\nPASS\n", encoding="utf-8")
            
            with mock.patch.object(generate_state, "ROOT", root), mock.patch.object(
                generate_state, "STATE_PATH", state_path
            ):
                generate_state.main()
                
            state_content = state_path.read_text(encoding="utf-8")
            self.assertIn("GATE-FR-001 — FINAL / PASS", state_content)
            self.assertIn("BRIEF-007 / Phase 6: Multi-Tenant Family Alpha (strictly blocked", state_content)
            self.assertIn("ORDERED SEQUENCE (C + A) -> B -> D", state_content)
            self.assertIn("Phase 0/1 Foundation & Web Integration", state_content)


class SourceCountsTest(unittest.TestCase):
    def test_counts_observed_status_per_source_from_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "SOURCE_REGISTRY.yaml"
            registry_path.write_text(
                "sources:\n"
                "  - source_id: alpha\n"
                "    observed:\n"
                "      status: allowed_ok\n"
                "  - source_id: beta\n"
                "    observed:\n"
                "      status: allowed_ok\n"
                "  - source_id: gamma\n"
                "    observed:\n"
                "      status: robots_unreachable\n",
                encoding="utf-8",
            )

            counts = generate_state.source_counts(registry_path)

            self.assertEqual(counts["allowed_ok"], 2)
            self.assertEqual(counts["robots_unreachable"], 1)
            self.assertEqual(sum(counts.values()), 3)

    def test_missing_registry_returns_empty_counter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "does-not-exist.yaml"

            counts = generate_state.source_counts(missing_path)

            self.assertEqual(counts, generate_state.Counter())

    def test_source_entry_without_observed_block_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "SOURCE_REGISTRY.yaml"
            registry_path.write_text(
                "sources:\n"
                "  - source_id: no_observed\n"
                "  - source_id: alpha\n"
                "    observed:\n"
                "      status: allowed_ok\n",
                encoding="utf-8",
            )

            counts = generate_state.source_counts(registry_path)

            self.assertEqual(counts, {"allowed_ok": 1})

    def test_no_regex_based_observed_status_scan_remains(self) -> None:
        source = Path(generate_state.__file__).read_text(encoding="utf-8")
        self.assertNotIn("observed_status", source)


class NextSummaryTest(unittest.TestCase):
    def test_colon_lead_in_joins_until_sentence_terminator(self) -> None:
        prerequisites = (
            "With the engine foundation, PostgreSQL relational persistence "
            "backbone, and Alembic versioned migrations established:\n"
            "- **BRIEF-FR-003:** FastAPI REST API Service & Next.js 14+ "
            "Founder Web Alpha UI Integration.\n"
            "- **BRIEF-007 (Private Family Alpha):** Remains strictly "
            "BLOCKED until Founder Web Alpha is live and validated."
        )

        next_summary = generate_state.next_summary_from_prerequisites(prerequisites)

        self.assertFalse(next_summary.rstrip().endswith(":"))
        self.assertNotIn(":.", next_summary)
        self.assertNotIn("..", next_summary)
        self.assertTrue(next_summary.endswith("."))
        self.assertLessEqual(len(next_summary), 300)

    def test_state_md_next_line_has_no_colon_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            docs.mkdir(parents=True)
            state_path = docs / "STATE.md"

            reports = root / "reports"
            reports.mkdir(parents=True)
            (reports / "REPORT-FR-002.md").write_text(
                "**Date:** 2026-09-01\n\n"
                "## 4. Next Phase Prerequisites\n\n"
                "With the engine foundation, PostgreSQL relational "
                "persistence backbone, and Alembic versioned migrations "
                "established:\n"
                "- **BRIEF-FR-003:** FastAPI REST API Service & Next.js "
                "14+ Founder Web Alpha UI Integration.\n"
                "- **BRIEF-007 (Private Family Alpha):** Remains strictly "
                "BLOCKED until Founder Web Alpha is live and validated.\n\n"
                "---\n\n"
                "## 5. Decision\n\n"
                "**PASS**\n",
                encoding="utf-8",
            )

            briefs = root / "briefs"
            briefs.mkdir(parents=True)

            with mock.patch.object(generate_state, "ROOT", root), mock.patch.object(
                generate_state, "STATE_PATH", state_path
            ):
                generate_state.main()

            next_line = next(
                line
                for line in state_path.read_text(encoding="utf-8").splitlines()
                if line.startswith("Next:")
            )

            self.assertFalse(next_line.rstrip().endswith(":"))
            self.assertNotIn(":.", next_line)
            self.assertTrue(next_line.endswith("."))


if __name__ == "__main__":
    unittest.main()
