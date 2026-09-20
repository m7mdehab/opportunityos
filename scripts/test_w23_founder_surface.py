from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]

class FounderSurfaceW23ContractTests(unittest.TestCase):
    def test_w23_web_sources_are_utf8_and_mojibake_free(self):
        bad = []
        for path in (ROOT / "web").rglob("*"):
            if not path.is_file() or any(part in {"node_modules", ".next"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if any(token in text for token in ("â€", "Ã", "�")):
                bad.append(str(path.relative_to(ROOT)))
        self.assertEqual(bad, [])

    def test_migration_is_current_truth_scoped_and_source_complete(self):
        source = (ROOT / "storage/migrations/versions/0015_hosted_founder_surface.py").read_text(encoding="utf-8")
        self.assertIn('revision: str = "0015_hosted_founder_surface"', source)
        self.assertIn("PARTITION BY fp.opportunity_id", source)
        self.assertIn("p.truth_pack_hash", source)
        self.assertIn("founder_dashboard_daily", source)
        self.assertIn("founder_source_overview", source)
        self.assertIn("FROM public.source_schedules s", source)
        self.assertIn("('reddit')", source)
        self.assertIn("f.visible IS TRUE", source)
        self.assertIn("regexp_split_to_table", source)\n        self.assertIn("visibility_reason", source)

    def test_hosted_route_has_visible_and_hidden_feed_contract(self):
        source = (ROOT / "web/app/api/[...path]/route.ts").read_text(encoding="utf-8")
        self.assertIn('query.searchParams.set("is_stale", "eq.false")', source)
        self.assertIn('query.searchParams.set("visible", "eq.true")', source)
        self.assertIn('url.searchParams.get("include_hidden") === "true"', source)
        self.assertIn('query.searchParams.set("visible", "eq.false")', source)
        self.assertIn("hidden_count: hiddenCount", source)
        self.assertIn("policyHiddenReasons", source)
        self.assertIn("priority_score.desc.nullslast", source)
        self.assertIn("founder_dashboard_daily", source)
        self.assertIn("hard_constraints", source)

    def test_detail_uses_intentional_dialog_layout_and_score(self):
        source = (ROOT / "web/components/feed/detail-drawer.tsx").read_text(encoding="utf-8")
        self.assertIn('from "@/components/ui/dialog"', source)
        self.assertIn("max-h-[92dvh]", source)
        self.assertIn("md:col-start-1 md:row-start-1", source)
        self.assertIn("md:col-start-2 md:row-start-1", source)
        self.assertIn('data-testid="detail-fit-score"', source)
        self.assertNotIn("SheetContent", source)

    def test_source_ui_aggregates_and_manual_path(self):
        source = (ROOT / "web/components/feed/filter-bar.tsx").read_text(encoding="utf-8")
        self.assertIn("Manual only · 0 automated", source)
        self.assertIn("reduce((total, row)", source)
        self.assertIn("onOpenManualSources", source)

    def test_poll_now_and_greenhouse_board_contracts_are_conservative(self):
        header = (ROOT / "web/components/feed/header-strip.tsx").read_text(encoding="utf-8")
        route = (ROOT / "web/app/api/[...path]/route.ts").read_text(encoding="utf-8")
        reverify = (ROOT / "opportunity/reverification.py").read_text(encoding="utf-8")
        self.assertIn("Queues currently due sources", header)
        self.assertIn("poll-result", header)
        self.assertIn("reverify_greenhouse_boards", reverify)
        self.assertIn("greenhouse_board_root", reverify)
        self.assertIn("boards.greenhouse.io", reverify)
        self.assertIn("manual_only", route)

if __name__ == "__main__":
    unittest.main()
