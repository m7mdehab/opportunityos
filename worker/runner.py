"""Background worker runner: claims and dispatches queued jobs to registered handlers."""
from __future__ import annotations

import json
import signal
import threading
import time
from typing import Callable, Mapping, Optional

from core.logging import get_logger, redact_data
from worker.queue import BackgroundWorkerQueue

logger = get_logger("opportunityos.worker.runner")

#: Distinctive marker included in the fail_job error message for a job_type with no
#: registered handler, so callers/tests can detect this specific failure mode.
UNKNOWN_JOB_TYPE_MARKER = "UNKNOWN_JOB_TYPE"


class WorkerRunner:
    """Claims jobs from BackgroundWorkerQueue and dispatches them to registered handlers.

    Each call into the runner that touches the database opens its own session from
    ``session_factory`` and closes it before returning; a WorkerRunner (and the
    sessions it creates) must never be shared across threads. Run one WorkerRunner
    per worker thread/process, each constructed with its own session_factory-backed
    sessions.
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
                queue.fail_job(job_id, f"Malformed payload_json: {exc}")
                logger.error(
                    "worker.job_payload_malformed",
                    extra={
                        "component": "worker.runner",
                        "extra_data": {"worker_id": self.worker_id, "job_id": job_id, "job_type": job_type},
                    },
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
                        "payload": redact_data(payload),
                    },
                },
            )

            handler = self.handlers.get(job_type)
            if handler is None:
                message = f"{UNKNOWN_JOB_TYPE_MARKER}: no handler registered for job_type '{job_type}'"
                queue.fail_job(job_id, message)
                logger.error(
                    "worker.job_unknown_type",
                    extra={
                        "component": "worker.runner",
                        "extra_data": {"worker_id": self.worker_id, "job_id": job_id, "job_type": job_type},
                    },
                )
                return True

            try:
                handler(payload)
            except Exception as exc:  # noqa: BLE001 - any handler failure must be recorded and retried/dead-lettered
                queue.fail_job(job_id, f"Handler raised: {exc}")
                logger.error(
                    "worker.job_failed",
                    extra={
                        "component": "worker.runner",
                        "extra_data": {
                            "worker_id": self.worker_id,
                            "job_id": job_id,
                            "job_type": job_type,
                            "error": redact_data(str(exc)),
                        },
                    },
                )
                return True

            queue.complete_job(job_id)
            logger.info(
                "worker.job_completed",
                extra={
                    "component": "worker.runner",
                    "extra_data": {"worker_id": self.worker_id, "job_id": job_id, "job_type": job_type},
                },
            )
            return True
        finally:
            session.close()

    def _install_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return

        def _handle_stop(signum, frame):  # noqa: ANN001 - signal handler signature is fixed
            logger.info(
                "worker.signal_received",
                extra={"component": "worker.runner", "extra_data": {"worker_id": self.worker_id, "signal": signum}},
            )
            self.stop_event.set()

        try:
            signal.signal(signal.SIGINT, _handle_stop)
        except ValueError:
            pass
        sigterm = getattr(signal, "SIGTERM", None)
        if sigterm is not None:
            try:
                signal.signal(sigterm, _handle_stop)
            except ValueError:
                pass

    def run_forever(self, max_jobs: Optional[int] = None) -> int:
        """Poll and process jobs until stop_event is set or max_jobs jobs have been processed.

        Returns the number of jobs processed.
        """
        self._install_signal_handlers()
        processed = 0
        logger.info(
            "worker.started",
            extra={"component": "worker.runner", "extra_data": {"worker_id": self.worker_id, "max_jobs": max_jobs}},
        )
        while not self.stop_event.is_set():
            if max_jobs is not None and processed >= max_jobs:
                break
            did_work = self.run_once()
            if did_work:
                processed += 1
                continue
            if max_jobs is not None and processed >= max_jobs:
                break
            self.stop_event.wait(self.poll_interval)
        logger.info(
            "worker.stopped",
            extra={"component": "worker.runner", "extra_data": {"worker_id": self.worker_id, "processed": processed}},
        )
        return processed
