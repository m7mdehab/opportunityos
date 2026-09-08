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

    def test_prefilter_failsafe_fallback(self):
        """When _extract_rule_tokens cannot prove that a literal token is a
        strictly necessary condition for a regex to match, it must return ()
        and the matcher must still execute the regex normally (never dropping
        a policy match)."""
        pattern = r"(?i)(crypto|foo|\d{4})"
        tokens = _extract_rule_tokens(pattern)
        self.assertEqual(tokens, (), "Expected fail-safe empty tokens for unprovable pattern")

        # Graph with the unprovable rule
        tg = TruthGraph()
        tg.add_career_profile(
            CareerProfile(
                id="career-unprovable",
                red_lines=(
                    RedLineRule(
                        id="rl-unprovable",
                        pattern=pattern,
                        reason="Pattern with non-literal branch",
                    ),
                ),
            )
        )

        # Text matches the \d{4} branch without containing 'crypto' or 'foo'
        opp = OpportunityRecord(
            id="opp-digit-match",
            title="Accountant",
            organization="Standard Corp",
            description="Reference code: 4892 in the department.",
        )
        ctx = _make_context(opp, tg)
        self.assertTrue(
            _red_lines_matches(ctx, {}),
            "Matcher must execute fallback regex and match even when tokens are empty",
        )

    def test_update_invalidation_red_lines(self):
        """Opportunity content updates must invalidate cached match outcomes
        even when the opportunity ID and TruthGraph ID remain identical."""
        tg = _build_test_graph()

        opp = OpportunityRecord(
            id="opp-mutable-redline",
            title="Python Engineer",
            organization="Tech Co",
            description="Developing web APIs.",
            content_hash="hash-initial-1",
        )
        ctx = _make_context(opp, tg)
        # Initial evaluation: no red line
        self.assertFalse(_red_lines_matches(ctx, {}))

        # Update description and content_hash (same opp.id)
        opp_updated = OpportunityRecord(
            id="opp-mutable-redline",
            title="Python Engineer",
            organization="Tech Co",
            description="Developing online sportsbook and casino betting algorithms.",
            content_hash="hash-updated-2",
        )
        ctx_updated = _make_context(opp_updated, tg)
        # Next evaluation MUST return True (cache invalidated by content_hash change)
        self.assertTrue(
            _red_lines_matches(ctx_updated, {}),
            "Updated content must miss stale cache and re-evaluate to True",
        )

    def test_update_invalidation_excluded_industries(self):
        """Excluded-industry matcher must invalidate cache when content updates."""
        tg = _build_test_graph()

        opp = OpportunityRecord(
            id="opp-mutable-industry",
            title="Platform Architect",
            organization="Retail Co",
            description="E-commerce infrastructure.",
            content_hash="hash-ind-1",
        )
        ctx = _make_context(opp, tg)
        self.assertFalse(_excluded_industries_matches(ctx, {}))

        # Update description to match excluded industry (Finance) with new hash
        opp_updated = OpportunityRecord(
            id="opp-mutable-industry",
            title="Platform Architect",
            organization="Retail Co",
            description="Core finance banking system integration.",
            content_hash="hash-ind-2",
        )
        ctx_updated = _make_context(opp_updated, tg)
        self.assertTrue(
            _excluded_industries_matches(ctx_updated, {}),
            "Updated content must miss stale cache and match excluded industry",
        )

    def test_update_invalidation_fallback_without_content_hash(self):
        """When content_hash is None, the fingerprint falls back to title/org/desc."""
        tg = _build_test_graph()

        opp = OpportunityRecord(
            id="opp-no-hash",
            title="Developer",
            organization="Corp",
            description="Simple tools.",
            content_hash=None,
        )
        ctx = _make_context(opp, tg)
        self.assertFalse(_red_lines_matches(ctx, {}))

        # Modify description directly
        opp_updated = OpportunityRecord(
            id="opp-no-hash",
            title="Developer",
            organization="Corp",
            description="Online casino systems.",
            content_hash=None,
        )
        ctx_updated = _make_context(opp_updated, tg)
        self.assertTrue(
            _red_lines_matches(ctx_updated, {}),
            "Fingerprint without content_hash must invalidate on description change",
        )


if __name__ == "__main__":
    unittest.main()

