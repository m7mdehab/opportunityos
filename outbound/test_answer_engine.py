"""Unit tests for Application Answer Engine and Provenance."""
from __future__ import annotations

import unittest
from matching.models import TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity, Track
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, EvidenceRecord, Modality, VerificationStatus
from outbound.answer_engine import ApplicationAnswerEngine
from outbound.models import AnswerClass, FieldOntologyType
from outbound.ontology import FieldClassifier


class TestApplicationAnswerEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.tg = TruthGraph()
        ev = EvidenceRecord(
            id="ev-1", source="document", locator="cv.pdf",
            content="Mohamed Ehab is a Data Engineer residing in Egypt with email mohamed@example.com."
        )
        self.tg.add_evidence(ev)
        self.tg.add_assertion(AtomicAssertion(
            id="a-name",
            subject_id="founder",
            predicate="identity.name",
            value="Mohamed Ehab",
            evidence_ids=("ev-1",),
            verification_status=VerificationStatus.VERIFIED,
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-email",
            subject_id="founder",
            predicate="identity.email",
            value="mohamed@example.com",
            evidence_ids=("ev-1",),
            verification_status=VerificationStatus.VERIFIED,
        ))
        self.tg.add_assertion(AtomicAssertion(
            id="a-auth",
            subject_id="founder",
            predicate="authorization.jurisdiction",
            value="Egypt",
            evidence_ids=("ev-1",),
            verification_status=VerificationStatus.VERIFIED,
        ))
        self.policy = TailoringPolicy(
            default_notice_period_days=30,
            min_target_compensation=120000.0,
        )
        self.engine = ApplicationAnswerEngine(self.tg, self.policy)
        self.opp = Opportunity(
            id="opp-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            source_url="https://example.com",
            source_id="1",
            organization="Tech Corp",
            title="Data Engineer",
            description="Engineering role.",
            content_hash="hash-opp",
        )

    def test_green_factual_answers_have_provenance(self) -> None:
        f_name = FieldClassifier.classify_field("First Name", name="first_name")
        ans_name = self.engine.answer_field(f_name, self.opp)
        self.assertEqual(ans_name.answer, "Mohamed")
        self.assertEqual(ans_name.answer_class, AnswerClass.GREEN)
        self.assertIn("a-name", ans_name.assertion_ids)

        f_email = FieldClassifier.classify_field("Email Address", name="email")
        ans_email = self.engine.answer_field(f_email, self.opp)
        self.assertEqual(ans_email.answer, "mohamed@example.com")
        self.assertEqual(ans_email.answer_class, AnswerClass.GREEN)
        self.assertIn("a-email", ans_email.assertion_ids)

    def test_yellow_policy_answers_have_policy_source(self) -> None:
        f_notice = FieldClassifier.classify_field("Notice Period", name="notice")
        ans_notice = self.engine.answer_field(f_notice, self.opp)
        self.assertEqual(ans_notice.answer, "30 days")
        self.assertEqual(ans_notice.answer_class, AnswerClass.YELLOW)
        self.assertIn("default_notice_period_days", ans_notice.policy_source)

    def test_red_sensitive_answers_pause(self) -> None:
        f_clearance = FieldClassifier.classify_field("Do you hold an active Top Secret Security Clearance?", name="clearance")
        ans_clearance = self.engine.answer_field(f_clearance, self.opp)
        self.assertEqual(ans_clearance.answer_class, AnswerClass.RED)
        self.assertEqual(ans_clearance.disposition, "pause")


if __name__ == "__main__":
    unittest.main()
