"""Contract tests for the predicate registry (ADR-0015, BRIEF-FR-005 D2).

Three things are asserted:

1. Every predicate string `matching/scorer.py` and `matching/qualification.py`
   compare against an `AtomicAssertion.predicate` attribute is declared in
   `truth/predicates.py`. This is implemented by parsing those files with
   `ast` and finding every string literal used as the other side of a
   `<expr>.predicate == "..."` / `<expr>.predicate in (...)` comparison — not
   by maintaining a second, hand-written list that could drift from the code.
2. Every registry predicate is either PROJECTED (derived from
   `truth.models.CANONICAL_MATERIAL_MANIFEST`, i.e. actually emitted by
   `truth/graph.py`) or ASSERTION_ONLY with a named owning pack section.
3. A founder-shaped graph with real `employment.responsibility` /
   `achievement.statement` assertions re-scores `responsibility_scope` above
   the historical flat 0.50, with non-empty evidence_refs.

Scope note: this scans `matching/scorer.py` and `matching/qualification.py`
only. `matching/validator.py`, `matching/compiler_employment.py`, and
`matching/compiler_independent.py` also have a `.predicate` attribute, but it
belongs to `GeneratedClaim` (`matching/models.py`), a distinct D1-owned claim
taxonomy, not the truth graph's `AtomicAssertion.predicate` vocabulary this
registry governs. `matching/mapping.py` does read `AtomicAssertion.predicate`
and carries an identical, unfixed instance of the same defect this brief's D2
scope fixes in scorer.py/qualification.py; it is out of D2's file scope and is
recorded in ADR-0015 rather than silently swept into this test's scan.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from truth import predicates
from truth.predicates import PredicateKind

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNED_FILES: tuple[Path, ...] = (
    REPO_ROOT / "matching" / "scorer.py",
    REPO_ROOT / "matching" / "qualification.py",
)


def _resolve_module_attribute(node: ast.Attribute) -> object | None:
    """Resolve a `predicates.NAME` module-qualified attribute to its runtime value.

    `matching/scorer.py` and `matching/qualification.py` import
    `from truth import predicates` and reference `predicates.SKILL_NAME` etc.
    instead of spelling predicate strings inline, so the scanner must resolve
    those references back to strings/tuples to see what predicate they name.
    """
    if isinstance(node.value, ast.Name) and node.value.id == "predicates":
        return getattr(predicates, node.attr, None)
    return None


def _predicate_values(node: ast.AST) -> list[str]:
    """Collect predicate strings out of a literal, a tuple/list/set of literals,
    or a `predicates.NAME` reference (scalar or tuple-valued)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        out: list[str] = []
        for elt in node.elts:
            out.extend(_predicate_values(elt))
        return out
    if isinstance(node, ast.Attribute):
        resolved = _resolve_module_attribute(node)
        if isinstance(resolved, str):
            return [resolved]
        if isinstance(resolved, (tuple, list, set)):
            return [v for v in resolved if isinstance(v, str)]
    return []


def _find_predicate_literals(source_path: Path) -> set[str]:
    """Find every predicate value compared against a `.predicate` attribute.

    Matches `a.predicate == "skill.name"`, `a.predicate == predicates.SKILL_NAME`,
    `a.predicate in ("x", "y")`, and `a.predicate in predicates.SOME_TUPLE` shapes
    (with or without `not`) — every shape used in matching/scorer.py and
    matching/qualification.py.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    found: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Compare(self, node: ast.Compare) -> None:
            operands: list[ast.expr] = [node.left, *node.comparators]
            is_predicate_comparison = any(
                isinstance(operand, ast.Attribute) and operand.attr == "predicate"
                for operand in operands
            )
            if is_predicate_comparison:
                for operand in operands:
                    if isinstance(operand, ast.Attribute) and operand.attr == "predicate":
                        continue
                    found.update(_predicate_values(operand))
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


class TestPredicateRegistryCompleteness(unittest.TestCase):
    """Every predicate matching/ reads must be declared; every declared predicate
    must be honestly classified as PROJECTED or ASSERTION_ONLY."""

    def test_every_scanned_file_exists(self) -> None:
        for path in SCANNED_FILES:
            self.assertTrue(path.is_file(), f"expected scanned file to exist: {path}")

    def test_every_referenced_predicate_is_registered(self) -> None:
        registry = predicates.all_predicates()
        for path in SCANNED_FILES:
            referenced = _find_predicate_literals(path)
            unregistered = sorted(p for p in referenced if p not in registry)
            self.assertEqual(
                unregistered,
                [],
                f"{path.name} references predicate(s) not declared in truth/predicates.py: {unregistered}",
            )

    def test_scanned_files_reference_at_least_one_predicate(self) -> None:
        # Guards against the scanner silently finding nothing due to a refactor
        # that changes the `.predicate == "..."` shape it looks for.
        total = sum(len(_find_predicate_literals(path)) for path in SCANNED_FILES)
        self.assertGreater(total, 0)

    def test_registry_predicates_are_classified_projected_or_assertion_only(self) -> None:
        registry = predicates.all_predicates()
        self.assertTrue(registry, "predicate registry must not be empty")
        for name, spec in registry.items():
            self.assertEqual(spec.name, name)
            self.assertIn(spec.kind, (PredicateKind.PROJECTED, PredicateKind.ASSERTION_ONLY))
            self.assertTrue(spec.source, f"predicate {name!r} must name its source")

    def test_projected_predicates_match_the_canonical_manifest(self) -> None:
        from truth.models import CANONICAL_MATERIAL_MANIFEST

        manifest_predicates = {spec.predicate for spec in CANONICAL_MATERIAL_MANIFEST}
        registry = predicates.all_predicates()
        projected = {
            name for name, spec in registry.items() if spec.kind is PredicateKind.PROJECTED
        }
        self.assertEqual(projected, manifest_predicates)

    def test_assertion_only_predicates_name_the_assertions_section(self) -> None:
        registry = predicates.all_predicates()
        for name, spec in registry.items():
            if spec.kind is PredicateKind.ASSERTION_ONLY:
                self.assertEqual(
                    spec.source,
                    "assertions",
                    f"assertion-only predicate {name!r} must name its owning pack section",
                )

    def test_known_orphans_are_no_longer_referenced_by_their_old_spelling(self) -> None:
        """The specific orphan spellings this brief's defect list named must be gone
        from scorer.py/qualification.py; only their real, registered replacements
        (or a declared assertion-only predicate) may remain."""
        orphans = {
            "responsibility.item",
            "employment.role_description",
            "experience.summary",
            "achievement.description",
            "authorization.jurisdiction",
            "language.name",
            "business.team_size",
            "capacity.headcount",
            "business.annual_turnover",
            "capacity.annual_turnover",
            "portfolio.item",
        }
        for path in SCANNED_FILES:
            referenced = _find_predicate_literals(path)
            leftover = referenced & orphans
            self.assertEqual(leftover, set(), f"{path.name} still references orphan predicate(s): {leftover}")


class TestResponsibilityScopeRescores(unittest.TestCase):
    """D2 acceptance: a founder-shaped graph with real responsibilities must no
    longer flatten responsibility_scope to 0.50."""

    def _founder_graph(self):
        from truth.graph import TruthGraph
        from truth.models import AtomicAssertion, EvidenceRecord, VerificationStatus

        graph = TruthGraph()
        ev_title = EvidenceRecord(
            id="ev-title",
            content="Senior Data Engineer",
            source="manual",
            locator="employment.title",
            metadata={"title": "Senior Data Engineer"},
        )
        ev_resp1 = EvidenceRecord(
            id="ev-resp1",
            content="Designed and operated petabyte-scale streaming data pipelines on AWS",
            source="manual",
            locator="employment.responsibility",
            metadata={"responsibility": "Designed and operated petabyte-scale streaming data pipelines"},
        )
        ev_resp2 = EvidenceRecord(
            id="ev-resp2",
            content="Owned on-call rotation for distributed backend data services",
            source="manual",
            locator="employment.responsibility",
            metadata={"responsibility": "Owned on-call rotation for distributed backend data services"},
        )
        ev_ach = EvidenceRecord(
            id="ev-ach",
            content="Reduced pipeline latency by 40 percent through Kafka partition rebalancing",
            source="manual",
            locator="achievement.statement",
            metadata={"statement": "Reduced pipeline latency by 40 percent through Kafka partition rebalancing"},
        )
        for ev in (ev_title, ev_resp1, ev_resp2, ev_ach):
            graph.add_evidence(ev)

        graph.add_assertion(AtomicAssertion(
            id="a-title",
            subject_id="founder",
            predicate=predicates.EMPLOYMENT_TITLE,
            value="Senior Data Engineer",
            evidence_ids=("ev-title",),
            verification_status=VerificationStatus.VERIFIED,
        ))
        graph.add_assertion(AtomicAssertion(
            id="a-resp1",
            subject_id="founder",
            predicate=predicates.EMPLOYMENT_RESPONSIBILITY,
            value="Designed and operated petabyte-scale streaming data pipelines",
            evidence_ids=("ev-resp1",),
            verification_status=VerificationStatus.VERIFIED,
        ))
        graph.add_assertion(AtomicAssertion(
            id="a-resp2",
            subject_id="founder",
            predicate=predicates.EMPLOYMENT_RESPONSIBILITY,
            value="Owned on-call rotation for distributed backend data services",
            evidence_ids=("ev-resp2",),
            verification_status=VerificationStatus.VERIFIED,
        ))
        graph.add_assertion(AtomicAssertion(
            id="a-ach",
            subject_id="founder",
            predicate=predicates.ACHIEVEMENT_STATEMENT,
            value="Reduced pipeline latency by 40 percent through Kafka partition rebalancing",
            evidence_ids=("ev-ach",),
            verification_status=VerificationStatus.VERIFIED,
        ))
        return graph

    def _remote_data_engineer_opportunity(self):
        from opportunity.models import (
            EmploymentType,
            GeographicEligibility,
            Opportunity,
            RemotePolicy,
            SeniorityLevel,
            SourceProvenance,
            Track,
        )

        prov = SourceProvenance(
            source_id="greenhouse:example",
            source_url="https://boards-api.greenhouse.io/v1/boards/example/jobs/1",
            feed_url="https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true",
            fetched_at="2026-09-03T00:00:00Z",
            payload_checksum="sha256fake",
        )
        geo = GeographicEligibility(status="eligible", reason="Worldwide remote")
        return Opportunity(
            id="opp-data-eng",
            track=Track.EMPLOYMENT,
            source="greenhouse:example",
            source_url="https://boards-api.greenhouse.io/v1/boards/example/jobs/1",
            source_id="1",
            organization="Example Corp",
            title="Remote Data Engineer",
            description="Own our streaming data platform end to end.",
            responsibilities=(
                "Designed and operated petabyte-scale streaming data pipelines",
                "Owned on-call rotation for distributed backend data services",
            ),
            requirements=("5+ years data engineering", "Kafka experience"),
            skills=("Python", "Kafka"),
            seniority=SeniorityLevel.SENIOR,
            employment_type=EmploymentType.FULL_TIME,
            location_raw="Remote, Worldwide",
            remote_policy=RemotePolicy.REMOTE,
            geographic_eligibility=geo,
            compensation=None,
            posted_date="2026-09-01",
            closing_date=None,
            procurement_metadata=None,
            raw_provenance=prov,
            record_checksum="sha256fake",
            raw_record_pointer="feed:jobs[0]",
            field_provenances=(),
        )

    def test_responsibility_scope_exceeds_flat_half_with_evidence(self) -> None:
        from matching.scorer import OpportunityScorer

        graph = self._founder_graph()
        opp = self._remote_data_engineer_opportunity()
        evaluation = OpportunityScorer().evaluate(opp, graph)

        resp_dim = next(
            ds for ds in evaluation.dimension_scores if ds.dimension_name == "responsibility_scope"
        )
        self.assertGreater(resp_dim.raw_score, 0.50)
        self.assertTrue(resp_dim.evidence_refs, "responsibility_scope must cite evidence when it re-scores above 0.50")
        self.assertEqual(resp_dim.dimension_name, "responsibility_scope")
        self.assertIsInstance(resp_dim.weighted_score, float)
        self.assertGreaterEqual(resp_dim.weight, 0.0)
        self.assertIsInstance(resp_dim.explanation, str)


if __name__ == "__main__":
    unittest.main()
