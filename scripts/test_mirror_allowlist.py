from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from scripts import check_guard, derive_founder_patterns, sync_mirror
except ImportError:  # running from the scripts directory
    import check_guard
    import derive_founder_patterns
    import sync_mirror


ROOT = Path(__file__).resolve().parents[1]


class MirrorAllowlistTest(unittest.TestCase):
    def setUp(self) -> None:
        self.patterns = sync_mirror.load_allowlist(ROOT / ".mirror-allowlist")

    def test_fr008_paths_are_denied_and_safe_brief_and_report_are_allowed(self) -> None:
        denied = [
            "briefs/BRIEF-FR-008.md",
            "briefs/FR-008-FOLLOW-UP.md",
            "reports/REPORT-FR-008.md",
            "reports/evidence/FR-008/orders/W0-MIRROR.md",
        ]
        allowed = ["briefs/BRIEF-SAFE-001.md", "reports/REPORT-SAFE-001.md"]

        for relative in denied:
            with self.subTest(path=relative):
                self.assertFalse(sync_mirror.is_allowlisted(relative, self.patterns))
                self.assertFalse(check_guard.mirrored(ROOT / relative, self.patterns))

        for relative in allowed:
            with self.subTest(path=relative):
                self.assertTrue(sync_mirror.is_allowlisted(relative, self.patterns))
                self.assertTrue(check_guard.mirrored(ROOT / relative, self.patterns))

    def test_last_matching_rule_wins_including_later_reinclusion(self) -> None:
        relative = "briefs/BRIEF-FR-008.md"
        self.assertFalse(sync_mirror.is_allowlisted(relative, self.patterns))

        re_included = [*self.patterns, relative]
        self.assertTrue(sync_mirror.is_allowlisted(relative, re_included))
        self.assertTrue(check_guard.mirrored(ROOT / relative, re_included))

        denied_again = [*re_included, f"!{relative}"]
        self.assertFalse(sync_mirror.is_allowlisted(relative, denied_again))
        self.assertFalse(check_guard.mirrored(ROOT / relative, denied_again))

    def test_founder_pattern_derivation_uses_the_same_effective_rules(self) -> None:
        tracked = [
            "briefs/BRIEF-SAFE-001.md",
            "reports/REPORT-SAFE-001.md",
            "briefs/BRIEF-FR-008.md",
            "briefs/FR-008-FOLLOW-UP.md",
            "reports/REPORT-FR-008.md",
            "reports/evidence/FR-008/orders/W0-MIRROR.md",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".mirror-allowlist").write_text(
                (ROOT / ".mirror-allowlist").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            with mock.patch.object(
                derive_founder_patterns,
                "command",
                return_value="\0".join(tracked),
            ):
                mirrored = derive_founder_patterns.mirrored_files(root)

        mirrored_relatives = {path.relative_to(root).as_posix() for path in mirrored}
        self.assertEqual(
            mirrored_relatives,
            {"briefs/BRIEF-SAFE-001.md", "reports/REPORT-SAFE-001.md"},
        )


if __name__ == "__main__":
    unittest.main()
