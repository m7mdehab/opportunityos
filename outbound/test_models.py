"""Unit tests for outbound data models."""
import unittest
from matching.models import QualificationDecision
from outbound.models import (
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    ConfirmationEvidence,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    GraduationRecord,
    PreSubmitManifest,
    SourceActionPolicy,
)


class TestOutboundModels(unittest.TestCase):
    def test_application_answer_validations(self) -> None:
        # Green requires assertions and truth_graph source
        with self.assertRaises(ValueError):
            ApplicationAnswer(
                opportunity_id="opp-1",
                opportunity_content_hash="h1",
                action_id="act-1",
                field_type=FieldOntologyType.IDENTITY,
                original_label="Full Name",
                normalized_question="full name",
                answer="Founder Name",
                answer_class=AnswerClass.GREEN,
                answer_source="",
                assertion_ids=(),
            )

        # Valid Green answer
        ans = ApplicationAnswer(
            opportunity_id="opp-1",
            opportunity_content_hash="h1",
            action_id="act-1",
            field_type=FieldOntologyType.IDENTITY,
            original_label="Full Name",
            normalized_question="full name",
            answer="Founder Name",
            answer_class=AnswerClass.GREEN,
            answer_source="truth_graph:a-1",
            assertion_ids=("a-1",),
        )
        self.assertEqual(ans.answer, "Founder Name")

    def test_presubmit_manifest_hash(self) -> None:
        manifest = PreSubmitManifest(
            workspace="default",
            candidate_id="founder",
            opportunity_id="opp-1",
            opportunity_content_hash="h1",
            action_type="application",
            adapter_name="greenhouse",
            adapter_version="1.0.0",
            graduation_record_version="1.0.0",
            source_policy_version="1.0.0",
            artifact_ids=("art-1",),
            artifact_hashes=("hash-1",),
            answers=(),
            answers_hash="ans_hash",
            qualification_decision=QualificationDecision.QUALIFIED,
            unresolved_mandatory_count=0,
            red_answers_count=0,
            idempotency_key="key-1",
            compiled_at="2026-08-30T00:00:00Z",
        )
        self.assertTrue(len(manifest.manifest_hash) == 64)


if __name__ == "__main__":
    unittest.main()
