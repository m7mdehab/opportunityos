"""Unit tests for opportunity.clustering (A2, BRIEF-FR-006).

Builds its own fixture corpus (see module docstring in ``clustering.py`` and
the FR-006 A2 work order: a real ``opportunity/fixtures/corpus/`` set may not
be on this branch yet). The Cloudflare "Senior Customer Engineer" defect
scenario is reproduced by hand: fourteen locations for one role, plus
distinct-employer, distinct-title, and distinct-level postings that must
never be folded into that family.
"""
from __future__ import annotations

import unittest

from opportunity import clustering
from opportunity.models import Opportunity, SeniorityLevel, Track
from opportunity.clustering import (
    Family,
    FamilyMember,
    check_family_invariants,
    cluster_members,
    cluster_opportunities,
    compute_family_key,
    family_key,
    normalized_title_key,
)


def _opp(
    id: str,
    organization: str,
    title: str,
    location_raw: str = "",
    **kwargs,
) -> Opportunity:
    return Opportunity(
        id=id,
        track=Track.EMPLOYMENT,
        source="greenhouse:cloudflare",
        source_url=f"https://boards.greenhouse.io/cloudflare/jobs/{id}",
        source_id=id,
        organization=organization,
        title=title,
        description="A role description long enough to be non-empty.",
        location_raw=location_raw,
        **kwargs,
    )


_CLOUDFLARE_LOCATIONS = (
    "Remote - US Only", "Remote - EMEA", "Remote - APAC", "London, UK",
    "Austin, TX", "New York, NY", "Singapore", "Sydney, Australia",
    "Lisbon, Portugal", "Toronto, Canada", "Remote - LATAM", "Berlin, Germany",
    "San Francisco, CA", "Dublin, Ireland",
)


def _build_cloudflare_customer_engineer_family() -> list[Opportunity]:
    """Fourteen near-identical "Senior Customer Engineer" postings at
    Cloudflare, differing only by location -- the founder's reported defect,
    reproduced by hand."""
    return [
        _opp(f"cf-sce-{i:02d}", "Cloudflare", "Senior Customer Engineer", loc)
        for i, loc in enumerate(_CLOUDFLARE_LOCATIONS)
    ]


def _build_full_corpus() -> list[Opportunity]:
    """The whole hand-built fixture corpus: the 14-member Cloudflare family
    above, plus postings that must never be folded into it or into each
    other -- different employer, different normalized title, different
    seniority level, and two genuine singletons."""
    corpus: list[Opportunity] = []
    corpus += _build_cloudflare_customer_engineer_family()

    # Same title text, different employer -- must never merge with Cloudflare's family.
    corpus.append(_opp("acme-sce-01", "Acme Corp", "Senior Customer Engineer", "Remote - US Only"))

    # Same employer, different normalized title (different family entirely).
    corpus.append(_opp("cf-be-01", "Cloudflare", "Senior Backend Engineer", "Remote - EMEA"))
    corpus.append(_opp("cf-be-02", "Cloudflare", "Senior Backend Engineer - NYC", "New York, NY"))

    # Same employer, same title family, different seniority level -- a real
    # distinction per this module's named assumption; must stay a separate family.
    corpus.append(_opp("cf-ce-01", "Cloudflare", "Customer Engineer", "Remote - US Only"))
    corpus.append(_opp("cf-ce-02", "Cloudflare", "Customer Engineer", "Berlin, Germany"))
    corpus.append(_opp("cf-sce-staff-01", "Cloudflare", "Staff Customer Engineer", "Remote - Worldwide"))

    # Two "other"-bucket postings (no known family match) with genuinely
    # different titles that must not collide just because both are "other".
    corpus.append(_opp("cf-other-01", "Cloudflare", "Zorbatron Wrangler", "Remote - Worldwide"))
    corpus.append(_opp("cf-other-02", "Cloudflare", "Quantum Flux Herder", "Remote - Worldwide"))

    # Two singletons: no sibling anywhere in the corpus.
    corpus.append(_opp("nimbus-de-01", "Nimbus Data", "Data Engineer", "Remote - Worldwide"))
    corpus.append(_opp("acme-pm-01", "Acme Corp", "Product Manager", "San Francisco, CA"))

    return corpus


class TestFamilyKeyDeterminism(unittest.TestCase):
    def test_same_opportunity_same_key(self):
        opp = _opp("x-1", "Cloudflare", "Senior Customer Engineer", "London, UK")
        self.assertEqual(family_key(opp), family_key(opp))

    def test_recompute_over_corpus_twice_is_identical(self):
        """A2.5 determinism check: keys recomputed over the corpus twice are
        identical, independent of dict/set iteration order."""
        corpus = _build_full_corpus()
        first_pass = {opp.id: family_key(opp) for opp in corpus}
        # Recompute in reverse order to actually exercise "independent of
        # iteration order" rather than just re-running the same loop.
        second_pass: dict[str, str] = {}
        for opp in reversed(corpus):
            second_pass[opp.id] = family_key(opp)
        self.assertEqual(first_pass, second_pass)
        print(f"A2.5 determinism: {len(first_pass)} keys compared, "
              f"identical={first_pass == second_pass}")

    def test_compute_family_key_matches_family_key(self):
        opp = _opp("x-2", "Cloudflare", "Senior Customer Engineer", "London, UK")
        self.assertEqual(family_key(opp), compute_family_key(opp.organization, opp.title))

    def test_location_variation_does_not_change_key(self):
        base = _opp("x-3", "Cloudflare", "Senior Customer Engineer", "London, UK")
        other_loc = _opp("x-4", "Cloudflare", "Senior Customer Engineer", "Austin, TX")
        self.assertEqual(family_key(base), family_key(other_loc))


class TestFamilyMembershipRules(unittest.TestCase):
    def test_cloudflare_customer_engineer_set_is_one_family(self):
        members = [FamilyMember(opp) for opp in _build_cloudflare_customer_engineer_family()]
        families = cluster_members(members)
        self.assertEqual(len(families), 1)
        self.assertEqual(families[0].member_count, 14)

    def test_zero_families_span_two_employers(self):
        corpus = _build_full_corpus()
        _count, cross_employer, _cross_title = check_family_invariants(
            FamilyMember(opp) for opp in corpus
        )
        self.assertEqual(cross_employer, 0)

    def test_zero_families_span_two_normalized_titles(self):
        corpus = _build_full_corpus()
        _count, _cross_employer, cross_title = check_family_invariants(
            FamilyMember(opp) for opp in corpus
        )
        self.assertEqual(cross_title, 0)

    def test_different_employer_same_title_text_is_separate_family(self):
        cf = _opp("cf-x", "Cloudflare", "Senior Customer Engineer", "London, UK")
        acme = _opp("acme-x", "Acme Corp", "Senior Customer Engineer", "London, UK")
        self.assertNotEqual(family_key(cf), family_key(acme))

    def test_different_seniority_level_is_separate_family(self):
        senior = _opp("cf-y1", "Cloudflare", "Senior Customer Engineer", "London, UK")
        unleveled = _opp("cf-y2", "Cloudflare", "Customer Engineer", "London, UK")
        self.assertNotEqual(family_key(senior), family_key(unleveled))

    def test_other_bucket_distinct_titles_do_not_collide(self):
        a = _opp("cf-z1", "Cloudflare", "Zorbatron Wrangler", "Remote - Worldwide")
        b = _opp("cf-z2", "Cloudflare", "Quantum Flux Herder", "Remote - Worldwide")
        self.assertNotEqual(family_key(a), family_key(b))

    def test_singleton_is_family_of_one_and_behaves_like_plain_card(self):
        opp = _opp("solo-1", "Nimbus Data", "Data Engineer", "Remote - Worldwide")
        families = cluster_opportunities([opp])
        self.assertEqual(len(families), 1)
        fam = families[0]
        self.assertTrue(fam.is_singleton)
        self.assertEqual(fam.member_count, 1)
        self.assertEqual(fam.member_ids, (opp.id,))
        self.assertEqual(fam.best_member_id, opp.id)
        self.assertEqual(fam.locations, (opp.location_raw,))


class TestFamilyCard(unittest.TestCase):
    def test_family_carries_best_fit_members_score_not_average(self):
        members = [
            FamilyMember(_opp("cf-a", "Cloudflare", "Senior Customer Engineer", "London, UK"), fit_score=73.0, decision="qualified"),
            FamilyMember(_opp("cf-b", "Cloudflare", "Senior Customer Engineer", "Austin, TX"), fit_score=91.0, decision="qualified"),
            FamilyMember(_opp("cf-c", "Cloudflare", "Senior Customer Engineer", "Berlin, Germany"), fit_score=60.0, decision="qualified"),
        ]
        families = cluster_members(members)
        self.assertEqual(len(families), 1)
        fam = families[0]
        self.assertEqual(fam.best_fit_score, 91.0)
        self.assertEqual(fam.best_member_id, "cf-b")
        # Never an average: (73+91+60)/3 = 74.666..., not the family's score.
        self.assertNotAlmostEqual(fam.best_fit_score, (73.0 + 91.0 + 60.0) / 3.0)

    def test_family_carries_location_list_and_member_count(self):
        members = [FamilyMember(opp) for opp in _build_cloudflare_customer_engineer_family()]
        fam = cluster_members(members)[0]
        self.assertEqual(fam.member_count, 14)
        self.assertEqual(len(fam.locations), 14)
        self.assertEqual(fam.locations, tuple(sorted(_CLOUDFLARE_LOCATIONS)))

    def test_best_fit_selection_is_deterministic_regardless_of_input_order(self):
        opps = [
            (FamilyMember(_opp("cf-a", "Cloudflare", "Senior Customer Engineer", "London, UK"), fit_score=73.0)),
            (FamilyMember(_opp("cf-b", "Cloudflare", "Senior Customer Engineer", "Austin, TX"), fit_score=91.0)),
            (FamilyMember(_opp("cf-c", "Cloudflare", "Senior Customer Engineer", "Berlin, Germany"), fit_score=60.0)),
        ]
        forward = cluster_members(opps)[0]
        backward = cluster_members(list(reversed(opps)))[0]
        self.assertEqual(forward.best_member_id, backward.best_member_id)
        self.assertEqual(forward.best_fit_score, backward.best_fit_score)


class TestNeverMergeAcrossDecisions(unittest.TestCase):
    def test_ineligible_member_status_is_flagged_not_hidden(self):
        """A family must never hide an ineligible member's status behind a
        qualified sibling's: the family card shows the best-fit member's
        decision AND flags that members differ."""
        members = [
            FamilyMember(_opp("cf-a", "Cloudflare", "Senior Customer Engineer", "London, UK"), fit_score=91.0, decision="qualified"),
            FamilyMember(_opp("cf-b", "Cloudflare", "Senior Customer Engineer", "Austin, TX"), fit_score=40.0, decision="ineligible"),
        ]
        fam = cluster_members(members)[0]
        self.assertEqual(fam.best_member_id, "cf-a")
        self.assertEqual(fam.best_decision, "qualified")
        self.assertTrue(fam.decisions_differ)

    def test_no_flag_when_all_members_share_one_decision(self):
        members = [
            FamilyMember(_opp("cf-a", "Cloudflare", "Senior Customer Engineer", "London, UK"), fit_score=91.0, decision="qualified"),
            FamilyMember(_opp("cf-b", "Cloudflare", "Senior Customer Engineer", "Austin, TX"), fit_score=80.0, decision="qualified"),
        ]
        fam = cluster_members(members)[0]
        self.assertFalse(fam.decisions_differ)

    def test_clustering_never_changes_any_members_decision_or_fit_score(self):
        """A2.7 no-re-judgement test: no member's decision or fit_score
        differs before and after clustering."""
        before = [
            FamilyMember(_opp("cf-a", "Cloudflare", "Senior Customer Engineer", "London, UK"), fit_score=91.0, decision="qualified"),
            FamilyMember(_opp("cf-b", "Cloudflare", "Senior Customer Engineer", "Austin, TX"), fit_score=40.0, decision="ineligible"),
            FamilyMember(_opp("nimbus-1", "Nimbus Data", "Data Engineer", "Remote"), fit_score=55.0, decision="review"),
        ]
        before_snapshot = {m.opportunity.id: (m.fit_score, m.decision) for m in before}

        families = cluster_members(before)

        after_snapshot = {m.opportunity.id: (m.fit_score, m.decision) for m in before}
        self.assertEqual(before_snapshot, after_snapshot)

        # And every member's own fit_score/decision is still individually
        # recoverable from the input list -- clustering only builds Family
        # cards alongside the members, it does not overwrite them.
        seen_ids = {mid for fam in families for mid in fam.member_ids}
        self.assertEqual(seen_ids, set(before_snapshot.keys()))
        for member in before:
            score, decision = before_snapshot[member.opportunity.id]
            self.assertEqual(member.fit_score, score)
            self.assertEqual(member.decision, decision)
        print(f"A2.7 no-re-judgement: {len(before)} members compared before/after clustering, "
              f"all decision/fit_score pairs unchanged=True")


class TestNormalizedTitleKey(unittest.TestCase):
    def test_pure_function_of_title_text(self):
        self.assertEqual(
            normalized_title_key("Senior Customer Engineer"),
            normalized_title_key("Senior Customer Engineer"),
        )

    def test_level_word_changes_the_key(self):
        self.assertNotEqual(
            normalized_title_key("Customer Engineer"),
            normalized_title_key("Senior Customer Engineer"),
        )


class TestCorpusWideReport(unittest.TestCase):
    """A2.3 (family report) and A2.4 (whole-corpus invariant check), run as
    printable evidence. No real ``opportunity/fixtures/corpus/`` set was
    present on this branch at implementation time -- see this module's
    docstring and the work order return -- so this exercises the hand-built
    fixture corpus above (28 postings) rather than the real Cloudflare
    Greenhouse pull. A separate script (see the evidence report) re-runs the
    same check over whatever corpus directory is actually present.
    """

    def test_a2_3_family_report_over_hand_built_corpus(self):
        corpus = _build_full_corpus()
        families = cluster_opportunities(corpus)
        print(f"\nA2.3 corpus run: {len(corpus)} postings -> {len(families)} families "
              f"(title normalizer: {clustering.TITLE_NORMALIZER_SOURCE})")
        cloudflare_sce_family = None
        for fam in sorted(families, key=lambda f: f.family_key):
            print(f"  family_key={fam.family_key[:12]}... employer={fam.employer!r} "
                  f"normalized_title={fam.normalized_title!r} member_count={fam.member_count}")
            if fam.employer == "Cloudflare" and fam.normalized_title.startswith("customer_solutions_engineering:senior"):
                cloudflare_sce_family = fam
        self.assertIsNotNone(cloudflare_sce_family, "Cloudflare Senior Customer Engineer family not found")
        self.assertEqual(cloudflare_sce_family.member_count, 14)
        print(f"A2.3 result: the Cloudflare 'Senior Customer Engineer' set collapsed to ONE family "
              f"with member_count={cloudflare_sce_family.member_count}")

    def test_a2_4_whole_corpus_invariant_check(self):
        corpus = _build_full_corpus()
        family_count, cross_employer, cross_title = check_family_invariants(
            FamilyMember(opp) for opp in corpus
        )
        print(f"\nA2.4 whole-corpus invariant check: {len(corpus)} postings, "
              f"{family_count} families, cross_employer_violations={cross_employer}, "
              f"cross_title_violations={cross_title}")
        self.assertEqual(cross_employer, 0)
        self.assertEqual(cross_title, 0)


if __name__ == "__main__":
    unittest.main()
