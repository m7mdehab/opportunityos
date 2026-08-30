"""Tests for ApplicationAnswerEngine with strict zero-fabrication and explicit compensation authority."""
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
            default_hourly_rate=100.0,
            default_sponsorship_required=False,
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

    def test_unconfigured_sponsorship_policy_fails_closed_to_pause(self) -> None:
        empty_policy = TailoringPolicy()  # default_sponsorship_required is None
        engine = ApplicationAnswerEngine(TruthGraph(), empty_policy)
        field = DetectedFormField(
            field_id="sponsorship", name="sponsorship", field_type="radio",
            label="Will you now or in the future require visa sponsorship?",
            normalized_label="will you require sponsorship",
            ontology_type=FieldOntologyType.SPONSORSHIP,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unconfigured_sponsorship_policy")

    def test_explicit_sponsorship_policy_yields_exact_yellow_answer(self) -> None:
        policy = TailoringPolicy(default_sponsorship_required=False)
        engine = ApplicationAnswerEngine(TruthGraph(), policy)
        field = DetectedFormField(
            field_id="sponsorship", name="sponsorship", field_type="radio",
            label="Will you now or in the future require visa sponsorship?",
            normalized_label="will you require sponsorship",
            ontology_type=FieldOntologyType.SPONSORSHIP,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertEqual(ans.answer, "No")
        self.assertEqual(ans.answer_class, AnswerClass.YELLOW)
        self.assertEqual(ans.policy_source, f"TailoringPolicy.{policy.version}.default_sponsorship_required")

    def test_unconfigured_notice_period_policy_fails_closed_to_pause(self) -> None:
        empty_policy = TailoringPolicy()  # default_notice_period_days is None
        engine = ApplicationAnswerEngine(TruthGraph(), empty_policy)
        field = DetectedFormField(
            field_id="notice", name="notice", field_type="text",
            label="Notice Period", normalized_label="notice period",
            ontology_type=FieldOntologyType.AVAILABILITY,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unconfigured_notice_period_policy")

    def test_explicit_notice_period_policy_yields_exact_yellow_answer(self) -> None:
        policy = TailoringPolicy(default_notice_period_days=14)
        engine = ApplicationAnswerEngine(TruthGraph(), policy)
        field = DetectedFormField(
            field_id="notice", name="notice", field_type="text",
            label="Notice Period", normalized_label="notice period",
            ontology_type=FieldOntologyType.AVAILABILITY,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertEqual(ans.answer, "14 days")
        self.assertEqual(ans.answer_class, AnswerClass.YELLOW)
        self.assertEqual(ans.policy_source, f"TailoringPolicy.{policy.version}.default_notice_period_days")

    def test_compensation_hourly_rate_without_explicit_currency_fails_closed_to_pause(self) -> None:
        policy = TailoringPolicy(default_hourly_rate=120.0, default_currency=None)
        engine = ApplicationAnswerEngine(TruthGraph(), policy)
        field = DetectedFormField(
            field_id="rate", name="rate", field_type="text",
            label="Desired Compensation / Rate", normalized_label="desired compensation",
            ontology_type=FieldOntologyType.COMPENSATION,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unconfigured_compensation_policy")

    def test_compensation_daily_rate_without_explicit_currency_fails_closed_to_pause(self) -> None:
        policy = TailoringPolicy(default_daily_rate=900.0, default_currency=None)
        engine = ApplicationAnswerEngine(TruthGraph(), policy)
        field = DetectedFormField(
            field_id="rate", name="rate", field_type="text",
            label="Desired Compensation / Rate", normalized_label="desired compensation",
            ontology_type=FieldOntologyType.COMPENSATION,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unconfigured_compensation_policy")

    def test_compensation_empty_policy_fails_closed_to_pause(self) -> None:
        empty_policy = TailoringPolicy()
        engine = ApplicationAnswerEngine(TruthGraph(), empty_policy)
        field = DetectedFormField(
            field_id="rate", name="rate", field_type="text",
            label="Desired Compensation", normalized_label="desired compensation",
            ontology_type=FieldOntologyType.COMPENSATION,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertIsNone(ans.answer)
        self.assertEqual(ans.answer_class, AnswerClass.RED)
        self.assertEqual(ans.disposition, "pause")
        self.assertEqual(ans.answer_source, "unconfigured_compensation_policy")

    def test_compensation_explicit_hourly_rate_and_currency_yields_exact_yellow_answer(self) -> None:
        policy = TailoringPolicy(default_hourly_rate=120.0, default_currency="USD")
        engine = ApplicationAnswerEngine(TruthGraph(), policy)
        field = DetectedFormField(
            field_id="rate", name="rate", field_type="text",
            label="Desired Compensation", normalized_label="desired compensation",
            ontology_type=FieldOntologyType.COMPENSATION,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertEqual(ans.answer, "USD 120.0/hr")
        self.assertEqual(ans.answer_class, AnswerClass.YELLOW)
        self.assertEqual(ans.policy_source, f"TailoringPolicy.{policy.version}.default_hourly_rate")

    def test_compensation_explicit_daily_rate_and_currency_yields_exact_yellow_answer(self) -> None:
        policy = TailoringPolicy(default_daily_rate=850.0, default_currency="EUR")
        engine = ApplicationAnswerEngine(TruthGraph(), policy)
        field = DetectedFormField(
            field_id="rate", name="rate", field_type="text",
            label="Desired Compensation", normalized_label="desired compensation",
            ontology_type=FieldOntologyType.COMPENSATION,
        )
        ans = engine.answer_field(field, self.opportunity)
        self.assertEqual(ans.answer, "EUR 850.0/day")
        self.assertEqual(ans.answer_class, AnswerClass.YELLOW)
        self.assertEqual(ans.policy_source, f"TailoringPolicy.{policy.version}.default_daily_rate")

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
