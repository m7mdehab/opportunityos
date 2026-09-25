"""Contract tests for the predicate registry (ADR-0015, BRIEF-FR-005 D2).

Three things are asserted:

1. Every predicate string any non-test module in `matching/` compares against
   an `AtomicAssertion.predicate` attribute is declared in
   `truth/predicates.py`. This is implemented by parsing every `matching/*.py`
   file (discovered by glob, not a hand-listed tuple, so a new file cannot
   silently reintroduce the defect this brief fixes) with `ast` and finding
   every string literal or `predicates.NAME` reference used as the other side
   of a `<expr>.predicate == "..."` / `<expr>.predicate in (...)` comparison —
   not by maintaining a second, hand-written list that could drift from the
   code.
2. Every registry predicate is either PROJECTED (derived from
   `truth.models.CANONICAL_MATERIAL_MANIFEST`, i.e. actually emitted by
   `truth/graph.py`) or ASSERTION_ONLY with a named owning pack section.
3. A founder-shaped graph with real `employment.responsibility` /
   `achievement.statement` assertions re-scores `responsibility_scope` above
   the historical flat 0.50, with non-empty evidence_refs.

Scope note — GeneratedClaim exclusion (narrow, not a file omission): every
`matching/*.py` file is scanned, including `matching/validator.py`,
`matching/compiler_employment.py`, and `matching/compiler_independent.py`.
Those three also compare a `.predicate` attribute, but on `GeneratedClaim`
(`matching/models.py:153`), a distinct, D1-owned claim-type tag vocabulary
("metric", "summary", "employment.record", …) that is not the truth graph's
`AtomicAssertion.predicate` vocabulary this registry governs. `ast` carries no
type information, so this scan excludes only comparisons where the `.predicate`
attribute is accessed on a variable named `claim` — the one naming convention
every file in `matching/` uses without exception for `GeneratedClaim`
instances (verified by inspection; `AtomicAssertion` instances are uniformly
bound to `a`). This is a narrow, documented exclusion of specific comparisons,
not an excluded file: `matching/validator.py:265`'s
`a.predicate in ("credential.status", "certification.state")` iterates
`truth_graph.assertions.values()` (genuinely `AtomicAssertion`) and is scanned.

Scope note — out-of-scope orphans, tracked not hidden: this D2 deliverable's
file scope is `matching/scorer.py`, `matching/qualification.py`, and
`matching/mapping.py`. The widened, file-agnostic scan above also reaches
`matching/compiler_independent.py` and `matching/validator.py` (D1-owned,
frozen for D2) and finds genuine unregistered `AtomicAssertion.predicate`
values there: `compiler_independent.py`'s `"portfolio.item"` (same defect as
the one fixed in `scorer.py`; real name `portfolio.title`) and
`validator.py`'s `"credential.status"` (no such manifest field exists).
`_KNOWN_OUT_OF_SCOPE_ORPHANS` below records exactly these two findings so the
scan can widen honestly without either (a) silently passing by not looking, or
(b) failing this deliverable's suite over defects two files outside its scope.
Any predicate found anywhere that is not registered *and* not on this exact,
per-file, per-predicate allowlist is still a hard failure.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from truth import predicates
from truth.predicates import PredicateKind

REPO_ROOT = Path(__file__).resolve().parent.parent
MATCHING_DIR = REPO_ROOT / "matching"

# Every non-test module in matching/, discovered by glob. A new file dropped
# into matching/ is scanned automatically; nothing here needs updating for it
# to be covered.
SCANNED_FILES: tuple[Path, ...] = tuple(
    sorted(
        p for p in MATCHING_DIR.glob("*.py")
        if not p.name.startswith("test_") and p.name != "__init__.py"
    )
)

# Files this D2 deliverable actually fixes. `test_known_orphans_are_no_longer_referenced`
# and `test_d2_fixed_files_have_zero_out_of_scope_allowance` hold these to a
# stricter bar than the rest of matching/.
D2_FIXED_FILES: frozenset[str] = frozenset({"scorer.py", "qualification.py", "mapping.py"})

# GeneratedClaim.predicate accesses are excluded from the scan (see module
# docstring) by the one naming convention matching/ uses without exception.
_GENERATED_CLAIM_VAR_NAMES = frozenset({"claim"})

# Genuine AtomicAssertion.predicate orphans the widened scan reaches in files
# outside D2's fix scope (D1-owned, frozen here). Tracked, not hidden — see
# module docstring. `test_out_of_scope_allowlist_is_exact` keeps this from
# going stale.
_KNOWN_OUT_OF_SCOPE_ORPHANS: dict[str, frozenset[str]] = {
    # `compiler_independent.py`'s "portfolio.item" was on this list when D2
    # wrote it. D1 fixed the truth-graph read to "portfolio.title" in the same
    # brief, so the entry went stale and
    # `test_out_of_scope_allowlist_is_exact_not_a_ceiling` failed at
    # integration demanding its removal -- which is precisely what that test
    # exists to do. Removed by the Master at integration, not by either
    # implementer. The surviving `GeneratedClaim(predicate="portfolio.item")`
    # in that file is the compiler's own claim-type tag consumed by
    # `matching/validator.py::ArtifactClaimValidator`, not a truth-graph
    # predicate, and the scanner correctly does not count it.
    "validator.py": frozenset({"credential.status"}),
}


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


def _is_generated_claim_predicate_access(node: ast.Attribute) -> bool:
    """True if `node` is `.predicate` accessed on a variable named `claim`
    (the GeneratedClaim naming convention this scan excludes; see module
    docstring)."""
    return (
        node.attr == "predicate"
        and isinstance(node.value, ast.Name)
        and node.value.id in _GENERATED_CLAIM_VAR_NAMES
    )


def _find_predicate_literals(source_path: Path) -> set[str]:
    """Find every predicate value compared against an `AtomicAssertion.predicate`
    attribute.

    Matches `a.predicate == "skill.name"`, `a.predicate == predicates.SKILL_NAME`,
    `a.predicate in ("x", "y")`, and `a.predicate in predicates.SOME_TUPLE` shapes
    (with or without `not`) — every shape used across matching/. Comparisons
    where every `.predicate` operand is a GeneratedClaim access (variable named
    `claim`) are excluded; see module docstring.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    found: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Compare(self, node: ast.Compare) -> None:
            operands: list[ast.expr] = [node.left, *node.comparators]
            predicate_operands = [
                operand for operand in operands
                if isinstance(operand, ast.Attribute) and operand.attr == "predicate"
            ]
            if predicate_operands and not all(
                _is_generated_claim_predicate_access(operand) for operand in predicate_operands
            ):
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
            unregistered = {p for p in referenced if p not in registry}
            allowed_out_of_scope = _KNOWN_OUT_OF_SCOPE_ORPHANS.get(path.name, frozenset())
            unexpected = sorted(unregistered - allowed_out_of_scope)
            self.assertEqual(
                unexpected,
                [],
                f"{path.name} references predicate(s) neither declared in truth/predicates.py "
                f"nor on the tracked out-of-scope allowlist: {unexpected}",
            )

    def test_d2_fixed_files_have_zero_out_of_scope_allowance(self) -> None:
        """scorer.py, qualification.py, and mapping.py are this D2 deliverable's
        actual fix scope: they get no out-of-scope allowance at all."""
        for filename in D2_FIXED_FILES:
            self.assertNotIn(
                filename,
                _KNOWN_OUT_OF_SCOPE_ORPHANS,
                f"{filename} is in D2 scope and must have zero unregistered predicates, "
                "not a tracked allowance",
            )

    def test_out_of_scope_allowlist_is_exact_not_a_ceiling(self) -> None:
        """Every allowlisted (file, predicate) pair must still be actually
        referenced and actually unregistered, so a future fix removes the
        entry instead of leaving a stale allowance masking a regression."""
        registry = predicates.all_predicates()
        files_by_name = {path.name: path for path in SCANNED_FILES}
        for filename, allowed in _KNOWN_OUT_OF_SCOPE_ORPHANS.items():
            path = files_by_name.get(filename)
            self.assertIsNotNone(path, f"tracked file {filename!r} is no longer scanned")
            referenced = _find_predicate_literals(path)
            for predicate_name in allowed:
                self.assertIn(
                    predicate_name, referenced,
                    f"{filename} no longer references {predicate_name!r}; remove it from the allowlist",
                )
                self.assertNotIn(
                    predicate_name, registry,
                    f"{predicate_name!r} is now registered; remove the {filename} allowlist entry",
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

    def test_target_role_predicates_are_projected(self) -> None:
        registry = predicates.all_predicates()
        for name in (predicates.CAREER_TARGET_ROLE, predicates.CAREER_TARGET_ROLE_TIER):
            self.assertEqual(PredicateKind.PROJECTED, registry[name].kind)
            self.assertIn("TargetRoleRecord", registry[name].source)

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

    def test_fr008_preference_predicates_are_registered_as_assertion_only(self) -> None:
        registry = predicates.all_predicates()
        for name in (
            predicates.PREFERENCE_WORK_MODE,
            predicates.PREFERENCE_EMPLOYMENT_TYPE,
            predicates.PREFERENCE_GEOGRAPHY,
            predicates.PREFERENCE_RELOCATION,
            predicates.PREFERENCE_COMPENSATION,
            predicates.PREFERENCE_INDUSTRY,
            predicates.PREFERENCE_COMPANY,
            predicates.PREFERENCE_TIME_ZONE,
            predicates.PREFERENCE_TRAVEL,
        ):
            self.assertEqual(registry[name].kind, PredicateKind.ASSERTION_ONLY)
            self.assertEqual(registry[name].source, "assertions")

    def test_known_orphans_are_no_longer_referenced_by_their_old_spelling(self) -> None:
        """The specific orphan spellings this brief's defect list named must be gone
        from the files this D2 deliverable fixed (scorer.py, qualification.py,
        mapping.py); only their real, registered replacements (or a declared
        assertion-only predicate) may remain. `compiler_independent.py` still
        references `"portfolio.item"` — tracked separately, out of D2 scope,
        via `_KNOWN_OUT_OF_SCOPE_ORPHANS`, not asserted against here."""
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
            if path.name not in D2_FIXED_FILES:
                continue
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
            WorkMode,
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
            work_mode=WorkMode.REMOTE,
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
