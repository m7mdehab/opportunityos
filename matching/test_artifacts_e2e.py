"""End-to-end artifact tests (BRIEF-FR-005 D1 / ADR-0014).

Compiles a tailored CV, a cover letter, and (for the procurement fixture) a
proposal against two synthetic truth packs -- the shipped
`truth.fixtures.synthetic_graph()` template and the new, larger
`truth.fixtures.founder_shaped_graph()` pack (nine employment roles including
internships and three concurrent group roles, five certifications, 38
skills, and preference assertions; every name in it is obviously fake) --
and asserts, for every resulting artifact:

1. zero `ClaimValidator` rejections (the D1 defect this brief fixes: a
   naturally-written pack used to reject nearly every generated claim);
2. every non-NARRATIVE claim carries at least one evidence id, and no word
   rendered into a section's DOCX text is untraceable to a claim covering
   that section, `_NON_MATERIAL_WORDS`, the committed `CONNECTIVE_TERMS`
   stop-list, or the opportunity's own field values;
3. no term from the committed forbidden-inflation list appears in the
   rendered DOCX text unless the pack's own evidence contains it verbatim.

This test compiles directly against the compiler + validator; it does not
exercise the HTTP/DB layer (that is `api/test_api.py`'s
`ArtifactRoutesTest`, extended separately for the same ADR-0014 tripwire).
"""
from __future__ import annotations

import io
import unittest

import docx

from matching.binary_export import BinaryArtifactExporter
from matching.compiler_employment import EmploymentArtifactCompiler
from matching.compiler_independent import IndependentArtifactCompiler
from matching.models import TailoredArtifact
from opportunity.models import (
    Opportunity,
    ProcurementMetadata,
    RemotePolicy,
    Track,
)
from truth.fixtures import founder_shaped_graph, synthetic_graph
from truth.graph import TruthGraph
from truth.validator import (
    CONNECTIVE_TERMS,
    ClaimValidator,
    _NON_MATERIAL_WORDS,
    _tokens,
    opportunity_terms_from_values,
)

# Committed forbidden-inflation list (BRIEF-FR-005 D1 acceptance): words a
# compiler must never introduce on its own initiative. It is legitimate for
# one of these words to appear in a generated document ONLY when the pack's
# own evidence already contains it, verbatim -- i.e. it is a fact the founder
# actually stated, not compiler-added color.
FORBIDDEN_INFLATION_TERMS = (
    "senior",
    "lead",
    "expert",
    "guaranteed",
    "fortune 500",
    "world-class",
    "renowned",
    "extensive",
    "proven",
)

# Sections whose `content`/`items` are forward-commitment policy statements
# (`ForwardCommitment`, a distinct model from `GeneratedClaim` -- see
# `matching/models.py`), not evidence-backed claims about the founder's
# history. They are intentionally excluded from the claim-coverage mapping
# below; `commitment_checklist` carries its own RESOLVED/UNRESOLVED (RED)
# discipline, unchanged by this brief.
_NON_CLAIM_SECTIONS = frozenset({"commitments"})


def _remote_employment_opportunity() -> Opportunity:
    return Opportunity(
        id="opp-e2e-remote",
        track=Track.EMPLOYMENT,
        source="synthetic_source",
        source_url="https://example.invalid/jobs/1",
        source_id="job-1",
        organization="Globex Corp",
        title="Data Engineer",
        description="Build and operate data pipelines for a distributed team.",
        skills=("Python", "SQL", "Docker", "Apache Kafka"),
        remote_policy=RemotePolicy.REMOTE,
    )


def _onsite_employment_opportunity() -> Opportunity:
    return Opportunity(
        id="opp-e2e-onsite",
        track=Track.EMPLOYMENT,
        source="synthetic_source",
        source_url="https://example.invalid/jobs/2",
        source_id="job-2",
        organization="Initech LLC",
        title="Platform Engineer",
        description="Operate the on-site data platform for a logistics group.",
        skills=("Python", "Kubernetes", "Terraform"),
        remote_policy=RemotePolicy.ON_SITE,
        location_raw="Cairo, Egypt",
    )


def _procurement_opportunity() -> Opportunity:
    return Opportunity(
        id="opp-e2e-procurement",
        track=Track.PROCUREMENT,
        source="synthetic_source",
        source_url="https://example.invalid/tenders/1",
        source_id="tender-1",
        organization="World Bank",
        title="Data Advisory RFP",
        description="Technical advisory for a regional data governance programme.",
        procurement_metadata=ProcurementMetadata(
            buyer_name="World Bank",
            buyer_country="Egypt",
            notice_type="RFP",
        ),
    )


class _ArtifactE2ECase(unittest.TestCase):
    """Shared assertion helpers; concrete cases are generated below."""

    def _validate_all(
        self, artifact: TailoredArtifact, graph: TruthGraph, opportunity: Opportunity
    ) -> list[tuple[str, str, tuple[str, ...]]]:
        """Mirror `api/routes_api.py::_compile_and_export`'s validation dispatch
        exactly: NARRATIVE claims go through `validate_narrative` (prohibited
        concepts / red lines only); every other claim goes through
        `validate_claim` with class (b) opportunity terms derived, by this
        caller, from the opportunity's own real field values."""
        validator = ClaimValidator(graph)
        opportunity_terms = opportunity_terms_from_values(opportunity.organization, opportunity.title)
        findings: list[tuple[str, str, tuple[str, ...]]] = []
        for claim in artifact.generated_claims:
            if claim.policy_source == "NARRATIVE":
                result = validator.validate_narrative(claim.text)
            else:
                result = validator.validate_claim(claim.text, claim.evidence_ids, opportunity_terms=opportunity_terms)
            if not result.allowed:
                findings.append((claim.claim_id, claim.text, result.reasons))
        return findings

    def _assert_claim_coverage(
        self, artifact: TailoredArtifact, opportunity: Opportunity
    ) -> None:
        """Every non-NARRATIVE claim carries evidence ids, and no word
        rendered into a (claim-bearing) section's DOCX text is untraceable to
        a claim covering that section, non-material vocabulary, the
        committed connective stop-list, or the opportunity's own fields."""
        opportunity_terms = opportunity_terms_from_values(opportunity.organization, opportunity.title)

        for claim in artifact.generated_claims:
            if claim.policy_source == "NARRATIVE":
                continue
            self.assertTrue(
                claim.evidence_ids,
                f"non-narrative claim '{claim.claim_id}' ({claim.text!r}) has no evidence ids",
            )

        claims_by_section: dict[str, list] = {}
        for claim in artifact.generated_claims:
            claims_by_section.setdefault(claim.section_id, []).append(claim)

        for section in artifact.sections:
            if section.section_id in _NON_CLAIM_SECTIONS:
                continue
            section_claims = claims_by_section.get(section.section_id, [])
            allowed = set(_NON_MATERIAL_WORDS) | set(CONNECTIVE_TERMS) | opportunity_terms
            for claim in section_claims:
                allowed |= _tokens(claim.text)

            content_stray = _tokens(section.content) - allowed
            self.assertFalse(
                content_stray,
                f"section '{section.section_id}' content has untraceable words {sorted(content_stray)}: {section.content!r}",
            )
            for item in section.items:
                item_stray = _tokens(item) - allowed
                self.assertFalse(
                    item_stray,
                    f"section '{section.section_id}' item has untraceable words {sorted(item_stray)}: {item!r}",
                )

    def _assert_docx_clean(self, artifact: TailoredArtifact, graph: TruthGraph) -> None:
        """DOCX bytes are real (start with the ZIP/docx `PK` magic) and
        contain no forbidden-inflation term the pack's own evidence does not
        already contain, verbatim."""
        docx_bytes = BinaryArtifactExporter.export_to_docx(artifact)
        self.assertTrue(docx_bytes.startswith(b"PK"), "exported artifact is not a docx/zip payload")

        document = docx.Document(io.BytesIO(docx_bytes))
        rendered_text = "\n".join(p.text for p in document.paragraphs).casefold()

        evidence_blob = " ".join(
            (record.content or "") for record in graph.evidence_records.values()
        ).casefold()

        for term in FORBIDDEN_INFLATION_TERMS:
            if term in rendered_text:
                self.assertIn(
                    term,
                    evidence_blob,
                    f"forbidden-inflation term '{term}' appears in the generated document "
                    "but not verbatim anywhere in the pack's evidence",
                )

    def _check_employment_artifact(
        self, graph: TruthGraph, opportunity: Opportunity, artifact: TailoredArtifact
    ) -> None:
        findings = self._validate_all(artifact, graph, opportunity)
        self.assertEqual(findings, [], f"validator rejected claims: {findings}")
        self._assert_claim_coverage(artifact, opportunity)
        self._assert_docx_clean(artifact, graph)


def _make_case(pack_name: str, pack_factory) -> type[_ArtifactE2ECase]:
    """Build a concrete `TestCase` subclass for one synthetic pack, covering
    all three fixture opportunities (employment remote, employment on-site,
    procurement) with both compilers. A factory function (rather than a
    shared `setUp` parametrized by hand) keeps `unittest discover` picking
    up one clearly-named class per pack without extra test-runner plumbing.
    """

    class Case(_ArtifactE2ECase):
        def setUp(self) -> None:
            self.graph = pack_factory()
            self.emp_compiler = EmploymentArtifactCompiler()
            self.ind_compiler = IndependentArtifactCompiler()

        def test_tailored_cv_remote(self) -> None:
            opp = _remote_employment_opportunity()
            cv = self.emp_compiler.compile_tailored_cv(opp, self.graph)
            self._check_employment_artifact(self.graph, opp, cv)

        def test_cover_letter_remote(self) -> None:
            opp = _remote_employment_opportunity()
            cover = self.emp_compiler.compile_cover_letter(opp, self.graph)
            self._check_employment_artifact(self.graph, opp, cover)

        def test_tailored_cv_onsite(self) -> None:
            opp = _onsite_employment_opportunity()
            cv = self.emp_compiler.compile_tailored_cv(opp, self.graph)
            self._check_employment_artifact(self.graph, opp, cv)

        def test_cover_letter_onsite(self) -> None:
            opp = _onsite_employment_opportunity()
            cover = self.emp_compiler.compile_cover_letter(opp, self.graph)
            self._check_employment_artifact(self.graph, opp, cover)

        def test_proposal_procurement(self) -> None:
            opp = _procurement_opportunity()
            proposal = self.ind_compiler.compile_proposal(opp, self.graph)
            self._check_employment_artifact(self.graph, opp, proposal)

    Case.__name__ = f"Test{pack_name}ArtifactsE2E"
    Case.__qualname__ = Case.__name__
    return Case


TestSyntheticArtifactsE2E = _make_case("Synthetic", synthetic_graph)
TestFounderShapedArtifactsE2E = _make_case("FounderShaped", founder_shaped_graph)


class FounderShapedPackShapeTest(unittest.TestCase):
    """Sanity checks on the founder-shaped pack's own shape, independent of
    the compiler/validator: this is what BRIEF-FR-005 D1 asked the pack to
    contain."""

    def setUp(self) -> None:
        self.graph = founder_shaped_graph()

    def test_nine_employment_roles(self) -> None:
        titles = {a.subject_id for a in self.graph.assertions.values() if a.predicate == "employment.title"}
        self.assertEqual(len(titles), 9)

    def test_three_concurrent_group_roles(self) -> None:
        from truth.fixtures import _FOUNDER_ROLES

        concurrent = [
            role for role in _FOUNDER_ROLES
            if role["start"].isoformat() == "2023-01-01" and role["end"].isoformat() == "2026-08-31"
        ]
        self.assertEqual(len(concurrent), 3)
        self.assertEqual(len({role["org"] for role in concurrent}), 3, "concurrent roles must span distinct entities")

    def test_internships_present(self) -> None:
        from truth.fixtures import _FOUNDER_ROLES

        internship_titles = {role["title"] for role in _FOUNDER_ROLES if "Intern" in role["title"]}
        self.assertGreaterEqual(len(internship_titles), 2)

    def test_five_certifications(self) -> None:
        names = {a.subject_id for a in self.graph.assertions.values() if a.predicate == "certification.name"}
        self.assertEqual(len(names), 5)

    def test_thirty_eight_skills(self) -> None:
        skills = {a.value for a in self.graph.assertions.values() if a.predicate == "skill.name"}
        self.assertEqual(len(skills), 38)

    def test_preferences_are_assertions(self) -> None:
        preference_predicates = {
            a.predicate for a in self.graph.assertions.values()
            if a.predicate.startswith("preference.") or a.predicate.startswith("career.")
        }
        self.assertIn("career.target_role", preference_predicates)
        self.assertIn("preference.track", preference_predicates)
        self.assertIn("preference.fulltime_onsite_premium_monthly", preference_predicates)


if __name__ == "__main__":
    unittest.main()
