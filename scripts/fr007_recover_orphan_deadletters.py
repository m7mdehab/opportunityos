"""Bounded recovery for poll jobs exhausted by the fixed orphan-cleanup race.

This script never edits or resets historical worker rows. It identifies only
DEAD_LETTER poll_source jobs whose recorded error matches the
OpportunityArchiveOrphanRecord stale-ORM race fixed in PR #155, then enqueues
a fresh ordinary poll_source job for an eligible source when no newer poll job
already exists.

The operation is intentionally idempotent: after a recovery job is created,
a rerun sees that newer job and skips the source.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Any

from opportunity.registry import SourceRegistry
from scripts.db_capacity_guard import assert_heavy_work_allowed
from storage.engine import get_engine, get_session_factory
from storage.models import WorkerJobRecord
from worker.queue import BackgroundWorkerQueue

ORPHAN_RACE_ERROR_PREFIX = (
    "Handler raised: Instance '<OpportunityArchiveOrphanRecord"
)
ACTIVE_STATUSES = frozenset({"PENDING", "RETRY", "RUNNING"})


def _source_id(payload_json: str | None) -> str | None:
    try:
        payload = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("source_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _later(left: datetime | None, right: datetime | None) -> bool:
    """Return whether left is strictly later than right, tolerating nulls."""
    if left is None:
        return False
    if right is None:
        return True
    # Project queue timestamps are consistently written as UTC. SQLite test
    # fixtures and PostgreSQL's historical columns are both naive DateTime.
    return left > right


def recover_orphan_race_dead_letters(
    session: Any,
    *,
    registry: SourceRegistry | Any | None = None,
) -> dict[str, int]:
    """Enqueue fresh jobs for defect-induced dead letters without mutating them."""
    reg = registry or SourceRegistry()

    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        assert_heavy_work_allowed(session.connection())

    dead_rows = (
        session.query(
            WorkerJobRecord.id,
            WorkerJobRecord.payload_json,
            WorkerJobRecord.updated_at,
            WorkerJobRecord.created_at,
        )
        .filter(
            WorkerJobRecord.job_type == "poll_source",
            WorkerJobRecord.status == "DEAD_LETTER",
            WorkerJobRecord.error_message.like(ORPHAN_RACE_ERROR_PREFIX + "%"),
        )
        .all()
    )

    latest_dead_at: dict[str, datetime | None] = {}
    dead_ids: set[str] = set()
    malformed_dead = 0
    for job_id, payload_json, updated_at, created_at in dead_rows:
        dead_ids.add(job_id)
        source_id = _source_id(payload_json)
        if source_id is None:
            malformed_dead += 1
            continue
        dead_at = updated_at or created_at
        previous = latest_dead_at.get(source_id)
        if previous is None or _later(dead_at, previous):
            latest_dead_at[source_id] = dead_at

    all_poll_rows = (
        session.query(
            WorkerJobRecord.id,
            WorkerJobRecord.payload_json,
            WorkerJobRecord.status,
            WorkerJobRecord.created_at,
        )
        .filter(WorkerJobRecord.job_type == "poll_source")
        .all()
    )

    active_sources: set[str] = set()
    newer_sources: set[str] = set()
    for job_id, payload_json, status, created_at in all_poll_rows:
        source_id = _source_id(payload_json)
        if source_id is None:
            continue
        if status in ACTIVE_STATUSES:
            active_sources.add(source_id)
        dead_at = latest_dead_at.get(source_id)
        if (
            dead_at is not None
            and job_id not in dead_ids
            and _later(created_at, dead_at)
        ):
            newer_sources.add(source_id)

    queue = BackgroundWorkerQueue(session, worker_id="orphan-deadletter-recovery")
    enqueued = 0
    skipped_active = 0
    skipped_newer = 0
    skipped_policy = 0

    for source_id in sorted(latest_dead_at):
        if not reg.is_read_allowed(source_id):
            skipped_policy += 1
            continue
        if source_id in active_sources:
            skipped_active += 1
            continue
        if source_id in newer_sources:
            skipped_newer += 1
            continue
        queue.enqueue_job(
            "poll_source",
            {"source_id": source_id, "recovery_reason": "orphan_cleanup_race"},
            max_retries=3,
            commit=False,
        )
        enqueued += 1

    session.commit()
    return {
        "matched_dead_letter_rows": len(dead_rows),
        "matched_sources": len(latest_dead_at),
        "malformed_dead_letter_rows": malformed_dead,
        "enqueued": enqueued,
        "skipped_active": skipped_active,
        "skipped_newer": skipped_newer,
        "skipped_policy": skipped_policy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default=os.environ.get("OPOS_TARGET_DB_URL", ""),
        help="PostgreSQL DSN; defaults to OPOS_TARGET_DB_URL",
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("OPOS_TARGET_DB_URL is required")

    engine = get_engine(args.database_url)
    factory = get_session_factory(engine)
    with factory() as session:
        result = recover_orphan_race_dead_letters(session)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
