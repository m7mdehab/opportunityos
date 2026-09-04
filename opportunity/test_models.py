"""Unit Tests for Opportunity Data Models and Field Manifest."""
from __future__ import annotations

import dataclasses
import re
import unittest

from opportunity.adapters import (
    GreenhouseAdapter,
    HimalayasAdapter,
    LeverAdapter,
    RemoteOKAdapter,
    RemotiveAdapter,
    UNGMAdapter,
    WeWorkRemotelyAdapter,
)
from opportunity.fixtures import load_corpus
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

# Mirrors api/test_search.py's `_SINGLETON_ADAPTER_FACTORIES` / `_adapter_for_source_id`:
# maps a `CorpusFixture.source_id` back to the adapter class that would have
# produced it live, so re-parsing the committed corpus exercises the exact same
# `compute_deterministic_id` call sites production uses.
_SINGLETON_ADAPTER_FACTORIES = {
    "himalayas": HimalayasAdapter,
    "remotive": RemotiveAdapter,
    "remote_ok": RemoteOKAdapter,
    "we_work_remotely": WeWorkRemotelyAdapter,
}


def _adapter_for_source_id(source_id: str):
    if source_id in _SINGLETON_ADAPTER_FACTORIES:
        return _SINGLETON_ADAPTER_FACTORIES[source_id]()
    prefix, _, company = source_id.partition(":")
    if prefix == "greenhouse":
        return GreenhouseAdapter(company)
    if prefix == "lever":
        return LeverAdapter(company)
    raise ValueError(f"no adapter mapping for corpus source_id {source_id!r}")


def _corpus_opportunities() -> list[Opportunity]:
    """Re-parse every committed corpus fixture with its real adapter and
    return every resulting `Opportunity`, in corpus order."""
    opps: list[Opportunity] = []
    for fixture in load_corpus():
        adapter = _adapter_for_source_id(fixture.source_id)
        result = adapter.parse_payload(fixture.raw_body)
        opps.extend(result.opportunities)
    return opps


def _unbounded_candidate_id(source: str, remote_id: str) -> str:
    """Reproduces the pre-fix, unbounded `compute_deterministic_id` remote_id
    branch (`f"{source}:{clean_remote}"` with no length check), used only to
    report what the previous maximum id length was -- not exercised by
    production any more."""
    clean_remote = re.sub(r"[^\w\-.]", "_", remote_id.strip())
    return f"{source}:{clean_remote}"


def _minimal_opportunity_for_alias_test() -> Opportunity:
    return Opportunity(
        id="opp-alias-test",
        track=Track.EMPLOYMENT,
        source="himalayas",
        source_url="",
        source_id="",
        organization="Acme",
        title="Engineer",
        description="",
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
            # BRIEF-FR-006 A1: work_mode_source / location_country / location_city /
            # location_region / remote_scope / remote_scope_regions are structured
            # detail of the single "work_mode" material fact (Master decision #2:
            # work_mode_source is recorded as a FieldProvenance entry for the
            # "work_mode" field -- one entry, not one per sub-detail). "work_mode"
            # itself has a rule below and is not excluded here.
            "work_mode_source",
            "location_country",
            "location_city",
            "location_region",
            "remote_scope",
            "remote_scope_regions",
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

    def test_remote_policy_alias_agrees_with_work_mode_for_every_value(self) -> None:
        """BRIEF-FR-006 A1 Master decision #1: `remote_policy` is a read-only derived
        @property of `work_mode`, never an independent constructor input."""
        from opportunity.models import WorkMode

        expected = {
            WorkMode.REMOTE: RemotePolicy.REMOTE,
            WorkMode.HYBRID: RemotePolicy.HYBRID,
            WorkMode.ONSITE: RemotePolicy.ON_SITE,
            WorkMode.UNSPECIFIED: RemotePolicy.UNSPECIFIED,
        }
        for work_mode, remote_policy in expected.items():
            with self.subTest(work_mode=work_mode):
                opp = dataclasses.replace(
                    _minimal_opportunity_for_alias_test(), work_mode=work_mode
                )
                self.assertEqual(remote_policy, opp.remote_policy)
        # Not a constructor kwarg any more.
        self.assertNotIn("remote_policy", {f.name for f in dataclasses.fields(Opportunity)})

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
            "work_mode",
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


class TestComputeDeterministicIdVarcharBound(unittest.TestCase):
    """FR-004 erratum: `compute_deterministic_id` must bound the composed id at
    <= 64 chars (storage/models.py's `id = Column(String(64), primary_key=True)`)
    without changing any id that already fit, over the full 540-payload corpus."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus_opps = _corpus_opportunities()
        if len(cls.corpus_opps) < 500:
            raise AssertionError(
                "expected the real ~540-payload corpus (opportunity/fixtures/corpus/), "
                f"not a partial or absent one (got {len(cls.corpus_opps)})"
            )

    def test_every_corpus_id_fits_varchar64(self) -> None:
        ids = [opp.id for opp in self.corpus_opps]
        max_len = max(len(i) for i in ids)

        # Previous (pre-fix) max, reconstructed from the unbounded remote_id
        # branch this fix replaced, for the entries where it would have applied.
        previous_lengths = []
        for opp in self.corpus_opps:
            if opp.source_id and opp.source_id.strip():
                previous_lengths.append(len(_unbounded_candidate_id(opp.source, opp.source_id)))
            else:
                previous_lengths.append(len(opp.id))
        previous_max = max(previous_lengths)

        print(f"id-length check: {len(ids)} ids checked; current max={max_len}; previous max={previous_max}")
        self.assertTrue(all(len(i) <= 64 for i in ids), f"found id(s) longer than 64 chars; max={max_len}")

    def test_no_id_collisions_across_corpus(self) -> None:
        ids = [opp.id for opp in self.corpus_opps]
        duplicates = {i for i in ids if ids.count(i) > 1}
        print(f"collision check: {len(ids)} ids checked; {len(set(ids))} unique; duplicates={sorted(duplicates)}")
        self.assertEqual(len(ids), len(set(ids)), f"id collisions found: {sorted(duplicates)}")

    def test_fitting_id_unchanged_by_fix(self) -> None:
        # A short remote_id whose composed id already fits comfortably in 64 chars.
        source = "greenhouse:cloudflare"
        remote_id = "123456"
        title = "Software Engineer"
        organization = "Cloudflare"
        raw_pointer = "https://example.test/jobs/123456"

        expected = f"{source}:{remote_id}"
        self.assertLessEqual(len(expected), 64)

        actual = compute_deterministic_id(source, remote_id, title, organization, raw_pointer)
        self.assertEqual(actual, expected, "an id that already fit must be byte-identical after the fix")

    def test_long_remote_id_is_stable_across_calls(self) -> None:
        source = "we_work_remotely"
        remote_id = "smartsheet-director-of-business-planning-strategic-initiatives-and-operations"
        title = "Director of Business Planning, Strategic Initiatives and Operations"
        organization = "Smartsheet"
        raw_pointer = "https://weworkremotely.com/listings/smartsheet-director"

        first = compute_deterministic_id(source, remote_id, title, organization, raw_pointer)
        second = compute_deterministic_id(source, remote_id, title, organization, raw_pointer)

        self.assertEqual(first, second, "same inputs must yield the same id across calls")
        self.assertLessEqual(len(first), 64)
        # Confirms it actually took the bounded fallback path (i.e. this test
        # is exercising the fix, not accidentally already fitting).
        self.assertGreater(len(f"{source}:{remote_id}"), 64)


if __name__ == "__main__":
    unittest.main()
