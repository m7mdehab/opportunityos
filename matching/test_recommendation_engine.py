from __future__ import annotations

import unittest

from matching.recommendation_engine import (
    BehaviorSignal,
    RecommendationCandidate,
    build_behavior_profile,
    compose_for_you,
    recommend,
)


def candidate(opportunity_id: str = "job-1", **overrides) -> RecommendationCandidate:
    values = dict(
        opportunity_id=opportunity_id,
        role_relevance="core",
        geography="likely_eligible",
        application_access="direct_free",
        application_url="https://jobs.example/apply",
        decision="qualified",
        fit_score=82,
        confidence_score=76,
        role_family="data_engineering",
        source_family="greenhouse",
        evidence_completeness=80,
        freshness_score=90,
        source_application_confidence=75,
        family_key=f"family-{opportunity_id}",
        organization="Employer",
    )
    values.update(overrides)
    return RecommendationCandidate(**values)


class RecommendationEngineTests(unittest.TestCase):
    def test_for_you_requires_all_hard_gates_and_evidence(self):
        result = recommend(candidate())
        self.assertEqual(result.state, "for_you")
        self.assertEqual(result.reasons, ("recommendation_gates_passed",))
        self.assertEqual(recommend(candidate(application_access="unknown")).state, "review")
        self.assertEqual(recommend(candidate(application_url=None)).state, "review")
        self.assertEqual(recommend(candidate(geography="review")).state, "review")
        self.assertEqual(recommend(candidate(role_relevance="unknown")).state, "review")
        self.assertEqual(recommend(candidate(evidence_completeness=55)).state, "review")

    def test_explicit_incompatibilities_staleness_and_founder_rejections_exclude(self):
        for overrides in (
            {"role_relevance": "non_target"},
            {"geography": "ineligible"},
            {"is_stale": True},
            {"feedback_label": "irrelevant_role"},
            {"feedback_label": "bad_match"},
            {"action_state": "rejected"},
            {"action_state": "applied"},
            {"decision": "ineligible"},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(recommend(candidate(**overrides)).state, "excluded")

    def test_eligibility_correction_does_not_become_role_negative(self):
        result = recommend(candidate(feedback_label="eligibility_wrong"))
        self.assertEqual(result.state, "review")
        self.assertEqual(result.reasons, ("founder_eligibility_correction",))

    def test_fit_is_not_replaced_and_rank_is_lexicographic(self):
        lower_role = recommend(candidate(role_relevance="adjacent", fit_score=100))
        core = recommend(candidate(role_relevance="core", fit_score=1))
        self.assertGreater(core.rank_key, lower_role.rank_key)
        self.assertEqual(core.fit_score, 1)

    def test_saved_is_neutral_and_behavior_signals_are_bounded(self):
        saved = build_behavior_profile([BehaviorSignal(
            role_family="data_engineering", source_family="greenhouse", action_type="save",
        )])
        neutral = saved.score(role_family="data_engineering", source_family="greenhouse")
        positive = build_behavior_profile([BehaviorSignal(
            role_family="data_engineering", source_family="greenhouse", feedback_label="good_match",
        )]).score(role_family="data_engineering", source_family="greenhouse")
        eligibility = build_behavior_profile([BehaviorSignal(
            role_family="data_engineering", source_family="greenhouse", feedback_label="eligibility_wrong",
        )]).score(role_family="data_engineering", source_family="greenhouse")
        applied = build_behavior_profile([BehaviorSignal(
            role_family="data_engineering", action_type="applied",
        )]).score(role_family="data_engineering", source_family="greenhouse")
        self.assertEqual(neutral, 50.0)
        self.assertEqual(eligibility, 50.0)
        self.assertGreater(positive, neutral)
        self.assertGreater(applied, neutral)
        self.assertLessEqual(positive, 100.0)

    def test_composition_dedupes_families_and_is_deterministic(self):
        candidates = [
            candidate("job-b", family_key="same", organization="Alpha", fit_score=70),
            candidate("job-a", family_key="same", organization="Alpha", fit_score=90),
            candidate("job-c", family_key="other", organization="Beta", fit_score=80),
        ]
        recs = [recommend(item) for item in candidates]
        self.assertEqual(compose_for_you(recs, candidates), ("job-a", "job-c"))
        self.assertEqual(compose_for_you(reversed(recs), reversed(candidates)), ("job-a", "job-c"))

    def test_employer_cap_limits_first_twenty_when_inventory_allows(self):
        items = [candidate(f"a-{i}", family_key=f"family-a-{i}", organization="Alpha", fit_score=100-i) for i in range(10)]
        items += [candidate(f"b-{i}", family_key=f"family-b-{i}", organization=f"Employer {i}", fit_score=70-i) for i in range(16)]
        order = compose_for_you([recommend(item) for item in items], items, limit=20)
        alpha_count = sum(1 for item in order if next(row for row in items if row.opportunity_id == item).organization == "Alpha")
        self.assertEqual(len(order), 20)
        self.assertLessEqual(alpha_count, 4)


if __name__ == "__main__":
    unittest.main()
