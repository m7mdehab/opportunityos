"""Entrypoint: ``python -m worker``.

Reads the production database URL through ``get_production_db_url`` (fail-closed:
missing or non-PostgreSQL DSNs raise ``ProductionDatabaseConfigurationError``
and exit non-zero), builds the default handler registry, and runs the worker
loop. ``--once`` processes at most one job (or one idle poll) and exits 0
unconditionally (regardless of that job's outcome); ``--max-jobs N`` runs
continuously and stops after N jobs are processed. ``--schedule`` runs the
``WorkerRunner`` and ``worker.scheduler.PollScheduler`` together in one
process (the scheduler on a background thread, the runner on the main
thread so it keeps installing the real SIGINT/SIGTERM handlers); a shared
``threading.Event`` means the signal that stops the runner also stops the
scheduler, so the whole process exits cleanly instead of leaving the
scheduler thread spinning. ``--poll-now`` builds a ``PollScheduler`` and
calls its ``run_once()`` exactly once (enqueuing ``poll_source`` for every
due, read-allowed source with no job already queued) and exits 0
immediately -- it enqueues jobs only, it never fetches anything itself.
All four modes are mutually exclusive.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import uuid

from core.logging import get_logger
from storage.engine import ProductionDatabaseConfigurationError, get_engine, get_production_db_url, get_session_factory
from worker.digest import generate_digest
from worker.handlers import default_handler_registry
from worker.runner import WorkerRunner
from worker.scheduler import PollScheduler

logger = get_logger("opportunityos.worker.main")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m worker", description="OpportunityOS background worker runner.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--once",
        action="store_true",
        help=(
            "Process at most one job -- or perform exactly one idle poll if the queue is empty -- "
            "then exit 0. Exit code 0 is unconditional: it does not reflect whether the one job "
            "processed succeeded, was retried, or was dead-lettered; check the structured logs or "
            "the job's row for that. Mutually exclusive with --max-jobs (which runs continuously)."
        ),
    )
    mode_group.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Run continuously (polling on --poll-interval when idle) and stop after processing N jobs. Mutually exclusive with --once.",
    )
    mode_group.add_argument(
        "--schedule",
        action="store_true",
        help=(
            "Run the WorkerRunner and worker.scheduler.PollScheduler together in one process: the "
            "scheduler enqueues poll_source for each due, read-allowed source (see "
            "OPPORTUNITYOS_POLL_INTERVAL_HOURS) while the runner processes the queue. Runs until "
            "SIGINT/SIGTERM. Mutually exclusive with --once/--max-jobs/--poll-now."
        ),
    )
    mode_group.add_argument(
        "--poll-now",
        action="store_true",
        help=(
            "Enqueue poll_source immediately for every due, read-allowed source (skipping any "
            "source with a PENDING/RETRY poll_source job already queued), then exit 0. Enqueues "
            "only -- fetches nothing itself. Mutually exclusive with --once/--max-jobs/--schedule."
        ),
    )
    mode_group.add_argument(
        "--digest",
        action="store_true",
        help=(
            "Write the F3 daily Markdown+HTML digest of new, high-fit opportunities to "
            "out/digest/ (worker.digest.generate_digest), from stored rows only, then exit 0. "
            "Makes zero network requests. Mutually exclusive with --once/--max-jobs/--schedule/--poll-now."
        ),
    )
    parser.add_argument("--worker-id", default=None, help="Override the worker id (default: a generated id).")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Idle poll interval in seconds.")
    parser.add_argument("--lease-seconds", type=int, default=60, help="Job lease duration in seconds.")
    parser.add_argument(
        "--scheduler-tick-seconds",
        type=float,
        default=30.0,
        help="How often (seconds) the --schedule scheduler thread checks for due sources.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        db_url = get_production_db_url()
    except ProductionDatabaseConfigurationError as exc:
        logger.error(
            "worker.startup_failed",
            extra={"component": "worker.__main__", "extra_data": {"error": str(exc)}},
        )
        print(f"ProductionDatabaseConfigurationError: {exc}", file=sys.stderr)
        return 1

    engine = get_engine(db_url)
    session_factory = get_session_factory(engine)
    worker_id = args.worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    if args.poll_now:
        scheduler = PollScheduler(session_factory)
        enqueued = scheduler.run_once()
        logger.info(
            "worker.poll_now_completed",
            extra={"component": "worker.__main__", "extra_data": {"enqueued": enqueued}},
        )
        print(f"poll-now: enqueued poll_source for {len(enqueued)} source(s): {enqueued}")
        return 0

    if args.digest:
        session = session_factory()
        try:
            summary = generate_digest(session)
        finally:
            session.close()
        logger.info(
            "worker.digest_completed",
            extra={"component": "worker.__main__", "extra_data": summary},
        )
        print(
            f"digest: {summary['count']} new high-fit item(s) for {summary['date']} written to "
            f"{summary['markdown_path']} and {summary['html_path']}"
        )
        return 0

    truth_pack_path = os.environ.get("OPPORTUNITYOS_TRUTH_PACK_PATH") or None
    handlers = default_handler_registry(truth_pack_path=truth_pack_path)

    if args.schedule:
        # A single threading.Event shared by the runner and the scheduler: the
        # runner's own _install_signal_handlers (main-thread only) sets this
        # event on SIGINT/SIGTERM, which is therefore also what stops the
        # scheduler thread below -- one signal cleanly stops both loops and
        # lets this process actually exit instead of leaving the scheduler
        # thread spinning after the runner has returned.
        stop_event = threading.Event()
        scheduler = PollScheduler(
            session_factory,
            stop_event=stop_event,
            tick_interval_seconds=args.scheduler_tick_seconds,
        )
        scheduler_thread = threading.Thread(
            target=scheduler.run_forever, name="poll-scheduler", daemon=True
        )
        scheduler_thread.start()

        runner = WorkerRunner(
            session_factory,
            handlers,
            worker_id=worker_id,
            lease_seconds=args.lease_seconds,
            poll_interval=args.poll_interval,
            stop_event=stop_event,
        )
        try:
            runner.run_forever()
        finally:
            # Belt-and-braces: even if run_forever exited some other way
            # (e.g. an uncaught exception that isn't a signal), make sure the
            # scheduler thread is told to stop and give it a bounded window
            # to do so before this process exits.
            stop_event.set()
            scheduler_thread.join(timeout=args.scheduler_tick_seconds + 5)
        return 0

    runner = WorkerRunner(
        session_factory,
        handlers,
        worker_id=worker_id,
        lease_seconds=args.lease_seconds,
        poll_interval=args.poll_interval,
    )

    if args.once:
        runner.run_once()
        return 0

    runner.run_forever(max_jobs=args.max_jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
