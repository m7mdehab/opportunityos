"""Background worker runner: claims and dispatches queued jobs to registered handlers.

If a worker process crashes between claiming a job (status=RUNNING) and
calling ``complete_job``/``fail_job``, the stale-lease sweep inside
``BackgroundWorkerQueue.claim_next_job`` recovers the job for another worker
once its lease expires. That sweep increments ``retry_count`` on each
reclaim and dead-letters the job once ``max_retries`` is reached, exactly as
``fail_job`` would for a handler that raises. A job whose handler reliably
crashes the *process* (a "poison" job, as opposed to one that merely raises)
is therefore bounded by ``max_retries`` and eventually dead-lettered the same
way a repeatedly-raising job is, rather than being retried indefinitely.
"""
from __future__ import annotations

import json
import signal
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional

from core.logging import get_logger, redact_data
from storage.models import WorkerJobRecord
from worker.queue import BackgroundWorkerQueue

logger = get_logger("opportunityos.worker.runner")

#: Distinctive marker included in the fail_job error message for a job_type with no
#: registered handler, so callers/tests can detect this specific failure mode.
UNKNOWN_JOB_TYPE_MARKER = "UNKNOWN_JOB_TYPE"

#: Payload keys considered safe to log verbatim (never a place secrets live).
#: Everything else in a payload is logged only by key name, never by value, so a
#: secret under an unanticipated key never reaches the log even though
#: core.logging.redact_data is also applied as defense in depth.
_LOGGABLE_PAYLOAD_KEYS: tuple[str, ...] = ("source_id", "marker")

#: How often, relative to the lease duration, the heartbeat thread renews a
#: RUNNING job's lease while its handler is executing.
_LEASE_HEARTBEAT_FRACTION = 1.0 / 3.0

#: Failure reasons that can never succeed on redispatch: dead-letter promptly
#: (zero backoff) instead of paying exponential backoff on every retry.
_NON_RETRYABLE_BACKOFF_SECONDS = 0


def _safe_payload_summary(payload: dict) -> dict:
    """Whitelist-only summary of a payload for logging: known-safe keys plus key names."""
    summary = {key: payload[key] for key in _LOGGABLE_PAYLOAD_KEYS if key in payload}
    summary["payload_keys"] = sorted(payload.keys())
    return redact_data(summary)


def _as_aware_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize a DB-read datetime (naive, but always stored as UTC) to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class WorkerRunner:
    """Claims jobs from BackgroundWorkerQueue and dispatches them to registered handlers.

    Each call into the runner that touches the database opens its own session from
    ``session_factory`` and closes it before returning; a WorkerRunner (and the
    sessions it creates) must never be shared across threads. Run one WorkerRunner
    per worker thread/process, each constructed with its own session_factory-backed
    sessions.

    While a handler runs, a background heartbeat thread periodically renews the
    job's lease (using its own session, distinct from the one the claim/handler
    path uses) so a handler that runs longer than ``lease_seconds`` is not
    silently reassigned to another worker by the stale-lease sweep. Immediately
    before writing an outcome (``complete_job``/``fail_job``), the runner
    re-reads the job row and refuses to write unless it still holds an
    unexpired lease under its own ``worker_id`` -- so if the lease *was* lost
    (heartbeat starved, clock skew, a bug), this worker cannot clobber whatever
    the new lease holder does with the job.
    """

    def __init__(
        self,
        session_factory: Callable[[], object],
        handlers: Mapping[str, Callable[[dict], None]],
        *,
        worker_id: str,
        lease_seconds: int = 60,
        poll_interval: float = 1.0,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        self.session_factory = session_factory
        self.handlers = dict(handlers)
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self.stop_event = stop_event or threading.Event()

    # -- lease ownership fencing -------------------------------------------------

    def _has_valid_lease(self, session, job_id: str) -> bool:
        """Re-read the job row fresh and confirm this worker still owns an unexpired lease."""
        session.expire_all()
        row = session.query(WorkerJobRecord).filter_by(id=job_id).first()
        if row is None:
            return False
        if row.lease_owner != self.worker_id:
            return False
        expires_at = _as_aware_utc(row.lease_expires_at)
        if expires_at is not None and expires_at < datetime.now(timezone.utc):
            return False
        return True

    def _complete_job_fenced(self, session, queue: BackgroundWorkerQueue, job_id: str, job_type: str) -> None:
        if not self._has_valid_lease(session, job_id):
            logger.error(
                "worker.lease_lost",
                extra={
                    "component": "worker.runner",
                    "extra_data": {
                        "worker_id": self.worker_id,
                        "job_id": job_id,
                        "job_type": job_type,
                        "attempted_outcome": "complete",
                    },
                },
            )
            return
        queue.complete_job(job_id)
        logger.info(
            "worker.job_completed",
            extra={
                "component": "worker.runner",
                "extra_data": {"worker_id": self.worker_id, "job_id": job_id, "job_type": job_type},
            },
        )

    def _fail_job_fenced(
        self,
        session,
        queue: BackgroundWorkerQueue,
        job_id: str,
        job_type: str,
        message: str,
        *,
        backoff_seconds: Optional[int] = None,
    ) -> None:
        if not self._has_valid_lease(session, job_id):
            logger.error(
                "worker.lease_lost",
                extra={
                    "component": "worker.runner",
                    "extra_data": {
                        "worker_id": self.worker_id,
                        "job_id": job_id,
                        "job_type": job_type,
                        "attempted_outcome": "fail",
                    },
                },
            )
            return
        if backoff_seconds is not None:
            queue.fail_job(job_id, message, backoff_seconds=backoff_seconds)
        else:
            queue.fail_job(job_id, message)
        logger.error(
            "worker.job_failed",
            extra={
                "component": "worker.runner",
                "extra_data": {
                    "worker_id": self.worker_id,
                    "job_id": job_id,
                    "job_type": job_type,
                    "error": redact_data(message),
                },
            },
        )

    # -- lease renewal heartbeat --------------------------------------------------

    def _heartbeat_loop(self, job_id: str, stop_heartbeat: threading.Event) -> None:
        """Periodically extend the job's lease while its handler is still running.

        Uses its own session (never the run_once/handler session) so the heartbeat's
        writes and the claim/complete/fail path's reads and writes never interleave
        on one connection. The renewal UPDATE itself is scoped to
        ``lease_owner == self.worker_id AND status == 'RUNNING'``, so it is
        naturally a no-op (and stops itself) once this worker's lease is lost.
        """
        interval = max(self.lease_seconds * _LEASE_HEARTBEAT_FRACTION, 0.05)
        hb_session = self.session_factory()
        try:
            while not stop_heartbeat.wait(interval):
                now = datetime.now(timezone.utc)
                updated = (
                    hb_session.query(WorkerJobRecord)
                    .filter(
                        WorkerJobRecord.id == job_id,
                        WorkerJobRecord.lease_owner == self.worker_id,
                        WorkerJobRecord.status == "RUNNING",
                    )
                    .update({"lease_expires_at": now + timedelta(seconds=self.lease_seconds)}, synchronize_session=False)
                )
                hb_session.commit()
                if not updated:
                    logger.warning(
                        "worker.heartbeat_lease_lost",
                        extra={
                            "component": "worker.runner",
                            "extra_data": {"worker_id": self.worker_id, "job_id": job_id},
                        },
                    )
                    return
        finally:
            hb_session.close()

    # -- main dispatch loop --------------------------------------------------------

    def run_once(self) -> bool:
        """Claim and process at most one job. Returns True if a job was processed."""
        session = self.session_factory()
        try:
            queue = BackgroundWorkerQueue(session, worker_id=self.worker_id)
            job = queue.claim_next_job(lease_duration_seconds=self.lease_seconds)
            if job is None:
                logger.info(
                    "worker.idle_poll",
                    extra={"component": "worker.runner", "extra_data": {"worker_id": self.worker_id}},
                )
                return False

            job_id = job.id
            job_type = job.job_type
            try:
                payload = json.loads(job.payload_json) if job.payload_json else {}
            except (TypeError, ValueError) as exc:
                logger.error(
                    "worker.job_payload_malformed",
                    extra={
                        "component": "worker.runner",
                        "extra_data": {"worker_id": self.worker_id, "job_id": job_id, "job_type": job_type},
                    },
                )
                # Malformed payload can never succeed on redispatch: dead-letter promptly.
                self._fail_job_fenced(
                    session, queue, job_id, job_type,
                    f"Malformed payload_json: {exc}",
                    backoff_seconds=_NON_RETRYABLE_BACKOFF_SECONDS,
                )
                return True

            logger.info(
                "worker.job_claimed",
                extra={
                    "component": "worker.runner",
                    "extra_data": {
                        "worker_id": self.worker_id,
                        "job_id": job_id,
                        "job_type": job_type,
                        "payload_summary": _safe_payload_summary(payload),
                    },
                },
            )

            handler = self.handlers.get(job_type)
            if handler is None:
                message = f"{UNKNOWN_JOB_TYPE_MARKER}: no handler registered for job_type '{job_type}'"
                logger.error(
                    "worker.job_unknown_type",
                    extra={
                        "component": "worker.runner",
                        "extra_data": {"worker_id": self.worker_id, "job_id": job_id, "job_type": job_type},
                    },
                )
                # An unregistered job_type can never succeed on redispatch either.
                self._fail_job_fenced(
                    session, queue, job_id, job_type, message,
                    backoff_seconds=_NON_RETRYABLE_BACKOFF_SECONDS,
                )
                return True

            stop_heartbeat = threading.Event()
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, args=(job_id, stop_heartbeat), daemon=True
            )
            heartbeat_thread.start()
            handler_exc: Optional[BaseException] = None
            try:
                handler(payload)
            except Exception as exc:  # noqa: BLE001 - any handler failure must be recorded and retried/dead-lettered
                handler_exc = exc
            finally:
                stop_heartbeat.set()
                heartbeat_thread.join(timeout=self.lease_seconds + 5)

            if handler_exc is not None:
                self._fail_job_fenced(session, queue, job_id, job_type, f"Handler raised: {handler_exc}")
                return True

            self._complete_job_fenced(session, queue, job_id, job_type)
            return True
        finally:
            session.close()

    def _install_signal_handlers(self) -> list[tuple[int, object]]:
        """Install stop-on-signal handlers (main thread only) and return what was replaced.

        Returns a list of (signal_number, previous_handler) pairs actually
        installed, so the caller can restore them afterward instead of leaving
        process-global signal state mutated for the rest of the process.
        """
        if threading.current_thread() is not threading.main_thread():
            return []

        def _handle_stop(signum, frame):  # noqa: ANN001 - signal handler signature is fixed
            logger.info(
                "worker.signal_received",
                extra={"component": "worker.runner", "extra_data": {"worker_id": self.worker_id, "signal": signum}},
            )
            self.stop_event.set()

        candidate_signals = [signal.SIGINT]
        sigterm = getattr(signal, "SIGTERM", None)
        if sigterm is not None:
            candidate_signals.append(sigterm)

        installed: list[tuple[int, object]] = []
        for sig in candidate_signals:
            try:
                previous = signal.getsignal(sig)
                signal.signal(sig, _handle_stop)
            except ValueError:
                continue
            installed.append((sig, previous))
        return installed

    def _restore_signal_handlers(self, installed: list[tuple[int, object]]) -> None:
        for sig, previous in installed:
            try:
                signal.signal(sig, previous)
            except ValueError:
                pass

    def run_forever(self, max_jobs: Optional[int] = None) -> int:
        """Poll and process jobs until stop_event is set or max_jobs jobs have been processed.

        Returns the number of jobs processed.
        """
        installed_handlers = self._install_signal_handlers()
        processed = 0
        logger.info(
            "worker.started",
            extra={"component": "worker.runner", "extra_data": {"worker_id": self.worker_id, "max_jobs": max_jobs}},
        )
        try:
            while not self.stop_event.is_set():
                if max_jobs is not None and processed >= max_jobs:
                    break
                try:
                    did_work = self.run_once()
                except Exception as exc:  # noqa: BLE001 - a transient DB/infra error must not kill the process
                    logger.error(
                        "worker.run_once_error",
                        extra={
                            "component": "worker.runner",
                            "extra_data": {"worker_id": self.worker_id, "error": redact_data(str(exc))},
                        },
                    )
                    self.stop_event.wait(self.poll_interval)
                    continue
                if did_work:
                    processed += 1
                    continue
                if max_jobs is not None and processed >= max_jobs:
                    break
                self.stop_event.wait(self.poll_interval)
        finally:
            self._restore_signal_handlers(installed_handlers)
            logger.info(
                "worker.stopped",
                extra={"component": "worker.runner", "extra_data": {"worker_id": self.worker_id, "processed": processed}},
            )
        return processed
