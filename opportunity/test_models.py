"""Unit Tests for Opportunity Data Models and Field Manifest."""
from __future__ import annotations

import dataclasses
import unittest

from opportunity.adapters import GreenhouseAdapter, UNGMAdapter
from opportunity.models import (
    Compensation,
    CompensationInterval,
    DerivationType,
    EmploymentType,
    FieldProvenance,
    GeographicEligibility,
    MATERIAL_OPPORTUNITY_FIELD_MANIFEST,
    MATERIAL_OPPORTUNITY_FIELD_RULES,
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
        """Every field on Opportunity must have an executable rule in MATERIAL_OPPORTUNITY_FIELD_RULES."""
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
        rule_field_names = {r.field_name for r in MATERIAL_OPPORTUNITY_FIELD_RULES}

        for field_name in material_fields:
            self.assertIn(
                field_name,
                rule_field_names,
                f"Opportunity field '{field_name}' lacks an executable rule in MATERIAL_OPPORTUNITY_FIELD_RULES",
            )
            self.assertIn(
                field_name,
                MATERIAL_OPPORTUNITY_FIELD_MANIFEST,
                f"Opportunity field '{field_name}' is missing from MATERIAL_OPPORTUNITY_FIELD_MANIFEST",
            )

    def test_greenhouse_field_provenance_individual_removal_regressions(self) -> None:
        """Removing provenance for each populated field individually MUST fail validation."""
        payload = """{
            "jobs": [
                {
                    "id": 1001,
                    "title": "Staff Backend Engineer",
                    "content": "<h3>Responsibilities</h3><ul><li>Build distributed services</li></ul><h3>Requirements</h3><ul><li>5+ years Python</li></ul><p>Salary: USD 150k - 200k.</p>",
                    "location": {"name": "Remote"},
                    "updated_at": "2026-08-15T00:00:00Z",
                    "employment_type": "Full-time"
                }
            ]
        }"""
        adapter = GreenhouseAdapter("cloudflare")
        result = adapter.parse_payload(payload)
        self.assertEqual(len(result.opportunities), 1)
        opp = result.opportunities[0]

        # Verify all targeted fields are populated
        self.assertTrue(bool(opp.skills), "Skills should be populated")
        self.assertTrue(bool(opp.responsibilities), "Responsibilities should be populated")
        self.assertTrue(bool(opp.requirements), "Requirements should be populated")
        self.assertIsNotNone(opp.compensation, "Compensation should be populated")
        self.assertIsNotNone(opp.posted_date, "Posted date should be populated")

        # Valid baseline
        valid, err = validate_opportunity_provenance(opp)
        self.assertTrue(valid, err)

        # Fields to test removing individually
        fields_to_test = [
            "skills",
            "responsibilities",
            "requirements",
            "compensation",
            "compensation.min_amount",
            "compensation.max_amount",
            "compensation.currency",
            "posted_date",
            "track",
            "organization",
            "title",
            "seniority",
            "employment_type",
            "location_raw",
            "remote_policy",
            "geographic_eligibility",
        ]

        for field_to_remove in fields_to_test:
            with self.subTest(field_removed=field_to_remove):
                stripped_provs = tuple(fp for fp in opp.field_provenances if fp.field_name != field_to_remove)
                mutated_opp = dataclasses.replace(opp, field_provenances=stripped_provs)
                val_res, val_err = validate_opportunity_provenance(mutated_opp)
                self.assertFalse(val_res, f"Expected validation to fail when '{field_to_remove}' provenance is missing")
                self.assertIn("Missing provenance", val_err)

    def test_compensation_atomic_subfield_provenance_regressions(self) -> None:
        """Generic 'compensation' provenance cannot substitute for missing atomic subfield provenance."""
        comp = Compensation(
            min_amount=120000.0,
            max_amount=180000.0,
            currency="USD",
            interval=CompensationInterval.YEARLY,
        )
        base_provs = (
            FieldProvenance("track", "full_time", "employment", "rule_derivation", "p:0", "chk1", "r1"),
            FieldProvenance("organization", "Acme", "Acme", "raw_extraction", "p:1", "chk1", "r1"),
            FieldProvenance("title", "Engineer", "Engineer", "raw_extraction", "p:2", "chk1", "r1"),
            FieldProvenance("description", "Desc", "Desc", "raw_extraction", "p:3", "chk1", "r1"),
            FieldProvenance("compensation", "$120k-$180k USD", "120000-180000 USD", "rule_derivation", "p:4", "chk1", "r1"),
            FieldProvenance("compensation.min_amount", "120000", "120000", "rule_derivation", "p:4", "chk1", "r1"),
            FieldProvenance("compensation.max_amount", "180000", "180000", "rule_derivation", "p:4", "chk1", "r1"),
            FieldProvenance("compensation.currency", "USD", "USD", "rule_derivation", "p:4", "chk1", "r1"),
            FieldProvenance("compensation.interval", "yearly", "yearly", "rule_derivation", "p:4", "chk1", "r1"),
        )
        opp = Opportunity(
            id="test:1",
            track=Track.EMPLOYMENT,
            source="test",
            source_url="https://example.com",
            source_id="1",
            organization="Acme",
            title="Engineer",
            description="Desc",
            compensation=comp,
            field_provenances=base_provs,
        )
        valid, err = validate_opportunity_provenance(opp)
        self.assertTrue(valid, err)

        # 1. Remove ONLY compensation.currency while generic compensation remains
        no_curr_provs = tuple(fp for fp in base_provs if fp.field_name != "compensation.currency")
        no_curr_opp = dataclasses.replace(opp, field_provenances=no_curr_provs)
        v_res, v_err = validate_opportunity_provenance(no_curr_opp)
        self.assertFalse(v_res)
        self.assertIn("compensation.currency", v_err)

        # 2. Remove ONLY compensation.min_amount
        no_min_provs = tuple(fp for fp in base_provs if fp.field_name != "compensation.min_amount")
        no_min_opp = dataclasses.replace(opp, field_provenances=no_min_provs)
        v_res, v_err = validate_opportunity_provenance(no_min_opp)
        self.assertFalse(v_res)
        self.assertIn("compensation.min_amount", v_err)

        # 3. Remove ONLY compensation.max_amount
        no_max_provs = tuple(fp for fp in base_provs if fp.field_name != "compensation.max_amount")
        no_max_opp = dataclasses.replace(opp, field_provenances=no_max_provs)
        v_res, v_err = validate_opportunity_provenance(no_max_opp)
        self.assertFalse(v_res)
        self.assertIn("compensation.max_amount", v_err)

        # 4. Remove ONLY compensation.interval
        no_int_provs = tuple(fp for fp in base_provs if fp.field_name != "compensation.interval")
        no_int_opp = dataclasses.replace(opp, field_provenances=no_int_provs)
        v_res, v_err = validate_opportunity_provenance(no_int_opp)
        self.assertFalse(v_res)
        self.assertIn("compensation.interval", v_err)

    def test_procurement_provenance_individual_removal_regressions(self) -> None:
        """Removing CPV, buyer, or deadline provenance on procurement notice MUST fail."""
        payload = """{
            "notices": [
                {
                    "id": "UNGM-001",
                    "title": "Consulting Services for Enterprise Architecture",
                    "agency": "UNDP",
                    "country": "Egypt",
                    "type": "RFP",
                    "deadline": "2026-10-01",
                    "posted_date": "2026-08-20",
                    "unspsc": ["80101500"]
                }
            ]
        }"""
        adapter = UNGMAdapter()
        result = adapter.parse_payload(payload)
        self.assertEqual(len(result.opportunities), 1)
        opp = result.opportunities[0]

        # Valid baseline
        valid, err = validate_opportunity_provenance(opp)
        self.assertTrue(valid, err)

        # Remove buyer_name / organization
        no_buyer = dataclasses.replace(opp, field_provenances=tuple(fp for fp in opp.field_provenances if fp.field_name not in {"buyer_name", "organization"}))
        v_res, v_err = validate_opportunity_provenance(no_buyer)
        self.assertFalse(v_res)
        self.assertIn("Missing provenance", v_err)

        # Remove deadline / closing_date
        no_deadline = dataclasses.replace(opp, field_provenances=tuple(fp for fp in opp.field_provenances if fp.field_name not in {"deadline", "closing_date"}))
        v_res, v_err = validate_opportunity_provenance(no_deadline)
        self.assertFalse(v_res)
        self.assertIn("Missing provenance", v_err)

        # Remove unspsc_codes
        no_unspsc = dataclasses.replace(opp, field_provenances=tuple(fp for fp in opp.field_provenances if fp.field_name != "unspsc_codes"))
        v_res, v_err = validate_opportunity_provenance(no_unspsc)
        self.assertFalse(v_res)
        self.assertIn("Missing provenance", v_err)


if __name__ == "__main__":
    unittest.main()
