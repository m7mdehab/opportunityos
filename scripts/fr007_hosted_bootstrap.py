"""Bounded, repeatable hosted staging bootstrap for FR-007.

The command only creates durable source schedules for registry-approved reads,
enqueues due work using the canonical scheduler, and drains a bounded queue
slice. It never prints a DSN or payload/private content.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Direct script execution puts ``scripts/`` ahead of the repository root on
# sys.path.  Worker queue handlers intentionally import the repository-owned
# capacity guard as ``scripts.*``; make that namespace available in hosted
# runners as well as editable installs.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory, get_production_db_url
from storage.models import WorkerJobRecord
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
HOSTED_WORKER_APPLICATION_NAME = "opportunityos-fr007-worker"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FR-007 hosted source schedule/bootstrap runner")
    p.add_argument("--mode", choices=("bootstrap", "enqueue", "drain", "all"), default="all")
    p.add_argument("--max-jobs", type=int, default=10)
    p.add_argument("--time-budget-seconds", type=float, default=300.0)
    p.add_argument("--worker-id", type=str, default=None, help="Explicit worker identity")
    p.add_argument(
        "--source-id",
        type=str,
        default=None,
        help="Restrict schedule/enqueue to one registered, read-allowed source; requires bounded all mode",
    )
    p.add_argument(
        "--source-ids",
        type=str,
        default=None,
        help="Explicit comma-separated bootstrap batch (1-5 registered, read-allowed sources)",
    )
    p.add_argument("--dry-run", action="store_true", help="inspect and report without writes")
    return p


def _source_schedules(
    session,
    registry: SourceRegistry,
    *,
    dry_run: bool,
    source_id: str | None = None,
    source_ids: list[str] | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    try:
        cadence = _parse_cadence_hours(registry.path.read_text(encoding="utf-8"))
    except OSError:
        cadence = {}
    count = 0
    if source_id is not None and source_ids is not None:
        raise ValueError("source_id and source_ids are mutually exclusive")
    if source_id is not None:
        if source_id not in registry._sources:
            raise ValueError(f"unregistered representative source: {source_id}")
        if not registry.is_read_allowed(source_id):
            raise ValueError(f"representative source is not read-allowed: {source_id}")
        source_ids = [source_id]
    elif source_ids is not None:
        if not 1 <= len(source_ids) <= 5:
            raise ValueError("source bootstrap batch must contain between one and five sources")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source bootstrap batch contains duplicate IDs")
        invalid = [sid for sid in source_ids if sid not in registry._sources]
        if invalid:
            raise ValueError(f"unregistered source(s) in bootstrap batch: {', '.join(invalid)}")
        disallowed = [sid for sid in source_ids if not registry.is_read_allowed(sid)]
        if disallowed:
            raise ValueError(f"source(s) are not read-allowed: {', '.join(disallowed)}")
    else:
        raise ValueError("source schedule creation requires an explicit source ID or bounded source batch")

    for sid in source_ids:
        count += 1
        if not dry_run:
            # Existing scheduler semantics are authoritative for cadence and
            # next_due_at; do not manufacture a warm-up storm.
            get_or_create_source_schedule(session, sid, cadence.get(sid, 6.0), now)
    if not dry_run:
        session.commit()
    return count


def _assert_no_runnable_jobs(session) -> None:
    """Fail closed rather than letting a bounded source batch drain unrelated work."""
    count = (
        session.query(WorkerJobRecord)
        .filter(WorkerJobRecord.status.in_(("PENDING", "RETRY", "RUNNING")))
        .count()
    )
    if count:
        raise RuntimeError(
            "bounded source bootstrap requires an empty runnable worker queue; "
            f"found {count} existing runnable job(s)"
        )


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
    selected_source_ids = None
    if args.source_ids is not None:
        selected_source_ids = [part.strip() for part in args.source_ids.split(",") if part.strip()]
        if not selected_source_ids:
            raise SystemExit("--source-ids must contain at least one comma-separated source ID")
        if len(selected_source_ids) > 5:
            raise SystemExit("source bootstrap batches are limited to five sources")
        if len(set(selected_source_ids)) != len(selected_source_ids):
            raise SystemExit("--source-ids contains duplicate source IDs")
        if args.source_id is not None:
            raise SystemExit("--source-id and --source-ids cannot be combined")
        if args.mode not in ("bootstrap", "all"):
            raise SystemExit("--source-ids is permitted only with --mode bootstrap or all")
        if args.mode == "all" and (
            args.max_jobs < len(selected_source_ids)
            or args.max_jobs > 2 * len(selected_source_ids)
            or args.time_budget_seconds <= 0
            or args.time_budget_seconds > 480
        ):
            raise SystemExit("source-batch execution requires one to two jobs per source and <=480 seconds")
    if args.mode == "bootstrap" and args.source_id is None and selected_source_ids is None:
        raise SystemExit("bootstrap requires an explicit --source-id or bounded --source-ids batch")
    if args.source_id is not None:
        if args.mode != "all":
            raise SystemExit("--source-id is permitted only with --mode all")
        if args.max_jobs < 0 or args.max_jobs > 2:
            raise SystemExit("representative-source execution is limited to at most 2 jobs")
        if not args.dry_run and args.max_jobs == 0:
            raise SystemExit("representative-source execution must allow at least the source poll job")
        if args.time_budget_seconds <= 0 or args.time_budget_seconds > 480:
            raise SystemExit("representative-source execution is limited to 480 seconds")
    registry = SourceRegistry()
    if args.source_id is not None:
        if args.source_id not in registry._sources:
            raise SystemExit(f"unregistered representative source: {args.source_id}")
        if not registry.is_read_allowed(args.source_id):
            raise SystemExit(f"representative source is not read-allowed: {args.source_id}")
    if selected_source_ids is not None:
        try:
            _source_schedules(
                None,
                registry,
                dry_run=True,
                source_ids=selected_source_ids,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

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
        application_name=HOSTED_WORKER_APPLICATION_NAME,
    )
    # The runner dispatches from a committed claim and then waits on remote
    # source I/O. Disable post-commit expiration for this worker-only factory
    # so dispatch does not create an idle foreground transaction.
    factory = get_session_factory(engine, expire_on_commit=False)
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
                if (args.source_id is not None or selected_source_ids is not None) and not args.dry_run:
                    _assert_no_runnable_jobs(session)
                if args.mode in ("bootstrap", "all") and (
                    args.source_id is not None or selected_source_ids is not None
                ):
                    scheduled = _source_schedules(
                        session,
                        registry,
                        dry_run=args.dry_run,
                        source_id=args.source_id,
                        source_ids=selected_source_ids,
                    )
                if args.mode in ("enqueue", "all") and not args.dry_run:
                    enqueue_kwargs = {"registry": registry}
                    if args.source_id is not None:
                        enqueue_kwargs["source_id"] = args.source_id
                    elif selected_source_ids is not None:
                        enqueue_kwargs["source_ids"] = selected_source_ids
                        enqueue_kwargs["force"] = True
                        enqueue_kwargs["create_missing_schedules"] = False
                    else:
                        # Routine cron/manual enqueue only advances schedules
                        # created by explicit, bounded source-bootstrap batches.
                        enqueue_kwargs["create_missing_schedules"] = False
                    items, _ = enqueue_due_sources(session, **enqueue_kwargs)
                    if args.source_id is not None and (
                        len(items) != 1 or items[0].get("source_id") != args.source_id
                    ):
                        raise RuntimeError(
                            "representative-source scheduler did not enqueue exactly the requested source"
                        )
                    if selected_source_ids is not None and {
                        item.get("source_id") for item in items
                    } != set(selected_source_ids):
                        raise RuntimeError(
                            "source-batch scheduler did not enqueue exactly the requested batch"
                        )
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
