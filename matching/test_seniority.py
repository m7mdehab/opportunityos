"""Tests for `matching/seniority.py` (ADR-0016): founder seniority derived
from truth-graph employment tenure and verified leadership evidence, never
from title-keyword substring matching. Boundary cases named per BRIEF-FR-006
order B1's acceptance list.
"""
from __future__ import annotations

import unittest
from datetime import date

from truth import predicates
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, VerificationStatus

from matching import seniority


def _build_graph(roles: list[dict]) -> TruthGraph:
    """Build a TruthGraph from simple role dicts: rid, title, start, end
    (optional), responsibilities (optional list of str). Each role's
    evidence content exactly echoes the value it backs, so the graph's
    honest value-support check (`truth/graph.py::_is_value_supported_by_evidence`)
    is satisfied without shaping a fixture around the model under test.
    """
    graph = TruthGraph()
    for role in roles:
        rid = role["rid"]
        title = role["title"]
        ev_title = EvidenceRecord(
            id=f"ev-{rid}-title", content=title, source="test", locator=f"employment.{rid}.title",
        )
        graph.add_evidence(ev_title)
        graph.add_assertion(AtomicAssertion(
            id=f"a-{rid}-title", subject_id=rid, predicate=predicates.EMPLOYMENT_TITLE,
            value=title, evidence_ids=(ev_title.id,), verification_status=VerificationStatus.VERIFIED,
        ))

        start = role.get("start")
        if start is not None:
            end = role.get("end")
            content = f"{start.isoformat()} to {end.isoformat()}" if end else f"{start.isoformat()} to present"
            ev_dates = EvidenceRecord(
                id=f"ev-{rid}-dates", content=content, source="test", locator=f"employment.{rid}.dates",
            )
            graph.add_evidence(ev_dates)
            graph.add_assertion(AtomicAssertion(
                id=f"a-{rid}-start", subject_id=rid, predicate=predicates.EMPLOYMENT_START_DATE,
                value=start, evidence_ids=(ev_dates.id,), verification_status=VerificationStatus.VERIFIED,
            ))
            if end is not None:
                graph.add_assertion(AtomicAssertion(
                    id=f"a-{rid}-end", subject_id=rid, predicate=predicates.EMPLOYMENT_END_DATE,
                    value=end, evidence_ids=(ev_dates.id,), verification_status=VerificationStatus.VERIFIED,
                ))

        for idx, resp in enumerate(role.get("responsibilities", ())):
            ev_resp = EvidenceRecord(
                id=f"ev-{rid}-resp{idx}", content=resp, source="test",
                locator=f"employment.{rid}.responsibilities.{idx}",
            )
            graph.add_evidence(ev_resp)
            graph.add_assertion(AtomicAssertion(
                id=f"a-{rid}-resp{idx}", subject_id=rid, predicate=predicates.EMPLOYMENT_RESPONSIBILITY,
                value=resp, evidence_ids=(ev_resp.id,), verification_status=VerificationStatus.VERIFIED,
            ))
    return graph


class TestExtractEmploymentSpans(unittest.TestCase):
    def test_title_without_start_date_produces_no_span(self) -> None:
        graph = _build_graph([{"rid": "r1", "title": "Backend Engineer"}])
        self.assertEqual(seniority.extract_employment_spans(graph), ())

    def test_empty_graph_has_no_spans(self) -> None:
        self.assertEqual(seniority.extract_employment_spans(TruthGraph()), ())


class TestTotalProfessionalMonths(unittest.TestCase):
    def test_meets_requirement_exactly_at_mid_threshold(self) -> None:
        graph = _build_graph([{
            "rid": "mid-role", "title": "Backend Developer",
            "start": date(2020, 1, 1), "end": date(2021, 12, 31),
        }])
        assessment = seniority.assess(graph, required_level="mid")
        self.assertEqual(assessment.total_months, 24)
        self.assertTrue(assessment.meets_requirement)
        self.assertEqual(assessment.months_gap, 0)

    def test_fails_one_month_under_mid_threshold(self) -> None:
        graph = _build_graph([{
            "rid": "mid-role", "title": "Backend Developer",
            "start": date(2020, 1, 1), "end": date(2021, 11, 30),
        }])
        assessment = seniority.assess(graph, required_level="mid")
        self.assertEqual(assessment.total_months, 23)
        self.assertFalse(assessment.meets_requirement)
        self.assertEqual(assessment.months_gap, 1)

    def test_meets_one_month_over_mid_threshold(self) -> None:
        graph = _build_graph([{
            "rid": "mid-role", "title": "Backend Developer",
            "start": date(2020, 1, 1), "end": date(2022, 1, 31),
        }])
        assessment = seniority.assess(graph, required_level="mid")
        self.assertEqual(assessment.total_months, 25)
        self.assertTrue(assessment.meets_requirement)

    def test_internship_excluded_from_total_months(self) -> None:
        graph = _build_graph([
            {
                "rid": "intern-role", "title": "Software Engineering Intern",
                "start": date(2017, 6, 1), "end": date(2017, 8, 31),
            },
            {
                "rid": "real-role", "title": "Backend Developer",
                "start": date(2020, 1, 1), "end": date(2021, 12, 31),
            },
        ])
        spans = seniority.extract_employment_spans(graph)
        self.assertEqual(seniority.total_professional_months(spans), 24)

    def test_concurrent_overlapping_roles_counted_once(self) -> None:
        graph = _build_graph([
            {"rid": "role-a", "title": "Data Engineer", "start": date(2020, 1, 1), "end": date(2020, 12, 31)},
            {"rid": "role-b", "title": "Platform Lead", "start": date(2020, 6, 1), "end": date(2021, 5, 31)},
        ])
        spans = seniority.extract_employment_spans(graph)
        # Naive sum would be 12 + 12 = 24; the union (2020-01 through 2021-05) is 17.
        self.assertEqual(seniority.total_professional_months(spans), 17)


class TestMonthsInFamily(unittest.TestCase):
    def test_family_alias_restricts_to_matching_titles(self) -> None:
        graph = _build_graph([
            {"rid": "data-role", "title": "Data Engineer", "start": date(2020, 1, 1), "end": date(2020, 12, 31)},
            {"rid": "sales-role", "title": "Sales Manager", "start": date(2021, 1, 1), "end": date(2021, 12, 31)},
        ])
        spans = seniority.extract_employment_spans(graph)
        self.assertEqual(seniority.months_in_family(spans, ("Data Engineer",)), 12)
        self.assertEqual(seniority.total_professional_months(spans), 24)


class TestPeopleLeadershipEvidence(unittest.TestCase):
    def test_leadership_present_in_responsibility_text_counts(self) -> None:
        graph = _build_graph([{
            "rid": "lead-role", "title": "Backend Engineer",
            "start": date(2023, 1, 1), "end": date(2023, 12, 31),
            "responsibilities": ["Led the data platform team of five engineers across two squads."],
        }])
        spans = seniority.extract_employment_spans(graph)
        found, refs = seniority.has_people_leadership(spans)
        self.assertTrue(found)
        self.assertTrue(refs)

    def test_leadership_in_title_only_does_not_count(self) -> None:
        graph = _build_graph([{
            "rid": "titled-lead-role", "title": "Team Lead",
            "start": date(2023, 1, 1), "end": date(2023, 12, 31),
            "responsibilities": ["Maintained REST API endpoints for the billing platform."],
        }])
        spans = seniority.extract_employment_spans(graph)
        found, refs = seniority.has_people_leadership(spans)
        self.assertFalse(found)
        self.assertEqual(refs, ())


class TestStaffPrincipalRequireLeadership(unittest.TestCase):
    def test_enough_months_without_leadership_still_fails_staff(self) -> None:
        graph = _build_graph([{
            "rid": "long-tenure", "title": "Senior Backend Developer",
            "start": date(2010, 1, 1), "end": date(2023, 12, 31),
            "responsibilities": ["Owned the billing platform's data ingestion service."],
        }])
        assessment = seniority.assess(graph, required_level="staff")
        self.assertGreaterEqual(assessment.total_months, 120)
        self.assertFalse(assessment.has_leadership)
        self.assertFalse(assessment.meets_requirement)

    def test_enough_months_with_leadership_meets_staff(self) -> None:
        graph = _build_graph([{
            "rid": "long-tenure-lead", "title": "Senior Backend Developer",
            "start": date(2010, 1, 1), "end": date(2023, 12, 31),
            "responsibilities": ["Led the shared data platform team across the engineering group."],
        }])
        assessment = seniority.assess(graph, required_level="staff")
        self.assertGreaterEqual(assessment.total_months, 120)
        self.assertTrue(assessment.has_leadership)
        self.assertTrue(assessment.meets_requirement)


class TestAssessmentEdgeCases(unittest.TestCase):
    def test_no_employment_history_returns_none(self) -> None:
        self.assertIsNone(seniority.assess(TruthGraph(), required_level="senior"))

    def test_unspecified_required_level_does_not_meet_but_is_not_fabricated(self) -> None:
        graph = _build_graph([{
            "rid": "some-role", "title": "Backend Developer",
            "start": date(2020, 1, 1), "end": date(2021, 12, 31),
        }])
        assessment = seniority.assess(graph, required_level=None)
        self.assertIsNotNone(assessment)
        self.assertIsNone(assessment.requirement)
        self.assertFalse(assessment.meets_requirement)


class TestExplain(unittest.TestCase):
    def test_explanation_names_months_family_level_and_gap(self) -> None:
        graph = _build_graph([{
            "rid": "gap-role", "title": "Data Engineer",
            "start": date(2024, 1, 1), "end": date(2025, 12, 31),
        }])
        assessment = seniority.assess(graph, required_level="senior", family_aliases=("Data Engineer",))
        text = seniority.explain(assessment, family_label="data engineering")
        self.assertIn("Founder:", text)
        self.assertIn("data engineering", text)
        self.assertIn("Senior", text)
        self.assertIn("gap", text.casefold())


if __name__ == "__main__":
    unittest.main()
