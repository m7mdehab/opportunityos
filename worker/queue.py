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

    def claim_next_job(self, lease_duration_seconds: int = 60) -> Optional[WorkerJobRecord]:
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

        if not job:
            # Check for stale leased jobs
            stale_query = (
                self.session.query(WorkerJobRecord)
                .filter(
                    WorkerJobRecord.status == "RUNNING",
                    WorkerJobRecord.lease_expires_at < now,
                )
            )
            if is_postgres:
                stale_query = stale_query.with_for_update(skip_locked=True)
            job = stale_query.first()

        if job:
            job.status = "RUNNING"
            job.lease_owner = self.worker_id
            job.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
            self.session.commit()
            return job
        return None

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
