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
                "id": "ev-role", "content": "Example Engineer", "source": "fixture",
                "locator": "employment.0.title",
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
        document = minimal_document()
        document["evidence"].append(dict(document["evidence"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate graph node"):
            graph_from_dict(document)


if __name__ == "__main__":
    unittest.main()
