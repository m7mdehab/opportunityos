"""Tests for ApplicationAnswerEngine with strict zero-fabrication and open-world work authorization."""
import unittest
from matching.models import TailoringPolicy
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, Modality, Polarity, VerificationStatus
from outbound.answer_engine import ApplicationAnswerEngine
from outbound.models import AnswerClass, DetectedFormField, FieldOntologyType


class ApplicationAnswerEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.opportunity = Opportunity(
            id="opp-test-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/123",
            source_id="123",
            organization="Acme",
            title="Senior Data Engineer",
            description="Looking for Senior Data Engineer in Egypt.",
        )
        self.policy = TailoringPolicy(
            default_notice_period_days=30,
            default_currency="USD",
        )

    def test_empty_truth_graph_name_field_fails_closed_to_pause(self) -> None:
        tg = TruthGraph()
        engine = ApplicationAnswerEngine(tg, self.policy)
        field = DetectedFormField(
            field_id="first_name", name="first_name", field_type="text",
            label="First Name", normalized_label="first name",
            ontology_type=FieldOntologyType.IDENTITY,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unasserted_identity")

    def test_empty_truth_graph_email_field_fails_closed_to_pause(self) -> None:
        tg = TruthGraph()
        engine = ApplicationAnswerEngine(tg, self.policy)
        field = DetectedFormField(
            field_id="email", name="email", field_type="text",
            label="Email Address", normalized_label="email address",
            ontology_type=FieldOntologyType.CONTACT,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unasserted_email")

    def test_empty_truth_graph_phone_field_fails_closed_to_pause(self) -> None:
        tg = TruthGraph()
        engine = ApplicationAnswerEngine(tg, self.policy)
        field = DetectedFormField(
            field_id="phone", name="phone", field_type="text",
            label="Phone Number", normalized_label="phone number",
            ontology_type=FieldOntologyType.CONTACT,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unasserted_phone")

    def test_empty_truth_graph_linkedin_field_fails_closed_to_pause(self) -> None:
        tg = TruthGraph()
        engine = ApplicationAnswerEngine(tg, self.policy)
        field = DetectedFormField(
            field_id="linkedin", name="linkedin", field_type="text",
            label="LinkedIn URL", normalized_label="linkedin url",
            ontology_type=FieldOntologyType.LINKS,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unasserted_links")

    def test_work_authorization_egypt_positive_with_us_question_yields_pause_not_no(self) -> None:
        tg = TruthGraph()
        ev = EvidenceRecord(id="ev-auth-eg", source="passport", locator="p1", content="Authorized to work in Egypt indefinitely.")
        tg.add_evidence(ev)
        tg.add_assertion(AtomicAssertion(
            id="a-auth-eg", subject_id="founder", predicate="authorization.jurisdiction",
            value="Egypt", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-auth-eg",),
        ))

        engine = ApplicationAnswerEngine(tg, self.policy)
        field_us = DetectedFormField(
            field_id="auth_us", name="auth_us", field_type="radio",
            label="Are you authorized to work in the United States?",
            normalized_label="are you authorized to work in the united states",
            ontology_type=FieldOntologyType.WORK_AUTHORIZATION,
        )
        ans = engine.answer_field(field_us, self.opportunity)
        # UNKNOWN != FALSE: absent evidence for US is unknown, so it must NOT infer "No" or "Yes"
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unresolved_work_authorization")

    def test_work_authorization_explicit_verified_positive_yields_green_yes(self) -> None:
        tg = TruthGraph()
        ev = EvidenceRecord(id="ev-auth-us", source="passport", locator="p1", content="Authorized to work in United States.")
        tg.add_evidence(ev)
        tg.add_assertion(AtomicAssertion(
            id="a-auth-us", subject_id="founder", predicate="authorization.jurisdiction",
            value="United States", polarity=Polarity.POSITIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-auth-us",),
        ))

        engine = ApplicationAnswerEngine(tg, self.policy)
        field_us = DetectedFormField(
            field_id="auth_us", name="auth_us", field_type="radio",
            label="Are you authorized to work in the United States?",
            normalized_label="are you authorized to work in the united states",
            ontology_type=FieldOntologyType.WORK_AUTHORIZATION,
        )
        ans = engine.answer_field(field_us, self.opportunity)
        self.assertEqual(ans.answer, "Yes")
        self.assertEqual(ans.answer_class, AnswerClass.GREEN)
        self.assertEqual(ans.assertion_ids, ("a-auth-us",))

    def test_work_authorization_explicit_verified_negative_yields_green_no(self) -> None:
        tg = TruthGraph()
        ev = EvidenceRecord(id="ev-neg-us", source="visa_refusal", locator="p1", content="Not authorized to work in United States.")
        tg.add_evidence(ev)
        tg.add_assertion(AtomicAssertion(
            id="a-neg-us", subject_id="founder", predicate="authorization.jurisdiction",
            value="United States", polarity=Polarity.NEGATIVE, modality=Modality.DEFINITE,
            verification_status=VerificationStatus.VERIFIED, evidence_ids=("ev-neg-us",),
        ))

        engine = ApplicationAnswerEngine(tg, self.policy)
        field_us = DetectedFormField(
            field_id="auth_us", name="auth_us", field_type="radio",
            label="Are you authorized to work in the United States?",
            normalized_label="are you authorized to work in the united states",
            ontology_type=FieldOntologyType.WORK_AUTHORIZATION,
        )
        ans = engine.answer_field(field_us, self.opportunity)
        self.assertEqual(ans.answer, "No")
        self.assertEqual(ans.answer_class, AnswerClass.GREEN)
        self.assertEqual(ans.assertion_ids, ("a-neg-us",))


if __name__ == "__main__":
    unittest.main()
