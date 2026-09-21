import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable
from sqlalchemy.orm import Session
from sqlalchemy import text
from storage.models import WorkerJobRecord


class BackgroundWorkerQueue:
    """Production-ready transactional background worker queue with SKIP LOCKED and lease recovery."""

    def __init__(self, session: Session, worker_id: Optional[str] = None):
        self.session = session
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    def enqueue_job(
        self,
        job_type: str,
        payload: Dict[str, Any],
        run_after: Optional[datetime] = None,
        max_retries: int = 3,
        *,
        commit: bool = True,
    ) -> str:
        """Persist a queue row and return its job id.

        ``commit=True`` preserves the historical queue API for ordinary callers.
        Transactional schedulers may pass ``commit=False`` so the job insert and
        the schedule-row advancement are committed atomically while the
        ``source_schedules`` row lock is still held. In that mode this method
        only flushes; the caller owns the surrounding transaction.
        """
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
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return job_id

    def enqueue_evaluate_new_coalesced(self, *, commit: bool = True) -> Optional[str]:
        """Ensure the global evaluation safety-net has at most one running job
        and one pending/retry successor.

        The check and insert are one short transaction.  PostgreSQL serializes
        concurrent poll completions with a transaction advisory lock; SQLite
        and test doubles retain the same status semantics without pretending
        to offer PostgreSQL locking.
        """
        bind = self.session.get_bind()
        is_postgres = bool(bind is not None and bind.dialect.name == "postgresql")
        if is_postgres:
            from scripts.db_capacity_guard import assert_heavy_work_allowed

            # Fail closed before taking the coalescing lock or creating a job.
            # This keeps provider quota/read-only failures observable and
            # prevents another multi-shard wave from starting unusable work.
            assert_heavy_work_allowed(self.session.connection())
            self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('evaluate_new_coalesce')::bigint)"))
        running = (
            self.session.query(WorkerJobRecord.id)
            .filter(WorkerJobRecord.job_type == "evaluate_new", WorkerJobRecord.status == "RUNNING")
            .first()
        )
        pending = (
            self.session.query(WorkerJobRecord.id)
            .filter(
                WorkerJobRecord.job_type == "evaluate_new",
                WorkerJobRecord.status.in_(["PENDING", "RETRY"]),
            )
            .first()
        )
        if running is not None and pending is not None:
            return None
        if running is None and pending is not None:
            return None
        job_id = self.enqueue_job("evaluate_new", {}, commit=False)
        if commit:
            self.session.commit()
        return job_id

    def _invoke_claim_hook(self, claim_hook: Optional[Callable[[], None]]) -> None:
        """Run claim_hook (if any) with the invariant that a raising hook never
        leaves an uncommitted, in-session mutation behind. Without this, a
        direct queue user with a persistent session that swallowed the
        exception and called claim_next_job again would autoflush the
        phantom (never-committed) status="RUNNING" claim alongside its next
        write. The runner path is immune (it opens/closes a session per
        call), but the invariant is enforced unconditionally here rather than
        relying on every caller's session lifecycle to save it.
        """
        if claim_hook is None:
            return
        try:
            claim_hook()
        except Exception:
            self.session.rollback()
            raise

    def claim_next_job(
        self,
        lease_duration_seconds: int = 60,
        *,
        claim_hook: Optional[Callable[[], None]] = None,
    ) -> Optional[WorkerJobRecord]:
        """Atomically claim the next runnable job, or return None if none is available.

        First sweeps for RUNNING jobs whose lease has expired -- i.e. jobs whose
        worker crashed or was killed without ever calling complete_job/fail_job.
        Recovering expired leases before ordinary PENDING/RETRY selection ensures
        stale work is never starved behind an arbitrarily large fresh backlog.
        A reclaimed stale-leased job has its retry_count incremented and is
        dead-lettered on threshold exactly as fail_job would (see fail_job for the
        shared increment-then-threshold policy): a job whose process reliably dies
        is thereby bounded by max_retries instead of being retried forever
        (council C10-2). A job that is dead-lettered by this sweep is never
        returned to a caller; this method keeps looking for another claimable job
        instead (whether another stale lease or ordinary due work).

        If no stale-leased job is eligible, looks for PENDING/RETRY jobs whose
        run_after has elapsed, ordered by run_after ascending.

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

            # 1. Sweep for stale leases first (expired RUNNING jobs).
            stale_query = (
                self.session.query(WorkerJobRecord)
                .filter(
                    WorkerJobRecord.status == "RUNNING",
                    WorkerJobRecord.lease_expires_at < now,
                )
                .order_by(WorkerJobRecord.lease_expires_at.asc())
            )
            if is_postgres:
                stale_query = stale_query.with_for_update(skip_locked=True)
            stale_job = stale_query.first()

            if stale_job:
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
                    self._invoke_claim_hook(claim_hook)
                    self.session.commit()
                    # A dead-lettered job must not be handed to a worker; keep looking
                    # (may claim another stale lease or ordinary due work in this same call).
                    continue

                stale_job.status = "RUNNING"
                stale_job.lease_owner = self.worker_id
                stale_job.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
                self._invoke_claim_hook(claim_hook)
                self.session.commit()
                return stale_job

            # 2. No stale leases; claim ordinary PENDING/RETRY work whose run_after has elapsed.
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
                self._invoke_claim_hook(claim_hook)
                self.session.commit()
                return job

            return None

    def complete_job(self, job_id: str) -> bool:
        """Guarded UPDATE: marks the job COMPLETED only if this worker still holds
        an apparently-valid RUNNING lease on it (lease_owner == self.worker_id AND
        status == 'RUNNING'). This is a plain UPDATE ... WHERE ..., not a
        load-then-mutate-then-commit, so it cannot clobber a job that another
        worker's stale-lease sweep has already reclaimed out from under this one
        (the sweep changes lease_owner and/or status, so the WHERE clause simply
        stops matching).

        Returns True if the write applied, False if no row matched -- i.e. the
        lease had already been lost by the time this call reached the database.
        A caller that gets False must not assume the job was completed; the job
        is now some other worker's responsibility (or already dead-lettered).
        """
        updated = (
            self.session.query(WorkerJobRecord)
            .filter(
                WorkerJobRecord.id == job_id,
                WorkerJobRecord.lease_owner == self.worker_id,
                WorkerJobRecord.status == "RUNNING",
            )
            .update(
                {"status": "COMPLETED", "lease_owner": None, "lease_expires_at": None},
                synchronize_session=False,
            )
        )
        self.session.commit()
        return bool(updated)

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        base_backoff_seconds: int = 30,
        backoff_seconds: Optional[int] = None,
    ) -> bool:
        """Guarded UPDATE: records the failure only if this worker still holds an
        apparently-valid RUNNING lease on the job (lease_owner == self.worker_id
        AND status == 'RUNNING'), applying the same increment-then-threshold
        policy as the stale-lease reclaim path in claim_next_job.

        retry_count/max_retries are read via a column-only query rather than
        through the mapped entity, so the decision is never taken from a
        stale identity-map-cached instance (a persistent session that already
        loaded this row -- e.g. via the runner's lease-fence check -- would
        otherwise hand back that cached object's attributes instead of a fresh
        read). Freshness of this read is a courtesy, not the safety mechanism,
        though: the guard on the write itself is what actually prevents a lost
        update or a double-increment against a job another worker's stale-lease
        sweep has since reclaimed. If the row changed between the read and the
        write -- including via a concurrent reclaim -- the guarded UPDATE's
        WHERE clause matches zero rows, so no incorrect value is ever written;
        this call just reports False.

        Returns True if the write applied, False if no row matched -- i.e. the
        lease had already been lost by the time this call reached the database.
        """
        row = (
            self.session.query(WorkerJobRecord.retry_count, WorkerJobRecord.max_retries)
            .filter(WorkerJobRecord.id == job_id)
            .first()
        )
        if row is None:
            return False
        current_retry_count, max_retries = row
        new_retry_count = current_retry_count + 1

        values: Dict[str, Any] = {"retry_count": new_retry_count, "error_message": error_message}
        if new_retry_count >= max_retries:
            values.update(status="DEAD_LETTER", lease_owner=None, lease_expires_at=None)
        else:
            base = backoff_seconds if backoff_seconds is not None else base_backoff_seconds
            backoff_delay = base * (2 ** (new_retry_count - 1)) if base > 0 else 0
            values.update(
                status="RETRY",
                run_after=datetime.now(timezone.utc) + timedelta(seconds=backoff_delay),
                lease_owner=None,
                lease_expires_at=None,
            )

        updated = (
            self.session.query(WorkerJobRecord)
            .filter(
                WorkerJobRecord.id == job_id,
                WorkerJobRecord.lease_owner == self.worker_id,
                WorkerJobRecord.status == "RUNNING",
            )
            .update(values, synchronize_session=False)
        )
        self.session.commit()
        return bool(updated)
