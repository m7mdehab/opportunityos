"""Privacy-safe scoring contract for the repository-managed canonical profile."""
from __future__ import annotations

import unittest
from datetime import date

from matching.scorer import OpportunityScorer
from matching.test_qualification import create_test_opportunity
from truth import predicates
from truth.models import VerificationStatus
from truth.pack import (
    CANONICAL_REPO_TRUTH_PACK,
    CANONICAL_REPO_TRUTH_PACK_RAW_SHA256,
    load_truth_pack,
)


class TestCanonicalProfileScoringContract(unittest.TestCase):
    def test_hash_verified_profile_populates_employment_scoring(self) -> None:
        try:
            loaded_pack = load_truth_pack(
                target=CANONICAL_REPO_TRUTH_PACK,
                expected_hash=CANONICAL_REPO_TRUTH_PACK_RAW_SHA256,
            )
        except Exception:
            self.fail("canonical profile must load through its hash-verifying loader")

        verified_responsibilities = tuple(
            assertion.value
            for assertion in loaded_pack.graph.assertions.values()
            if assertion.predicate in predicates.RESPONSIBILITY_SCOPE_PREDICATES
            and assertion.verification_status == VerificationStatus.VERIFIED
            and isinstance(assertion.value, str)
            and assertion.value.strip()
        )
        self.assertTrue(
            bool(verified_responsibilities),
            "canonical profile must project verified responsibility evidence",
        )

        opportunity = create_test_opportunity(
            title="Senior Software Engineer",
            description="Design and build software systems.",
            skills=(),
            responsibilities=(verified_responsibilities[0],),
        )
        try:
            evaluation = OpportunityScorer().evaluate(
                opportunity,
                loaded_pack.graph,
                evaluated_at=date.today().isoformat(),
            )
        except Exception:
            self.fail("canonical profile must score without exposing profile details")

        dimensions = {score.dimension_name: score for score in evaluation.dimension_scores}
        self.assertTrue(
            "seniority_and_experience" in dimensions,
            "employment scoring must include the seniority and experience dimension",
        )
        self.assertTrue(
            "responsibility_scope" in dimensions,
            "employment scoring must include the responsibility scope dimension",
        )

        seniority = dimensions["seniority_and_experience"]
        responsibility = dimensions["responsibility_scope"]
        self.assertFalse(
            any("No verified employment record" in item for item in seniority.unknowns),
            "dated canonical employment evidence must avoid the missing-history unknown",
        )
        self.assertFalse(
            any(
                "No verified responsibility/experience records" in item
                for item in responsibility.unknowns
            ),
            "canonical responsibility evidence must avoid the missing-history unknown",
        )
        self.assertTrue(
            bool(seniority.evidence_refs),
            "seniority and experience scoring must retain evidence references",
        )
        self.assertTrue(
            bool(responsibility.evidence_refs),
            "responsibility scoring must retain evidence references",
        )


if __name__ == "__main__":
    unittest.main()
