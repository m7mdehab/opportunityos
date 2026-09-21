"""Bounded, repeatable hosted staging bootstrap for FR-007.

The command only creates durable source schedules for registry-approved reads,
enqueues due work using the canonical scheduler, and drains a bounded queue
slice. It never prints a DSN or payload/private content.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory, get_production_db_url
from worker.handlers import default_handler_registry
from worker.scheduler import enqueue_due_sources, get_or_create_source_schedule, _parse_cadence_hours
from worker.runner import WorkerRunner

# Supabase staging exposes a 15-connection session-mode pool. Each hosted
# worker process needs at most one foreground database connection plus one
# heartbeat connection at the same time. Five shards therefore cap at ten
# retained connections, leaving deliberate headroom for web/bootstrap/monitor
# traffic instead of allowing SQLAlchemy's default pool to retain five
# connections per process.
HOSTED_WORKER_POOL_SIZE = 2
HOSTED_WORKER_MAX_OVERFLOW = 0
HOSTED_WORKER_POOL_TIMEOUT_SECONDS = 30.0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FR-007 hosted source schedule/bootstrap runner")
    p.add_argument("--mode", choices=("bootstrap", "enqueue", "drain", "all"), default="all")
    p.add_argument("--max-jobs", type=int, default=10)
    p.add_argument("--time-budget-seconds", type=float, default=300.0)
    p.add_argument("--worker-id", type=str, default=None, help="Explicit worker identity")
    p.add_argument("--dry-run", action="store_true", help="inspect and report without writes")
    return p


def _source_schedules(session, registry: SourceRegistry, *, dry_run: bool) -> int:
    now = datetime.now(timezone.utc)
    try:
        cadence = _parse_cadence_hours(registry.path.read_text(encoding="utf-8"))
    except OSError:
        cadence = {}
    count = 0
    for source_id in sorted(registry._sources):
        if not registry.is_read_allowed(source_id):
            continue
        count += 1
        if not dry_run:
            # Existing scheduler semantics are authoritative for cadence and
            # next_due_at; do not manufacture a warm-up storm.
            get_or_create_source_schedule(session, source_id, cadence.get(source_id, 6.0), now)
    if not dry_run:
        session.commit()
    return count


def _drain(session_factory, *, max_jobs: int, budget: float, worker_id: str | None = None) -> int:
    effective_worker_id = worker_id or os.environ.get("OPOS_WORKER_ID") or "hosted-bootstrap"

    # Critical connection-pressure invariant: the runner and every default
    # handler share this exact process-local session factory. Without this
    # injection, handlers lazily create a second SQLAlchemy engine/pool and a
    # five-shard run can consume the full Supavisor session-mode allowance.
    handlers = default_handler_registry(
        session_factory=session_factory,
        truth_pack_path=os.environ.get("OPPORTUNITYOS_TRUTH_PACK_PATH") or None,
    )
    runner = WorkerRunner(
        session_factory,
        handlers,
        worker_id=effective_worker_id,
        poll_interval=0.1,
    )
    started = time.monotonic()
    processed = 0
    while processed < max_jobs and time.monotonic() - started < budget:
        if not runner.run_once():
            break  # queue-empty is a successful bounded stop condition
        processed += 1
    return processed


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raw = os.environ.get("OPOS_TARGET_DB_URL") or os.environ.get("OPPORTUNITYOS_DB_URL")
    if not raw:
        raise SystemExit("hosted bootstrap requires OPOS_TARGET_DB_URL (secret value is never printed)")

    os.environ["OPPORTUNITYOS_DB_URL"] = raw
    engine = get_engine(
        get_production_db_url(raw),
        pool_size=HOSTED_WORKER_POOL_SIZE,
        max_overflow=HOSTED_WORKER_MAX_OVERFLOW,
        pool_timeout=HOSTED_WORKER_POOL_TIMEOUT_SECONDS,
        pool_pre_ping=True,
    )
    factory = get_session_factory(engine)
    registry = SourceRegistry()

    scheduled = 0
    enqueued = 0
    processed = 0

    try:
        # Keep bootstrap/enqueue transaction scope completely separate from the
        # long-running worker drain. The committed session is closed before
        # any network-bound handler starts.
        if args.mode in ("bootstrap", "enqueue", "all"):
            session = factory()
            try:
                if args.mode in ("bootstrap", "all"):
                    scheduled = _source_schedules(session, registry, dry_run=args.dry_run)
                if args.mode in ("enqueue", "all") and not args.dry_run:
                    items, _ = enqueue_due_sources(session, registry=registry)
                    session.commit()
                    enqueued = len(items)
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        if args.mode in ("drain", "all") and not args.dry_run:
            processed = _drain(
                factory,
                max_jobs=max(0, args.max_jobs),
                budget=max(0.0, args.time_budget_seconds),
                worker_id=args.worker_id,
            )

        print(
            f"mode={args.mode} dry_run={args.dry_run} "
            f"schedules={scheduled} enqueued={enqueued} processed={processed}"
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
