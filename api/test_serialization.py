"""API serialization tests for the FR-008 hard-constraint evidence contract."""
from __future__ import annotations

import unittest

from api.serialization import serialize_constraint


class HardConstraintSerializationTests(unittest.TestCase):
    def test_serializes_new_evidence_fields_and_legacy_compatibility_fields(self) -> None:
        serialized = serialize_constraint({
            "constraint_name": "work_authorization",
            "passed": False,
            "reason": "Founder has verified negative authorization.",
            "required_field": "description",
            "founder_fact": "Verified lack of authorization.",
            "is_hard_failure": True,
            "provenance_pointer": "fixture:job.description",
            "constraint_type": "work_authorization",
            "job_evidence_text": "Must have valid work authorization in Germany.",
            "job_evidence_field": "description",
            "source_pointer": "fixture:job.description",
            "founder_side_evidence": "Verified lack of authorization.",
            "decision": False,
            "confidence": 0.97,
            "requirement_mandatory": True,
            "explanation": "Founder has verified negative authorization.",
        })

        self.assertEqual(serialized["outcome"], "FAIL")
        self.assertEqual(serialized["constraint_name"], "work_authorization")
        self.assertEqual(serialized["constraint_type"], "work_authorization")
        self.assertEqual(serialized["job_evidence_text"], "Must have valid work authorization in Germany.")
        self.assertEqual(serialized["job_evidence_field"], "description")
        self.assertEqual(serialized["source_pointer"], "fixture:job.description")
        self.assertEqual(serialized["founder_side_evidence"], "Verified lack of authorization.")
        self.assertIs(serialized["decision"], False)
        self.assertEqual(serialized["confidence"], 0.97)
        self.assertIs(serialized["requirement_mandatory"], True)
        self.assertEqual(serialized["explanation"], serialized["reason"])

    def test_old_persisted_shape_remains_readable_with_contract_defaults(self) -> None:
        serialized = serialize_constraint({
            "constraint_name": "geographic_eligibility",
            "passed": None,
            "reason": "Scope is unresolved.",
            "required_field": "remote_scope",
            "founder_fact": "Founder compatibility is unasserted.",
            "is_hard_failure": False,
            "provenance_pointer": "fixture:job.remote_scope",
        })

        self.assertEqual(serialized["outcome"], "UNKNOWN")
        self.assertEqual(serialized["constraint_type"], "geographic_eligibility")
        self.assertEqual(serialized["job_evidence_field"], "remote_scope")
        self.assertEqual(serialized["source_pointer"], "fixture:job.remote_scope")
        self.assertIsNone(serialized["decision"])
        self.assertIsNone(serialized["confidence"])
        self.assertIsNone(serialized["requirement_mandatory"])


if __name__ == "__main__":
    unittest.main()
