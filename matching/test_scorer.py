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
from truth.graph import TruthGraph
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


def _with_skill_proficiency(graph, *, proficiency: str):
    """`matching.test_qualification.create_test_graph()` (frozen) asserts
    `skill.name` = Python and `skill.name` = Go both under subject
    `"founder"` -- a flat, hand-built fixture, unlike a real founder-shaped
    pack where each `SkillRecord` is its own graph entity with its own
    `subject_id` (`truth/graph.py`'s manifest projection). Because both
    skill.name assertions here share subject `"founder"`, a single
    `skill.proficiency` assertion under that same subject resolves for both
    (BRIEF-FR-006 B2's scorer joins skill.proficiency to skill.name by
    `subject_id`, matching how the real graph actually projects proficiency
    per skill entity). This is additive, not an edit to the frozen fixture.
    """
    ev = EvidenceRecord(
        id="ev-skill-proficiency",
        content=f"{proficiency.title()} proficiency with Python and Go, verified across roles.",
        source="manual",
        locator="skills.proficiency",
    )
    graph.add_evidence(ev)
    graph.add_assertion(AtomicAssertion(
        id="a-skill-proficiency",
        subject_id="founder",
        predicate=predicates.SKILL_PROFICIENCY,
        value=proficiency,
        evidence_ids=("ev-skill-proficiency",),
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
        # BRIEF-FR-006 B2: a "high fit" fixture must be genuinely high fit --
        # required skills at >= working proficiency -- not merely name-matched.
        # `_with_skill_proficiency` adds real skill.proficiency evidence; the
        # description's "Requirements:" header is what makes Python/Go
        # *required* rather than nice-to-have (opportunity/inference_rules.yaml).
        graph = _with_skill_proficiency(self.truth_graph, proficiency="expert")
        opp = create_test_opportunity(
            skills=("Python", "Go"),
            title="Senior Distributed Systems Architect",
            description="Build distributed systems.\nRequirements:\nPython\nGo",
        )
        eval_res = self.scorer.evaluate(opp, graph)
        self.assertEqual(eval_res.qualification_decision, QualificationDecision.QUALIFIED)
        self.assertTrue(eval_res.overall_fit_score >= 80.0)
        self.assertTrue(len(eval_res.strengths) > 0)
        self.assertTrue(any("Core skill match" in s for s in eval_res.strengths))
        self.assertTrue(len(eval_res.dimension_scores) >= 5)

    def test_name_matched_skill_with_unknown_proficiency_is_not_a_strength(self) -> None:
        # The regression this whole work order exists to fix: the frozen
        # `create_test_graph()` fixture's Python/Go skill.name assertions
        # carry no proficiency evidence at all. Unknown proficiency must be
        # partial, never a strength -- even though the name matches and the
        # posting's default description carries no required/nice-to-have
        # header (so every skill is conservatively nice-to-have too).
        opp = create_test_opportunity(skills=("Python", "Go"), title="Senior Distributed Systems Architect")
        eval_res = self.scorer.evaluate(opp, self.truth_graph)
        skills_dim = next(d for d in eval_res.dimension_scores if d.dimension_name == "core_skills")
        self.assertEqual(skills_dim.strengths, ())
        self.assertTrue(any("Partial skill signal" in u for u in skills_dim.unknowns))

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


class TestScoringPolicyWeightsSumToOne(unittest.TestCase):
    """B3 (BRIEF-FR-006) council review #2 defect fix: a `weights.get(key,
    default)` fallback default only ever fires when `key` is *absent* from
    the policy dict. Editing the fallback default alone (as the domain_fit
    rebalance originally did) silently does nothing when the key is
    present, and the effective total weight can drift above 1.0 without any
    test catching it. This asserts both totals exactly, and -- the
    assertion that actually matters -- that every weight key
    `matching/scorer.py` reads is present in the corresponding
    `ScoringPolicy` dict, so a future dimension cannot be added by relying
    on a fallback again."""

    def _referenced_weight_keys(self, function_name: str) -> set[str]:
        """Scan `matching/scorer.py`'s source (not a hand-listed set) for
        every string literal passed as the first argument of a
        `weights.get("<key>", ...)` call textually inside the named
        top-level method, via `ast` -- not by hand-listing the keys."""
        import ast
        import inspect

        from matching import scorer as scorer_module

        source = inspect.getsource(scorer_module)
        tree = ast.parse(source, filename=scorer_module.__file__)

        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "OpportunityScorer"
        )
        method_def = next(
            node for node in class_def.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )

        found: set[str] = set()

        class Visitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "weights"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    found.add(node.args[0].value)
                self.generic_visit(node)

        Visitor().visit(method_def)
        return found

    def test_employment_weights_sum_to_one(self) -> None:
        policy = ScoringPolicy()
        self.assertEqual(sum(policy.employment_weights.values()), 1.0)

    def test_independent_weights_sum_to_one(self) -> None:
        policy = ScoringPolicy()
        self.assertEqual(sum(policy.independent_weights.values()), 1.0)

    def test_every_employment_weight_key_scorer_reads_is_in_the_policy_dict(self) -> None:
        referenced = self._referenced_weight_keys("_score_employment")
        self.assertTrue(referenced, "expected _score_employment to reference at least one weight key")
        policy_keys = set(ScoringPolicy().employment_weights)
        missing = referenced - policy_keys
        self.assertEqual(
            missing, set(),
            f"matching/scorer.py._score_employment reads weight key(s) {sorted(missing)} that "
            "are absent from ScoringPolicy().employment_weights -- each such key silently falls "
            "back to the weights.get(...) default forever, which is exactly how the domain_fit "
            "rebalance regression happened.",
        )

    def test_every_independent_weight_key_scorer_reads_is_in_the_policy_dict(self) -> None:
        referenced = self._referenced_weight_keys("_score_independent")
        self.assertTrue(referenced, "expected _score_independent to reference at least one weight key")
        policy_keys = set(ScoringPolicy().independent_weights)
        missing = referenced - policy_keys
        self.assertEqual(
            missing, set(),
            f"matching/scorer.py._score_independent reads weight key(s) {sorted(missing)} that "
            "are absent from ScoringPolicy().independent_weights.",
        )

def _skill_assertion(graph: TruthGraph, *, skill_id: str, name: str, proficiency: str | None, evidence_count: int) -> None:
    """Add one skill.name (+ optional skill.proficiency) assertion under its
    own subject_id -- `skill_id` -- exactly as a real founder-shaped pack's
    manifest projection does (`truth/graph.py`'s `_project_entity_manifest`
    projects one `SkillRecord` entity per skill, so `skill.name` and
    `skill.proficiency` share that entity's own subject_id, not a shared
    "founder" subject). `evidence_count` evidence records are attached so
    the rendered reason string's evidence-strength phrase is meaningful.
    """
    evidence_ids = tuple(f"ev-{skill_id}-{i}" for i in range(evidence_count))
    proficiency_phrase = f" {proficiency} proficiency." if proficiency is not None else ""
    for ev_id in evidence_ids:
        graph.add_evidence(EvidenceRecord(
            id=ev_id, content=f"Used {name} professionally.{proficiency_phrase}", source="manual", locator=f"skills.{skill_id}",
        ))
    graph.add_assertion(AtomicAssertion(
        id=f"a-{skill_id}-name", subject_id=skill_id, predicate=predicates.SKILL_NAME,
        value=name, evidence_ids=evidence_ids, verification_status=VerificationStatus.VERIFIED,
    ))
    if proficiency is not None:
        graph.add_assertion(AtomicAssertion(
            id=f"a-{skill_id}-proficiency", subject_id=skill_id, predicate=predicates.SKILL_PROFICIENCY,
            value=proficiency, evidence_ids=evidence_ids, verification_status=VerificationStatus.VERIFIED,
        ))


class TestSkillProficiencyOrderingAcceptance(unittest.TestCase):
    """BRIEF-FR-006 B2's required ordering acceptance and anti-regression
    check, run over a minimal fixture corpus (`opportunity/fixtures/corpus/`
    per work order A1C is not yet merged into this worktree; this builds an
    equivalent minimal, real, deterministic two-posting corpus in-process).
    """

    def setUp(self) -> None:
        graph = TruthGraph()
        # Founder target role and employment tenure -- a verified senior
        # data-engineering career, same shape as matching.test_qualification's
        # frozen create_test_graph() (subject "founder" for the single span).
        ev_target = EvidenceRecord(
            id="ev-target-role", content="Targeting Data Engineer roles.",
            source="manual", locator="assertions.career.target_role",
        )
        ev_title = EvidenceRecord(
            id="ev-de-title", content="Senior Data Engineer at a logistics group.",
            source="manual", locator="employment.title",
        )
        ev_resp = EvidenceRecord(
            id="ev-de-resp", content="Built and operated Airflow-orchestrated ETL pipelines on Python and SQL.",
            source="manual", locator="employment.responsibility",
        )
        for ev in (ev_target, ev_title, ev_resp):
            graph.add_evidence(ev)
        graph.add_assertion(AtomicAssertion(
            id="a-target-role", subject_id="founder", predicate=predicates.CAREER_TARGET_ROLE,
            value="Data Engineer", evidence_ids=("ev-target-role",), verification_status=VerificationStatus.VERIFIED,
        ))
        graph.add_assertion(AtomicAssertion(
            id="a-de-title", subject_id="founder", predicate=predicates.EMPLOYMENT_TITLE,
            value="Senior Data Engineer", evidence_ids=("ev-de-title",), verification_status=VerificationStatus.VERIFIED,
        ))
        graph.add_assertion(AtomicAssertion(
            id="a-de-resp", subject_id="founder", predicate=predicates.EMPLOYMENT_RESPONSIBILITY,
            value="Built and operated Airflow-orchestrated ETL pipelines on Python and SQL.",
            evidence_ids=("ev-de-resp",), verification_status=VerificationStatus.VERIFIED,
        ))
        graph = _with_employment_tenure(graph, start=date(2015, 1, 1), end=date(2026, 8, 31))

        # Founder skills: real data-engineering strengths at working+ proficiency...
        _skill_assertion(graph, skill_id="skill-python", name="Python", proficiency="expert", evidence_count=3)
        _skill_assertion(graph, skill_id="skill-sql", name="SQL", proficiency="advanced", evidence_count=3)
        _skill_assertion(graph, skill_id="skill-airflow", name="Airflow", proficiency="working", evidence_count=2)
        # ...and the exact defect scenario named in the work order: a skill
        # the founder's own CV records as *basic*.
        _skill_assertion(graph, skill_id="skill-javascript", name="Javascript", proficiency="basic", evidence_count=1)

        self.graph = graph
        self.scorer = OpportunityScorer()

    def test_senior_customer_engineer_no_longer_outscores_data_engineering_match(self) -> None:
        data_eng_opp = create_test_opportunity(
            opp_id="opp-data-eng",
            title="Senior Data Engineer",
            description="Build ETL pipelines.\nRequirements:\nPython\nSQL\nAirflow",
            skills=("Python", "SQL", "Airflow"),
        )
        # Reproduces the reported defect verbatim: a posting requiring a skill
        # the founder's CV records as basic, on a title-mismatched family
        # (matching/title_families.yaml: customer_solutions_engineering, not
        # data_engineering -- matching/test_title_family.py already covers the
        # family split; B2 only changes whether "Javascript" can be a strength).
        customer_eng_opp = create_test_opportunity(
            opp_id="opp-customer-eng",
            title="Senior Customer Engineer",
            description="Support enterprise customers.\nRequirements:\nJavascript\nZendesk\nSalesforce",
            skills=("Javascript", "Zendesk", "Salesforce"),
        )

        de_eval = self.scorer.evaluate(data_eng_opp, self.graph)
        sce_eval = self.scorer.evaluate(customer_eng_opp, self.graph)

        print(
            f"\nB2.6 corpus ordering: Senior Customer Engineer = {sce_eval.overall_fit_score}, "
            f"Senior Data Engineer (best data-engineering match) = {de_eval.overall_fit_score}"
        )

        # The specific anti-regression this work order fixes: Javascript is
        # `basic` proficiency, so the *core_skills* dimension can never render
        # it as a verified/core skill strength, on either evaluation. (Other
        # dimensions, e.g. domain_fit's independent term-overlap check, are
        # out of B2's scope -- confined to matching/scorer.py's skills
        # dimension per the work order's allowed-files list.)
        for evaluation in (de_eval, sce_eval):
            skills_dim = next(d for d in evaluation.dimension_scores if d.dimension_name == "core_skills")
            for strength in skills_dim.strengths:
                self.assertNotIn("Verified core skill: Javascript", strength)
                if "Javascript" in strength:
                    self.fail(f"basic-proficiency skill produced a core_skills strength string: {strength!r}")

        sce_skills_dim = next(d for d in sce_eval.dimension_scores if d.dimension_name == "core_skills")
        self.assertEqual(sce_skills_dim.strengths, ())
        self.assertTrue(any("Javascript" in u and "basic" in u for u in sce_skills_dim.unknowns))

        self.assertLess(
            sce_eval.overall_fit_score, de_eval.overall_fit_score,
            "Senior Customer Engineer must not outscore the founder's data-engineering match",
        )


if __name__ == "__main__":
    unittest.main()
