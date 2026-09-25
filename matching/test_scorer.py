"""Tests for Multidimensional Scorer and Requirement Mapping."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date

from opportunity.models import (
    Compensation,
    CompensationInterval,
    EmploymentType,
    Opportunity,
    RemoteScope,
    SeniorityLevel,
    WorkMode,
    Track,
)
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, CertificationState, EvidenceRecord, Polarity, VerificationStatus
from truth import predicates
from matching.mapping import RequirementMapper
from matching.models import (
    QualificationDecision,
    RequirementPriority,
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
            remote_scope=RemoteScope.WORLDWIDE,
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
        opp = create_test_opportunity(
            skills=("Python", "Go"),
            title="Senior Distributed Systems Architect",
            description="Requirements:\nPython\nGo",
        )
        eval_res = self.scorer.evaluate(opp, self.truth_graph)
        skills_dim = next(d for d in eval_res.dimension_scores if d.dimension_name == "core_skills")
        self.assertEqual(skills_dim.strengths, ())
        self.assertTrue(any("Partial skill signal" in u for u in skills_dim.unknowns))

    def test_low_fit_different_skills_opportunity(self) -> None:
        opp = create_test_opportunity(
            skills=("Rust", "Haskell", "Scala"),
            title="Junior Frontend Developer",
            description="Requirements:\nRust\nHaskell\nScala",
        )
        eval_res = self.scorer.evaluate(opp, self.truth_graph)
        self.assertTrue(eval_res.overall_fit_score < 70.0)
        self.assertTrue(len(eval_res.gaps) > 0)

    def test_requirement_mapping_classification(self) -> None:
        opp = create_test_opportunity(
            skills=("Python", "Rust"),
            description="Requirements:\nPython\nRust",
        )
        req_map = self.mapper.map_requirements(opp, self.truth_graph)
        self.assertEqual(req_map.opportunity_id, opp.id)
        statuses = [m.status for m in req_map.mappings]
        self.assertIn(RequirementSupportStatus.SUPPORTED, statuses)  # Python
        self.assertIn(RequirementSupportStatus.GAP, statuses)        # Rust
        priorities = {
            m.requirement_text.removeprefix("Proficiency in "): m.requirement_priority
            for m in req_map.mappings if m.requirement_type == "skill"
        }
        self.assertEqual(priorities["Python"], RequirementPriority.MANDATORY)
        self.assertEqual(priorities["Rust"], RequirementPriority.MANDATORY)

    def test_company_technology_mentions_are_context_not_skill_gaps(self) -> None:
        opp = create_test_opportunity(
            skills=("Python", "Go"),
            description="About Us:\nWe use Python and Go in our platform.",
        )
        req_map = self.mapper.map_requirements(opp, self.truth_graph)
        skill_maps = [m for m in req_map.mappings if m.requirement_type == "skill"]
        self.assertTrue(skill_maps)
        self.assertTrue(all(m.requirement_priority == RequirementPriority.CONTEXTUAL for m in skill_maps))
        self.assertTrue(all(m.status != RequirementSupportStatus.GAP for m in skill_maps))

        evaluation = self.scorer.evaluate(opp, self.truth_graph)
        skills_dim = next(d for d in evaluation.dimension_scores if d.dimension_name == "core_skills")
        self.assertEqual(skills_dim.raw_score, 0.5)
        self.assertEqual(skills_dim.strengths, ())
        self.assertEqual(skills_dim.gaps, ())

    def test_full_description_skill_extraction_precedes_neutral_fallback(self) -> None:
        graph = _with_skill_proficiency(self.truth_graph, proficiency="expert")
        opp = create_test_opportunity(
            skills=(),
            description="Requirements:\nPython\nGo",
        )
        evaluation = self.scorer.evaluate(opp, graph)
        skills_dim = next(d for d in evaluation.dimension_scores if d.dimension_name == "core_skills")
        self.assertTrue(any("Python" in s for s in skills_dim.strengths))
        self.assertTrue(any("Go" in s for s in skills_dim.strengths))
        self.assertEqual(skills_dim.raw_score, 1.0)


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


class TestPreferenceScoreIsolation(unittest.TestCase):
    def _add_preference(
        self,
        graph: TruthGraph,
        *,
        value: str,
        status: VerificationStatus = VerificationStatus.VERIFIED,
        polarity: Polarity = Polarity.POSITIVE,
        predicate: str = predicates.PREFERENCE_WORK_MODE,
    ) -> None:
        sequence = getattr(self, "_preference_fixture_sequence", 0) + 1
        self._preference_fixture_sequence = sequence
        ev_id = f"ev-pref-{sequence}"
        assertion_id = f"a-pref-{sequence}"
        graph.add_evidence(EvidenceRecord(
            id=ev_id, content=f"Preference: {value}", source="manual", locator=predicate,
        ))
        graph.add_assertion(AtomicAssertion(
            id=assertion_id,
            subject_id="founder",
            predicate=predicate,
            value=value,
            evidence_ids=(ev_id,),
            verification_status=status,
            polarity=polarity,
        ))

    def test_work_mode_preference_is_separate_from_capability_and_qualification(self) -> None:
        graph = create_test_graph()
        opp = create_test_opportunity(work_mode=WorkMode.REMOTE, remote_scope=RemoteScope.WORLDWIDE)
        baseline = OpportunityScorer().evaluate(opp, graph)
        self._add_preference(graph, value="remote")
        preferred = OpportunityScorer().evaluate(opp, graph)

        self.assertEqual(preferred.preference_score, 100.0)
        self.assertEqual(preferred.overall_fit_score, baseline.overall_fit_score)
        self.assertEqual(preferred.qualification_decision, baseline.qualification_decision)
        self.assertEqual(preferred.confidence_score, baseline.confidence_score)
        self.assertEqual(
            next(d for d in preferred.dimension_scores if d.dimension_name == "preference_work_mode").weight,
            0.0,
        )

    def test_only_verified_positive_preference_assertions_are_scored(self) -> None:
        for status, polarity in (
            (VerificationStatus.UNVERIFIED, Polarity.POSITIVE),
            (VerificationStatus.VERIFIED, Polarity.NEGATIVE),
        ):
            graph = create_test_graph()
            self._add_preference(graph, value="remote", status=status, polarity=polarity)
            evaluation = OpportunityScorer().evaluate(
                create_test_opportunity(work_mode=WorkMode.REMOTE, remote_scope=RemoteScope.WORLDWIDE),
                graph,
            )
            self.assertIsNone(evaluation.preference_score)
            self.assertNotIn("preference_work_mode", {d.dimension_name for d in evaluation.dimension_scores})

    def test_preference_track_does_not_accept_work_mode_values(self) -> None:
        graph = create_test_graph()
        self._add_preference(graph, value="remote", predicate=predicates.PREFERENCE_TRACK)
        evaluation = OpportunityScorer().evaluate(create_test_opportunity(), graph)

        self.assertIsNone(evaluation.preference_score)
        self.assertNotIn("preference_track", {d.dimension_name for d in evaluation.dimension_scores})

    def test_missing_structured_job_value_does_not_create_a_preference_score(self) -> None:
        graph = create_test_graph()
        self._add_preference(graph, value="remote")
        opp = replace(create_test_opportunity(), work_mode=WorkMode.UNSPECIFIED, remote_scope=RemoteScope.UNSPECIFIED)
        evaluation = OpportunityScorer().evaluate(opp, graph)

        self.assertIsNone(evaluation.preference_score)
        dimension = next(d for d in evaluation.dimension_scores if d.dimension_name == "preference_work_mode")
        self.assertTrue(dimension.unknowns)
        self.assertEqual(dimension.weighted_score, 0.0)

    def test_currency_and_interval_typed_compensation_preference(self) -> None:
        graph = create_test_graph()
        self._add_preference(
            graph,
            value="85000 EGP monthly",
            predicate=predicates.PREFERENCE_COMPENSATION,
        )
        opportunity = create_test_opportunity(
            compensation=Compensation(
                min_amount=90000,
                max_amount=100000,
                currency="EGP",
                interval=CompensationInterval.MONTHLY,
            ),
        )
        evaluation = OpportunityScorer().evaluate(opportunity, graph)

        self.assertEqual(evaluation.preference_score, 100.0)
        dimension = next(d for d in evaluation.dimension_scores if d.dimension_name == "preference_compensation")
        self.assertEqual(dimension.raw_score, 1.0)
        self.assertTrue(dimension.evidence_refs)
        self.assertTrue(all(ref.startswith("a-pref-") for ref in dimension.evidence_refs))

    def test_geography_and_other_preferences_read_structured_job_attributes(self) -> None:
        graph = create_test_graph()
        self._add_preference(graph, value="Egypt", predicate=predicates.PREFERENCE_GEOGRAPHY)
        self._add_preference(graph, value="fintech", predicate=predicates.PREFERENCE_INDUSTRY)
        self._add_preference(graph, value="Cloudflare", predicate=predicates.PREFERENCE_COMPANY)
        self._add_preference(graph, value="UTC+2", predicate=predicates.PREFERENCE_TIME_ZONE)
        self._add_preference(graph, value="contract", predicate=predicates.PREFERENCE_EMPLOYMENT_TYPE)
        self._add_preference(graph, value="willing to relocate", predicate=predicates.PREFERENCE_RELOCATION)
        self._add_preference(graph, value="none", predicate=predicates.PREFERENCE_TRAVEL)
        opp = replace(
            create_test_opportunity(work_mode=WorkMode.ONSITE, employment_type=EmploymentType.CONTRACT),
            location_country="EG",
            extra_attributes=(
                ("industry", "FinTech"),
                ("time_zone", "utc+02:00"),
                ("relocation_required", "true"),
                ("travel_expectation", "none"),
            ),
        )
        evaluation = OpportunityScorer().evaluate(opp, graph)

        self.assertEqual(evaluation.preference_score, 100.0)
        for name in (
            "preference_geography", "preference_industry", "preference_company",
            "preference_time_zone", "preference_employment_type", "preference_relocation",
            "preference_travel",
        ):
            dimension = next(d for d in evaluation.dimension_scores if d.dimension_name == name)
            self.assertEqual(dimension.raw_score, 1.0)

class TestConfidenceScore(unittest.TestCase):
    def _score(self, opp=None, graph=None, evaluated_at="2026-09-25", policy=None):
        return OpportunityScorer(policy=policy).evaluate(
            opp if opp is not None else create_test_opportunity(),
            graph if graph is not None else create_test_graph(),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _factor(evaluation, name):
        return next(factor for factor in evaluation.confidence_factors if factor.name == name)

    def test_seven_named_factors_are_bounded_deterministic_and_equally_averaged(self) -> None:
        opportunity = create_test_opportunity()
        first = self._score(opportunity)
        second = self._score(opportunity)
        expected_names = {
            "description_completeness", "location_remote_scope_clarity",
            "experience_requirement_clarity", "required_skill_extraction_reliability",
            "compensation_completeness", "source_freshness_and_strength",
            "founder_evidence_completeness",
        }
        self.assertEqual({factor.name for factor in first.confidence_factors}, expected_names)
        self.assertEqual(first.confidence_factors, second.confidence_factors)
        self.assertEqual(first.confidence_score, second.confidence_score)
        self.assertEqual(first.confidence_score, round(sum(f.score for f in first.confidence_factors) / 7, 2))
        self.assertGreaterEqual(first.confidence_score, 0.0)
        self.assertLessEqual(first.confidence_score, 100.0)
        self.assertIn("not gold-set calibrated", first.explanation)

    def test_description_location_experience_and_skill_factors_track_evidence_quality(self) -> None:
        baseline = create_test_opportunity()
        short = replace(baseline, description="Short posting.")
        complete_description = replace(baseline, description="D" * 1200)
        self.assertLess(
            self._factor(self._score(short), "description_completeness").score,
            self._factor(self._score(complete_description), "description_completeness").score,
        )

        remote_unspecified = replace(baseline, remote_scope=RemoteScope.UNSPECIFIED)
        remote_worldwide = replace(baseline, remote_scope=RemoteScope.WORLDWIDE)
        self.assertLess(
            self._factor(self._score(remote_unspecified), "location_remote_scope_clarity").score,
            self._factor(self._score(remote_worldwide), "location_remote_scope_clarity").score,
        )

        clear_experience = replace(baseline, requirements=("5+ years of experience",))
        vague_experience = replace(
            baseline,
            title="Engineer",
            seniority=SeniorityLevel.UNSPECIFIED,
            requirements=("Several years of experience",),
        )
        self.assertGreater(
            self._factor(self._score(clear_experience), "experience_requirement_clarity").score,
            self._factor(self._score(vague_experience), "experience_requirement_clarity").score,
        )

        structured_skills = replace(baseline, skills=("Python",))
        unextractable_skills = replace(
            baseline,
            skills=(),
            requirements=(),
            description="Collaborate on product work.",
        )
        self.assertGreater(
            self._factor(self._score(structured_skills), "required_skill_extraction_reliability").score,
            self._factor(self._score(unextractable_skills), "required_skill_extraction_reliability").score,
        )

    def test_compensation_source_and_founder_evidence_factors_reflect_completeness(self) -> None:
        baseline = create_test_opportunity()
        complete_compensation = replace(
            baseline,
            compensation=Compensation(
                min_amount=100000,
                currency="USD",
                interval=CompensationInterval.YEARLY,
            ),
        )
        self.assertGreater(
            self._factor(self._score(complete_compensation), "compensation_completeness").score,
            self._factor(self._score(baseline), "compensation_completeness").score,
        )

        fresh_provenance = replace(baseline.raw_provenance, fetched_at="2026-09-24T00:00:00Z")
        stale_provenance = replace(baseline.raw_provenance, fetched_at="2025-01-01T00:00:00Z")
        fresh = replace(baseline, raw_provenance=fresh_provenance)
        stale = replace(baseline, raw_provenance=stale_provenance)
        self.assertGreater(
            self._factor(self._score(fresh), "source_freshness_and_strength").score,
            self._factor(self._score(stale), "source_freshness_and_strength").score,
        )

        no_founder_evidence = self._score(baseline, graph=TruthGraph())
        reviewed_evidence = self._score(baseline, graph=create_test_graph())
        self.assertLess(
            self._factor(no_founder_evidence, "founder_evidence_completeness").score,
            self._factor(reviewed_evidence, "founder_evidence_completeness").score,
        )
        self.assertNotEqual(no_founder_evidence.qualification_decision, QualificationDecision.INELIGIBLE)

    def test_missing_evidence_does_not_reduce_fit_via_uncertainty_penalty(self) -> None:
        opportunity = create_test_opportunity()
        sparse_graph = TruthGraph()
        no_penalty = self._score(
            opportunity,
            graph=sparse_graph,
            policy=ScoringPolicy(uncertainty_penalty_weight=0.0),
        )
        configured_penalty = self._score(
            opportunity,
            graph=sparse_graph,
            policy=ScoringPolicy(uncertainty_penalty_weight=0.95),
        )
        self.assertEqual(no_penalty.qualification_decision, configured_penalty.qualification_decision)
        self.assertEqual(no_penalty.overall_fit_score, configured_penalty.overall_fit_score)
        self.assertGreater(no_penalty.uncertainty_penalty, 0.0)
        complete_evidence = self._score(opportunity, graph=create_test_graph())
        self.assertLess(no_penalty.confidence_score, complete_evidence.confidence_score)
        self.assertTrue(all(not result.is_hard_failure for result in no_penalty.hard_constraints))


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


def _graph_with_target_role(target_role_value: str) -> TruthGraph:
    """`create_test_graph()` (matching/test_qualification.py, frozen for
    this deliverable) carries no `career.target_role` assertion by default
    -- this adds exactly one, verified, so callers can exercise the
    `title_family_fit` dimension's matched/mismatched branches."""
    graph = create_test_graph()
    graph.add_evidence(EvidenceRecord(
        id="ev-target-role",
        content=target_role_value,
        source="manual",
        locator="career.target_role",
        metadata={"target_role": target_role_value},
    ))
    graph.add_assertion(AtomicAssertion(
        id="a-target-role",
        subject_id="founder",
        predicate=predicates.CAREER_TARGET_ROLE,
        value=target_role_value,
        evidence_ids=("ev-target-role",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    return graph


def _add_verified_assertion(
    graph: TruthGraph,
    *,
    assertion_id: str,
    predicate: str,
    value,
    subject_id: str = "founder",
    evidence_text: str | None = None,
    polarity: Polarity = Polarity.POSITIVE,
) -> None:
    evidence_id = f"ev-{assertion_id}"
    graph.add_evidence(EvidenceRecord(
        id=evidence_id,
        content=evidence_text or str(value),
        source="synthetic-test",
        locator=f"test.{predicate}",
    ))
    graph.add_assertion(AtomicAssertion(
        id=assertion_id,
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        evidence_ids=(evidence_id,),
        verification_status=VerificationStatus.VERIFIED,
        polarity=polarity,
    ))


def _opportunity_with_requirements(requirements: tuple[str, ...], **kwargs):
    return replace(
        create_test_opportunity(**kwargs),
        requirements=requirements,
    )


class TestCareerTrajectoryPredicateIsolation(unittest.TestCase):
    """Only verified career.target_role assertions may match posting titles."""

    def test_remote_track_does_not_match_remote_title_as_career_target_role(self) -> None:
        graph = TruthGraph()
        graph.add_evidence(EvidenceRecord(
            id="ev-remote-track",
            content="Prefers remote work.",
            source="manual",
            locator="preference.track",
        ))
        graph.add_assertion(AtomicAssertion(
            id="a-remote-track",
            subject_id="founder",
            predicate=predicates.PREFERENCE_TRACK,
            value=WorkMode.REMOTE.value,
            evidence_ids=("ev-remote-track",),
            verification_status=VerificationStatus.VERIFIED,
        ))

        evaluation = OpportunityScorer().evaluate(
            create_test_opportunity(title="Remote Data Engineer"),
            graph,
        )
        trajectory = next(
            ds for ds in evaluation.dimension_scores if ds.dimension_name == "career_trajectory"
        )

        self.assertEqual(trajectory.raw_score, 0.50)
        self.assertEqual(trajectory.weighted_score, 0.025)
        self.assertEqual(trajectory.strengths, ())
        self.assertEqual(trajectory.evidence_refs, ())
        self.assertNotIn("a-remote-track", trajectory.evidence_refs)

    def test_career_goal_does_not_match_as_a_target_role(self) -> None:
        graph = TruthGraph()
        graph.add_evidence(EvidenceRecord(
            id="ev-career-goal",
            content="Career goal: Data Engineer.",
            source="manual",
            locator="career.goal",
        ))
        graph.add_assertion(AtomicAssertion(
            id="a-career-goal",
            subject_id="founder",
            predicate=predicates.CAREER_GOAL,
            value="Data Engineer",
            evidence_ids=("ev-career-goal",),
            verification_status=VerificationStatus.VERIFIED,
        ))

        evaluation = OpportunityScorer().evaluate(
            create_test_opportunity(title="Data Engineer"),
            graph,
        )
        trajectory = next(
            ds for ds in evaluation.dimension_scores if ds.dimension_name == "career_trajectory"
        )

        self.assertEqual(trajectory.raw_score, 0.50)
        self.assertEqual(trajectory.weighted_score, 0.025)
        self.assertEqual(trajectory.strengths, ())
        self.assertEqual(trajectory.evidence_refs, ())
        self.assertNotIn("a-career-goal", trajectory.evidence_refs)

    def test_verified_target_role_matches_title_and_supplies_evidence(self) -> None:
        graph = _graph_with_target_role("Data Engineer")
        evaluation = OpportunityScorer().evaluate(
            create_test_opportunity(title="Data Engineer"),
            graph,
        )
        trajectory = next(
            ds for ds in evaluation.dimension_scores if ds.dimension_name == "career_trajectory"
        )

        self.assertEqual(trajectory.raw_score, 0.95)
        self.assertEqual(trajectory.weighted_score, 0.0475)
        self.assertEqual(
            trajectory.strengths,
            ("Opportunity title matches target role: Data Engineer",),
        )
        self.assertEqual(trajectory.evidence_refs, ("a-target-role",))


    def test_profile_target_role_projection_matches_title_and_supplies_evidence(self) -> None:
        from truth.models import CareerProfile, TargetRoleRecord, TargetRoleTier

        graph = TruthGraph()
        graph.add_evidence(EvidenceRecord(
            id="ev-typed-target-role",
            content="Primary target role: Data Engineer.",
            source="manual",
            locator="career_profile.target_roles.0",
        ))
        graph.add_career_profile(CareerProfile(
            id="career-typed-targets",
            target_roles=(TargetRoleRecord(
                id="target-data-engineer",
                title="Data Engineer",
                evidence_ids=("ev-typed-target-role",),
                tier=TargetRoleTier.PRIMARY,
            ),),
        ))

        evaluation = OpportunityScorer().evaluate(
            create_test_opportunity(title="Data Engineer"),
            graph,
        )
        trajectory = next(
            ds for ds in evaluation.dimension_scores if ds.dimension_name == "career_trajectory"
        )
        role_assertion = next(
            assertion for assertion in graph.assertions.values()
            if assertion.predicate == predicates.CAREER_TARGET_ROLE
        )

        self.assertEqual(trajectory.raw_score, 0.95)
        self.assertEqual(trajectory.evidence_refs, (role_assertion.id,))


class TestTitleFamilyFitDimensionIntegration(unittest.TestCase):
    """Council review #1 finding 3 (BRIEF-FR-006 B3): `title_family_fit`
    shipped with no test that ran a full `Opportunity`/`TruthGraph` pair
    through `OpportunityScorer.evaluate()` -- only `normalize_title` was
    unit-tested in isolation (`matching/test_title_family.py`), and nothing
    asserted on the dimension's actual `raw_score`/`strengths`/`gaps` as
    produced by the scorer. The council notes this is also why the
    domain_fit weight-normalization defect (review #2) went undetected:
    nothing exercised this dimension's `weighted_score` end to end. Four
    cases, per the finding: a matching family, a mismatched family, an
    `other`-family posting, and a founder pack with no verified
    `career.target_role` assertion at all."""

    def _dimension(self, evaluation):
        return next(
            ds for ds in evaluation.dimension_scores if ds.dimension_name == "target_role_family_preference"
        )

    def test_matching_family(self) -> None:
        graph = _graph_with_target_role("Data Engineer")
        opp = create_test_opportunity(title="Senior Data Engineer")
        evaluation = OpportunityScorer().evaluate(opp, graph)
        dim = self._dimension(evaluation)
        self.assertEqual(dim.raw_score, 1.0)
        self.assertTrue(dim.strengths)
        self.assertEqual(dim.gaps, ())
        self.assertTrue(dim.evidence_refs)
        self.assertIn("data_engineering", dim.explanation)
        self.assertIn("senior", dim.explanation)  # Finding 8: level surfaced

    def test_mismatched_family(self) -> None:
        graph = _graph_with_target_role("Data Engineer")
        opp = create_test_opportunity(title="Customer Engineer")
        evaluation = OpportunityScorer().evaluate(opp, graph)
        dim = self._dimension(evaluation)
        self.assertEqual(dim.raw_score, 0.20)
        self.assertEqual(dim.strengths, ())
        self.assertTrue(dim.gaps)
        self.assertIn("customer_solutions_engineering", dim.explanation)

    def test_other_family_posting(self) -> None:
        graph = _graph_with_target_role("Data Engineer")
        opp = create_test_opportunity(title="Advisory RFP")
        evaluation = OpportunityScorer().evaluate(opp, graph)
        dim = self._dimension(evaluation)
        self.assertEqual(dim.raw_score, 0.40)
        self.assertEqual(dim.strengths, ())
        self.assertEqual(dim.gaps, ())
        self.assertTrue(dim.unknowns)
        self.assertIn("'other'", dim.explanation)

    def test_no_target_role_assertion(self) -> None:
        graph = create_test_graph()
        opp = create_test_opportunity(title="Data Engineer")
        evaluation = OpportunityScorer().evaluate(opp, graph)
        dim = self._dimension(evaluation)
        self.assertEqual(dim.raw_score, 0.50)
        self.assertTrue(dim.unknowns)
        self.assertIn("no verified career.target_role assertion", dim.unknowns[0])


class TestFR008CapabilityDimensions(unittest.TestCase):
    def _dimension(self, evaluation, name: str):
        return next(ds for ds in evaluation.dimension_scores if ds.dimension_name == name)

    def test_employment_capability_dimensions_are_distinct(self) -> None:
        evaluation = OpportunityScorer().evaluate(
            create_test_opportunity(title="Senior Data Engineer"),
            create_test_graph(),
        )
        dimensions = {dimension.dimension_name for dimension in evaluation.dimension_scores}
        self.assertTrue({
            "core_skills",
            "experience_fit",
            "seniority_fit",
            "responsibility_scope",
            "domain_fit",
            "title_family_fit",
            "education_certification_fit",
        }.issubset(dimensions))
        self.assertIn("target_role_family_preference", dimensions)

    def test_verified_employment_family_is_capability_evidence(self) -> None:
        graph = TruthGraph()
        _add_verified_assertion(
            graph,
            assertion_id="a-employment-title",
            predicate=predicates.EMPLOYMENT_TITLE,
            value="Senior Data Engineer",
            subject_id="employment-1",
        )
        evaluation = OpportunityScorer().evaluate(
            create_test_opportunity(title="Senior Data Engineer"),
            graph,
        )
        capability = self._dimension(evaluation, "title_family_fit")
        preference = self._dimension(evaluation, "target_role_family_preference")
        self.assertEqual(capability.raw_score, 1.0)
        self.assertEqual(capability.evidence_refs, ("a-employment-title",))
        self.assertTrue(capability.strengths)
        self.assertEqual(preference.evidence_refs, ())
        self.assertTrue(preference.unknowns)

    def test_verified_completed_certification_matches_explicit_requirement(self) -> None:
        graph = TruthGraph()
        _add_verified_assertion(
            graph,
            assertion_id="a-pmp-name",
            predicate=predicates.CERTIFICATION_NAME,
            value="PMP",
            subject_id="credential-pmp",
            evidence_text="PMP certification completed.",
        )
        _add_verified_assertion(
            graph,
            assertion_id="a-pmp-state",
            predicate=predicates.CERTIFICATION_STATE,
            value=CertificationState.COMPLETED,
            subject_id="credential-pmp",
            evidence_text="The PMP certification is completed.",
        )
        opportunity = _opportunity_with_requirements(("PMP certification required",))
        evaluation = OpportunityScorer().evaluate(opportunity, graph)
        dimension = self._dimension(evaluation, "education_certification_fit")
        self.assertEqual(dimension.raw_score, 1.0)
        self.assertEqual(dimension.gaps, ())
        self.assertEqual(set(dimension.evidence_refs), {"a-pmp-name", "a-pmp-state"})
        self.assertTrue(dimension.strengths)

    def test_higher_verified_degree_matches_required_degree_and_field(self) -> None:
        graph = TruthGraph()
        _add_verified_assertion(
            graph,
            assertion_id="a-education-qualification",
            predicate=predicates.EDUCATION_QUALIFICATION,
            value="Master of Science in Computer Science",
            subject_id="education-1",
        )
        opportunity = _opportunity_with_requirements(
            ("Bachelor's degree in Computer Science required",),
        )
        evaluation = OpportunityScorer().evaluate(opportunity, graph)
        dimension = self._dimension(evaluation, "education_certification_fit")
        self.assertEqual(dimension.raw_score, 1.0)
        self.assertEqual(dimension.evidence_refs, ("a-education-qualification",))

    def test_missing_credential_evidence_stays_unknown_not_gap(self) -> None:
        evaluation = OpportunityScorer().evaluate(
            _opportunity_with_requirements(("PMP certification required",)),
            TruthGraph(),
        )
        dimension = self._dimension(evaluation, "education_certification_fit")
        self.assertEqual(dimension.raw_score, 0.5)
        self.assertEqual(dimension.gaps, ())
        self.assertTrue(any("No verified matching certification record" in note for note in dimension.unknowns))

    def test_company_context_credential_mention_is_not_applicant_requirement(self) -> None:
        evaluation = OpportunityScorer().evaluate(
            create_test_opportunity(description="We use CISSP standards in our internal controls."),
            TruthGraph(),
        )
        dimension = self._dimension(evaluation, "education_certification_fit")
        self.assertEqual(dimension.raw_score, 0.5)
        self.assertFalse(dimension.gaps)
        self.assertEqual(
            dimension.unknowns,
            ("Posting does not state an explicit applicant-facing education or certification requirement",),
        )

    def test_planned_certification_does_not_match_as_held(self) -> None:
        graph = TruthGraph()
        _add_verified_assertion(
            graph,
            assertion_id="a-pmp-name",
            predicate=predicates.CERTIFICATION_NAME,
            value="PMP",
            subject_id="credential-pmp",
        )
        _add_verified_assertion(
            graph,
            assertion_id="a-pmp-state",
            predicate=predicates.CERTIFICATION_STATE,
            value=CertificationState.PLANNED,
            subject_id="credential-pmp",
        )
        evaluation = OpportunityScorer().evaluate(
            _opportunity_with_requirements(("PMP certification required",)),
            graph,
        )
        dimension = self._dimension(evaluation, "education_certification_fit")
        self.assertEqual(dimension.strengths, ())
        self.assertEqual(dimension.gaps, ())
        self.assertTrue(dimension.unknowns)


if __name__ == "__main__":
    unittest.main()
