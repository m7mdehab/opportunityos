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

    def test_default_policy_iran_buyer_country_is_uncertain(self) -> None:
        # Default policy must not default to prohibited jurisdictions
        qual_engine = QualificationEngine()
        opp = create_test_opportunity(
            track=Track.PROCUREMENT,
            title="Statistical Consulting Services",
            procurement_metadata=ProcurementMetadata(
                buyer_name="Tehran Statistical Center",
                buyer_country="Iran",
                notice_type="RFP",
            ),
        )
        decision, hard_results = qual_engine.evaluate(opp, self.truth_graph)
        # Without explicit prohibited_jurisdictions, buyer country is UNCERTAIN (not hard failure / INELIGIBLE)
        self.assertNotEqual(decision, QualificationDecision.INELIGIBLE)
        buyer_results = [r for r in hard_results if r.constraint_name == "buyer_country_policy"]
        self.assertTrue(all(not r.is_hard_failure for r in buyer_results))

    def test_explicit_policy_prohibiting_iran_triggers_hard_rejection(self) -> None:
        from matching.models import ScoringPolicy
        qual_engine = QualificationEngine(policy=ScoringPolicy(prohibited_jurisdictions=("Iran", "Syria")))
        opp = create_test_opportunity(
            track=Track.PROCUREMENT,
            title="Statistical Consulting Services",
            procurement_metadata=ProcurementMetadata(
                buyer_name="Tehran Statistical Center",
                buyer_country="Iran",
                notice_type="RFP",
            ),
        )
        decision, hard_results = qual_engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.INELIGIBLE)
        buyer_results = [r for r in hard_results if r.constraint_name == "buyer_country_policy"]
        self.assertTrue(any(r.is_hard_failure and r.passed is False for r in buyer_results))

    def test_unrelated_service_assertion_does_not_prove_manageable_scope(self) -> None:
        scorer = OpportunityScorer()
        opp = create_test_opportunity(
            track=Track.PROCUREMENT,
            title="Multi-Year Enterprise Transformation",
            description="Massive 500-person multi-year migration project.",
            procurement_metadata=ProcurementMetadata(
                buyer_name="Enterprise Buyer",
                buyer_country="Egypt",
                notice_type="RFP",
            ),
        )
        # self.truth_graph has service.name assertions but NO business/team capacity assertions
        match = scorer.evaluate(opp, self.truth_graph)
        dim_map = {d.dimension_name: d for d in match.dimension_scores}
        # Scope dimension must not have "manageable" strength
        self.assertEqual(len(dim_map["scope_complexity"].strengths), 0)
        self.assertEqual(dim_map["scope_complexity"].raw_score, 0.50)

    def test_stated_procurement_budget_without_founder_economics_is_neutral(self) -> None:
        from opportunity.models import Compensation, CompensationInterval
        scorer = OpportunityScorer()  # Default policy has min_target_compensation=None
        opp = create_test_opportunity(
            track=Track.PROCUREMENT,
            title="Consulting Assignment",
            compensation=Compensation(
                min_amount=150000.0,
                max_amount=200000.0,
                currency="USD",
                interval=CompensationInterval.PROJECT,
            ),
            procurement_metadata=ProcurementMetadata(
                buyer_name="Client Corp",
                buyer_country="Egypt",
                notice_type="RFP",
            ),
        )
        match = scorer.evaluate(opp, self.truth_graph)
        dim_map = {d.dimension_name: d for d in match.dimension_scores}
        # Stated budget without policy comparison produces zero strengths and neutral score
        self.assertEqual(len(dim_map["budget_fit"].strengths), 0)
        self.assertEqual(dim_map["budget_fit"].raw_score, 0.50)

    def test_validate_stale_artifact_without_opportunity_fails_closed(self) -> None:
        opp = create_test_opportunity()
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
        result = self.validator.validate_artifact(cv, self.truth_graph, opportunity=None)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Opportunity binding is mandatory" in err for err in result.errors))

    def test_resolved_commitment_without_policy_object_fails(self) -> None:
        opp = create_test_opportunity()
        policy = TailoringPolicy(default_notice_period_days=30)
        compiler = EmploymentArtifactCompiler(policy=policy)
        cv = compiler.compile_tailored_cv(opp, self.truth_graph)
        # Validate without providing policy object
        result = self.validator.validate_artifact(cv, self.truth_graph, opportunity=opp, policy=None)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("TailoringPolicy object is required" in err for err in result.errors))

    def test_fake_policy_field_in_resolved_commitment_fails(self) -> None:
        opp = create_test_opportunity()
        policy = TailoringPolicy(default_notice_period_days=30)
        tampered_commitment = ForwardCommitment(
            commitment_type="availability",
            description="Notice period",
            status=CommitmentStatus.RESOLVED,
            value="30 days notice",
            policy_source="TailoringPolicy.fake_nonexistent_field",
        )
        cv = self.emp_compiler.compile_tailored_cv(opp, self.truth_graph)
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
        result = self.validator.validate_artifact(tampered_cv, self.truth_graph, opportunity=opp, policy=policy)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("cites non-existent policy field" in err for err in result.errors))

    def test_fabricated_summary_using_valid_unrelated_assertion_ids_fails(self) -> None:
        opp = create_test_opportunity()
        # Create a summary claim that cites valid Python skill assertion (a-skill-py) but makes title claim "Chief Executive Officer"
        tampered_claim = GeneratedClaim(
            claim_id="claim-summary-fabricated",
            text="Professional background as Chief Executive Officer with verified competencies in Rust.",
            section_id="summary",
            assertion_ids=("a-skill-py",),
            evidence_ids=("ev-py",),
            predicate="summary",
            authorized_value="Professional background as Chief Executive Officer with verified competencies in Rust.",
        )
        sec = ArtifactSection(
            section_id="summary",
            heading="Professional Summary",
            content=tampered_claim.text,
            items=(),
            assertion_ids=("a-skill-py",),
            evidence_ids=("ev-py",),
        )
        fabricated_cv = TailoredArtifact(
            artifact_id=f"artifact-cv-{opp.id}",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=opp.id,
            opportunity_content_hash=opp.content_hash,
            template_version="cv-v1.0",
            policy_version="1.0.0",
            title="Fabricated CV",
            sections=(sec,),
            generated_claims=(tampered_claim,),
            commitment_checklist=(),
            compiled_at="2026-08-30",
        )
        result = self.validator.validate_artifact(fabricated_cv, self.truth_graph, opportunity=opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("lacks supporting employment.title" in err or "does not contain cited title" in err for err in result.errors))

    def test_fabricated_employment_record_using_valid_unrelated_assertion_ids_fails(self) -> None:
        opp = create_test_opportunity()
        # Cite valid employment assertion a-title ("Senior Distributed Systems Architect"), but text claims "Chief Executive Officer | Google (2020 – 2024)"
        tampered_claim = GeneratedClaim(
            claim_id="claim-emp-fabricated",
            text="Chief Executive Officer | Google (2020 – 2024)",
            section_id="experience",
            assertion_ids=("a-title",),
            evidence_ids=("ev-title",),
            predicate="employment.record",
            authorized_value="Chief Executive Officer | Google (2020 – 2024)",
        )
        sec = ArtifactSection(
            section_id="experience",
            heading="Professional Experience",
            content=tampered_claim.text,
            items=(tampered_claim.text,),
            assertion_ids=("a-title",),
            evidence_ids=("ev-title",),
        )
        fabricated_cv = TailoredArtifact(
            artifact_id=f"artifact-cv-{opp.id}",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=opp.id,
            opportunity_content_hash=opp.content_hash,
            template_version="cv-v1.0",
            policy_version="1.0.0",
            title="Fabricated CV",
            sections=(sec,),
            generated_claims=(tampered_claim,),
            commitment_checklist=(),
            compiled_at="2026-08-30",
        )
        result = self.validator.validate_artifact(fabricated_cv, self.truth_graph, opportunity=opp)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("does not match cited title" in err or "does not match cited organization" in err for err in result.errors))


if __name__ == "__main__":
    unittest.main()
