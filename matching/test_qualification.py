"""Tests for Hard-Constraint Qualification Engine."""
from __future__ import annotations

import unittest

from opportunity.models import (
    EmploymentType,
    GeographicEligibility,
    Opportunity,
    ProcurementMetadata,
    RemotePolicy,
    SeniorityLevel,
    SourceProvenance,
    Track,
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
    ev_resp1 = EvidenceRecord(
        id="ev-resp1",
        content="Build distributed systems handling millions of requests per day",
        source="manual",
        locator="employment.responsibility",
        metadata={"responsibility": "Build distributed systems"},
    )
    ev_resp2 = EvidenceRecord(
        id="ev-resp2",
        content="Maintain cloud infrastructure supporting the platform's uptime",
        source="manual",
        locator="employment.responsibility",
        metadata={"responsibility": "Maintain cloud infrastructure"},
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
        value="Build distributed systems",
        evidence_ids=("ev-resp1",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    g.add_assertion(AtomicAssertion(
        id="a-resp2",
        subject_id="founder",
        predicate="employment.responsibility",
        value="Maintain cloud infrastructure",
        evidence_ids=("ev-resp2",),
        verification_status=VerificationStatus.VERIFIED,
    ))
    return g


def create_test_opportunity(
    opp_id: str = "opp-1",
    track: Track = Track.EMPLOYMENT,
    title: str = "Staff Backend Engineer",
    geo_status: str = "eligible",
    remote_policy: RemotePolicy = RemotePolicy.REMOTE,
    location_raw: str = "Remote, Worldwide",
    description: str = "Build distributed systems with Python.",
    skills: tuple[str, ...] = ("Python", "Go"),
    responsibilities: tuple[str, ...] = ("Build distributed systems", "Maintain cloud infrastructure"),
    procurement_metadata: ProcurementMetadata | None = None,
    compensation: Any = None,
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
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
        remote_policy=remote_policy,
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
        opp = create_test_opportunity()
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.QUALIFIED)
        self.assertTrue(all(c.passed is True for c in constraints))

    def test_ineligible_geographically_excluded(self) -> None:
        opp = create_test_opportunity(geo_status="excluded")
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.INELIGIBLE)
        failed = [c for c in constraints if c.constraint_name == "geographic_eligibility"]
        self.assertTrue(len(failed) > 0)
        self.assertTrue(failed[0].is_hard_failure)

    def test_ineligible_mandatory_onsite_foreign_location(self) -> None:
        opp = create_test_opportunity(
            remote_policy=RemotePolicy.ON_SITE,
            location_raw="Berlin, Germany",
        )
        decision, constraints = self.engine.evaluate(opp, self.truth_graph)
        self.assertEqual(decision, QualificationDecision.INELIGIBLE)
        failed = [c for c in constraints if c.constraint_name == "work_mode_onsite"]
        self.assertTrue(len(failed) > 0)
        self.assertTrue(failed[0].is_hard_failure)

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


if __name__ == "__main__":
    unittest.main()
