"""Unit tests for Canonical Field Ontology and Classification."""
from __future__ import annotations

import unittest
from outbound.models import AnswerClass, FieldOntologyType
from outbound.ontology import FieldClassifier


class TestFieldOntology(unittest.TestCase):
    def test_classify_identity(self) -> None:
        f1 = FieldClassifier.classify_field("First Name", name="first_name")
        self.assertEqual(f1.ontology_type, FieldOntologyType.IDENTITY)
        self.assertEqual(f1.sensitivity_class, AnswerClass.GREEN)

        f2 = FieldClassifier.classify_field("Legal Family Name", name="last_name")
        self.assertEqual(f2.ontology_type, FieldOntologyType.IDENTITY)
        self.assertEqual(f2.sensitivity_class, AnswerClass.GREEN)

    def test_classify_contact_and_links(self) -> None:
        f1 = FieldClassifier.classify_field("Email Address", name="email")
        self.assertEqual(f1.ontology_type, FieldOntologyType.CONTACT)

        f2 = FieldClassifier.classify_field("LinkedIn Profile URL", name="linkedin")
        self.assertEqual(f2.ontology_type, FieldOntologyType.LINKS)

    def test_classify_work_auth_and_sponsorship(self) -> None:
        f1 = FieldClassifier.classify_field("Are you legally authorized to work in the UK?", name="work_auth")
        self.assertEqual(f1.ontology_type, FieldOntologyType.WORK_AUTHORIZATION)
        self.assertEqual(f1.sensitivity_class, AnswerClass.YELLOW)

        f2 = FieldClassifier.classify_field("Will you require visa sponsorship now or in the future?", name="sponsorship")
        self.assertEqual(f2.ontology_type, FieldOntologyType.SPONSORSHIP)
        self.assertEqual(f2.sensitivity_class, AnswerClass.YELLOW)

    def test_classify_sensitive_and_unknown(self) -> None:
        f1 = FieldClassifier.classify_field("Do you have an active Top Secret Security Clearance?", name="clearance")
        self.assertEqual(f1.ontology_type, FieldOntologyType.SECURITY_CLEARANCE)
        self.assertEqual(f1.sensitivity_class, AnswerClass.RED)

        f2 = FieldClassifier.classify_field("Do you agree to the binding non-compete terms?", name="terms")
        self.assertEqual(f2.ontology_type, FieldOntologyType.LEGAL_DECLARATION)
        self.assertEqual(f2.sensitivity_class, AnswerClass.RED)

        f3 = FieldClassifier.classify_field("XYZ Custom Mystery Question 99", name="mystery")
        self.assertEqual(f3.ontology_type, FieldOntologyType.OTHER_UNKNOWN)
        self.assertEqual(f3.sensitivity_class, AnswerClass.RED)


if __name__ == "__main__":
    unittest.main()
