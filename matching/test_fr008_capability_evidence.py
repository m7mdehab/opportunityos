"""FR-008 W1.2 capability evidence normalization contracts."""
from __future__ import annotations

import unittest

from matching import skills
from truth import predicates
from truth.models import AtomicAssertion, CapabilityProfile, CareerProfile, Polarity, VerificationStatus
from truth.pack import (
    CANONICAL_REPO_TRUTH_PACK,
    CANONICAL_REPO_TRUTH_PACK_RAW_SHA256,
    load_truth_pack,
)


def _assertion(
    assertion_id: str,
    subject_id: str,
    predicate: str,
    value: object,
    evidence_ref: str,
    *,
    status: VerificationStatus = VerificationStatus.VERIFIED,
    polarity: Polarity = Polarity.POSITIVE,
) -> AtomicAssertion:
    return AtomicAssertion(
        id=assertion_id,
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        evidence_ids=(evidence_ref,),
        verification_status=status,
        polarity=polarity,
    )


class TestVerifiedSkillIndex(unittest.TestCase):
    def test_duplicate_labels_aggregate_name_and_proficiency_references(self) -> None:
        index = skills.build_verified_skill_index((
            _assertion("a-name-one", "skill-one", predicates.SKILL_NAME, "  Data   Engineer ", "ev-name-one"),
            _assertion("a-tier-one", "skill-one", predicates.SKILL_PROFICIENCY, "Expert", "ev-tier-one"),
            _assertion("a-name-two", "skill-two", predicates.SKILL_NAME, "data engineer", "ev-name-two"),
            _assertion("a-tier-two", "skill-two", predicates.SKILL_PROFICIENCY, "expert", "ev-tier-two"),
        ))

        self.assertEqual(
            index.get("data engineer"),
            ("expert", ("ev-name-one", "ev-name-two", "ev-tier-one", "ev-tier-two")),
        )

    def test_unverified_proficiency_cannot_change_tier_or_add_references(self) -> None:
        index = skills.build_verified_skill_index((
            _assertion("a-name", "skill-one", predicates.SKILL_NAME, "Python", "ev-name"),
            _assertion(
                "a-tier", "skill-one", predicates.SKILL_PROFICIENCY, "expert", "ev-unverified-tier",
                status=VerificationStatus.UNVERIFIED,
            ),
        ))

        self.assertEqual(index.get("python"), (None, ("ev-name",)))

    def test_conflicting_verified_tiers_remain_unknown(self) -> None:
        index = skills.build_verified_skill_index((
            _assertion("a-name-one", "skill-one", predicates.SKILL_NAME, "SQL", "ev-name-one"),
            _assertion("a-tier-one", "skill-one", predicates.SKILL_PROFICIENCY, "expert", "ev-tier-one"),
            _assertion("a-name-two", "skill-two", predicates.SKILL_NAME, "sql", "ev-name-two"),
            _assertion("a-tier-two", "skill-two", predicates.SKILL_PROFICIENCY, "basic", "ev-tier-two"),
        ))

        self.assertEqual(index.get("sql"), (None, ("ev-name-one", "ev-name-two")))

    def test_unicode_whitespace_and_case_are_formatting_only(self) -> None:
        decomposed = "  Cafe\u0301\tData  "
        composed = "café data"
        self.assertEqual(skills.normalize_skill_label(decomposed), "café data")

        index = skills.build_verified_skill_index((
            _assertion("a-name", "skill-one", predicates.SKILL_NAME, decomposed, "ev-name"),
            _assertion("a-tier", "skill-one", predicates.SKILL_PROFICIENCY, "working", "ev-tier"),
        ))
        matches = skills.evaluate_skill_matches((composed,), frozenset({"café data"}), index)

        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].has_founder_match)
        self.assertEqual(matches[0].evidence_refs, ("ev-name", "ev-tier"))

    def test_synonyms_and_capability_tools_do_not_enter_career_skill_index(self) -> None:
        index = skills.build_verified_skill_index((
            _assertion("a-name", "skill-one", predicates.SKILL_NAME, "JavaScript", "ev-career-skill"),
            _assertion("a-tool", "tool-one", "tool.name", "JS", "ev-capability-tool"),
        ))
        matches = skills.evaluate_skill_matches(("JS",), frozenset({"js"}), index)

        self.assertEqual(tuple(index), ("javascript",))
        self.assertEqual(len(matches), 1)
        self.assertFalse(matches[0].has_founder_match)

    def test_unverified_names_and_narrative_values_are_not_skills(self) -> None:
        index = skills.build_verified_skill_index((
            _assertion(
                "a-unverified-name", "skill-one", predicates.SKILL_NAME, "Python", "ev-unverified-name",
                status=VerificationStatus.UNVERIFIED,
            ),
            _assertion(
                "a-responsibility", "employment-one", predicates.EMPLOYMENT_RESPONSIBILITY,
                "Used Python on a project.", "ev-responsibility",
            ),
        ))

        self.assertEqual(index, {})

    def test_verified_negative_assertions_do_not_create_positive_capabilities(self) -> None:
        index = skills.build_verified_skill_index((
            _assertion(
                "a-negative-name", "skill-one", predicates.SKILL_NAME, "Python", "ev-negative-name",
                polarity=Polarity.NEGATIVE,
            ),
            _assertion(
                "a-negative-tier", "skill-two", predicates.SKILL_PROFICIENCY, "expert", "ev-negative-tier",
                polarity=Polarity.NEGATIVE,
            ),
        ))

        self.assertEqual(index, {})


class TestCanonicalCapabilityEvidenceContract(unittest.TestCase):
    def test_hash_verified_skill_and_capability_graph_is_reference_complete(self) -> None:
        try:
            loaded = load_truth_pack(
                target=CANONICAL_REPO_TRUTH_PACK,
                expected_hash=CANONICAL_REPO_TRUTH_PACK_RAW_SHA256,
                allow_local_path=True,
                cloud_mode=True,
            )
        except Exception:
            self.fail("canonical profile must load through its pinned hash-verifying loader")

        graph = loaded.graph
        career_profiles = [profile for profile in graph.profiles.values() if isinstance(profile, CareerProfile)]
        capability_profiles = [profile for profile in graph.profiles.values() if isinstance(profile, CapabilityProfile)]
        self.assertEqual(len(career_profiles), 1, "canonical career profile must be loaded")
        self.assertEqual(len(capability_profiles), 1, "canonical capability profile must be loaded")

        career_skills = career_profiles[0].skills
        capability_tools = capability_profiles[0].tools
        self.assertTrue(career_skills, "canonical career skills must be loaded")
        self.assertTrue(capability_tools, "canonical capability tools must be loaded")

        known_evidence_refs = set(graph.evidence_records)
        for record in (*career_skills, *capability_tools):
            self.assertTrue(set(record.evidence_ids) <= known_evidence_refs)

        skill_index = skills.build_verified_skill_index(graph.assertions.values())
        self.assertTrue(skill_index, "canonical verified career skill index must be populated")
        for _, evidence_refs in skill_index.values():
            self.assertTrue(evidence_refs)
            self.assertTrue(set(evidence_refs) <= known_evidence_refs)


if __name__ == "__main__":
    unittest.main()
