"""Tests for the `identity` and `approved_phrases` pack sections (BRIEF-FR-006 F1).

Covers: loader acceptance/validation, evidence-backed projection into the
predicate registry, unknown-field rejection, and fixture coverage. See
`reports/evidence/FR-006/orders/F1-identity.md`.
"""
from __future__ import annotations

import unittest

from truth import predicates
from truth.graph import TruthGraph
from truth.ingest import IngestionError, graph_from_dict
from truth.models import ApprovedPhrase, EvidenceRecord, Identity
from truth.predicates import PredicateKind


def _minimal_document() -> dict:
    return {
        "evidence": [
            {
                "id": "ev-identity",
                "content": (
                    "Taylor R. Tester is a Widget Lead based in Test City, Testland. "
                    "Email taylor.tester@example.com, phone +1-555-0199, LinkedIn "
                    "https://linkedin.com/in/taylor-tester, GitHub https://github.com/taylor-tester, "
                    "website https://taylor-tester.example."
                ),
                "source": "self_reported",
                "locator": "identity",
            },
            {
                "id": "ev-phrase-1",
                "content": "I care about shipping dependable systems teammates can trust.",
                "source": "self_reported",
                "locator": "approved_phrases.0",
            },
        ],
        "identity": {
            "name": "Taylor R. Tester",
            "evidence_ids": ["ev-identity"],
            "headline": "Widget Lead",
            "email": "taylor.tester@example.com",
            "phone": "+1-555-0199",
            "linkedin": "https://linkedin.com/in/taylor-tester",
            "github": "https://github.com/taylor-tester",
            "website": "https://taylor-tester.example",
            "location_city": "Test City",
            "location_country": "Testland",
        },
        "approved_phrases": [
            {
                "id": "phrase-1",
                "text": "I care about shipping dependable systems teammates can trust.",
                "evidence_ids": ["ev-phrase-1"],
                "tags": ["motivation"],
            },
        ],
    }


class IdentitySectionLoadingTests(unittest.TestCase):
    def test_identity_and_approved_phrases_load_and_project(self) -> None:
        graph = graph_from_dict(_minimal_document())

        self.assertIsNotNone(graph.identity)
        self.assertEqual(graph.identity.name, "Taylor R. Tester")
        self.assertEqual(graph.identity.email, "taylor.tester@example.com")

        self.assertEqual(len(graph.approved_phrases), 1)
        self.assertEqual(
            graph.approved_phrases["phrase-1"].text,
            "I care about shipping dependable systems teammates can trust.",
        )

        projected_predicates = {a.predicate for a in graph.assertions.values()}
        self.assertIn("identity.name", projected_predicates)
        self.assertIn("identity.headline", projected_predicates)
        self.assertIn("identity.email", projected_predicates)
        self.assertIn("identity.location_city", projected_predicates)
        self.assertIn("approved_phrase.text", projected_predicates)

    def test_identity_section_is_optional(self) -> None:
        document = _minimal_document()
        document.pop("identity")
        document.pop("approved_phrases")
        graph = graph_from_dict(document)
        self.assertIsNone(graph.identity)
        self.assertEqual(len(graph.approved_phrases), 0)

    def test_identity_requires_name(self) -> None:
        document = _minimal_document()
        del document["identity"]["name"]
        with self.assertRaises(IngestionError):
            graph_from_dict(document)

    def test_identity_unknown_field_is_error(self) -> None:
        document = _minimal_document()
        document["identity"]["ssn"] = "000-00-0000"
        with self.assertRaises(IngestionError):
            graph_from_dict(document)

    def test_approved_phrase_unknown_field_is_error(self) -> None:
        document = _minimal_document()
        document["approved_phrases"][0]["unexpected"] = "nope"
        with self.assertRaises(IngestionError):
            graph_from_dict(document)

    def test_unsupported_identity_value_is_rejected(self) -> None:
        document = _minimal_document()
        document["identity"]["headline"] = "Completely Unsupported Headline Text"
        with self.assertRaises(ValueError):
            graph_from_dict(document)

    def test_duplicate_identity_section_rejected(self) -> None:
        graph = TruthGraph(evidence=(
            EvidenceRecord(
                id="ev-a", content="Alex Example is a Lead.", source="self_reported", locator="identity",
            ),
        ))
        graph.add_identity(Identity(id="identity", name="Alex Example", evidence_ids=("ev-a",)))
        with self.assertRaises(ValueError):
            graph.add_identity(Identity(id="identity-2", name="Alex Example", evidence_ids=("ev-a",)))

    def test_duplicate_approved_phrase_id_rejected(self) -> None:
        graph = TruthGraph(evidence=(
            EvidenceRecord(id="ev-p", content="Reliable and thorough.", source="self_reported", locator="approved_phrases.0"),
        ))
        graph.add_approved_phrase(ApprovedPhrase(id="phrase-x", text="Reliable and thorough.", evidence_ids=("ev-p",)))
        with self.assertRaises(ValueError):
            graph.add_approved_phrase(ApprovedPhrase(id="phrase-x", text="Reliable and thorough.", evidence_ids=("ev-p",)))


class IdentityPredicateRegistryTests(unittest.TestCase):
    def test_identity_predicates_are_registered_and_projected(self) -> None:
        for name in (
            "identity.name", "identity.headline", "identity.email", "identity.phone",
            "identity.linkedin", "identity.github", "identity.website",
            "identity.location_city", "identity.location_country",
        ):
            self.assertTrue(predicates.is_declared(name), f"{name} must be registered")
            spec = predicates.get(name)
            self.assertEqual(spec.kind, PredicateKind.PROJECTED)

    def test_approved_phrase_text_predicate_is_registered_and_projected(self) -> None:
        self.assertTrue(predicates.is_declared("approved_phrase.text"))
        spec = predicates.get("approved_phrase.text")
        self.assertEqual(spec.kind, PredicateKind.PROJECTED)


class FixtureIdentityCoverageTests(unittest.TestCase):
    def test_synthetic_graph_carries_identity_and_four_phrases(self) -> None:
        from truth.fixtures import synthetic_graph

        graph = synthetic_graph()
        self.assertIsNotNone(graph.identity)
        self.assertTrue(graph.identity.name)
        self.assertGreaterEqual(len(graph.approved_phrases), 4)

    def test_founder_shaped_graph_carries_identity_and_four_phrases(self) -> None:
        from truth.fixtures import founder_shaped_graph

        graph = founder_shaped_graph()
        self.assertIsNotNone(graph.identity)
        self.assertTrue(graph.identity.name)
        self.assertGreaterEqual(len(graph.approved_phrases), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
