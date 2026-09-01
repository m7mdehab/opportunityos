"""Entrypoint: ``python -m worker``.

Reads the production database URL through ``get_production_db_url`` (fail-closed:
missing or non-PostgreSQL DSNs raise ``ProductionDatabaseConfigurationError``
and exit non-zero), builds the default handler registry, and runs the worker
loop. ``--once`` processes at most one job (or one idle poll) and exits 0
unconditionally (regardless of that job's outcome); ``--max-jobs N`` runs
continuously and stops after N jobs are processed. The two are mutually
exclusive.
"""
from __future__ import annotations

import argparse
import sys
import uuid

from core.logging import get_logger
from storage.engine import ProductionDatabaseConfigurationError, get_engine, get_production_db_url, get_session_factory
from worker.handlers import default_handler_registry
from worker.runner import WorkerRunner

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
    parser.add_argument("--worker-id", default=None, help="Override the worker id (default: a generated id).")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Idle poll interval in seconds.")
    parser.add_argument("--lease-seconds", type=int, default=60, help="Job lease duration in seconds.")
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
    handlers = default_handler_registry()
    worker_id = args.worker_id or f"worker-{uuid.uuid4().hex[:8]}"

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
