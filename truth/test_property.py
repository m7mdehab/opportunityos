"""Property-based randomized invariant tests for the OpportunityOS Truth Graph."""

from __future__ import annotations

from datetime import date
import math
import random
import re
import unittest

from truth.fixtures import synthetic_graph
from truth.graph import TruthGraph
from truth.models import (
    Achievement,
    AssertionType,
    BusinessCapacity,
    CapabilityProfile,
    CareerProfile,
    EmploymentRecord,
    EvidenceRecord,
    MetricVerification,
    NeverClaimRule,
    ProhibitedConceptCategory,
    RedLineRule,
    SkillRecord,
    VerificationStatus,
)
from truth.validator import ClaimValidator, _tokens


class TruthGraphPropertyTests(unittest.TestCase):
    """Randomized property-based testing of core epistemic and relational invariants."""

    def test_epistemic_monotonicity_property(self):
        """Property: The resolved assertion type of a multi-evidence claim is strictly
        bounded by the weakest assertion type among its supporting evidence records."""
        ranks = {
            AssertionType.DIRECT_FACT: 4,
            AssertionType.NORMALIZED_FACT: 3,
            AssertionType.DERIVED_CAPABILITY: 2,
            AssertionType.USER_ASSERTION: 1,
        }
        types = list(ranks.keys())
        rng = random.Random(42)

        for iteration in range(100):
            k = rng.randint(1, 4)
            chosen_types = [rng.choice(types) for _ in range(k)]
            min_rank = min(ranks[t] for t in chosen_types)

            records = []
            words = []
            for i, t in enumerate(chosen_types):
                w = f"factword{i}"
                words.append(w)
                records.append(
                    EvidenceRecord(
                        f"ev-prop-{iteration}-{i}",
                        f"Subject has {w} at PropOrg as Title from 2020-01-01.",
                        "property_fixture",
                        f"loc-{i}",
                        assertion_type=t,
                    )
                )

            # Link records under a common entity so relational composition passes
            emp = EmploymentRecord(
                f"emp-prop-{iteration}", "PropOrg", "Title", date(2020, 1, 1), None,
                evidence_ids=tuple(r.id for r in records),
            )
            profile = CareerProfile(f"prof-prop-{iteration}", employment=(emp,))
            graph = TruthGraph(records)
            graph.add_career_profile(profile)
            validator = ClaimValidator(graph)

            claim = f"Subject has {' '.join(words)}."
            result = validator.validate_claim(claim, [r.id for r in records])

            if result.allowed:
                result_rank = ranks.get(result.assertion_type, 0)
                self.assertLessEqual(
                    result_rank, min_rank,
                    f"Epistemic violation: result {result.assertion_type} (rank {result_rank}) > input min {min_rank}",
                )

    def test_relational_isolation_property(self):
        """Property: Two evidence records from disjoint entity scopes can NEVER be joined
        into a composite relational claim without an establishing graph entity."""
        rng = random.Random(1337)

        for iteration in range(50):
            org_name = f"Company_{iteration}_{rng.randint(1000, 9999)}"
            skill_name = f"Skill_{iteration}_{rng.randint(1000, 9999)}"

            ev_org = EvidenceRecord(f"ev-org-{iteration}", f"{org_name} Eng from 2020-01-01.", "cv", "org")
            ev_skill = EvidenceRecord(f"ev-skill-{iteration}", f"Expert in {skill_name}.", "cv", "skill")

            # Entity 1 has ev_org, Entity 2 has ev_skill (disconnected)
            emp = EmploymentRecord(f"emp-{iteration}", org_name, "Eng", date(2020, 1, 1), None, (ev_org.id,))
            skill = SkillRecord(f"sk-{iteration}", skill_name, (ev_skill.id,))
            profile = CareerProfile(f"prof-{iteration}", employment=(emp,), skills=(skill,))

            graph = TruthGraph((ev_org, ev_skill))
            graph.add_career_profile(profile)
            validator = ClaimValidator(graph)

            composite_claim = f"Expert in {skill_name} at {org_name}."
            result = validator.validate_claim(composite_claim, (ev_org.id, ev_skill.id))

            self.assertFalse(
                result.allowed,
                f"Relational laundering failure: '{composite_claim}' was incorrectly allowed!",
            )
            self.assertEqual(AssertionType.UNSUPPORTED_CLAIM, result.assertion_type)

    def test_never_claim_dominance_property(self):
        """Property: Prohibited concepts are 100% rejected regardless of evidence existence,
        casing, whitespace mutation, or synonym realization."""
        rng = random.Random(999)
        base_phrases = (
            "We guarantee 100% positive outcomes",
            "Guaranteed results for all projects",
            "Fortune 500 enterprise clients",
            "Top F500 client experience",
            "Formal legal representation and binding counsel",
        )
        validator = ClaimValidator(synthetic_graph())

        for _ in range(100):
            base = rng.choice(base_phrases)
            # Apply random case and spacing mutations
            mutated = "".join(c.upper() if rng.random() > 0.5 else c.lower() for c in base)
            mutated = re.sub(r" ", lambda _: " " * rng.randint(1, 3), mutated)
            prefix = rng.choice(["Our team provides ", "Proudly: ", "Directly: ", ""])
            suffix = rng.choice([" across all sectors.", " unconditionally.", " with high quality.", ""])
            candidate = f"{prefix}{mutated}{suffix}"

            result = validator.validate_claim(candidate)
            self.assertFalse(result.allowed, f"Never-Claim bypassed: {candidate}")
            self.assertEqual(AssertionType.PROHIBITED_CLAIM, result.assertion_type)

    def test_business_capacity_numeric_fuzzing(self):
        """Property: BusinessCapacity strictly rejects non-finite or negative values across
        all numeric fields under randomized fuzzing."""
        rng = random.Random(2026)
        invalid_numeric_generators = [
            lambda: bool(rng.randint(0, 1)),
            lambda: float("nan"),
            lambda: float("inf"),
            lambda: float("-inf"),
            lambda: -rng.uniform(0.001, 100000.0),
            lambda: -rng.randint(1, 10000),
        ]

        for _ in range(100):
            gen = rng.choice(invalid_numeric_generators)
            bad_val = gen()

            with self.assertRaises(ValueError):
                BusinessCapacity(
                    f"cap-{rng.randint(1, 99999)}", ("ev-capacity",),
                    annual_turnover_usd=bad_val,
                )

            with self.assertRaises(ValueError):
                BusinessCapacity(
                    f"cap-{rng.randint(1, 99999)}", ("ev-capacity",),
                    bid_bond_capacity_usd=bad_val,
                )

            with self.assertRaises(ValueError):
                BusinessCapacity(
                    f"cap-{rng.randint(1, 99999)}", ("ev-capacity",),
                    hours_per_week=bad_val,
                )

    def test_polarity_preservation_property(self):
        """Property: Negative particles in evidence strictly forbid positive claims under fuzzing."""
        rng = random.Random(404)
        negative_markers = ["not", "no", "never", "without", "cannot", "unauthorized"]
        subjects = ["Kubernetes", "AWS architecture", "budget management", "direct client sales"]

        for iteration in range(50):
            neg = rng.choice(negative_markers)
            subj = rng.choice(subjects)
            ev = EvidenceRecord(f"ev-neg-{iteration}", f"Professional has {neg} experience in {subj}.", "cv", "loc")
            graph = TruthGraph((ev,))
            validator = ClaimValidator(graph)

            positive_claim = f"Professional has experience in {subj}."
            result = validator.validate_claim(positive_claim, (ev.id,))
            self.assertFalse(result.allowed, f"Polarity leak: '{positive_claim}' allowed with negative evidence '{ev.content}'")

    def test_modality_bound_monotonicity_property(self):
        """Property: Upper-bound evidence records strictly forbid lower-bound or exact strengthening."""
        rng = random.Random(505)
        for iteration in range(50):
            hours = rng.randint(5, 35)
            ev = EvidenceRecord(f"ev-bound-{iteration}", f"Available at most {hours} hours per week.", "cv", "loc")
            graph = TruthGraph((ev,))
            validator = ClaimValidator(graph)

            strengthened_lower = f"Available at least {hours} hours per week."
            result_lower = validator.validate_claim(strengthened_lower, (ev.id,))
            self.assertFalse(result_lower.allowed)

            strengthened_exact = f"Available exactly {hours} hours per week."
            result_exact = validator.validate_claim(strengthened_exact, (ev.id,))
            self.assertFalse(result_exact.allowed)


if __name__ == "__main__":
    unittest.main()
