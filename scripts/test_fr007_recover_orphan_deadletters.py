import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.fr007_recover_orphan_deadletters import (
    ORPHAN_RACE_ERROR_PREFIX,
    recover_orphan_race_dead_letters,
)
from storage.models import Base, WorkerJobRecord


class _Registry:
    def __init__(self, allowed: set[str]):
        self.allowed = allowed

    def is_read_allowed(self, source_id: str) -> bool:
        return source_id in self.allowed


class OrphanDeadLetterRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(prefix="opos-deadletter-recovery-", suffix=".sqlite3")
        os.close(fd)
        self.engine = create_engine(f"sqlite:///{self.path}")
        Base.metadata.create_all(self.engine, tables=[WorkerJobRecord.__table__])
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.now = datetime(2026, 9, 27, 0, 0, 0)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        os.unlink(self.path)

    def _job(
        self,
        job_id: str,
        source_id: str,
        status: str,
        *,
        created_offset: int,
        error_message: str | None = None,
    ) -> WorkerJobRecord:
        created = self.now + timedelta(seconds=created_offset)
        return WorkerJobRecord(
            id=job_id,
            job_type="poll_source",
            payload_json=json.dumps({"source_id": source_id}),
            status=status,
            run_after=created,
            retry_count=3 if status == "DEAD_LETTER" else 0,
            max_retries=3,
            error_message=error_message,
            created_at=created,
            updated_at=created,
        )

    def test_enqueues_only_unrecovered_defect_sources_and_preserves_history(self) -> None:
        defect = ORPHAN_RACE_ERROR_PREFIX + " at 0xabc>' has been deleted, or its row is otherwise not present."
        self.session.add_all(
            [
                self._job("dead-a", "greenhouse:a", "DEAD_LETTER", created_offset=0, error_message=defect),
                self._job("dead-b", "greenhouse:b", "DEAD_LETTER", created_offset=1, error_message=defect),
                self._job("dead-c", "greenhouse:c", "DEAD_LETTER", created_offset=2, error_message=defect),
                self._job("dead-other", "greenhouse:other", "DEAD_LETTER", created_offset=3, error_message="unrelated failure"),
                # b already received a newer successful poll, so it must not be re-polled.
                self._job("newer-b", "greenhouse:b", "COMPLETED", created_offset=20),
                # c already has active normal work.
                self._job("active-c", "greenhouse:c", "RETRY", created_offset=-20),
            ]
        )
        self.session.commit()

        result = recover_orphan_race_dead_letters(
            self.session,
            registry=_Registry({"greenhouse:a", "greenhouse:b", "greenhouse:c"}),
        )

        self.assertEqual(result["matched_dead_letter_rows"], 3)
        self.assertEqual(result["matched_sources"], 3)
        self.assertEqual(result["enqueued"], 1)
        self.assertEqual(result["skipped_newer"], 1)
        self.assertEqual(result["skipped_active"], 1)
        self.assertEqual(
            self.session.query(WorkerJobRecord).filter_by(status="DEAD_LETTER").count(),
            4,
        )
        recovery = (
            self.session.query(WorkerJobRecord)
            .filter_by(status="PENDING")
            .one()
        )
        self.assertEqual(
            json.loads(recovery.payload_json),
            {"source_id": "greenhouse:a", "recovery_reason": "orphan_cleanup_race"},
        )

        # Idempotency: the fresh PENDING recovery now suppresses a second enqueue.
        second = recover_orphan_race_dead_letters(
            self.session,
            registry=_Registry({"greenhouse:a", "greenhouse:b", "greenhouse:c"}),
        )
        self.assertEqual(second["enqueued"], 0)
        self.assertEqual(second["skipped_active"], 2)

    def test_read_disabled_source_is_never_reenqueued(self) -> None:
        defect = ORPHAN_RACE_ERROR_PREFIX + " at 0xabc>' has been deleted, or its row is otherwise not present."
        self.session.add(
            self._job("dead-disabled", "greenhouse:disabled", "DEAD_LETTER", created_offset=0, error_message=defect)
        )
        self.session.commit()

        result = recover_orphan_race_dead_letters(
            self.session,
            registry=_Registry(set()),
        )
        self.assertEqual(result["enqueued"], 0)
        self.assertEqual(result["skipped_policy"], 1)
        self.assertEqual(
            self.session.query(WorkerJobRecord).filter_by(status="DEAD_LETTER").count(),
            1,
        )


if __name__ == "__main__":
    unittest.main()
