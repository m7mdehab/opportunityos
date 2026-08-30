"""Tests for Durable SQLite IdempotencyLedger."""
import os
import tempfile
import unittest
from matching.models import QualificationDecision, Track
from outbound.idempotency import (
    DuplicateSubmissionError,
    IdempotencyLedger,
    UnknownOutcomeFrozenError,
)
from outbound.models import (
    ActionStatus,
    ConfirmationEvidence,
    ExecutionMode,
    OutboundActionRecord,
)


class IdempotencyLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.ledger = IdempotencyLedger(self.db_path)

        self.key = self.ledger.compute_idempotency_key("default", "founder", "opp-123", "job_application")
        self.record = OutboundActionRecord(
            action_id="act-123",
            opportunity_id="opp-123",
            opportunity_content_hash="hash-123",
            workspace="default",
            candidate_id="founder",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            adapter_name="greenhouse",
            adapter_version="1.0.0",
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED,
            match_score_snapshot=0.95,
            artifact_ids=("art-1",),
            artifact_hashes=("hash-art-1",),
            manifest_hash="manifest-123",
            action_status=ActionStatus.PLANNED,
            idempotency_key=self.key,
            created_at="2026-08-30T00:00:00Z",
            updated_at="2026-08-30T00:00:00Z",
        )

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_survives_process_restart_and_blocks_unknown_outcome_retry(self) -> None:
        self.ledger.reserve_submission(self.record)
        self.ledger.transition_status(self.key, ActionStatus.UNKNOWN_OUTCOME, blocker_reason="Timeout")

        # Simulate process restart
        restarted_ledger = IdempotencyLedger(self.db_path)
        rec = restarted_ledger.get_record(self.key)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.action_status, ActionStatus.UNKNOWN_OUTCOME)

        with self.assertRaises(UnknownOutcomeFrozenError):
            restarted_ledger.reserve_submission(self.record)

    def test_duplicate_submission_blocked(self) -> None:
        self.ledger.reserve_submission(self.record)
        with self.assertRaises(DuplicateSubmissionError):
            self.ledger.reserve_submission(self.record)

    def test_reconciliation_unfreezes_ledger(self) -> None:
        self.ledger.reserve_submission(self.record)
        self.ledger.transition_status(self.key, ActionStatus.UNKNOWN_OUTCOME, blocker_reason="Crash")

        self.ledger.reconcile_unknown_outcome(self.key, ActionStatus.FAILED, reason="Founder verified application was NOT submitted")

        self.ledger.reserve_submission(self.record)
        rec = self.ledger.get_record(self.key)
        self.assertEqual(rec.action_status, ActionStatus.SUBMITTING)


if __name__ == "__main__":
    unittest.main()
