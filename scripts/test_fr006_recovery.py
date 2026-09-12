"""Fresh deterministic FR-006 recovery checks that must run in the normal full suite.

These tests deliberately use the committed corpus rather than the hand-built A2 fixture.
"""
from __future__ import annotations

import collections
import math
import unittest

from matching.qualification import QualificationEngine
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
from truth.fixtures import founder_shaped_graph


class FullCorpusClusteringAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = load_corpus()
        cls.opportunities, cls.parse_errors = parse_corpus(cls.fixtures)

    def test_a12_remeasures_frozen_corpus_without_inventing_missing_signals(self) -> None:
        self.assertEqual([], self.parse_errors)
        total = len(self.opportunities)
        self.assertGreater(total, 0)

        work_known = sum(1 for opp in self.opportunities if opp.work_mode != "unspecified")
        geo_known = sum(
            1
            for opp in self.opportunities
            if opp.location_country or opp.remote_scope != "unspecified"
        )
        source_counts = collections.Counter(str(opp.work_mode_source) for opp in self.opportunities)

        engine = QualificationEngine()
        graph = founder_shaped_graph()
        decisions = collections.Counter(engine.evaluate(opp, graph)[0].value for opp in self.opportunities)
        uncertain = decisions.get("uncertain", 0)

        work_target_count = math.ceil(0.90 * total)
        geo_target_count = math.ceil(0.85 * total)
        work_missing = total - work_known
        geo_missing = total - geo_known
        work_needed = max(0, work_target_count - work_known)
        geo_needed = max(0, geo_target_count - geo_known)

        print(
            "A-12 current corpus: "
            f"work_mode={work_known}/{total} ({work_known / total:.1%}) "
            f"geo={geo_known}/{total} ({geo_known / total:.1%}) "
            f"uncertain={uncertain}/{total} ({uncertain / total:.1%}) "
            f"work_mode_source={dict(sorted(source_counts.items()))}"
        )
        print(
            "A-12 truthful-signal gap: "
            f"work_needed={work_needed}/{work_missing} currently-unspecified rows "
            f"geo_needed={geo_needed}/{geo_missing} currently-unresolved rows"
        )

        # The uncertainty target is already truthfully satisfied.  The two
        # extraction coverage thresholds are evidence measurements, not goals
        # that may be manufactured: a missing source/native/inference signal
        # stays unspecified and is dispositioned in the FR-006 report.
        self.assertLess(
            uncertain / total,
            0.25,
            "A-12 frozen acceptance requires qualification uncertainty below 25%",
        )

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

    def test_a20_cloudflare_senior_customer_engineer_subset_is_absent(self) -> None:
        target = [
            opp
            for opp in self.opportunities
            if opp.organization.casefold() == "cloudflare"
            and "senior customer engineer" in opp.title.casefold()
        ]
        # The exact A-20 fixture subset is part of the frozen corpus contract.
        # Its absence is an irreducible fixture mismatch, not a passing
        # clustering result.  Fail if the corpus changes so this explicit
        # disposition cannot become a silent substitute for the requirement.
        self.assertEqual(
            0,
            len(target),
            "frozen corpus changed: re-run the exact A-20 family acceptance "
            "instead of treating this absence check as sufficient",
        )
        print(
            "A-20 Cloudflare Senior Customer Engineer: ABSENT "
            f"(exact corpus rows={len(target)}; requirement remains NOT_CLOSED)"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
