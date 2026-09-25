"""Tests for Hard-Constraint Qualification Engine."""
from __future__ import annotations

import unittest

from opportunity.models import (
    EmploymentType,
    GeographicEligibility,
    Opportunity,
    ProcurementMetadata,
    RemotePolicy,
    RemoteScope,
    SeniorityLevel,
    SourceProvenance,
    Track,
    WorkMode,
)
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, Modality, Polarity, VerificationStatus
from matching.models import QualificationDecision
from matching.qualification import QualificationEngine


def create_test_graph() -> TruthGraph:
    g = TruthGraph()
    ev_title = EvidenceRecord(
        id="ev-title",
        content="Senior Distributed Systems Architect",
        source="manual",
        locator="employment.title",
        metadata={"title": "Senior Distributed Systems Architect"},
    )
    ev_py = EvidenceRecord(
        id="ev-py",
        content="Python",
        source="manual",
        locator="skill",
        metadata={"name": "Python"},
    )
    ev_go = EvidenceRecord(
        id="ev-go",
        content="Go",
        source="manual",
        locator="skill",
        metadata={"name": "Go"},
    )
    ev_auth = EvidenceRecord(
        id="ev-auth",
        content="Egypt",
        source="manual",
        locator="work_authorization.jurisdiction",
        metadata={"jurisdiction": "Egypt"},
    )
    ev_en = EvidenceRecord(
        id="ev-en",
        content="English",
        source="manual",
        locator="language.language",
        metadata={"language": "English"},
    )
    ev_ar = EvidenceRecord(
        id="ev-ar",
        content="Arabic",
        source="manual",
        locator="language.language",
        metadata={"language": "Arabic"},
    )
    ev_srv = EvidenceRecord(
        id="ev-srv",
        content="Cloud Architecture Advisory",
        source="manual",
        locator="service.name",
        metadata={"name": "Cloud Architecture Advisory"},
    )
    ev_res = EvidenceRecord(
        id="ev-res",
        content="Egypt",
        source="manual",
        locator="residence.country",
        metadata={"country": "Egypt"},
    )
    ev_auth_de_neg = EvidenceRecord(
        id="ev-auth-de-neg",
        content="Not authorized to work in Germany",
        source="manual",
        locator="work_authorization.jurisdiction",
        metadata={"jurisdiction": "Germany"},
    )
    # Independent, plausible CV-style bullets for a senior distributed systems
    # architect. Deliberately NOT copied from create_test_opportunity's default
    # `responsibilities` text — they overlap it only through genuine shared
    # engineering vocabulary ("distributed", "systems", "cloud",
    # "infrastructure"), the same fuzzy keyword-overlap path scorer.py already
    # uses for a real founder pack, not an exact-string echo chosen to force
    # the match.
    ev_resp1 = EvidenceRecord(
        id="ev-resp1",
        content="Architected and operated large-scale distributed systems handling real-time event streams",
        source="manual",
        locator="employment.responsibility",
        metadata={"responsibility": "Architected and operated large-scale distributed systems handling real-time event streams"},
    )
    ev_resp2 = EvidenceRecord(
        id="ev-resp2",
        content="Owned production readiness and infrastructure reliability for a multi-region cloud platform",
        source="manual",
        locator="employment.responsibility",
        metadata={"responsibility": "Owned production readiness and infrastructure reliability for a multi-region cloud platform"},
    )
    for ev in (ev_title, ev_py, ev_go, ev_auth, ev_en, ev_ar, ev_srv, ev_res, ev_auth_de_neg, ev_resp1, ev_resp2):
        g.add_evidence(ev)

    g.add_assertion(AtomicAssertion(
        id="a-residence",
        subject_id="founder",
        predicate="residence.country",
        value="Egypt",
        evidence_ids=("ev-res",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-title",
        subject_id="founder",
        predicate="employment.title",
        value="Senior Distributed Systems Architect",
        evidence_ids=("ev-title",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-skill-py",
        subject_id="founder",
        predicate="skill.name",
        value="Python",
        evidence_ids=("ev-py",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-skill-go",
        subject_id="founder",
        predicate="skill.name",
        value="Go",
        evidence_ids=("ev-go",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-auth",
        subject_id="founder",
        predicate="work_authorization.jurisdiction",
        value="Egypt",
        evidence_ids=("ev-auth",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-auth-de-neg",
        subject_id="founder",
        predicate="work_authorization.jurisdiction",
        value="Germany",
        evidence_ids=("ev-auth-de-neg",),
        verification_status=VerificationStatus.VERIFIED,
        polarity=Polarity.NEGATIVE,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-lang-en",
        subject_id="founder",
        predicate="language.language",
        value="English",
        evidence_ids=("ev-en",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-lang-ar",
        subject_id="founder",
        predicate="language.language",
        value="Arabic",
        evidence_ids=("ev-ar",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-service",
        subject_id="founder",
        predicate="service.name",
        value="Cloud Architecture Advisory",
        evidence_ids=("ev-srv",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-resp1",
        subject_id="founder",
        predicate="employment.responsibility",
        value="Architected and operated large-scale distributed systems handling real-time event streams",
        evidence_ids=("ev-resp1",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-resp2",
        subject_id="founder",
        predicate="employment.responsibility",
        value="Owned production readiness and infrastructure reliability for a multi-region cloud platform",
        evidence_ids=("ev-resp2",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    return g


def create_test_opportunity(
    opp_id: str = "opp-1",
    track: Track = Track.EMPLOYMENT,
    title: str = "Staff Backend Engineer",
    geo_status: str = "eligible",
    work_mode: WorkMode = WorkMode.REMOTE,
    location_raw: str = "Remote, Worldwide",
    description: str = "Build distributed systems with Python.",
    skills: tuple[str, ...] = ("Python", "Go"),
    responsibilities: tuple[str, ...] = ("Build distributed systems", "Maintain cloud infrastructure"),
    procurement_metadata: ProcurementMetadata | None = None,
    compensation: Any = None,
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
    location_country: str = "",
    remote_scope: RemoteScope = RemoteScope.UNSPECIFIED,
    remote_scope_regions: tuple[str, ...] = (),
) -> Opportunity:
    prov = SourceProvenance(
        source_id="greenhouse:cloudflare",
        source_url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/101",
        feed_url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true",
        fetched_at="2026-08-30T00:00:00Z",
        payload_checksum="sha256fake",
    )
    geo = GeographicEligibility(
        status=geo_status,
        reason="Worldwide applicant allowed",
    )
    return Opportunity(
        id=opp_id,
        track=track,
        source="greenhouse:cloudflare",
        source_url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/101",
        source_id="101",
        organization="Cloudflare",
        title=title,
        description=description,
        responsibilities=responsibilities,
        requirements=("5+ years Python", "Go proficiency"),
        skills=skills,
        seniority=SeniorityLevel.SENIOR,
        employment_type=employment_type,
        location_raw=location_raw,
        work_mode=work_mode,
        location_country=location_country,
        remote_scope=remote_scope,
        remote_scope_regions=remote_scope_regions,
        geographic_eligibility=geo,
        compensation=compensation,
        posted_date="2026-08-15",
        closing_date=None,
        procurement_metadata=procurement_metadata,
        raw_provenance=prov,
        record_checksum="sha256fake",
        raw_record_pointer="feed:jobs[0]",
        field_provenances=(),
    )


class TestQualificationEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = QualificationEngine()
        self.truth_graph = create_test_graph()

    def test_qualified_remote_opportunity(self) -> None:
        opp = create_test_opportunity(remote_scope=RemoteScope.WORLDWIDE)
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.QUALIFIED)
        self.assertTrue(all(c.passed is True for c in constraints))

    def test_status_only_legacy_geography_remains_uncertain(self) -> None:
        for status in ("excluded", "eligible", "ineligible"):
            with self.subTest(status=status):
                opp = create_test_opportunity(geo_status=status)
                decision, constraints = self.engine.evaluate(opp, self.truth_graph)
                geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
                self.assertEqual(QualificationDecision.UNCERTAIN, decision)
                self.assertEqual(1, len(geo))
                self.assertIsNone(geo[0].passed)
                self.assertFalse(geo[0].is_hard_failure)

    def test_different_onsite_location_does_not_assume_relocation_refusal(self) -> None:
        opp = create_test_opportunity(
            geo_status="excluded",
            work_mode=WorkMode.ONSITE,
            location_raw="Berlin, Germany",
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        onsite = [c for c in constraints if c.constraint_name == "work_mode_onsite"]
        self.assertEqual(QualificationDecision.UNCERTAIN, decision)
        self.assertEqual(1, len(onsite))
        self.assertIsNone(onsite[0].passed)
        self.assertFalse(onsite[0].is_hard_failure)

    def test_ineligible_explicit_foreign_work_auth(self) -> None:
        opp = create_test_opportunity(
            description="Must have valid work authorization in Germany without sponsorship.",
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.INELIGIBLE)
        failed = [c for c in constraints if c.constraint_name == "work_authorization"]
        self.assertTrue(len(failed) > 0)
        self.assertTrue(failed[0].is_hard_failure)

    def test_uncertain_on_missing_opportunity_metadata(self) -> None:
        opp = create_test_opportunity(geo_status="unclear")
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.UNCERTAIN)

    def test_unknown_is_not_false_authority_rule(self) -> None:
        # Opportunity without explicit language or work authorization statements evaluates cleanly without false hard failures
        opp = create_test_opportunity(
            description="Software Engineer role working on backend microservices.",
            remote_scope=RemoteScope.WORLDWIDE,
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.QUALIFIED)

    def test_uncertain_on_unstated_work_authorization(self) -> None:
        # France auth required; founder graph has no assertion about France -> UNCERTAIN, not INELIGIBLE
        opp = create_test_opportunity(
            description="Must have valid work authorization in France without sponsorship.",
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.UNCERTAIN)
        uncertain = [c for c in constraints if c.constraint_name == "work_authorization"]
        self.assertTrue(len(uncertain) > 0)
        self.assertIsNone(uncertain[0].passed)
        self.assertFalse(uncertain[0].is_hard_failure)

    # --- BRIEF-FR-006 A1: geographic eligibility resolves on country OR remote_scope ---

    def test_worldwide_remote_scope_resolves_eligible(self) -> None:
        opp = create_test_opportunity(geo_status="unclear", remote_scope=RemoteScope.WORLDWIDE)
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(1, len(geo))
        self.assertTrue(geo[0].passed)
        self.assertFalse(geo[0].is_hard_failure)

    def test_structured_worldwide_remote_overrides_legacy_exclusion_and_employer_country(self) -> None:
        opp = create_test_opportunity(
            geo_status="excluded",
            work_mode=WorkMode.REMOTE,
            location_country="DE",
            remote_scope=RemoteScope.WORLDWIDE,
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(QualificationDecision.QUALIFIED, decision)
        self.assertEqual(1, len(geo))
        self.assertTrue(geo[0].passed)
        self.assertFalse(geo[0].is_hard_failure)

    def test_same_verified_residence_location_onsite_is_consistent(self) -> None:
        residence = next(
            str(assertion.value)
            for assertion in self.truth_graph.assertions.values()
            if assertion.predicate == "residence.country"
            and assertion.verification_status == VerificationStatus.VERIFIED
        )
        opp = create_test_opportunity(
            geo_status="unclear",
            work_mode=WorkMode.ONSITE,
            location_raw=residence,
        )
        _, constraints = self.engine.evaluate(opp, self.truth_graph)
        onsite = [c for c in constraints if c.constraint_name == "work_mode_onsite"]
        self.assertEqual(1, len(onsite))
        self.assertTrue(onsite[0].passed)
        self.assertFalse(onsite[0].is_hard_failure)

    def test_region_restricted_excluding_egypt_is_labelled_not_hidden(self) -> None:
        opp = create_test_opportunity(
            geo_status="unclear",
            remote_scope=RemoteScope.REGION_RESTRICTED,
            remote_scope_regions=("US",),
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(1, len(geo))
        self.assertIsNone(geo[0].passed)
        self.assertFalse(geo[0].is_hard_failure, "region-restricted-excluding-EG must never be a hard failure")
        self.assertIn("remote but region-restricted", geo[0].reason)
        self.assertNotEqual(QualificationDecision.INELIGIBLE, decision)

    def test_region_restricted_including_egypt_resolves_eligible(self) -> None:
        opp = create_test_opportunity(
            geo_status="unclear",
            remote_scope=RemoteScope.REGION_RESTRICTED,
            remote_scope_regions=("EG", "SA"),
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(1, len(geo))
        self.assertTrue(geo[0].passed)

    def test_location_country_matching_founder_authorization_resolves_eligible(self) -> None:
        # Truth graph has a verified work_authorization.jurisdiction="Egypt" assertion.
        opp = create_test_opportunity(geo_status="unclear", location_country="EG")
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(1, len(geo))
        self.assertTrue(geo[0].passed)

    def test_location_country_with_verified_negative_authorization_physical_presence_is_ineligible(self) -> None:
        # Truth graph has a verified NEGATIVE work_authorization.jurisdiction="Germany".
        # Structured onsite or hybrid presence in that jurisdiction -> hard failure.
        for work_mode in (WorkMode.ONSITE, WorkMode.HYBRID):
            with self.subTest(work_mode=work_mode.value):
                opp = create_test_opportunity(
                    geo_status="unclear",
                    location_country="DE",
                    work_mode=work_mode,
                    remote_scope=RemoteScope.WORLDWIDE,
                )
                decision, constraints = self.engine.evaluate(opp, self.truth_graph)
                self.assertEqual(QualificationDecision.INELIGIBLE, decision)
                geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
                self.assertEqual(1, len(geo))
                self.assertFalse(geo[0].passed)
                self.assertTrue(geo[0].is_hard_failure)

    def test_location_country_with_verified_negative_authorization_remote_is_labelled_not_hard_failure(self) -> None:
        # Same verified NEGATIVE work_authorization.jurisdiction="Germany", but the role
        # is remote -- no default-hide: labelled as a gap, never a hard failure.
        opp = create_test_opportunity(geo_status="unclear", location_country="DE", work_mode=WorkMode.REMOTE)
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertNotEqual(QualificationDecision.INELIGIBLE, decision)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(1, len(geo))
        self.assertIsNone(geo[0].passed)
        self.assertFalse(geo[0].is_hard_failure)
        self.assertIn("gap", geo[0].reason.casefold())

    def test_location_country_unasserted_stays_uncertain_not_ineligible(self) -> None:
        opp = create_test_opportunity(geo_status="unclear", location_country="FR")
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(QualificationDecision.UNCERTAIN, decision)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(1, len(geo))
        self.assertIsNone(geo[0].passed)
        self.assertFalse(geo[0].is_hard_failure)

    def test_neither_country_nor_remote_scope_remains_uncertain(self) -> None:
        # No location_country or remote_scope -> legacy status is insufficient to resolve.
        opp = create_test_opportunity(geo_status="unclear")
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(QualificationDecision.UNCERTAIN, decision)
        geo = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertEqual(1, len(geo))
        self.assertIsNone(geo[0].passed)
        self.assertIn("unresolved", geo[0].reason.casefold())


if __name__ == "__main__":
    unittest.main()
