"""Adversarial and Claim Validation Tests for Matching Subsystem."""
from __future__ import annotations

import unittest

from matching.compiler_employment import EmploymentArtifactCompiler
from matching.compiler_independent import IndependentArtifactCompiler
from matching.mapping import RequirementMapper
from matching.models import (
    ArtifactSection,
    ArtifactType,
    CommitmentStatus,
    ForwardCommitment,
    GeneratedClaim,
    QualificationDecision,
    RequirementSupportStatus,
    TailoredArtifact,
    TailoringPolicy,
)
from matching.qualification import QualificationEngine
from matching.scorer import OpportunityScorer
from matching.test_qualification import create_test_graph, create_test_opportunity
from matching.validator import ArtifactClaimValidator
from opportunity.models import Opportunity, ProcurementMetadata, RemotePolicy, Track
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, Modality, Polarity, VerificationStatus


class TestArtifactValidatorAndAdversarial(unittest.TestCase):
    def setUp(self) -> None:
        self.truth_graph = create_test_graph()
        self.validator = ArtifactClaimValidator()
        self.emp_compiler = EmploymentArtifactCompiler()

    def test_valid_compiled_cv_passes_validation(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        result = self.validator.validate_artifact(cv, self.truth_graph, opportunity=opp)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
        self.assertTrue(result.verified_claims > 0)
        self.assertEqual(result.unverified_claims, 0)

    def test_adversarial_unrelated_assertion_id_laundering(self) -> None:
        # Cited assertion is valid verified Python skill, but claim asserts Kubernetes
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        laundered_claim = GeneratedClaim(
            claim_id="claim-laundered-k8s",
            text="Kubernetes Expert",
            section_id="skills",
            assertion_ids=("a-skill-py",),
            evidence_ids=("ev-py",),
            predicate="skill.name",
            authorized_value="Kubernetes",
        )
        tampered_cv = TailoredArtifact(
            artifact_id=cv.artifact_id,
            artifact_type=cv.artifact_type,
            opportunity_id=cv.opportunity_id,
            opportunity_content_hash=cv.opportunity_content_hash,
            template_version=cv.template_version,
            policy_version=cv.policy_version,
            title=cv.title,
            sections=cv.sections,
            generated_claims=cv.generated_claims + (laundered_claim,),
            commitment_checklist=cv.commitment_checklist,
            compiled_at=cv.compiled_at,
        )
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph, opportunity=opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("not authorized by cited assertions" in err for err in result.errors))

    def test_adversarial_unsupported_skill_rejected(self) -> None:
        # Generate valid CV then inject an unsupported material claim with non-existent assertion
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        fake_claim = GeneratedClaim(
            claim_id="claim-fake-skill",
            text="Kubernetes Expert",
            section_id="skills",
            assertion_ids=("a-nonexistent-k8s",),
            evidence_ids=(),
            predicate="skill.name",
            authorized_value="Kubernetes",
        )
        tampered_cv = TailoredArtifact(
            artifact_id=cv.artifact_id,
            artifact_type=cv.artifact_type,
            opportunity_id=cv.opportunity_id,
            opportunity_content_hash=cv.opportunity_content_hash,
            template_version=cv.template_version,
            policy_version=cv.policy_version,
            title=cv.title,
            sections=cv.sections,
            generated_claims=cv.generated_claims + (fake_claim,),
            commitment_checklist=cv.commitment_checklist,
            compiled_at=cv.compiled_at,
        )
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph, opportunity=opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("non-existent assertion" in err for err in result.errors))

    def test_adversarial_unverified_status_assertion_rejected(self) -> None:
        # Add unverified assertion to graph and reference it in artifact
        unverified_assertion = AtomicAssertion(
            id="a-unverified-skill",
            subject_id="founder",
            predicate="skill.name",
            value="Solidity",
            evidence_ids=("ev-py",),
            verification_status=VerificationStatus.UNVERIFIED,
        )
        self.truth_graph._assertions["a-unverified-skill"] = unverified_assertion

        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        unverified_claim = GeneratedClaim(
            claim_id="claim-solidity",
            text="Solidity",
            section_id="skills",
            assertion_ids=("a-unverified-skill",),
            evidence_ids=("ev-py",),
            predicate="skill.name",
            authorized_value="Solidity",
        )
        tampered_cv = TailoredArtifact(
            artifact_id=cv.artifact_id,
            artifact_type=cv.artifact_type,
            opportunity_id=cv.opportunity_id,
            opportunity_content_hash=cv.opportunity_content_hash,
            template_version=cv.template_version,
            policy_version=cv.policy_version,
            title=cv.title,
            sections=cv.sections,
            generated_claims=cv.generated_claims + (unverified_claim,),
            commitment_checklist=cv.commitment_checklist,
            compiled_at=cv.compiled_at,
        )
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph, opportunity=opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("unverified assertion" in err for err in result.errors))

    def test_adversarial_planned_credential_upgrade_rejected(self) -> None:
        planned_assertion = AtomicAssertion(
            id="a-planned-cert",
            subject_id="founder",
            predicate="credential.status",
            value="AWS Solutions Architect Professional",
            evidence_ids=("ev-py",),
            verification_status=VerificationStatus.UNVERIFIED,
            modality=Modality.PLANNED,
        )
        self.truth_graph._assertions["a-planned-cert"] = planned_assertion

        sec = ArtifactSection(
            section_id="certs",
            heading="Certifications",
            content="Completed AWS Solutions Architect Professional in 2026.",
            items=("Completed AWS Solutions Architect Professional",),
            assertion_ids=("a-planned-cert",),
            evidence_ids=("ev-py",),
        )
        claim = GeneratedClaim(
            claim_id="claim-cert",
            text="Completed AWS Solutions Architect Professional",
            section_id="certs",
            assertion_ids=("a-planned-cert",),
            evidence_ids=("ev-py",),
            predicate="credential.status",
            authorized_value="Completed AWS Solutions Architect Professional",
        )
        art = TailoredArtifact(
            artifact_id="art-cert",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id="opp-cert",
            opportunity_content_hash="hashcert",
            template_version="v1.0",
            policy_version="1.0.0",
            title="CV with Cert",
            sections=(sec,),
            generated_claims=(claim,),
            commitment_checklist=(),
            compiled_at="2026-08-30",
        )
        result = self.validator.validate_artifact(art, self.truth_graph)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Planned credential" in err or "unverified assertion" in err for err in result.errors))

    def test_adversarial_empty_truth_graph_qualification(self) -> None:
        empty_graph = TruthGraph()
        engine = QualificationEngine()

        # 1. On-site requirement with empty graph -> UNCERTAIN, not INELIGIBLE
        opp_onsite = create_test_opportunity(remote_policy=RemotePolicy.ON_SITE, location_raw="Berlin, Germany")
        decision, constraints = engine.evaluate(opp_onsite, empty_graph)
        self.assertEqual(decision, QualificationDecision.UNCERTAIN)
        c_onsite = [c for c in constraints if c.constraint_name == "work_mode_onsite"][0]
        self.assertIsNone(c_onsite.passed)
        self.assertFalse(c_onsite.is_hard_failure)

        # 2. Explicit US work authorization requirement with empty graph -> UNCERTAIN, not INELIGIBLE
        opp_us_auth = create_test_opportunity(description="Must have valid work authorization in United States.")
        decision, constraints = engine.evaluate(opp_us_auth, empty_graph)
        self.assertEqual(decision, QualificationDecision.UNCERTAIN)
        c_auth = [c for c in constraints if c.constraint_name == "work_authorization"][0]
        self.assertIsNone(c_auth.passed)
        self.assertFalse(c_auth.is_hard_failure)

        # 3. Explicit German language requirement with empty graph -> UNCERTAIN, not INELIGIBLE
        opp_de_lang = create_test_opportunity(description="Role requires fluent in German.")
        decision, constraints = engine.evaluate(opp_de_lang, empty_graph)
        self.assertEqual(decision, QualificationDecision.UNCERTAIN)
        c_lang = [c for c in constraints if c.constraint_name == "language_requirement"][0]
        self.assertIsNone(c_lang.passed)
        self.assertFalse(c_lang.is_hard_failure)

        # 4. Procurement turnover requirement with empty graph -> UNCERTAIN, not INELIGIBLE
        opp_proc = create_test_opportunity(
            track=Track.PROCUREMENT,
            title="Advisory RFP",
            procurement_metadata=ProcurementMetadata(
                buyer_name="UN",
                buyer_country="Egypt",
                notice_type="RFP",
                turnover_required=500000.0,
            ),
        )
        decision, constraints = engine.evaluate(opp_proc, empty_graph)
        self.assertEqual(decision, QualificationDecision.UNCERTAIN)
        c_turn = [c for c in constraints if c.constraint_name == "financial_turnover_requirement"][0]
        self.assertIsNone(c_turn.passed)
        self.assertFalse(c_turn.is_hard_failure)

    def test_adversarial_explicit_negative_founder_fact_qualification(self) -> None:
        engine = QualificationEngine()
        # Graph with explicit negative German auth fact
        opp_de = create_test_opportunity(description="Must have valid work authorization in Germany.")
        decision, constraints = engine.evaluate(opp_de, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.INELIGIBLE)
        c_auth = [c for c in constraints if c.constraint_name == "work_authorization"][0]
        self.assertFalse(c_auth.passed)
        self.assertTrue(c_auth.is_hard_failure)

    def test_adversarial_no_fallback_identities_in_compilers(self) -> None:
        empty_graph = TruthGraph()
        emp_compiler = EmploymentArtifactCompiler()
        ind_compiler = IndependentArtifactCompiler(policy=TailoringPolicy())
        opp = create_test_opportunity()

        cv = emp_compiler.compile_tailored_cv(opp, empty_graph)
        cv_text = " ".join(s.content for s in cv.sections)
        self.assertNotIn("Software Engineer", cv_text)
        self.assertNotIn("Engineering Leader", cv_text)
        self.assertNotIn("Technology Enterprise", cv_text)
        self.assertNotIn("Present", cv_text)
        self.assertNotIn("cloud infrastructure", cv_text.casefold())
        self.assertNotIn("distributed systems", cv_text.casefold())
        self.assertNotIn("summary", [s.section_id for s in cv.sections])

        prop = ind_compiler.compile_proposal(opp, empty_graph)
        prop_text = " ".join(s.content for s in prop.sections)
        self.assertNotIn("Enterprise architecture", prop_text)

    def test_adversarial_unconfigured_commitments_marked_red(self) -> None:
        ind_compiler = IndependentArtifactCompiler(policy=TailoringPolicy())
        opp = create_test_opportunity(track=Track.PROCUREMENT)
        prop = ind_compiler.compile_proposal(opp, self.truth_graph)
        self.assertTrue(all(c.status == CommitmentStatus.UNRESOLVED for c in prop.commitment_checklist))
        self.assertTrue(all("UNRESOLVED (RED)" in c.value for c in prop.commitment_checklist))

    def test_adversarial_fake_generic_policy_source_rejected(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        tampered_commitment = ForwardCommitment(
            commitment_type="availability",
            description="Engagement availability",
            status=CommitmentStatus.RESOLVED,
            value="Immediate availability",
            policy_source="TailoringPolicy",  # Generic policy source without attribute
        )
        tampered_cv = TailoredArtifact(
            artifact_id=cv.artifact_id,
            artifact_type=cv.artifact_type,
            opportunity_id=cv.opportunity_id,
            opportunity_content_hash=cv.opportunity_content_hash,
            template_version=cv.template_version,
            policy_version=cv.policy_version,
            title=cv.title,
            sections=cv.sections,
            generated_claims=cv.generated_claims,
            commitment_checklist=(tampered_commitment,),
            compiled_at=cv.compiled_at,
        )
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph, opportunity=opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("specific approved policy source" in err for err in result.errors))

    def test_adversarial_stale_opportunity_hash_rejected(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        stale_opp = Opportunity(
            id=opp.id,
            track=opp.track,
            source=opp.source,
            source_url=opp.source_url,
            source_id=opp.source_id,
            organization=opp.organization,
            title="Modified Title Changed",
            description="Modified description triggering hash change",
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
            procurement_metadata=opp.procurement_metadata,
            raw_provenance=opp.raw_provenance,
            record_checksum="modified-checksum",
            raw_record_pointer=opp.raw_record_pointer,
            field_provenances=(),
        )
        result = self.validator.validate_artifact(cv, self.truth_graph, opportunity=stale_opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Opportunity content hash mismatch" in err for err in result.errors))

    def test_adversarial_tampered_commitment_hash_mismatch(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        # Directly tamper the internal tuple without recomputing hash
        tampered_checklist = (
            ForwardCommitment(
                commitment_type="availability",
                description="Tampered notice",
                status=CommitmentStatus.RESOLVED,
                value="0 days notice",
                policy_source="TailoringPolicy.default_notice_period_days",
            ),
        )
        tampered_cv = TailoredArtifact(
            artifact_id=cv.artifact_id,
            artifact_type=cv.artifact_type,
            opportunity_id=cv.opportunity_id,
            opportunity_content_hash=cv.opportunity_content_hash,
            template_version=cv.template_version,
            policy_version=cv.policy_version,
            title=cv.title,
            sections=cv.sections,
            generated_claims=cv.generated_claims,
            commitment_checklist=tampered_checklist,
            compiled_at=cv.compiled_at,
            artifact_hash=cv.artifact_hash,  # Stale hash
        )
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph, opportunity=opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Artifact hash mismatch" in err for err in result.errors))

    def test_adversarial_scorer_with_empty_founder_truth_emits_no_strengths(self) -> None:
        scorer = OpportunityScorer()
        empty_graph = TruthGraph()
        opp = create_test_opportunity()
        match = scorer.evaluate(opp, empty_graph)
        self.assertEqual(len(match.strengths), 0)
        self.assertTrue(match.uncertainty_penalty >= 0.15)

    def test_adversarial_procurement_scope_with_no_capacity_evidence(self) -> None:
        scorer = OpportunityScorer()
        empty_graph = TruthGraph()
        opp = create_test_opportunity(
            track=Track.PROCUREMENT,
            title="Enterprise Cloud Migration Tender",
            procurement_metadata=ProcurementMetadata(
                buyer_name="World Bank",
                buyer_country="Egypt",
                notice_type="RFP",
            ),
        )
        match = scorer.evaluate(opp, empty_graph)
        self.assertEqual(len(match.strengths), 0)
        dim_map = {d.dimension_name: d.raw_score for d in match.dimension_scores}
        self.assertEqual(dim_map["service_capabilities"], 0.0)
        self.assertEqual(dim_map["portfolio_evidence"], 0.0)
        self.assertEqual(dim_map["evidence_sufficiency"], 0.0)

    def test_adversarial_cross_predicate_requirement_mapping_laundering(self) -> None:
        mapper = RequirementMapper()
        opp = create_test_opportunity(
            responsibilities=("Collaborate with Advisory Services LLC on 2026-08-30 in Egypt.",),
            skills=(),
        )
        req_map = mapper.map_requirements(opp, self.truth_graph)
        # Even though "Egypt" is in residence.country and "Advisory" is in service.name,
        # non-matching responsibilities must NOT be marked SUPPORTED
        resp_mappings = [m for m in req_map.mappings if m.requirement_type == "responsibility"]
        self.assertTrue(all(m.status != RequirementSupportStatus.SUPPORTED for m in resp_mappings))


if __name__ == "__main__":
    unittest.main()
