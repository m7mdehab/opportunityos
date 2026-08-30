"""Unit tests for Idempotency Ledger and Duplicate Prevention."""
from __future__ import annotations

import unittest
from matching.models import QualificationDecision
from opportunity.models import Track
from outbound.idempotency import IdempotencyLedger
from outbound.models import ActionStatus, ConfirmationEvidence, ExecutionMode, OutboundActionRecord


class TestIdempotencyLedger(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = IdempotencyLedger()
        self.key = self.ledger.compute_idempotency_key("ws", "cand", "opp-1", "job_application")
        self.record = OutboundActionRecord(
            action_id="act-1",
            opportunity_id="opp-1",
            opportunity_content_hash="hash-1",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            adapter_name="greenhouse",
            adapter_version="1.0.0",
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED,
            match_score_snapshot=1.0,
            artifact_ids=("art-1",),
            artifact_hashes=("hash-art",),
            answer_manifest_hash="ans-hash",
            action_status=ActionStatus.PLANNED,
            idempotency_key=self.key,
            created_at="2026-08-30T00:00:00Z",
            updated_at="2026-08-30T00:00:00Z",
        )

    def test_record_intent_and_prevent_duplicate_submit(self) -> None:
        self.ledger.record_intent(self.record)
        self.assertFalse(self.ledger.is_duplicate("ws", "cand", "opp-1", "job_application"))

        # Transition to SUBMITTING
        self.ledger.transition_status(self.key, ActionStatus.SUBMITTING)
        self.assertTrue(self.ledger.is_duplicate("ws", "cand", "opp-1", "job_application"))

        # Attempting to record intent again raises duplicate error
        with self.assertRaises(ValueError):
            self.ledger.record_intent(self.record)


if __name__ == "__main__":
    unittest.main()
