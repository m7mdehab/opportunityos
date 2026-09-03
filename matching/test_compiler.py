"""Tests for Employment and Independent Artifact Compilers."""
from __future__ import annotations

import unittest

from opportunity.models import Opportunity, ProcurementMetadata, Track
from matching.artifact_validation import validate_artifact_claims
from matching.compiler_employment import EmploymentArtifactCompiler
from matching.compiler_independent import IndependentArtifactCompiler
from matching.models import ArtifactType, CommitmentStatus, TailoringPolicy
from matching.test_qualification import create_test_graph, create_test_opportunity
from truth.validator import ClaimValidator


class TestArtifactCompilers(unittest.TestCase):
    def setUp(self) -> None:
        self.truth_graph = create_test_graph()
        self.emp_compiler = EmploymentArtifactCompiler()
        self.ind_compiler = IndependentArtifactCompiler(
            policy=TailoringPolicy(
                default_daily_rate=1200.0,
                default_currency="USD",
                default_availability_hours_per_week=40,
                business_legal_name="Advisory Services LLC",
                business_registration_country="Egypt",
                guarantees_policy="standard_commercial_warranty",
            )
        )

    def _rejections(self, artifact, opportunity=None) -> list[dict]:
        """Run every generated claim through the real, production ADR-0014
        validator dispatch (`matching.artifact_validation.validate_artifact_claims`
        -- the same function `api/routes_api.py::_compile_and_export` calls,
        not a hand-copied mirror of it) and return the findings. An empty
        list is the actual behaviour this deliverable fixes -- BRIEF-FR-004's
        compiler emitted composite claims that `ClaimValidator` correctly
        refused for any naturally-written pack; counting `len(sections) >= N`
        never caught that, because a section can exist and still carry a
        claim the validator would 409 on. `opportunity` is accepted and
        unused (kept so call sites that pass one for documentation purposes
        do not need updating) -- ADR-0014's class (b) was removed entirely
        after council review, so validation no longer depends on the
        opportunity at all."""
        validator = ClaimValidator(self.truth_graph)
        return validate_artifact_claims(artifact, validator)

    def test_compile_tailored_cv(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        self.assertEqual(cv.artifact_type, ArtifactType.TAILORED_CV)
        self.assertEqual(cv.opportunity_id, opp.id)
        self.assertTrue(len(cv.generated_claims) > 0)
        self.assertTrue(bool(cv.artifact_hash))
        # The actual deliverable: every claim the compiler generated against
        # a real (non-hand-tuned) truth graph must clear `ClaimValidator`.
        self.assertEqual(self._rejections(cv, opp), [])
        # `create_test_graph()` (matching/test_qualification.py, not part of
        # this order's scope) carries no `career_profile.approved_summaries`,
        # so the Summary section (BRIEF-FR-006 D1: selects an approved-
        # summary variant, never combines evidence) is legitimately empty
        # here -- the atomicity check below runs against
        # `truth.fixtures.synthetic_graph()`, which does carry one.
        from truth.fixtures import synthetic_graph

        summary_graph = synthetic_graph()
        summary_cv = self.emp_compiler.compile_tailored_cv(opp, summary_graph)
        # ADR-0014 atomicity (BRIEF-FR-006 D1 update): the summary claim is
        # the selected `profile.approved_summary` assertion verbatim -- it
        # cites exactly that one assertion's own evidence, never combining
        # unrelated evidence into the same claim (BRIEF-FR-004 defect: that
        # combination tripped the relational-composition guard for any
        # naturally-written pack).
        summary_claims = [c for c in summary_cv.generated_claims if c.predicate == "profile.approved_summary"]
        self.assertTrue(summary_claims, "expected a professional-summary claim")
        for claim in summary_claims:
            self.assertLessEqual(len(claim.assertion_ids), 1, "summary claim must cite at most one founder fact")

    def test_compile_tailored_cv_with_metric_bearing_graph(self) -> None:
        """Regression (BRIEF-FR-004 D6 council finding): `MetricAssertion`
        has a `context` field, not `semantic_context`. The achievements
        section of `compile_tailored_cv` used to read the wrong attribute
        name and raise `AttributeError` for any truth graph containing a
        metric -- which a real founder pack, with a quantified achievement,
        is very likely to have. `truth.fixtures.synthetic_graph()` includes
        exactly such a metric (evidence-supported, so it survives graph
        construction); this must compile cleanly and the metric's `context`
        text must actually appear in the output."""
        from truth.fixtures import synthetic_graph

        metric_graph = synthetic_graph()
        opp = create_test_opportunity()

        cv = self.emp_compiler.compile_tailored_cv(opp, metric_graph)

        self.assertTrue(len(cv.sections) >= 1)
        metric_claims = [c for c in cv.generated_claims if c.predicate == "metric"]
        self.assertTrue(metric_claims, "expected at least one metric-derived claim")
        self.assertTrue(
            any("reduced processing time by 40%" in claim.text for claim in metric_claims),
            [c.text for c in metric_claims],
        )

    def test_compile_cover_letter(self) -> None:
        opp = create_test_opportunity()
        cover = self.emp_compiler.compile_cover_letter(opp, self.truth_graph)
        self.assertEqual(cover.artifact_type, ArtifactType.COVER_LETTER)
        self.assertTrue(len(cover.generated_claims) > 0)
        # The actual deliverable: a cover letter naturally names the target
        # role and employer (BRIEF-FR-004 defect: the validator treated
        # those words as unsupported founder claims and 409'd 2 of 2 cover
        # letter claims against the shipped template). Every claim the
        # compiler generated must now clear `ClaimValidator`.
        self.assertEqual(self._rejections(cover, opp), [])
        # At least one claim must be a NARRATIVE segment (the greeting) and
        # at least one must be a real, evidence-backed founder claim -- a
        # cover letter that was entirely narrative would prove nothing about
        # the fix, and one with no narrative at all would not be a letter.
        policy_sources = {c.policy_source for c in cover.generated_claims}
        self.assertIn("NARRATIVE", policy_sources)
        non_narrative = [c for c in cover.generated_claims if c.policy_source != "NARRATIVE"]
        self.assertTrue(non_narrative, "expected at least one non-narrative (evidence-backed) claim")
        self.assertTrue(all(c.evidence_ids for c in non_narrative), "every non-narrative claim must cite evidence")

    def test_compile_independent_proposal_with_resolved_commitments(self) -> None:
        opp = create_test_opportunity(
            track=Track.PROCUREMENT,
            title="Cloud Infrastructure Advisory RFP",
        )
        opp = Opportunity(
            id=opp.id,
            track=opp.track,
            source=opp.source,
            source_url=opp.source_url,
            source_id=opp.source_id,
            organization=opp.organization,
            title=opp.title,
            description=opp.description,
            responsibilities=opp.responsibilities,
            requirements=opp.requirements,
            skills=opp.skills,
            seniority=opp.seniority,
            employment_type=opp.employment_type,
            location_raw=opp.location_raw,
            remote_policy=opp.remote_policy,
            geographic_eligibility=opp.geographic_eligibility,
            compensation=opp.compensation,
            posted_date=opp.posted_date,
            closing_date=opp.closing_date,
            procurement_metadata=ProcurementMetadata(
                buyer_name="World Bank",
                buyer_country="Egypt",
                notice_type="RFP",
            ),
            raw_provenance=opp.raw_provenance,
            record_checksum=opp.record_checksum,
            raw_record_pointer=opp.raw_record_pointer,
            field_provenances=(),
        )
        prop = self.ind_compiler.compile_proposal(opp, self.truth_graph)
        self.assertEqual(prop.artifact_type, ArtifactType.RFP_RESPONSE_SCAFFOLD)
        self.assertTrue(all(c.status == CommitmentStatus.RESOLVED for c in prop.commitment_checklist))

    def test_unresolved_commitments_marked_red_when_unstated(self) -> None:
        unconfigured_compiler = IndependentArtifactCompiler(policy=TailoringPolicy())
        opp = create_test_opportunity(track=Track.PROCUREMENT)
        prop = unconfigured_compiler.compile_proposal(opp, self.truth_graph)
        unresolved = [c for c in prop.commitment_checklist if c.status == CommitmentStatus.UNRESOLVED]
        self.assertTrue(len(unresolved) >= 2)
        self.assertTrue(any("UNRESOLVED" in c.value for c in unresolved))


if __name__ == "__main__":
    unittest.main()
