"""Unit tests for opportunity/discovery/boards.py (BRIEF-FR-006 E1)."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from opportunity.discovery import boards
from opportunity.registry import SourceRegistry
from opportunity.transport import DiscoveryRequest, MockTransport, RateLimiter, TransportResponse


def _gh_payload(titles_and_dates: list[tuple[str, str]]) -> str:
    return json.dumps({"jobs": [{"title": t, "updated_at": d} for t, d in titles_and_dates]})


def _lever_payload(titles_and_ms: list[tuple[str, int]]) -> str:
    return json.dumps([{"text": t, "createdAt": ms} for t, ms in titles_and_ms])


class CandidateUrlTests(unittest.TestCase):
    def test_greenhouse_url(self):
        self.assertEqual(
            boards.candidate_url("greenhouse", "acme"),
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        )

    def test_lever_url(self):
        self.assertEqual(
            boards.candidate_url("lever", "acme"),
            "https://api.lever.co/v0/postings/acme?mode=json",
        )

    def test_ashby_url(self):
        self.assertEqual(
            boards.candidate_url("ashby", "acme"),
            "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=false",
        )

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            boards.candidate_url("bogus", "acme")

    def test_candidate_id_and_url_properties(self):
        candidate = boards.BoardCandidate(kind="greenhouse", token="acme")
        self.assertEqual(candidate.candidate_id, "greenhouse:acme")
        self.assertEqual(candidate.url, boards.candidate_url("greenhouse", "acme"))


class ClassifyStatusTests(unittest.TestCase):
    def test_403_is_blocked(self):
        classification, detail, postings = boards.classify_status(403, "", "greenhouse")
        self.assertEqual(classification, "blocked")
        self.assertEqual(postings, ())

    def test_429_is_blocked(self):
        classification, _detail, _postings = boards.classify_status(429, "", "lever")
        self.assertEqual(classification, "blocked")

    def test_404_is_absent(self):
        classification, _detail, _postings = boards.classify_status(404, "", "greenhouse")
        self.assertEqual(classification, "absent")

    def test_200_with_postings_is_live(self):
        payload = _gh_payload([("Data Engineer", "2026-08-01T00:00:00Z")])
        classification, _detail, postings = boards.classify_status(200, payload, "greenhouse")
        self.assertEqual(classification, "live")
        self.assertEqual(len(postings), 1)

    def test_200_with_zero_postings_is_empty(self):
        classification, _detail, postings = boards.classify_status(200, _gh_payload([]), "greenhouse")
        self.assertEqual(classification, "empty")
        self.assertEqual(postings, ())

    def test_200_unparseable_body_is_error(self):
        classification, _detail, _postings = boards.classify_status(200, "not json", "greenhouse")
        self.assertEqual(classification, "error")

    def test_other_status_is_error(self):
        classification, _detail, _postings = boards.classify_status(500, "", "greenhouse")
        self.assertEqual(classification, "error")

    def test_lever_payload_parses(self):
        now_ms = 1_800_000_000_000
        classification, _detail, postings = boards.classify_status(
            200, _lever_payload([("Backend Engineer", now_ms)]), "lever"
        )
        self.assertEqual(classification, "live")
        self.assertEqual(postings[0].title, "Backend Engineer")


class TitleFamilyFilterTests(unittest.TestCase):
    def test_keyword_fallback_matches_known_keyword(self):
        classifier = boards.KeywordFallbackClassifier()
        self.assertTrue(classifier.is_target_family("Senior Data Engineer"))

    def test_keyword_fallback_rejects_unrelated_title(self):
        classifier = boards.KeywordFallbackClassifier()
        self.assertFalse(classifier.is_target_family("Executive Assistant"))

    def test_default_classifier_returns_a_label(self):
        classifier, label = boards.default_classifier()
        self.assertIn(label, {"title_family_model", "keyword_fallback"})
        self.assertIsInstance(classifier, boards.TitleFamilyClassifier)

    def test_relevant_postings_filters_by_family_and_window(self):
        classifier = boards.KeywordFallbackClassifier()
        today = date(2026, 9, 3)
        fresh = boards.Posting(title="Data Engineer", posted_date=(today - timedelta(days=10)).isoformat())
        stale = boards.Posting(title="Data Engineer", posted_date=(today - timedelta(days=200)).isoformat())
        irrelevant = boards.Posting(title="Office Manager", posted_date=today.isoformat())
        matched = boards.relevant_postings([fresh, stale, irrelevant], classifier, today)
        self.assertEqual(matched, [fresh])

    def test_relevant_postings_keeps_unparseable_date(self):
        classifier = boards.KeywordFallbackClassifier()
        today = date(2026, 9, 3)
        undated = boards.Posting(title="Data Engineer", posted_date="")
        matched = boards.relevant_postings([undated], classifier, today)
        self.assertEqual(matched, [undated])


class SeedLoadingTests(unittest.TestCase):
    def test_watchlist_ats_seed_loads_known_boards(self):
        candidates = boards.load_watchlist_ats_candidates()
        self.assertGreaterEqual(len(candidates), 12)
        self.assertTrue(all(isinstance(c, boards.BoardCandidate) for c in candidates))
        self.assertTrue(all(c.seed == "recon_ats_watchlist" for c in candidates))

    def test_remoteintech_seed_loads_committed_slugs(self):
        candidates = boards.load_remoteintech_seed_candidates()
        self.assertGreater(len(candidates), 100)
        kinds = {c.kind for c in candidates}
        self.assertEqual(kinds, {"greenhouse", "lever"})

    def test_founder_watchlist_never_reads_real_path_in_tests(self):
        # Uses an explicit temp file -- never the real private/watchlist.yaml path.
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = Path(tmp) / "watchlist.yaml"
            temp_path.write_text(
                "companies:\n  - kind: greenhouse\n    token: acme\n    name: Acme\n",
                encoding="utf-8",
            )
            candidates = boards.load_founder_watchlist_candidates(path=temp_path)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].candidate_id, "greenhouse:acme")
        self.assertEqual(candidates[0].seed, "founder_watchlist")

    def test_founder_watchlist_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist.yaml"
            self.assertEqual(boards.load_founder_watchlist_candidates(path=missing), [])

    def test_dedupe_candidates_drops_duplicates_and_registered(self):
        a = boards.BoardCandidate(kind="greenhouse", token="acme")
        b = boards.BoardCandidate(kind="greenhouse", token="acme")
        c = boards.BoardCandidate(kind="lever", token="beta")
        result = boards.dedupe_candidates([a, b, c], already_registered={"lever:beta"})
        self.assertEqual([x.candidate_id for x in result], ["greenhouse:acme"])


class RegistryEntryTemplateTests(unittest.TestCase):
    def test_render_registry_entry_disables_prepare_and_submit(self):
        candidate = boards.BoardCandidate(kind="greenhouse", token="acme")
        entry = boards.build_registry_entry(candidate, record_count=5, matched_count=2, latency_ms=120)
        text = boards.render_registry_entry(entry)
        self.assertIn("prepare: disabled", text)
        self.assertIn("submit: disabled", text)
        self.assertIn("source_id: greenhouse:acme", text)

    def test_generated_entry_validates_against_registry_loader(self):
        board_slug = "acme-discovery-test"
        candidate = boards.BoardCandidate(kind="greenhouse", token=board_slug)
        entry = boards.build_registry_entry(candidate, record_count=3, matched_count=1, latency_ms=80)
        block = boards.render_registry_entry(entry)
        content = "sources:\n" + block
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "SOURCE_REGISTRY.yaml"
            registry_path.write_text(content, encoding="utf-8")
            registry = SourceRegistry(registry_path)
        policy = registry.get_policy("greenhouse:acme-discovery-test")
        self.assertIsNotNone(policy)
        self.assertTrue(policy.read_allowed)
        authorized, reason = registry.validate_preflight(
            "greenhouse:acme-discovery-test", candidate.url, "GET"
        )
        self.assertTrue(authorized, reason)

    def test_append_registry_entries_skips_already_present_source_id(self):
        candidate = boards.BoardCandidate(kind="greenhouse", token="acme")
        entry = boards.build_registry_entry(candidate, record_count=1, matched_count=1, latency_ms=10)
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "SOURCE_REGISTRY.yaml"
            registry_path.write_text("sources:\n" + boards.render_registry_entry(entry), encoding="utf-8")
            written = boards.append_registry_entries(registry_path, [entry])
        self.assertEqual(written, 0)

    def test_append_registry_entries_writes_new_entry(self):
        board_slug = "brand-new"
        candidate = boards.BoardCandidate(kind="lever", token=board_slug)
        entry = boards.build_registry_entry(candidate, record_count=1, matched_count=1, latency_ms=10)
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "SOURCE_REGISTRY.yaml"
            registry_path.write_text("sources:\n", encoding="utf-8")
            written = boards.append_registry_entries(registry_path, [entry])
            self.assertEqual(written, 1)
            self.assertIn("source_id: lever:brand-new", registry_path.read_text(encoding="utf-8"))


class ProgressResumabilityTests(unittest.TestCase):
    def test_save_and_load_progress_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"
            boards.save_progress(path, {"greenhouse:acme": {"classification": "live"}})
            loaded = boards.load_progress(path)
        self.assertEqual(loaded["greenhouse:acme"]["classification"], "live")

    def test_load_progress_missing_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(boards.load_progress(Path(tmp) / "missing.json"), {})

    def test_resumed_sweep_skips_already_processed_and_never_reprobes_blocked(self):
        board_slug = "blocked-co"
        candidate = boards.BoardCandidate(kind="greenhouse", token=board_slug)
        transport = MockTransport({"greenhouse:blocked-co": TransportResponse(403, "", 5)})
        with tempfile.TemporaryDirectory() as tmp:
            progress_path = Path(tmp) / "progress.json"

            result_1 = boards.run_sweep(
                [candidate], transport=transport, progress_path=progress_path,
                classifier=boards.KeywordFallbackClassifier(), classifier_label="keyword_fallback",
            )
            self.assertEqual(result_1.counts["blocked"], 1)
            self.assertEqual(result_1.processed_this_run, 1)

            # Second run (simulating a resumed/interrupted sweep): transport now would error if
            # called again -- MockTransport still has the same fixed response, but we assert the
            # candidate was NOT re-requested by checking processed_this_run is 0 on resume.
            result_2 = boards.run_sweep(
                [candidate], transport=transport, progress_path=progress_path,
                classifier=boards.KeywordFallbackClassifier(), classifier_label="keyword_fallback",
            )
            self.assertEqual(result_2.processed_this_run, 0)
            self.assertEqual(result_2.counts["blocked"], 1)
            self.assertEqual(result_2.blocked_ids, ["greenhouse:blocked-co"])


class SweepOrchestrationTests(unittest.TestCase):
    def test_sweep_registers_live_relevant_board_and_reports_seed_and_classifier(self):
        candidate = boards.BoardCandidate(kind="greenhouse", token="acme", seed="test_seed")
        payload = _gh_payload([("Data Engineer", "2026-08-20T00:00:00Z")])
        transport = MockTransport({"greenhouse:acme": TransportResponse(200, payload, 42)})
        with tempfile.TemporaryDirectory() as tmp:
            progress_path = Path(tmp) / "progress.json"
            result = boards.run_sweep(
                [candidate],
                transport=transport,
                progress_path=progress_path,
                classifier=boards.KeywordFallbackClassifier(),
                classifier_label="keyword_fallback",
                now=date(2026, 9, 3),
                seeds_used=["test_seed"],
            )
        self.assertEqual(result.counts["live"], 1)
        self.assertEqual(len(result.registered), 1)
        self.assertEqual(result.registered[0].source_id, "greenhouse:acme")
        self.assertEqual(result.classifier_label, "keyword_fallback")
        self.assertEqual(result.seeds_used, ["test_seed"])

    def test_sweep_does_not_register_live_board_without_relevant_postings(self):
        candidate = boards.BoardCandidate(kind="greenhouse", token="acme")
        payload = _gh_payload([("Office Manager", "2026-08-20T00:00:00Z")])
        transport = MockTransport({"greenhouse:acme": TransportResponse(200, payload, 42)})
        with tempfile.TemporaryDirectory() as tmp:
            result = boards.run_sweep(
                [candidate],
                transport=transport,
                progress_path=Path(tmp) / "progress.json",
                classifier=boards.KeywordFallbackClassifier(),
                classifier_label="keyword_fallback",
                now=date(2026, 9, 3),
            )
        self.assertEqual(result.counts["live"], 1)
        self.assertEqual(len(result.registered), 0)

    def test_sweep_shares_rate_limit_across_boards_on_same_host(self):
        candidates = [
            boards.BoardCandidate(kind="greenhouse", token="a"),
            boards.BoardCandidate(kind="greenhouse", token="b"),
        ]
        transport = MockTransport(
            {
                "greenhouse:a": TransportResponse(200, _gh_payload([]), 5),
                "greenhouse:b": TransportResponse(200, _gh_payload([]), 5),
            }
        )
        clock = {"t": 0.0}
        limiter = RateLimiter(clock=lambda: clock["t"], default_min_interval_s=1.0)
        with tempfile.TemporaryDirectory() as tmp:
            boards.run_sweep(
                candidates,
                transport=transport,
                rate_limiter=limiter,
                progress_path=Path(tmp) / "progress.json",
                classifier=boards.KeywordFallbackClassifier(),
                classifier_label="keyword_fallback",
            )
        # Both boards share the same "greenhouse" key in the limiter, not their own source_id.
        self.assertIn("greenhouse", limiter._last_request_time)
        self.assertNotIn("greenhouse:a", limiter._last_request_time)

    def test_sweep_respects_max_new_requests_for_bounded_runs(self):
        candidates = [
            boards.BoardCandidate(kind="greenhouse", token="a"),
            boards.BoardCandidate(kind="greenhouse", token="b"),
        ]
        transport = MockTransport(
            {
                "greenhouse:a": TransportResponse(200, _gh_payload([]), 5),
                "greenhouse:b": TransportResponse(200, _gh_payload([]), 5),
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = boards.run_sweep(
                candidates,
                transport=transport,
                progress_path=Path(tmp) / "progress.json",
                classifier=boards.KeywordFallbackClassifier(),
                classifier_label="keyword_fallback",
                max_new_requests=1,
            )
        self.assertEqual(result.processed_this_run, 1)


if __name__ == "__main__":
    unittest.main()
