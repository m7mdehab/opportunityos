import unittest

from truth.fixtures import synthetic_career_profile, synthetic_evidence, synthetic_graph
from truth.graph import TruthGraph
from truth.models import AssertionType, CareerProfile, EvidenceRecord


class TruthGraphTests(unittest.TestCase):
    def test_indexes_atomic_evidence_and_profiles(self):
        graph = synthetic_graph()
        self.assertEqual("Uses Python for data engineering.", graph.evidence("ev-python").content)
        self.assertEqual("Data Engineer", graph.entity("job-synthetic").title)
        self.assertIn("career-synthetic", graph.profiles)
        self.assertIn("capability-synthetic", graph.profiles)

    def test_unknown_evidence_rejects_profile_transactionally(self):
        graph = TruthGraph()
        profile = CareerProfile("bad-profile", evidence_ids=("missing",))
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            graph.add_career_profile(profile)
        self.assertEqual({}, dict(graph.profiles))
        with self.assertRaises(KeyError):
            graph.entity("bad-profile")

    def test_duplicate_nodes_are_rejected(self):
        graph = TruthGraph(synthetic_evidence())
        graph.add_career_profile(synthetic_career_profile())
        with self.assertRaisesRegex(ValueError, "duplicate graph node"):
            graph.add_career_profile(synthetic_career_profile())
        with self.assertRaisesRegex(ValueError, "duplicate graph node"):
            graph.add_evidence(EvidenceRecord("job-synthetic", "collision", "fixture", "x"))

    def test_direct_and_recursive_provenance_are_distinct(self):
        graph = synthetic_graph()
        direct = graph.evidence_for("career-synthetic")
        recursive = graph.evidence_for("career-synthetic", recursive=True)
        self.assertEqual((), direct)
        self.assertIn("ev-achievement", {record.id for record in recursive})
        self.assertIn("ev-cert-plan", {record.id for record in recursive})
        self.assertEqual(len(recursive), len({record.id for record in recursive}))

    def test_provenance_edge_list_preserves_owning_node(self):
        edges = synthetic_graph().provenance("career-synthetic")
        self.assertIn(
            ("achievement-verified", "ev-achievement"),
            {(entity_id, evidence.id) for entity_id, evidence in edges},
        )

    def test_fact_and_inference_categories_do_not_overlap(self):
        graph = synthetic_graph()
        facts = {record.id for record in graph.facts()}
        inferences = {record.id for record in graph.inferences()}
        self.assertIn("ev-python", facts)
        self.assertIn("ev-service", inferences)
        self.assertFalse(facts & inferences)
        self.assertEqual(
            ("ev-service",),
            tuple(record.id for record in graph.records_by_assertion(AssertionType.DERIVED_CAPABILITY)),
        )

    def test_indexes_are_read_only_views(self):
        graph = synthetic_graph()
        with self.assertRaises(TypeError):
            graph.evidence_records["injected"] = object()
        with self.assertRaises(TypeError):
            graph.profiles["injected"] = object()

    def test_unknown_lookup_has_explicit_error(self):
        graph = TruthGraph()
        with self.assertRaisesRegex(KeyError, "unknown evidence id"):
            graph.evidence("missing")
        with self.assertRaisesRegex(KeyError, "unknown entity id"):
            graph.entity("missing")


if __name__ == "__main__":
    unittest.main()
