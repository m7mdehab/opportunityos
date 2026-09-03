"""Tests for Multidimensional Scorer and Requirement Mapping."""
from __future__ import annotations

import unittest
from datetime import date

from opportunity.models import (
    Compensation,
    CompensationInterval,
    EmploymentType,
    Opportunity,
    WorkMode,
    Track,
)
from truth.models import AtomicAssertion, EvidenceRecord, VerificationStatus
from truth import predicates
from matching.mapping import RequirementMapper
from matching.models import (
    QualificationDecision,
    RequirementSupportStatus,
    ScoringPolicy,
)
from matching.scorer import OpportunityScorer
from matching.test_qualification import create_test_graph, create_test_opportunity


def _with_employment_tenure(graph, *, start: date, end: date):
    """`matching.test_qualification.create_test_graph()` (frozen for this
    deliverable -- BRIEF-FR-006 order B1) asserts only `employment.title` and
    `employment.responsibility` under subject `"founder"`, with no dates. The
    old keyword-substring seniority model didn't need dates, so the fixture
    never carried any. `matching/seniority.py` (ADR-0016) computes tenure from
    verified `employment.start_date`/`employment.end_date` assertions, so
    without this helper every scorer test built on `create_test_graph()` would
    fall into the "no computable tenure" branch regardless of how senior the
    fixture's title reads. This adds real, evidence-backed dates under the
    same `"founder"` subject the existing title/responsibility assertions
    already use, rather than editing the frozen fixture.
    """
    ev_dates = EvidenceRecord(
        id="ev-title-dates",
        content=f"Employed as Senior Distributed Systems Architect from {start.isoformat()} to {end.isoformat()}.",
        source="manual",
        locator="employment.dates",
    )
    graph.add_evidence(ev_dates)
    graph.add_assertion(AtomicAssertion(
        id="a-title-start",
        subject_id="founder",
        predicate=predicates.EMPLOYMENT_START_DATE,
        value=start,
        evidence_ids=("ev-title-dates",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    graph.add_assertion(AtomicAssertion(
        id="a-title-end",
        subject_id="founder",
        predicate=predicates.EMPLOYMENT_END_DATE,
        value=end,
        evidence_ids=("ev-title-dates",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    return graph


class TestOpportunityScorerAndMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.truth_graph = _with_employment_tenure(
            create_test_graph(), start=date(2015, 1, 1), end=date(2026, 8, 31),
        )
        self.scorer = OpportunityScorer()
        self.mapper = RequirementMapper()

    def test_high_fit_employment_opportunity(self) -> None:
        opp = create_test_opportunity(
            skills=("Python", "Go"),
            title="Senior Distributed Systems Architect",
        )
        eval_res = self.scorer.evaluate(opp, self.truth_graph)
        self.assertEqual(eval_res.qualification_decision, QualificationDecision.QUALIFIED)
        self.assertTrue(eval_res.overall_fit_score >= 80.0)
        self.assertTrue(len(eval_res.strengths) > 0)
        self.assertTrue(len(eval_res.dimension_scores) >= 5)

    def test_low_fit_different_skills_opportunity(self) -> None:
        opp = create_test_opportunity(
            skills=("Rust", "Haskell", "Scala"),
            title="Junior Frontend Developer",
        )
        eval_res = self.scorer.evaluate(opp, self.truth_graph)
        self.assertTrue(eval_res.overall_fit_score < 70.0)
        self.assertTrue(len(eval_res.gaps) > 0)

    def test_requirement_mapping_classification(self) -> None:
        opp = create_test_opportunity(
            skills=("Python", "Rust"),
        )
        req_map = self.mapper.map_requirements(opp, self.truth_graph)
        self.assertEqual(req_map.opportunity_id, opp.id)
        statuses = [m.status for m in req_map.mappings]
        self.assertIn(RequirementSupportStatus.SUPPORTED, statuses)  # Python
        self.assertIn(RequirementSupportStatus.GAP, statuses)        # Rust


def _with_premium_threshold(graph, threshold: str):
    """Add a verified `preference.fulltime_onsite_premium_monthly` assertion to `graph`,
    backed by its own supporting evidence record so the graph's value-support check
    (`truth/graph.py::_is_value_supported_by_evidence`) is satisfied honestly.
    """
    from truth.models import EvidenceRecord

    graph.add_evidence(EvidenceRecord(
        id="ev-premium-threshold",
        content=f"Minimum acceptable full-time on-site compensation: {threshold} per month.",
        source="manual",
        locator="preference.fulltime_onsite_premium_monthly",
        metadata={"threshold": threshold},
    ))
    graph.add_assertion(AtomicAssertion(
        id="a-premium-threshold",
        subject_id="founder",
        predicate=predicates.PREFERENCE_FULLTIME_ONSITE_PREMIUM_MONTHLY,
        value=threshold,
        evidence_ids=("ev-premium-threshold",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    return graph


class TestPremiumFullTimeOnsiteRule(unittest.TestCase):
    """Premium full-time/on-site rule: a ranking signal, never a constraint (D2)."""

    def setUp(self) -> None:
        self.scorer = OpportunityScorer()

    def _comp_dimension(self, eval_res):
        for ds in eval_res.dimension_scores:
            if ds.dimension_name == "compensation_fit":
                return ds
        raise AssertionError("compensation_fit dimension not found")

    def test_egp_compensation_below_threshold_records_gap_but_stays_qualified(self) -> None:
        graph = _with_premium_threshold(create_test_graph(), "85000 EGP")
        opp = create_test_opportunity(
            employment_type=EmploymentType.FULL_TIME,
            work_mode=WorkMode.ONSITE,
            location_raw="Egypt",
            compensation=Compensation(min_amount=40000, max_amount=40000, currency="EGP", interval=CompensationInterval.MONTHLY),
        )
        eval_res = self.scorer.evaluate(opp, graph)
        comp = self._comp_dimension(eval_res)
        self.assertTrue(any("premium" in g.casefold() for g in comp.gaps))
        self.assertTrue(len(comp.evidence_refs) > 0)
        # Qualification decision is never changed by this ranking-only signal.
        self.assertNotEqual(eval_res.qualification_decision, QualificationDecision.INELIGIBLE)

    def test_usd_compensation_meets_threshold_records_no_gap(self) -> None:
        graph = _with_premium_threshold(create_test_graph(), "5000 USD")
        opp = create_test_opportunity(
            employment_type=EmploymentType.FULL_TIME,
            work_mode=WorkMode.ONSITE,
            location_raw="Egypt",
            compensation=Compensation(min_amount=6000, max_amount=6000, currency="USD", interval=CompensationInterval.MONTHLY),
        )
        eval_res = self.scorer.evaluate(opp, graph)
        comp = self._comp_dimension(eval_res)
        self.assertFalse(any("premium" in g.casefold() for g in comp.gaps))

    def test_unknown_compensation_is_never_penalized(self) -> None:
        graph = _with_premium_threshold(create_test_graph(), "85000 EGP")
        opp = create_test_opportunity(
            employment_type=EmploymentType.FULL_TIME,
            work_mode=WorkMode.ONSITE,
            location_raw="Egypt",
            compensation=None,
        )
        eval_res = self.scorer.evaluate(opp, graph)
        comp = self._comp_dimension(eval_res)
        self.assertFalse(any("premium" in g.casefold() for g in comp.gaps))
        self.assertTrue(any("unstated" in u.casefold() for u in comp.unknowns))
        self.assertEqual(comp.raw_score, 0.50)

    def test_non_fulltime_role_never_triggers_the_rule(self) -> None:
        graph = _with_premium_threshold(create_test_graph(), "85000 EGP")
        opp = create_test_opportunity(
            employment_type=EmploymentType.CONTRACT,
            work_mode=WorkMode.ONSITE,
            location_raw="Egypt",
            compensation=Compensation(min_amount=1000, max_amount=1000, currency="EGP", interval=CompensationInterval.MONTHLY),
        )
        eval_res = self.scorer.evaluate(opp, graph)
        comp = self._comp_dimension(eval_res)
        self.assertFalse(any("premium" in g.casefold() for g in comp.gaps))


if __name__ == "__main__":
    unittest.main()
