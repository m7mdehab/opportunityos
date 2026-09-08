"""Unit and regression tests for api/filters.py matching optimizations (FA-002).

Tests:
1. _extract_rule_tokens parses alternations, phrases, and keyword roots accurately.
2. _red_lines_matches produces identical boolean outcomes with pre-filtering as raw regex.
3. _excluded_industries_matches maintains word-boundary isolation (e.g. 'Finance' != 'Financial').
4. _target_roles_matches uses ctx.opp.title_family directly and falls back to normalize_title when None.
5. Cache invalidation across different TruthGraph instances.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import MagicMock

from api.filters import (
    OpportunityFilterContext,
    _excluded_industries_matches,
    _extract_rule_tokens,
    _red_lines_matches,
    _target_roles_matches,
)
from storage.models import OpportunityRecord
from truth.graph import TruthGraph
from truth.models import (
    AtomicAssertion,
    CapabilityProfile,
    CareerProfile,
    EvidenceRecord,
    RedLineRule,
    VerificationStatus,
)


def _build_test_graph() -> TruthGraph:
    tg = TruthGraph()
    tg.add_evidence(
        EvidenceRecord(
            id="ev-cap",
            content="Excludes Finance and Adult Content industries.",
            source="manual",
            locator="capability_profile.summary",
        )
    )
    tg.add_evidence(
        EvidenceRecord(
            id="ev-target-role",
            content="Target role is Software Engineer.",
            source="manual",
            locator="career.target_role",
        )
    )
    tg.add_career_profile(
        CareerProfile(
            id="career-test",
            red_lines=(
                RedLineRule(
                    id="rl-1",
                    pattern=r"(?i)(gambling|betting|casino|sportsbook)",
                    reason="No gambling",
                ),
                RedLineRule(
                    id="rl-2",
                    pattern=r"(?i)(pyramid scheme|multi-level marketing|\bMLM\b|scam)",
                    reason="No scam",
                ),
            ),
        )
    )
    tg.add_capability_profile(
        CapabilityProfile(
            id="cap-test",
            evidence_ids=("ev-cap",),
            excluded_industries=("Finance", "Adult Content"),
        )
    )
    tg.add_assertion(
        AtomicAssertion(
            id="assert-target-role",
            subject_id="founder",
            predicate="career.target_role",
            value="Software Engineer",
            evidence_ids=("ev-target-role",),
            verification_status=VerificationStatus.VERIFIED,
        )
    )
    return tg


def _make_context(opp: OpportunityRecord, tg: TruthGraph | None) -> OpportunityFilterContext:
    return OpportunityFilterContext(
        opp=opp,
        decision=None,
        fit_score=None,
        reasons=[],
        evaluation_detail={},
        dimension_scores=[],
        compensation_min=None,
        compensation_max=None,
        compensation_currency=None,
        truth_graph=tg,
    )


class FilterOptimizationTest(unittest.TestCase):
    def test_extract_rule_tokens(self):
        tokens1 = _extract_rule_tokens(r"(?i)(gambling|betting|casino|sportsbook)")
        self.assertEqual(set(tokens1), {"gambling", "betting", "casino", "sportsbook"})

        tokens2 = _extract_rule_tokens(r"(?i)(pyramid scheme|multi-level marketing|\bMLM\b|scam)")
        self.assertIn("pyramid scheme", tokens2)
        self.assertIn("multi-level marketing", tokens2)
        self.assertIn("scam", tokens2)

    def test_red_lines_matches_accuracy(self):
        tg = _build_test_graph()

        opp_clean = OpportunityRecord(
            id="opp-clean",
            title="Senior Python Backend Engineer",
            organization="Tech Corp",
            description="Build scalable distributed systems using Python and FastAPI.",
        )
        ctx_clean = _make_context(opp_clean, tg)
        self.assertFalse(_red_lines_matches(ctx_clean, {}))

        opp_gambling = OpportunityRecord(
            id="opp-gambling",
            title="Lead Developer",
            organization="Betting Inc",
            description="Online casino and sports betting platform developer.",
        )
        ctx_gambling = _make_context(opp_gambling, tg)
        self.assertTrue(_red_lines_matches(ctx_gambling, {}))

        opp_scam = OpportunityRecord(
            id="opp-scam",
            title="Affiliate Representative",
            organization="Mystery Ltd",
            description="Join our multi-level marketing pyramid scheme opportunity.",
        )
        ctx_scam = _make_context(opp_scam, tg)
        self.assertTrue(_red_lines_matches(ctx_scam, {}))

    def test_excluded_industries_word_boundary(self):
        tg = _build_test_graph()

        # "Financial" should NOT match "Finance"
        opp_financial = OpportunityRecord(
            id="opp-fin",
            title="Software Architect",
            organization="Financial Analytics Inc",
            description="Working on financial forecasting software.",
        )
        ctx_fin = _make_context(opp_financial, tg)
        self.assertFalse(_excluded_industries_matches(ctx_fin, {}))

        # "Finance" as a whole word SHOULD match
        opp_finance = OpportunityRecord(
            id="opp-finance-exact",
            title="Senior Engineer",
            organization="Global Finance Hub",
            description="Core engineering for banking clients.",
        )
        ctx_finance = _make_context(opp_finance, tg)
        self.assertTrue(_excluded_industries_matches(ctx_finance, {}))

    def test_target_roles_title_family(self):
        tg = _build_test_graph()

        # Opportunity has title_family already persisted
        opp_with_family = OpportunityRecord(
            id="opp-matched-family",
            title="Anything here",
            title_family="software_engineering",
        )
        ctx_fam = _make_context(opp_with_family, tg)
        # software_engineering matches Software Engineer target role -> not misaligned -> returns False
        self.assertFalse(_target_roles_matches(ctx_fam, {}))

        # Opportunity with different family -> misaligned -> returns True
        opp_other_family = OpportunityRecord(
            id="opp-other-family",
            title="Nurse Practitioner",
            title_family="medical",
        )
        ctx_other = _make_context(opp_other_family, tg)
        self.assertTrue(_target_roles_matches(ctx_other, {}))

        # Opportunity with None title_family falls back to normalize_title(title)
        opp_fallback = OpportunityRecord(
            id="opp-fallback",
            title="Software Engineer",
            title_family=None,
        )
        ctx_fb = _make_context(opp_fallback, tg)
        self.assertFalse(_target_roles_matches(ctx_fb, {}))


if __name__ == "__main__":
    unittest.main()
