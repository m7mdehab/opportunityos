"""Tests for Durable SQLite Idempotency Ledger."""
import os
import tempfile
import unittest
from matching.models import QualificationDecision, Track
from outbound.idempotency import (
    DuplicateSubmissionError,
    IdempotencyLedger,
    UnknownOutcomeFrozenError,
)
from outbound.models import ActionStatus, ExecutionMode, OutboundActionRecord


class IdempotencyLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.ledger = IdempotencyLedger(self.db_path)
        self.record = OutboundActionRecord(
            action_id="act-123",
            opportunity_id="opp-100",
            opportunity_content_hash="hash-100",
            workspace="default",
            candidate_id="founder",
            track=Track.EMPLOYMENT,
            source="greenhouse",
            adapter_name="greenhouse",
            adapter_version="1.0.0",
            execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED,
            match_score_snapshot=0.92,
            artifact_ids=("art-1",),
            artifact_hashes=("hash-art-1",),
            manifest_hash="manifest-hash-1",
            action_status=ActionStatus.PLANNED,
            idempotency_key=IdempotencyLedger.compute_idempotency_key("default", "founder", "opp-100", "application"),
            created_at="2026-08-30T00:00:00Z",
            updated_at="2026-08-30T00:00:00Z",
        )

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_reservation_and_process_restart_durability(self) -> None:
        self.ledger.reserve_submission(self.record)
        self.ledger.transition_status(self.record.idempotency_key, ActionStatus.UNKNOWN_OUTCOME)

        # Simulate process restart by creating new ledger pointing to same DB
        restarted_ledger = IdempotencyLedger(self.db_path)
        self.assertTrue(restarted_ledger.is_duplicate("default", "founder", "opp-100", "application"))

        # Automatic retry must raise UnknownOutcomeFrozenError
        with self.assertRaises(UnknownOutcomeFrozenError):
            restarted_ledger.reserve_submission(self.record)

        # Founder reconciliation recovers
        reconciled = restarted_ledger.reconcile_unknown_outcome(
            self.record.idempotency_key,
            new_status=ActionStatus.FAILED,
            reason="Founder verified application was not received",
        )
        self.assertEqual(reconciled.action_status, ActionStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
