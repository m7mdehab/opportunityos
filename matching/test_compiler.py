"""Tests for Employment and Independent Artifact Compilers."""
from __future__ import annotations

import unittest

from opportunity.models import Opportunity, ProcurementMetadata, Track
from matching.compiler_employment import EmploymentArtifactCompiler
from matching.compiler_independent import IndependentArtifactCompiler
from matching.models import ArtifactType, CommitmentStatus, TailoringPolicy
from matching.test_qualification import create_test_graph, create_test_opportunity


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

    def test_compile_tailored_cv(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        self.assertEqual(cv.artifact_type, ArtifactType.TAILORED_CV)
        self.assertEqual(cv.opportunity_id, opp.id)
        self.assertTrue(len(cv.sections) >= 3)
        self.assertTrue(len(cv.generated_claims) > 0)
        self.assertTrue(bool(cv.artifact_hash))

    def test_compile_cover_letter(self) -> None:
        opp = create_test_opportunity()
        cover = self.emp_compiler.compile_cover_letter(opp, self.truth_graph)
        self.assertEqual(cover.artifact_type, ArtifactType.COVER_LETTER)
        self.assertTrue(len(cover.sections) >= 2)

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
