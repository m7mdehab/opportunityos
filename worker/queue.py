import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable
from sqlalchemy.orm import Session
from storage.models import WorkerJobRecord


class BackgroundWorkerQueue:
    """Production-ready transactional background worker queue with SKIP LOCKED and lease recovery."""

    def __init__(self, session: Session, worker_id: Optional[str] = None):
        self.session = session
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    def enqueue_job(self, job_type: str, payload: Dict[str, Any], run_after: Optional[datetime] = None, max_retries: int = 3) -> str:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        record = WorkerJobRecord(
            id=job_id,
            job_type=job_type,
            payload_json=json.dumps(payload),
            status="PENDING",
            run_after=run_after or datetime.now(timezone.utc),
            retry_count=0,
            max_retries=max_retries,
        )
        self.session.add(record)
        self.session.commit()
        return job_id

    def claim_next_job(
        self,
        lease_duration_seconds: int = 60,
        *,
        claim_hook: Optional[Callable[[], None]] = None,
    ) -> Optional[WorkerJobRecord]:
        """Atomically claim the next runnable job, or return None if none is available.

        First looks for PENDING/RETRY jobs whose run_after has elapsed. If none is
        found, sweeps for RUNNING jobs whose lease has expired -- i.e. jobs whose
        worker crashed or was killed without ever calling complete_job/fail_job.
        A reclaimed stale-leased job has its retry_count incremented and is
        dead-lettered on threshold exactly as fail_job would (see fail_job for the
        shared increment-then-threshold policy): a job whose process reliably dies
        is thereby bounded by max_retries instead of being retried forever
        (council C10-2). A job that is dead-lettered by this sweep is never
        returned to a caller; this method keeps looking for another claimable job
        instead.

        ``claim_hook``, if provided, is invoked after the selected row has been
        mutated in-session but before the transaction is committed. It exists
        solely so tests can deterministically synchronise two concurrent claim
        attempts against real PostgreSQL row locking (see Case S in
        storage/test_postgres_integration.py). Production callers must not pass it.
        """
        while True:
            now = datetime.now(timezone.utc)
            bind = self.session.get_bind()
            is_postgres = bind.dialect.name == "postgresql" if bind else False

            query = (
                self.session.query(WorkerJobRecord)
                .filter(
                    WorkerJobRecord.status.in_(["PENDING", "RETRY"]),
                    WorkerJobRecord.run_after <= now,
                )
                .order_by(WorkerJobRecord.run_after.asc())
            )

            if is_postgres:
                query = query.with_for_update(skip_locked=True)

            job = query.first()

            if job:
                job.status = "RUNNING"
                job.lease_owner = self.worker_id
                job.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
                if claim_hook is not None:
                    claim_hook()
                self.session.commit()
                return job

            # No immediately runnable job; sweep for stale leases (crashed worker).
            stale_query = self.session.query(WorkerJobRecord).filter(
                WorkerJobRecord.status == "RUNNING",
                WorkerJobRecord.lease_expires_at < now,
            )
            if is_postgres:
                stale_query = stale_query.with_for_update(skip_locked=True)
            stale_job = stale_query.first()

            if not stale_job:
                return None

            # Mirror fail_job's increment-then-threshold policy exactly, so a job
            # whose worker process died without calling complete_job/fail_job is
            # still counted against max_retries instead of reclaimed forever.
            stale_job.retry_count += 1
            if stale_job.retry_count >= stale_job.max_retries:
                stale_job.status = "DEAD_LETTER"
                stale_job.lease_owner = None
                stale_job.lease_expires_at = None
                stale_job.error_message = (
                    "Lease expired without completion (worker presumed dead); "
                    f"retry_count {stale_job.retry_count} reached max_retries {stale_job.max_retries}"
                )
                if claim_hook is not None:
                    claim_hook()
                self.session.commit()
                # A dead-lettered job must not be handed to a worker; keep looking.
                continue

            stale_job.status = "RUNNING"
            stale_job.lease_owner = self.worker_id
            stale_job.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
            if claim_hook is not None:
                claim_hook()
            self.session.commit()
            return stale_job

    def complete_job(self, job_id: str) -> None:
        job = self.session.query(WorkerJobRecord).filter_by(id=job_id).first()
        if job:
            job.status = "COMPLETED"
            job.lease_owner = None
            job.lease_expires_at = None
            self.session.commit()

    def fail_job(self, job_id: str, error_message: str, base_backoff_seconds: int = 30, backoff_seconds: Optional[int] = None) -> None:
        job = self.session.query(WorkerJobRecord).filter_by(id=job_id).first()
        if job:
            job.retry_count += 1
            job.error_message = error_message
            if job.retry_count >= job.max_retries:
                job.status = "DEAD_LETTER"
                job.lease_owner = None
                job.lease_expires_at = None
            else:
                job.status = "RETRY"
                base = backoff_seconds if backoff_seconds is not None else base_backoff_seconds
                backoff_delay = base * (2 ** (job.retry_count - 1)) if base > 0 else 0
                job.run_after = datetime.now(timezone.utc) + timedelta(seconds=backoff_delay)
                job.lease_owner = None
                job.lease_expires_at = None
            self.session.commit()
