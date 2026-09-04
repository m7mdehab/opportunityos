#!/usr/bin/env python3
"""Unit tests for scripts/corpus_metrics.py (BRIEF-FR-006 work order A1C).

Runs both standalone (py -3.12 scripts/test_corpus_metrics.py -v) and as a package module
(py -3.12 -m unittest scripts.test_corpus_metrics -v / discover).
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
try:
    from scripts import corpus_metrics
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import corpus_metrics  # type: ignore[no-redef]

from opportunity.models import Opportunity, Track


def _capture(func, *args, **kwargs) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(*args, **kwargs)
    return buf.getvalue()


def _minimal_opportunity(**overrides) -> Opportunity:
    fields = dict(
        id="test:1",
        track=Track.EMPLOYMENT,
        source="test_source",
        source_url="https://example.test/job/1",
        source_id="1",
        organization="Acme",
        title="Engineer",
        description="A real job.",
    )
    fields.update(overrides)
    return Opportunity(**fields)


class PrintDenominatorLineTests(unittest.TestCase):
    def test_formats_numerator_denominator_and_percentage(self) -> None:
        out = _capture(corpus_metrics.print_denominator_line, "label", 3, 4)
        self.assertIn("label: 3/4 (75.0%)", out)

    def test_zero_denominator_does_not_divide_by_zero(self) -> None:
        out = _capture(corpus_metrics.print_denominator_line, "label", 0, 0)
        self.assertIn("label: 0/0 (0.0%)", out)


class _StrippedOpportunity:
    """Stand-in for an Opportunity that genuinely lacks a given attribute.

    Real ``opportunity.models.Opportunity`` instances have carried ``work_mode``,
    ``location_country``, ``remote_scope``, and ``work_mode_source`` (with defaults) since
    work order A1 landed, so a real instance can never exercise the "attribute is missing"
    branch below. This stub simulates the pre-A1 shape instead, by simply not defining the
    attribute the "missing" test is about, so that code path stays covered.
    """

    def __init__(self, **present: object) -> None:
        for key, value in present.items():
            setattr(self, key, value)


class WorkModeCoverageTests(unittest.TestCase):
    def test_missing_attribute_reports_not_available_not_zero(self) -> None:
        # Simulates the pre-A1 shape (Opportunity genuinely lacked `work_mode`): this must
        # never silently render as a 0% coverage number.
        opps = [_StrippedOpportunity() for _ in range(3)]
        out = _capture(corpus_metrics.report_work_mode_coverage, opps)
        self.assertIn("NOT AVAILABLE", out)
        self.assertIn("work_mode", out)
        self.assertNotIn("0.0%", out)

    def test_present_attribute_computes_real_percentage(self) -> None:
        fake = types.SimpleNamespace
        opps = [fake(work_mode="remote"), fake(work_mode="unspecified"), fake(work_mode="hybrid")]
        out = _capture(corpus_metrics.report_work_mode_coverage, opps)
        self.assertIn("2/3 (66.7%)", out)

    def test_real_opportunity_now_always_has_the_attribute(self) -> None:
        # Documents the A1 landing: a real Opportunity never takes the NOT AVAILABLE branch.
        opps = [_minimal_opportunity(id=f"test:{i}") for i in range(3)]
        out = _capture(corpus_metrics.report_work_mode_coverage, opps)
        self.assertNotIn("NOT AVAILABLE", out)
        self.assertIn("work_mode != unspecified: 0/3 (0.0%)", out)


class LocationCoverageTests(unittest.TestCase):
    def test_missing_attribute_reports_not_available(self) -> None:
        opps = [_StrippedOpportunity()]
        out = _capture(corpus_metrics.report_location_coverage, opps)
        self.assertIn("NOT AVAILABLE", out)

    def test_present_attribute_counts_country_or_scope(self) -> None:
        fake = types.SimpleNamespace
        opps = [
            fake(location_country="EG", remote_scope="unspecified"),
            fake(location_country=None, remote_scope="worldwide"),
            fake(location_country=None, remote_scope="unspecified"),
        ]
        out = _capture(corpus_metrics.report_location_coverage, opps)
        self.assertIn("2/3 (66.7%)", out)

    def test_real_opportunity_now_always_has_the_attribute(self) -> None:
        opps = [_minimal_opportunity()]
        out = _capture(corpus_metrics.report_location_coverage, opps)
        self.assertNotIn("NOT AVAILABLE", out)


class AdapterInferenceSplitTests(unittest.TestCase):
    def test_missing_attribute_reports_not_available(self) -> None:
        opps = [_StrippedOpportunity()]
        out = _capture(corpus_metrics.report_adapter_inference_split, opps)
        self.assertIn("NOT AVAILABLE", out)
        self.assertIn("work_mode_source", out)

    def test_real_opportunity_now_always_has_the_attribute(self) -> None:
        opps = [_minimal_opportunity()]
        out = _capture(corpus_metrics.report_adapter_inference_split, opps)
        self.assertNotIn("NOT AVAILABLE", out)
        self.assertIn("work_mode_source == none: 1/1 (100.0%)", out)

    def test_present_attribute_splits_by_label(self) -> None:
        fake = types.SimpleNamespace
        opps = [
            fake(work_mode_source="adapter"),
            fake(work_mode_source="adapter"),
            fake(work_mode_source="inference"),
            fake(work_mode_source="none"),
        ]
        out = _capture(corpus_metrics.report_adapter_inference_split, opps)
        self.assertIn("work_mode_source == adapter: 2/4 (50.0%)", out)
        self.assertIn("work_mode_source == inference: 1/4 (25.0%)", out)
        self.assertIn("work_mode_source == none: 1/4 (25.0%)", out)


class QualificationEmptyGraphTests(unittest.TestCase):
    def test_computes_real_distribution_over_given_opportunities(self) -> None:
        opps = [_minimal_opportunity(id=f"test:{i}") for i in range(5)]
        out = _capture(corpus_metrics.report_qualification_empty_graph, opps)
        self.assertIn("decision == qualified:", out)
        self.assertIn("decision == ineligible:", out)
        self.assertIn("decision == uncertain:", out)
        # Every evaluated opportunity must land in exactly one denominator of 5.
        for label in ("qualified", "ineligible", "uncertain"):
            self.assertIn(f"/5 (", out)
        self.assertIn("empty TruthGraph", out)

    def test_never_quotes_a_number_it_did_not_compute(self) -> None:
        # An empty opportunity list must show 0/0, not an omitted or fabricated line.
        out = _capture(corpus_metrics.report_qualification_empty_graph, [])
        self.assertIn("decision == qualified: 0/0", out)


class QualificationFounderShapedTests(unittest.TestCase):
    def test_computes_real_distribution_against_the_founder_shaped_pack(self) -> None:
        opps = [_minimal_opportunity(id=f"test:{i}") for i in range(5)]
        out = _capture(corpus_metrics.report_qualification_founder_shaped, opps)
        self.assertIn("decision == qualified:", out)
        self.assertIn("decision == ineligible:", out)
        self.assertIn("decision == uncertain:", out)
        for label in ("qualified", "ineligible", "uncertain"):
            self.assertIn(f"/5 (", out)
        self.assertIn("founder_shaped_graph", out)

    def test_never_quotes_a_number_it_did_not_compute(self) -> None:
        out = _capture(corpus_metrics.report_qualification_founder_shaped, [])
        self.assertIn("decision == qualified: 0/0", out)


class ParseCorpusTests(unittest.TestCase):
    def test_unregistered_source_id_is_reported_as_a_parse_error_not_silently_dropped(self) -> None:
        from opportunity.fixtures import CorpusFixture

        fixture = CorpusFixture(
            source_id="not_a_real_source",
            request_url="https://example.test/feed",
            fetched_at="2026-01-01T00:00:00+00:00",
            raw_body="{}",
            path=pathlib.Path("nonexistent.json"),
        )
        opportunities, errors = corpus_metrics.parse_corpus([fixture])
        self.assertEqual(opportunities, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("no adapter registered", errors[0])

    def test_real_greenhouse_fixture_reparses_to_one_opportunity(self) -> None:
        import json

        from opportunity.fixtures import CorpusFixture

        raw_job = {
            "id": 999,
            "title": "Senior Customer Engineer",
            "content": "<p>Work with customers.</p>",
            "location": {"name": "Remote"},
            "absolute_url": "https://boards.greenhouse.io/cloudflare/jobs/999",
            "updated_at": "2026-01-01T00:00:00Z",
            "employment_type": "Full-time",
        }
        fixture = CorpusFixture(
            source_id="greenhouse:cloudflare",
            request_url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true",
            fetched_at="2026-01-01T00:00:00+00:00",
            raw_body=json.dumps({"jobs": [raw_job]}),
            path=pathlib.Path("synthetic-test-only.json"),
        )
        opportunities, errors = corpus_metrics.parse_corpus([fixture])
        self.assertEqual(errors, [])
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].title, "Senior Customer Engineer")


class MainSmokeTests(unittest.TestCase):
    def test_main_runs_over_the_committed_corpus_and_exits_zero(self) -> None:
        out = _capture(lambda: self.assertEqual(corpus_metrics.main(), 0))
        self.assertIn("=== corpus size ===", out)
        self.assertIn("total payloads:", out)
        self.assertIn("--- per-source histogram ---", out)
        self.assertIn("qualification decision distribution: against truth.fixtures.founder_shaped_graph()", out)
        self.assertIn("qualification decision distribution: against an empty TruthGraph", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
