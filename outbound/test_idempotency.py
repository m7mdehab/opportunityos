"""Tests for Durable SQLite Idempotency Ledger and Cross-Instance Concurrency."""
import os
import tempfile
import threading
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

        restarted_ledger = IdempotencyLedger(self.db_path)
        self.assertTrue(restarted_ledger.is_duplicate("default", "founder", "opp-100", "application"))

        with self.assertRaises(UnknownOutcomeFrozenError):
            restarted_ledger.reserve_submission(self.record)

        reconciled = restarted_ledger.reconcile_unknown_outcome(
            self.record.idempotency_key,
            new_status=ActionStatus.FAILED,
            reason="Founder verified application was not received",
        )
        self.assertEqual(reconciled.action_status, ActionStatus.FAILED)

    def test_cross_instance_concurrent_reservation_atomicity(self) -> None:
        """Test two independent IdempotencyLedger instances racing on the same SQLite file."""
        ledger1 = IdempotencyLedger(self.db_path)
        ledger2 = IdempotencyLedger(self.db_path)

        results: list[str] = []
        errors: list[Exception] = []

        def task(ledger_instance: IdempotencyLedger, name: str):
            try:
                ledger_instance.reserve_submission(self.record)
                results.append(f"{name}_success")
            except Exception as e:
                errors.append(e)
                results.append(f"{name}_error")

        t1 = threading.Thread(target=task, args=(ledger1, "instance1"))
        t2 = threading.Thread(target=task, args=(ledger2, "instance2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one reservation must succeed, the other must raise DuplicateSubmissionError
        success_count = sum(1 for r in results if r.endswith("_success"))
        error_count = sum(1 for r in results if r.endswith("_error"))
        self.assertEqual(success_count, 1)
        self.assertEqual(error_count, 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], DuplicateSubmissionError)


if __name__ == "__main__":
    unittest.main()
