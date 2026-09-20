from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]

class FounderSurfaceW23ContractTests(unittest.TestCase):
    def test_migration_is_current_and_truth_scoped(self):
        source = (ROOT / "storage/migrations/versions/0015_hosted_founder_surface.py").read_text(encoding="utf-8")
        self.assertIn('revision: str = "0015_hosted_founder_surface"', source)
        self.assertIn("PARTITION BY fp.opportunity_id", source)
        self.assertIn("p.truth_pack_hash", source)
        self.assertIn("founder_dashboard_daily", source)
        self.assertIn("founder_source_overview", source)
        self.assertIn("is_stale", source)

    def test_hosted_route_reads_persisted_projection_and_parses_detail(self):
        source = (ROOT / "web/app/api/[...path]/route.ts").read_text(encoding="utf-8")
        self.assertIn('q.searchParams.set("is_stale", "eq.false")', source)
        self.assertIn("priority_score.desc.nullslast", source)
        self.assertIn("source_family", source)
        self.assertIn("source_id", source)
        self.assertIn("founder_dashboard_daily", source)
        self.assertIn("hard_constraints", source)
        self.assertIn("_evaluationDetail", source)

    def test_detail_uses_centered_dialog(self):
        source = (ROOT / "web/components/feed/detail-drawer.tsx").read_text(encoding="utf-8")
        self.assertIn('from "@/components/ui/dialog"', source)
        self.assertIn("max-h-[92dvh]", source)
        self.assertNotIn("SheetContent", source)

    def test_poll_now_is_truthful_and_sources_mark_reddit_manual(self):
        header = (ROOT / "web/components/feed/header-strip.tsx").read_text(encoding="utf-8")
        route = (ROOT / "web/app/api/[...path]/route.ts").read_text(encoding="utf-8")
        self.assertIn("Queues currently due sources", header)
        self.assertIn("poll-result", header)
        self.assertIn('=== "reddit"', route)

    def test_greenhouse_tombstone_is_exact_and_conservative(self):
        source = (ROOT / "opportunity/reverification.py").read_text(encoding="utf-8")
        self.assertIn("GREENHOUSE_INACTIVE_BOARD_MARKER", source)
        self.assertIn("Page not found. The job board you were viewing is no longer active.", source)
        tests = (ROOT / "opportunity/test_reverification.py").read_text(encoding="utf-8")
        self.assertIn("test_near_miss_and_non_greenhouse_are_not_stale", tests)

if __name__ == "__main__":
    unittest.main()
