#!/usr/bin/env python3
"""Unit tests for scripts/scoring_metrics.py (BRIEF-FR-006 claim A-13).

Runs both standalone (py -3.12 scripts/test_scoring_metrics.py -v) and as a package module
(py -3.12 -m unittest discover -s scripts -p "test_*.py" -v).
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
    from scripts import scoring_metrics
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import scoring_metrics  # type: ignore[no-redef]

from opportunity.models import Opportunity, SeniorityLevel, Track


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


class NotARolePostingRegexTests(unittest.TestCase):
    def test_matches_procurement_style_titles(self) -> None:
        for title in (
            "Advisory RFP",
            "Data Pipeline SOW",
            "Procurement Tender",
            "Cloud Security Assessment (Request for Proposal)",
            "Expression of Interest -- Can't see a role that's right for you?",
        ):
            self.assertRegex(title, scoring_metrics._NOT_A_ROLE_POSTING_RE, msg=title)

    def test_does_not_match_ordinary_job_titles(self) -> None:
        for title in ("Senior Data Engineer", "Customer Success Engineer, Federal", "Analyst II"):
            self.assertNotRegex(title, scoring_metrics._NOT_A_ROLE_POSTING_RE, msg=title)


class ReportB1SeniorityTableTests(unittest.TestCase):
    def test_reports_not_available_when_no_row_has_that_seniority(self) -> None:
        # No opportunity in this tiny list has SeniorityLevel.PRINCIPAL, so that row must say
        # NOT AVAILABLE rather than silently reusing a different level's posting.
        opps = [_minimal_opportunity(id="t:1", seniority=SeniorityLevel.ENTRY)]
        out = _capture(scoring_metrics.report_b1_seniority_table, opps)
        self.assertIn("Principal: NOT AVAILABLE", out)


class ReportB3TitleFamilyMappingTests(unittest.TestCase):
    def test_classifies_family_other_and_the_two_other_groups(self) -> None:
        fake = types.SimpleNamespace
        opps = [
            fake(title="Senior Data Engineer"),  # maps to data_engineering
            fake(title="Sales Role"),  # other, group (b): a real role the taxonomy missed
            fake(title="Procurement Tender"),  # other, group (a): not a role posting
        ]
        out = _capture(scoring_metrics.report_b3_title_family_mapping, opps)
        self.assertIn("titles mapping to a family (not 'other'): 1/3", out)
        self.assertIn("titles mapping to 'other': 2/3", out)
        self.assertIn("(a) not a role posting: 1/2", out)
        self.assertIn("(b) a role title the taxonomy failed to place: 1/2", out)


class MainSmokeTests(unittest.TestCase):
    def test_main_runs_over_the_committed_corpus_and_exits_zero(self) -> None:
        out = _capture(lambda: self.assertEqual(scoring_metrics.main(), 0))
        self.assertIn("corpus opportunities evaluated:", out)
        self.assertIn("=== B1:", out)
        self.assertIn("=== B2:", out)
        self.assertIn("=== B2 ordering:", out)
        self.assertIn("=== B3:", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
