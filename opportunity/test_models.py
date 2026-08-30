"""Unit Tests for Opportunity Data Models and Field Manifest."""
from __future__ import annotations

import dataclasses
import unittest

from opportunity.models import (
    Compensation,
    CompensationInterval,
    DerivationType,
    EmploymentType,
    FieldProvenance,
    GeographicEligibility,
    MATERIAL_OPPORTUNITY_FIELD_MANIFEST,
    Opportunity,
    OpportunityCluster,
    ProcurementMetadata,
    RemotePolicy,
    SeniorityLevel,
    SourceProvenance,
    Track,
    compute_canonical_content_hash,
    compute_dedup_key,
    compute_deterministic_id,
    validate_opportunity_provenance,
)


class TestOpportunityModels(unittest.TestCase):
    def test_material_field_manifest_reflection(self) -> None:
        """Every field on Opportunity must be classified or handled in MATERIAL_OPPORTUNITY_FIELD_MANIFEST."""
        opp_fields = {f.name for f in dataclasses.fields(Opportunity)}
        
        # Base infrastructure/structural fields not subject to field provenance directly
        infrastructure_fields = {
            "id",
            "source",
            "source_url",
            "source_id",
            "raw_provenance",
            "record_checksum",
            "raw_record_pointer",
            "field_provenances",
            "canonical_outbound_url",
            "content_hash",
            "dedup_key",
            "extra_attributes",
        }
        
        material_fields = opp_fields - infrastructure_fields
        for field_name in material_fields:
            self.assertIn(
                field_name,
                MATERIAL_OPPORTUNITY_FIELD_MANIFEST,
                f"Opportunity field '{field_name}' is not in MATERIAL_OPPORTUNITY_FIELD_MANIFEST",
            )

    def test_validate_opportunity_provenance_success(self) -> None:
        fp_title = FieldProvenance("title", "Lead Engineer", "Lead Engineer", "raw_extraction", "jobs[0].title", "abc", "clean_text")
        fp_org = FieldProvenance("organization", "Acme", "Acme", "raw_extraction", "jobs[0].org", "abc", "clean_text")
        fp_track = FieldProvenance("track", "full_time", "employment", "rule_derivation", "jobs[0]", "abc", "extract_track")
        fp_desc = FieldProvenance("description", "Desc", "Desc", "raw_extraction", "jobs[0].desc", "abc", "clean_text")

        opp = Opportunity(
            id="test:1",
            track=Track.EMPLOYMENT,
            source="test",
            source_url="https://example.com",
            source_id="1",
            organization="Acme",
            title="Lead Engineer",
            description="Desc",
            field_provenances=(fp_title, fp_org, fp_track, fp_desc),
        )
        valid, err = validate_opportunity_provenance(opp)
        self.assertTrue(valid, err)

    def test_validate_opportunity_provenance_missing_field_fails(self) -> None:
        fp_title = FieldProvenance("title", "Lead Engineer", "Lead Engineer", "raw_extraction", "jobs[0].title", "abc", "clean_text")
        # Missing organization and track provenance
        opp = Opportunity(
            id="test:1",
            track=Track.EMPLOYMENT,
            source="test",
            source_url="https://example.com",
            source_id="1",
            organization="Acme",
            title="Lead Engineer",
            description="Desc",
            field_provenances=(fp_title,),
        )
        valid, err = validate_opportunity_provenance(opp)
        self.assertFalse(valid)
        self.assertIn("Missing provenance", err)

    def test_deterministic_id_reproducibility(self) -> None:
        id1 = compute_deterministic_id("greenhouse:stripe", "12345", "Backend Engineer", "Stripe", "jobs[0]")
        id2 = compute_deterministic_id("greenhouse:stripe", "12345", "Backend Engineer", "Stripe", "jobs[0]")
        self.assertEqual(id1, id2)
        self.assertEqual(id1, "greenhouse:stripe:12345")

    def test_content_hash_and_dedup_key_whitespace_invariance(self) -> None:
        hash1 = compute_canonical_content_hash(" Acme Corp ", "Senior   Engineer", "Remote - US", " Great role! ")
        hash2 = compute_canonical_content_hash("acme corp", "Senior Engineer", "remote - us", "great role!")
        self.assertEqual(hash1, hash2)

        dedup1 = compute_dedup_key("Acme, Inc.", "Senior Engineer - Backend", "Remote")
        dedup2 = compute_dedup_key("Acme Inc", "Senior Engineer Backend", "remote")
        self.assertEqual(dedup1, dedup2)


if __name__ == "__main__":
    unittest.main()
