import json
import unittest
from datetime import date, timezone

from truth.ingest import (
    IngestionError,
    canonicalize_skill,
    graph_from_dict,
    load_document,
    load_json,
    load_yaml,
    parse_date,
)


def minimal_document():
    return {
        "evidence": [
            {
                "id": "ev-skill", "content": "Python", "source": "fixture",
                "locator": "skills.0", "assertion_type": "normalized_fact",
                "observed_at": "2026-08-29T10:00:00Z",
            },
            {
                "id": "ev-role", "content": "Example Engineer at Example Org from 2024-01-01", "source": "fixture",
                "locator": "employment.0",
                "metadata": {"organization": "Example Org", "title": "Example Engineer"},
            },
        ],
        "career_profile": {
            "id": "career-example",
            "employment": [
                {
                    "id": "job-example", "organization": "Example Org",
                    "title": "Example Engineer", "start_date": "2024-01-01",
                    "end_date": None, "evidence_ids": ["ev-role"],
                }
            ],
            "skills": [
                {"id": "skill-python", "name": "PYTHON", "evidence_ids": ["ev-skill"]}
            ],
        },
    }


class IngestionTests(unittest.TestCase):
    def test_dict_ingestion_constructs_and_links_graph(self):
        graph = graph_from_dict(minimal_document())
        self.assertEqual(date(2024, 1, 1), graph.entity("job-example").start_date)
        self.assertEqual("Python", graph.entity("skill-python").name)
        self.assertEqual(timezone.utc, graph.evidence("ev-skill").observed_at.tzinfo)

    def test_json_ingestion_is_deterministic(self):
        text = json.dumps(minimal_document(), sort_keys=True)
        first = load_json(text)
        second = load_json(text)
        self.assertEqual(dict(first.evidence_records), dict(second.evidence_records))
        self.assertEqual(dict(first.profiles), dict(second.profiles))

    def test_yaml_ingestion_supports_truth_pack_subset(self):
        graph = load_yaml(
            """
evidence:
  - id: ev-skill
    content: Python
    source: fixture
    locator: skills.0
career_profile:
  id: career-example
  skills:
    - id: skill-python
      name: python
      evidence_ids: ["ev-skill"]
"""
        )
        self.assertEqual("Python", graph.entity("skill-python").name)

    def test_target_role_tier_ingests_only_configured_values(self):
        document = {
            "evidence": [{
                "id": "ev-target-role",
                "content": "Primary target role: LLM Engineer.",
                "source": "fixture",
                "locator": "career_profile.target_roles.0",
            }],
            "career_profile": {
                "id": "career-targets",
                "target_roles": [{
                    "id": "target-llm-engineer",
                    "title": "LLM Engineer",
                    "tier": "primary",
                    "evidence_ids": ["ev-target-role"],
                }],
            },
        }
        graph = graph_from_dict(document)
        self.assertEqual("primary", graph.entity("target-llm-engineer").tier.value)
        document["career_profile"]["target_roles"][0]["tier"] = "core"
        with self.assertRaisesRegex(IngestionError, "target_role.tier must be one of"):
            graph_from_dict(document)

    def test_missing_target_role_tier_is_unknown_and_legacy_assertions_load(self):
        target_role_document = {
            "evidence": [
                {
                    "id": "ev-target-role",
                    "content": "Target role: Technical Consultant.",
                    "source": "fixture",
                    "locator": "career_profile.target_roles.0",
                },
                {
                    "id": "ev-target-tier-null",
                    "content": None,
                    "source": "fixture",
                    "locator": "career_profile.target_roles.0.tier",
                    "verification_status": "explicit_null",
                },
            ],
            "career_profile": {
                "id": "career-targets",
                "target_roles": [{
                    "id": "target-technical-consultant",
                    "title": "Technical Consultant",
                    "evidence_ids": ["ev-target-role", "ev-target-tier-null"],
                }],
            },
        }
        graph = graph_from_dict(target_role_document)
        self.assertIsNone(graph.entity("target-technical-consultant").tier)
        self.assertFalse(any(
            assertion.predicate == "career.target_role_tier"
            for assertion in graph.assertions.values()
        ))

        legacy_graph = graph_from_dict({
            "evidence": [{
                "id": "ev-legacy-target-role",
                "content": "Data Integration Engineer",
                "source": "fixture",
                "locator": "assertions.target_role",
            }],
            "assertions": [{
                "id": "legacy-target-role-assertion",
                "subject_id": "founder",
                "predicate": "career.target_role",
                "value": "Data Integration Engineer",
                "evidence_ids": ["ev-legacy-target-role"],
            }],
        })
        self.assertEqual(
            "Data Integration Engineer",
            legacy_graph.assertions["legacy-target-role-assertion"].value,
        )

    def test_canonical_skill_aliases_are_case_and_separator_insensitive(self):
        cases = {
            " AWS ": "AWS", "amazon-web-services": "AWS", "k8s": "Kubernetes",
            "google_cloud": "Google Cloud Platform", "POWER   BI": "Power BI",
            "novel tool": "Novel Tool",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected, canonicalize_skill(raw))

    def test_dates_are_strict_iso_8601_calendar_dates(self):
        self.assertEqual(date(2026, 8, 29), parse_date("2026-08-29", "test"))
        for bad in ("29/08/2026", "2026-8-29", "2026-02-30", 20260829):
            with self.subTest(value=bad), self.assertRaises(IngestionError):
                parse_date(bad, "test", allow_none=False)

    def test_unknown_fields_fail_closed(self):
        document = minimal_document()
        document["career_profile"]["invented_field"] = True
        with self.assertRaisesRegex(IngestionError, "unknown fields"):
            graph_from_dict(document)

    def test_unknown_evidence_reference_is_rejected(self):
        document = minimal_document()
        document["career_profile"]["skills"][0]["evidence_ids"] = ["not-present"]
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            graph_from_dict(document)

    def test_invalid_enum_and_naive_datetime_are_rejected(self):
        document = minimal_document()
        document["evidence"][0]["verification_status"] = "probably"
        with self.assertRaisesRegex(IngestionError, "must be one of"):
            graph_from_dict(document)
        document = minimal_document()
        document["evidence"][0]["observed_at"] = "2026-08-29T10:00:00"
        with self.assertRaisesRegex(IngestionError, "timezone"):
            graph_from_dict(document)

    def test_yaml_rejects_unsafe_features_and_duplicate_keys(self):
        unsafe_documents = (
            "evidence: !!python/object:example {}",
            "evidence: &records []\ncopy: *records",
            "evidence: []\nevidence: []",
            "\tevidence: []",
        )
        for text in unsafe_documents:
            with self.subTest(text=text), self.assertRaises(IngestionError):
                load_yaml(text)

    def test_loader_rejects_unknown_format(self):
        with self.assertRaisesRegex(IngestionError, "unsupported document format"):
            load_document("{}", "toml")

    def test_json_rejects_non_object_root_and_duplicate_graph_ids(self):
        with self.assertRaises(IngestionError):
            load_json("[]")
        with self.assertRaisesRegex(IngestionError, "duplicate JSON key"):
            load_json('{"evidence": [], "evidence": []}')
    def test_fractional_strings_are_rejected_for_integer_fields(self):
        doc1 = {
            "evidence": [{"id": "ev", "content": "test", "source": "test", "locator": "test"}],
            "capability_profile": {
                "id": "cap",
                "capacity": {"id": "c1", "evidence_ids": ["ev"], "hours_per_week": "1.5"},
            },
        }
        with self.assertRaises(IngestionError):
            graph_from_dict(doc1)

        doc2 = {
            "evidence": [{"id": "ev", "content": "test", "source": "test", "locator": "test"}],
            "capability_profile": {
                "id": "cap",
                "capacity": {"id": "c1", "evidence_ids": ["ev"], "min_project_value": "2.9"},
            },
        }
        with self.assertRaises(IngestionError):
            graph_from_dict(doc2)

    def test_never_claim_concept_is_validated_without_silent_default(self):
        doc = {
            "evidence": [{"id": "ev", "content": "test", "source": "test", "locator": "test"}],
            "career_profile": {
                "id": "career",
                "never_claims": [{"id": "custom-rule", "phrase": "some phrase"}],
            },
        }
        with self.assertRaises(IngestionError):
            graph_from_dict(doc)

    def test_ingestion_supports_assertions_relations_and_metrics(self):
        doc = {
            "evidence": [{"id": "ev-1", "content": "Python Engineer with 40% latency reduction", "source": "test", "locator": "title", "metadata": {"title": "Python Engineer"}}],
            "assertions": [
                {
                    "id": "as-1",
                    "subject_id": "job-1",
                    "predicate": "employment.title",
                    "value": "Python Engineer",
                    "evidence_ids": ["ev-1"],
                }
            ],
            "relations": [
                {
                    "id": "rel-1",
                    "source_id": "job-1",
                    "relation_type": "achieved_during",
                    "target_id": "ach-1",
                    "evidence_ids": ["ev-1"],
                }
            ],
            "metrics": [
                {
                    "id": "met-1",
                    "subject_id": "ach-1",
                    "numeric_value": 40.0,
                    "unit": "%",
                    "context": "latency",
                    "evidence_ids": ["ev-1"],
                }
            ],
        }
        graph = graph_from_dict(doc)
        self.assertIn("as-1", graph.assertions)
        self.assertIn("rel-1", graph.relations)
        self.assertIn("met-1", graph.metrics)


if __name__ == "__main__":
    unittest.main()
