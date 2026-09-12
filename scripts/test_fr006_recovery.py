"""Fresh deterministic FR-006 recovery checks that must run in the normal full suite.

These tests deliberately use the committed corpus rather than the hand-built A2 fixture.
"""
from __future__ import annotations

import collections
import unittest

from matching.title_family import normalize_title
from opportunity.clustering import (
    FamilyMember,
    check_family_invariants,
    cluster_opportunities,
    family_key,
    normalized_title_key,
)
from opportunity.fixtures import load_corpus
from scripts.corpus_metrics import parse_corpus


class FullCorpusClusteringAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = load_corpus()
        cls.opportunities, cls.parse_errors = parse_corpus(cls.fixtures)

    def test_a13_title_family_coverage_meets_frozen_threshold(self) -> None:
        self.assertEqual([], self.parse_errors)
        total = len(self.opportunities)
        mapped = [opp for opp in self.opportunities if normalize_title(opp.title)[0] != "other"]
        residual = collections.Counter(
            opp.title for opp in self.opportunities if normalize_title(opp.title)[0] == "other"
        )
        coverage = (len(mapped) / total) if total else 0.0
        print(
            "A-13 title-family coverage: "
            f"mapped={len(mapped)}/{total} ({coverage:.1%}) residual_unique={len(residual)}"
        )
        if residual:
            print("A-13 residual titles: " + repr(residual.most_common(30)))
        self.assertGreaterEqual(
            coverage,
            0.95,
            "A-13 frozen acceptance requires >=95% of committed-corpus opportunity titles to map to a real family",
        )

    def test_a20_runs_on_complete_committed_corpus(self) -> None:
        self.assertGreaterEqual(len(self.fixtures), 200)
        self.assertEqual([], self.parse_errors)
        self.assertGreaterEqual(len(self.opportunities), 200)

        family_count, cross_employer, cross_title = check_family_invariants(
            FamilyMember(opp) for opp in self.opportunities
        )
        self.assertEqual(0, cross_employer)
        self.assertEqual(0, cross_title)

        first = tuple(family_key(opp) for opp in self.opportunities)
        second = tuple(family_key(opp) for opp in self.opportunities)
        self.assertEqual(first, second)

        families = cluster_opportunities(self.opportunities)
        self.assertEqual(family_count, len(families))
        print(
            "A-20 full corpus: "
            f"payloads={len(self.fixtures)} opportunities={len(self.opportunities)} "
            f"families={len(families)} cross_employer={cross_employer} "
            f"cross_normalized_title={cross_title} deterministic={first == second}"
        )

    def test_a20_cloudflare_senior_customer_engineer_is_one_family(self) -> None:
        target = [
            opp
            for opp in self.opportunities
            if opp.organization.casefold() == "cloudflare"
            and "senior customer engineer" in opp.title.casefold()
        ]
        self.assertGreater(len(target), 1, "committed corpus must contain the multi-location Cloudflare set")
        keys = {family_key(opp) for opp in target}
        normalized_titles = {normalized_title_key(opp.title) for opp in target}
        self.assertEqual(1, len(keys))
        self.assertEqual(1, len(normalized_titles))

        family = next(f for f in cluster_opportunities(target) if f.family_key in keys)
        self.assertEqual(len(target), family.member_count)
        print(
            "A-20 Cloudflare Senior Customer Engineer: "
            f"member_count={family.member_count} family_key={family.family_key}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
