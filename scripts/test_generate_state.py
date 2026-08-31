from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import generate_state


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


if __name__ == "__main__":
    unittest.main()
