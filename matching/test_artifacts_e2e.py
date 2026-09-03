"""End-to-end artifact tests (BRIEF-FR-005 D1 / ADR-0014).

Compiles a tailored CV, a cover letter, and (for the procurement fixture) a
proposal against two synthetic truth packs -- the shipped
`truth.fixtures.synthetic_graph()` template and the new, larger
`truth.fixtures.founder_shaped_graph()` pack (nine employment roles including
internships and three concurrent group roles, five certifications, 38
skills, and preference assertions; every name in it is obviously fake) --
and asserts, for every resulting artifact:

1. zero `ClaimValidator` rejections via the shared, production dispatch
   (`matching.artifact_validation.validate_artifact_claims` -- the same
   function `api/routes_api.py::_compile_and_export` calls) (the D1 defect
   this brief fixes: a naturally-written pack used to reject nearly every
   generated claim);
2. every non-NARRATIVE claim carries at least one evidence id;
3. no term from the committed forbidden-inflation list appears, as a whole
   word, in the rendered DOCX text unless the pack's own evidence contains
   it verbatim;
4. (council remediation, defect 4) a claim mutated to add a genuinely
   unsupported word is rejected -- and ONLY that claim -- proving guard 9
   still functions on this exact compiler output, not merely that the
   positive cases happen to pass; and a NARRATIVE claim mutated to contain a
   red-line phrase is rejected.

This test compiles directly against the compiler + validator; it does not
exercise the HTTP/DB layer (that is `api/test_api.py`'s
`ArtifactRoutesTest`, extended separately for the same ADR-0014 tripwire).
"""
from __future__ import annotations

import dataclasses
import io
import re
import unittest

import docx

from matching.artifact_validation import validate_artifact_claims
from matching.binary_export import BinaryArtifactExporter
from matching.compiler_employment import EmploymentArtifactCompiler
from matching.compiler_independent import IndependentArtifactCompiler
from matching.models import TailoredArtifact
from opportunity.models import (
    Opportunity,
    ProcurementMetadata,
    WorkMode,
    Track,
)
from truth.fixtures import founder_shaped_graph, synthetic_graph
from truth.graph import TruthGraph
from truth.validator import ClaimValidator

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
        work_mode=WorkMode.REMOTE,
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
        work_mode=WorkMode.ONSITE,
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


def _replace_claim(
    artifact: TailoredArtifact, claim_id: str, **overrides
) -> TailoredArtifact:
    """Return a copy of `artifact` with exactly one generated claim (matched
    by `claim_id`) replaced by `dataclasses.replace(claim, **overrides)`.
    Used only to construct deliberately-broken artifacts for the negative
    tests below; `artifact_hash` is left stale on purpose since these
    artifacts are never exported, only validated."""
    new_claims = tuple(
        dataclasses.replace(claim, **overrides) if claim.claim_id == claim_id else claim
        for claim in artifact.generated_claims
    )
    return dataclasses.replace(artifact, generated_claims=new_claims)


class _ArtifactE2ECase(unittest.TestCase):
    """Shared assertion helpers; concrete cases are generated below."""

    def _assert_evidence_backed(self, artifact: TailoredArtifact) -> None:
        """Every non-NARRATIVE claim carries evidence ids -- a claim the
        validator would otherwise have to check against nothing."""
        for claim in artifact.generated_claims:
            if claim.policy_source == "NARRATIVE":
                continue
            self.assertTrue(
                claim.evidence_ids,
                f"non-narrative claim '{claim.claim_id}' ({claim.text!r}) has no evidence ids",
            )

    def _assert_docx_clean(self, artifact: TailoredArtifact, graph: TruthGraph) -> None:
        """DOCX bytes are real (start with the ZIP/docx `PK` magic) and
        contain no forbidden-inflation term, as a whole word, the pack's own
        evidence does not already contain verbatim. Word-boundary matching
        (council remediation, defect 4c): a naive substring check would
        flag "leading" for "lead" or "expertise" for "expert"."""
        docx_bytes = BinaryArtifactExporter.export_to_docx(artifact)
        self.assertTrue(docx_bytes.startswith(b"PK"), "exported artifact is not a docx/zip payload")

        document = docx.Document(io.BytesIO(docx_bytes))
        rendered_text = "\n".join(p.text for p in document.paragraphs).casefold()

        evidence_blob = " ".join(
            (record.content or "") for record in graph.evidence_records.values()
        ).casefold()

        for term in FORBIDDEN_INFLATION_TERMS:
            pattern = rf"\b{re.escape(term)}\b"
            if re.search(pattern, rendered_text):
                self.assertRegex(
                    evidence_blob,
                    pattern,
                    f"forbidden-inflation term '{term}' appears (whole word) in the generated "
                    "document but not verbatim, as a whole word, anywhere in the pack's evidence",
                )

    def _check_employment_artifact(
        self, graph: TruthGraph, opportunity: Opportunity, artifact: TailoredArtifact
    ) -> None:
        validator = ClaimValidator(graph)
        findings = validate_artifact_claims(artifact, validator)
        self.assertEqual(findings, [], f"validator rejected claims: {findings}")
        self._assert_evidence_backed(artifact)
        self._assert_docx_clean(artifact, graph)

    def _assert_mutated_non_narrative_claim_is_rejected_alone(
        self, graph: TruthGraph, artifact: TailoredArtifact
    ) -> None:
        """Council remediation (defect 4a): append a genuinely unsupported
        word to exactly one non-narrative claim's text and assert the
        validator rejects that claim -- and only that claim. This proves
        guard 9 still functions on this exact, real compiler output; the
        positive-only checks above cannot distinguish "guard 9 works" from
        "guard 9 was neutralised and everything happens to pass"."""
        non_narrative = [c for c in artifact.generated_claims if c.policy_source != "NARRATIVE"]
        self.assertTrue(non_narrative, "artifact has no non-narrative claim to mutate")
        target = non_narrative[0]

        mutated = _replace_claim(artifact, target.claim_id, text=target.text + " zorbaflex")
        validator = ClaimValidator(graph)
        findings = validate_artifact_claims(mutated, validator)

        rejected_ids = {finding["claim_id"] for finding in findings}
        self.assertEqual(
            rejected_ids, {target.claim_id},
            f"expected exactly claim '{target.claim_id}' to be rejected after mutation; got {findings}",
        )
        self.assertTrue(
            any("zorbaflex" in reason for reason in findings[0]["rejection_reasons"]),
            findings,
        )

    def _assert_red_line_in_narrative_is_rejected(
        self, graph: TruthGraph, artifact: TailoredArtifact
    ) -> None:
        """Council remediation (defect 4a): a NARRATIVE claim mutated to
        contain a red-line phrase must still be rejected -- proving
        `validate_narrative`'s prohibited-concept/red-line guard, which runs
        on the full narrative text, is not itself neutralised."""
        narrative = [c for c in artifact.generated_claims if c.policy_source == "NARRATIVE"]
        self.assertTrue(narrative, "artifact has no NARRATIVE claim to mutate")
        target = narrative[0]

        mutated = _replace_claim(
            artifact, target.claim_id,
            text=target.text + " This engagement guarantees a 100% success outcome.",
        )
        validator = ClaimValidator(graph)
        findings = validate_artifact_claims(mutated, validator)

        rejected_ids = {finding["claim_id"] for finding in findings}
        self.assertIn(target.claim_id, rejected_ids, findings)


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

        def test_mutated_non_narrative_claim_rejected_alone(self) -> None:
            opp = _remote_employment_opportunity()
            cv = self.emp_compiler.compile_tailored_cv(opp, self.graph)
            self._assert_mutated_non_narrative_claim_is_rejected_alone(self.graph, cv)

        def test_red_line_in_narrative_claim_rejected(self) -> None:
            opp = _remote_employment_opportunity()
            cover = self.emp_compiler.compile_cover_letter(opp, self.graph)
            self._assert_red_line_in_narrative_is_rejected(self.graph, cover)

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


class PeriodTerminatedMetricContextTest(unittest.TestCase):
    """Council remediation (defect 6): a `MetricAssertion.context` ending in
    a full stop used to make `compile_tailored_cv`'s
    "{context}: {value}{unit}" claim text read, to the validator's
    clause-context extraction, as two sentences -- truncating the clause the
    number is checked against and 409ing the CV. Ingest passes a
    founder-authored YAML `context` string through verbatim, so a founder
    who writes a full sentence there hits this; it is not hypothetical."""

    def test_period_terminated_context_still_validates(self) -> None:
        from truth.models import EvidenceRecord, MetricAssertion, MetricVerification

        evidence = (
            EvidenceRecord(
                "ev-period-ach",
                "Reduced deployment time by 25% across the release pipeline.",
                "synthetic_cv", "achievements.0",
                metadata={"subject_id": "achievement-period"},
            ),
        )
        graph = TruthGraph(evidence, metrics=(
            MetricAssertion(
                id="metric-period",
                subject_id="achievement-period",
                numeric_value=25,
                unit="%",
                # Deliberately period-terminated, like a real founder's
                # YAML-authored sentence.
                context="Reduced deployment time by 25% across the release pipeline.",
                verification_status=MetricVerification.VERIFIED,
                evidence_ids=("ev-period-ach",),
            ),
        ))

        opp = _remote_employment_opportunity()
        cv = EmploymentArtifactCompiler().compile_tailored_cv(opp, graph)

        metric_claims = [c for c in cv.generated_claims if c.predicate == "metric"]
        self.assertTrue(metric_claims, "expected a metric-derived claim")
        for claim in metric_claims:
            context_part = claim.text.split(":")[0]
            self.assertFalse(context_part.endswith("."), claim.text)

        validator = ClaimValidator(graph)
        findings = validate_artifact_claims(cv, validator)
        self.assertEqual(findings, [], findings)


if __name__ == "__main__":
    unittest.main()
