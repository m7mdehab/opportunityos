"""R2 regression tests for the outbound compatibility facade."""
from __future__ import annotations

import dataclasses
import io
import unittest

import docx

from matching.artifact_validation import validate_artifact_claims
from matching.binary_export import BinaryArtifactExporter
from matching.compiler_employment import EmploymentArtifactCompiler
from matching.ats_quality import AtsDocumentQualityHarness
from matching.test_artifacts_e2e import _remote_employment_opportunity
from matching.validator import ArtifactClaimValidator
from truth.fixtures import founder_shaped_graph
from truth.models import (
    AtomicAssertion,
    MetricAssertion,
    MetricVerification,
    Modality,
    Polarity,
    VerificationStatus,
    EvidenceRecord,
)
from truth.validator import ClaimValidator


class ValidatorFacadeR2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = founder_shaped_graph()
        self.opportunity = _remote_employment_opportunity()
        self.artifact = EmploymentArtifactCompiler().compile_tailored_cv(
            self.opportunity, self.graph
        )

    def test_facade_claim_semantics_parity_with_api_dispatch(self) -> None:
        canonical_findings = validate_artifact_claims(
            self.artifact, ClaimValidator(self.graph)
        )
        facade_result = ArtifactClaimValidator().validate_artifact(
            self.artifact, self.graph, opportunity=self.opportunity
        )
        self.assertEqual(canonical_findings, [])
        self.assertTrue(facade_result.is_valid, facade_result.errors)

        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.policy_source != "NARRATIVE"
        )
        mutated = dataclasses.replace(
            self.artifact,
            generated_claims=tuple(
                dataclasses.replace(claim, text=claim.text + " zorbaflex")
                if claim.claim_id == target.claim_id else claim
                for claim in self.artifact.generated_claims
            ),
        )
        canonical_mutated = validate_artifact_claims(
            mutated, ClaimValidator(self.graph)
        )
        facade_mutated = ArtifactClaimValidator().validate_artifact(
            mutated, self.graph, opportunity=self.opportunity
        )
        self.assertEqual(
            {finding["claim_id"] for finding in canonical_mutated},
            {target.claim_id},
        )
        self.assertFalse(facade_mutated.is_valid)
        self.assertTrue(any(target.claim_id in error for error in facade_mutated.errors))

    def test_unsupported_claim_and_tampered_envelope_fail_closed(self) -> None:
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.policy_source != "NARRATIVE"
        )
        unsupported = dataclasses.replace(
            self.artifact,
            generated_claims=self.artifact.generated_claims + (
                dataclasses.replace(target, claim_id="unsupported-r2", text="zorbaflex"),
            ),
        )
        result = ArtifactClaimValidator().validate_artifact(
            unsupported, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("unsupported-r2" in error for error in result.errors))

        tampered = dataclasses.replace(
            self.artifact, opportunity_content_hash="stale-opportunity-hash"
        )
        result = ArtifactClaimValidator().validate_artifact(
            tampered, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("content hash mismatch" in error for error in result.errors))
        self.assertTrue(any("Artifact hash mismatch" in error for error in result.errors))

    def test_claim_predicate_and_authorized_value_bind_to_cited_assertions(self) -> None:
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.predicate == "skill.name"
        )
        forged = dataclasses.replace(
            self.artifact,
            generated_claims=(
                dataclasses.replace(
                    target,
                    claim_id="predicate-laundered",
                    predicate="employment.title",
                    authorized_value="Go",
                    text="Go",
                ),
            ),
        )
        result = ArtifactClaimValidator().validate_artifact(
            forged, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("not bound to cited assertions" in error for error in result.errors))

    def test_scalar_skill_value_uses_casefolded_exact_equality(self) -> None:
        evidence = EvidenceRecord(
            "ev-go-exact", "Uses Go in production services.", "synthetic_cv", "skills.go"
        )
        self.graph.add_evidence(evidence)
        assertion = AtomicAssertion(
            id="a-skill-go-exact", subject_id="founder", predicate="skill.name",
            value="Go", evidence_ids=(evidence.id,), polarity=Polarity.POSITIVE,
            modality=Modality.DEFINITE, verification_status=VerificationStatus.VERIFIED,
        )
        self.graph.add_assertion(assertion)
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.predicate == "skill.name"
        )
        forged = dataclasses.replace(
            self.artifact,
            generated_claims=(
                dataclasses.replace(
                    target,
                    claim_id="skill-go-lang",
                    text="Go Lang",
                    assertion_ids=(assertion.id,),
                    evidence_ids=(evidence.id,),
                    authorized_value="Go Lang",
                ),
            ),
        )
        result = ArtifactClaimValidator().validate_artifact(
            forged, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("not authorized by cited assertions" in error for error in result.errors))

    def test_record_claim_requires_subject_domain_and_field_containment(self) -> None:
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.predicate == "employment.record"
        )
        forged = dataclasses.replace(
            self.artifact,
            generated_claims=(
                dataclasses.replace(
                    target,
                    claim_id="record-domain-laundered",
                    predicate="education.record",
                    authorized_value="BSc in Computer Science | Nile Institute",
                    text="BSc in Computer Science | Nile Institute",
                ),
            ),
        )
        result = ArtifactClaimValidator().validate_artifact(
            forged, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("mismatched-domain" in error for error in result.errors))

    def test_arbitrary_record_predicate_is_rejected(self) -> None:
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.predicate == "employment.record"
        )
        forged = dataclasses.replace(
            self.artifact,
            generated_claims=(dataclasses.replace(
                target,
                claim_id="arbitrary-record-predicate",
                predicate="founder.record",
            ),),
        )
        result = ArtifactClaimValidator().validate_artifact(
            forged, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("unsupported record predicate" in error for error in result.errors))

    def test_arbitrary_scalar_predicate_is_rejected(self) -> None:
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.predicate == "skill.name"
        )
        forged = dataclasses.replace(
            self.artifact,
            generated_claims=(dataclasses.replace(
                target,
                claim_id="arbitrary-scalar-predicate",
                predicate="hacker.fact",
            ),),
        )
        result = ArtifactClaimValidator().validate_artifact(
            forged, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Unknown or unauthorized claim predicate" in error for error in result.errors))

    def test_metric_claim_must_match_specifically_cited_metric_ids(self) -> None:
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.predicate == "metric"
        )
        original_id = target.assertion_ids[0]
        original = self.graph.metrics[original_id]
        self.graph._metrics["metric-unrelated-same-evidence"] = MetricAssertion(
            id="metric-unrelated-same-evidence",
            subject_id=original.subject_id,
            numeric_value=99,
            unit=original.unit,
            context=original.context,
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=original.evidence_ids,
        )
        forged = dataclasses.replace(
            self.artifact,
            generated_claims=(
                dataclasses.replace(
                    target,
                    claim_id="metric-id-laundered",
                    assertion_ids=("metric-unrelated-same-evidence",),
                ),
            ),
        )
        result = ArtifactClaimValidator().validate_artifact(
            forged, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("cited metric IDs" in error for error in result.errors))

    def test_material_claim_without_evidence_ids_fails_closed(self) -> None:
        target = next(
            claim for claim in self.artifact.generated_claims
            if claim.policy_source != "NARRATIVE"
        )
        forged = dataclasses.replace(
            self.artifact,
            generated_claims=(
                dataclasses.replace(target, claim_id="graph-wide-fallback", evidence_ids=()),
            ),
        )
        result = ArtifactClaimValidator().validate_artifact(
            forged, self.graph, opportunity=self.opportunity
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("graph-wide evidence fallback" in error for error in result.errors))

    def test_founder_shaped_fixture_dimensions_and_egyptian_phone_export(self) -> None:
        predicates = {assertion.predicate for assertion in self.graph.assertions.values()}
        for predicate in (
            "employment.start_date", "employment.end_date",
            "skill.proficiency", "work_authorization.jurisdiction",
            "work_authorization.status", "language.language",
            "language.proficiency", "service.name",
            "employment.responsibility",
        ):
            self.assertIn(predicate, predicates)

        phone_claim = next(
            claim for claim in self.artifact.generated_claims
            if claim.predicate == "identity.phone"
        )
        self.assertEqual(phone_claim.text, "+20-555-0101")
        self.assertEqual(
            validate_artifact_claims(self.artifact, ClaimValidator(self.graph)), []
        )
        facade_result = ArtifactClaimValidator().validate_artifact(
            self.artifact, self.graph, opportunity=self.opportunity
        )
        self.assertTrue(facade_result.is_valid, facade_result.errors)

        docx_bytes = BinaryArtifactExporter.export_to_docx(self.artifact)
        pdf_bytes = BinaryArtifactExporter.export_to_pdf(self.artifact)
        self.assertIn(
            "+20-555-0101",
            AtsDocumentQualityHarness.inspect_docx(docx_bytes)["full_text"],
        )
        self.assertIn(
            "+20-555-0101",
            AtsDocumentQualityHarness.inspect_pdf(pdf_bytes)["full_text"],
        )
        self.assertIn(
            "+20-555-0101",
            "\n".join(p.text for p in docx.Document(io.BytesIO(docx_bytes)).paragraphs),
        )


if __name__ == "__main__":
    unittest.main()
