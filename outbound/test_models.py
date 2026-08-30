"""Unit tests for Outbound Models and Invariants."""
from __future__ import annotations

import unittest
from matching.models import QualificationDecision
from opportunity.models import Track
from outbound.models import (
    ActionAuthorityDecision,
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    ConfirmationEvidence,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    OutboundActionRecord,
    PreSubmitManifest,
    SourceActionPolicy,
)


class TestOutboundModels(unittest.TestCase):
    def test_application_answer_validation(self) -> None:
        # Green answer with assertion IDs
        ans = ApplicationAnswer(
            opportunity_id="opp-1",
            opportunity_content_hash="hash-1",
            action_id="act-1",
            field_type=FieldOntologyType.IDENTITY,
            original_label="Full Name",
            normalized_question="full name",
            answer="Founder Candidate",
            answer_class=AnswerClass.GREEN,
            answer_source="truth_graph:a-1",
            assertion_ids=("a-1",),
        )
        self.assertEqual(ans.answer, "Founder Candidate")

        # Green answer without assertions raises error
        with self.assertRaises(ValueError):
            ApplicationAnswer(
                opportunity_id="opp-1",
                opportunity_content_hash="hash-1",
                action_id="act-1",
                field_type=FieldOntologyType.IDENTITY,
                original_label="Full Name",
                normalized_question="full name",
                answer="Founder Candidate",
                answer_class=AnswerClass.GREEN,
                answer_source="unbacked",
            )

        # Yellow answer without policy source raises error
        with self.assertRaises(ValueError):
            ApplicationAnswer(
                opportunity_id="opp-1",
                opportunity_content_hash="hash-1",
                action_id="act-1",
                field_type=FieldOntologyType.SPONSORSHIP,
                original_label="Sponsorship",
                normalized_question="sponsorship",
                answer="No",
                answer_class=AnswerClass.YELLOW,
                answer_source="unbacked",
            )

    def test_confirmation_evidence_checksum(self) -> None:
        ev = ConfirmationEvidence(
            confirmed=True,
            confirmation_text="Thank you for applying",
            application_id="app-1",
            receipt_reference="REC-999",
            final_url="https://example.com/thanks",
        )
        self.assertTrue(ev.evidence_checksum)
        self.assertEqual(len(ev.evidence_checksum), 64)

    def test_presubmit_manifest_hash(self) -> None:
        ans = ApplicationAnswer(
            opportunity_id="opp-1",
            opportunity_content_hash="hash-1",
            action_id="act-1",
            field_type=FieldOntologyType.IDENTITY,
            original_label="Full Name",
            normalized_question="full name",
            answer="Founder Candidate",
            answer_class=AnswerClass.GREEN,
            answer_source="truth_graph:a-1",
            assertion_ids=("a-1",),
        )
        manifest = PreSubmitManifest(
            workspace="ws-1",
            candidate_id="cand-1",
            opportunity_id="opp-1",
            opportunity_content_hash="hash-1",
            action_type="job_application",
            adapter_name="greenhouse",
            adapter_version="1.0.0",
            source_policy_version="1.0",
            artifact_ids=("art-1",),
            artifact_hashes=("hash-art-1",),
            answers=(ans,),
            answers_hash="ans-hash",
            qualification_decision=QualificationDecision.QUALIFIED,
            unresolved_questions_count=0,
            red_answers_count=0,
            idempotency_key="key-123",
        )
        self.assertTrue(manifest.manifest_hash)
        self.assertEqual(len(manifest.manifest_hash), 64)


if __name__ == "__main__":
    unittest.main()
