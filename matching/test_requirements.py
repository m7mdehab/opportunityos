"""Regression tests for FR-008 job requirement priority classification."""
from __future__ import annotations

import unittest

from matching.requirements import RequirementPriority, classify_requirement_text
from matching.skills import classify_skill_priorities


class RequirementTextPriorityTests(unittest.TestCase):
    def test_explicit_cues_cover_required_priority_classes(self) -> None:
        cases = (
            ("Must have Python experience", RequirementPriority.MANDATORY),
            ("Required certification: AWS Solutions Architect", RequirementPriority.MANDATORY),
            ("French is strongly preferred", RequirementPriority.STRONGLY_PREFERRED),
            ("Experience with Terraform preferred", RequirementPriority.NICE_TO_HAVE),
            ("Bonus points for Kafka experience", RequirementPriority.NICE_TO_HAVE),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(classify_requirement_text(text), expected)

    def test_section_context_and_boilerplate_do_not_overstate_priority(self) -> None:
        self.assertEqual(
            classify_requirement_text("5+ years Python", source_section="requirements"),
            RequirementPriority.MANDATORY,
        )
        self.assertEqual(
            classify_requirement_text("Build ETL pipelines", source_section="responsibilities"),
            RequirementPriority.CONTEXTUAL,
        )
        self.assertEqual(
            classify_requirement_text("We use Python to power our platform"),
            RequirementPriority.CONTEXTUAL,
        )
        self.assertEqual(
            classify_requirement_text("Python and Rust experience"),
            RequirementPriority.UNKNOWN,
        )
        self.assertEqual(classify_requirement_text(""), RequirementPriority.UNKNOWN)

    def test_explicit_applicant_cue_overrides_section_context(self) -> None:
        self.assertEqual(
            classify_requirement_text(
                "Must have SQL experience",
                source_section="responsibilities",
            ),
            RequirementPriority.MANDATORY,
        )


class SkillMentionPriorityTests(unittest.TestCase):
    def test_full_description_separates_candidate_requirements_from_context(self) -> None:
        description = (
            "About Us:\n"
            "We use Python and Go in our platform.\n"
            "What You'll Do:\n"
            "Design services with Rust.\n"
            "Requirements:\n"
            "Must have SQL experience.\n"
            "Strongly Preferred:\n"
            "Kafka\n"
            "Preferred Qualifications:\n"
            "AWS"
        )
        priorities = classify_skill_priorities(
            description,
            ("Python", "Go", "Rust", "SQL", "Kafka", "AWS", "C++"),
        )
        self.assertEqual(priorities["python"], RequirementPriority.CONTEXTUAL)
        self.assertEqual(priorities["go"], RequirementPriority.CONTEXTUAL)
        self.assertEqual(priorities["rust"], RequirementPriority.CONTEXTUAL)
        self.assertEqual(priorities["sql"], RequirementPriority.MANDATORY)
        self.assertEqual(priorities["kafka"], RequirementPriority.STRONGLY_PREFERRED)
        self.assertEqual(priorities["aws"], RequirementPriority.NICE_TO_HAVE)
        self.assertEqual(priorities["c++"], RequirementPriority.UNKNOWN)

    def test_inline_requirement_section_and_direct_cues_are_supported(self) -> None:
        priorities = classify_skill_priorities(
            "Requirements: Python\nGo is preferred.\nMust have SQL.",
            ("Python", "Go", "SQL"),
        )
        self.assertEqual(priorities["python"], RequirementPriority.MANDATORY)
        self.assertEqual(priorities["go"], RequirementPriority.NICE_TO_HAVE)
        self.assertEqual(priorities["sql"], RequirementPriority.MANDATORY)

    def test_legacy_splitter_keeps_its_two_set_contract(self) -> None:
        from matching.skills import split_required_and_nice_to_have

        required, optional = split_required_and_nice_to_have(
            "About Us\nWe use Python.\nRequirements:\nSQL",
            ("Python", "SQL", "Go"),
        )
        self.assertEqual(required, {"sql"})
        self.assertEqual(optional, {"python", "go"})


if __name__ == "__main__":
    unittest.main()
