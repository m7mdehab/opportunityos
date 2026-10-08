"""FR-007: read-only footprint audit and opt-in, capacity-gated online index maintenance.

This is deliberately NOT a table rewrite, retention job, data migration or a
catch-up trigger. It never exports job text or evaluation JSON. An explicit
one-index operation is available only when both internal and provider space
ceilings are satisfied. Database/queue safety wins over maintenance progress.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

from scripts.db_capacity_guard import (
    BLOCK_BYTES,
    HARD_STOP_BYTES,
    PROVIDER_LIMIT_BYTES,
    WARN_BYTES,
    inspect_connection,
)

MIB = 1024 * 1024
# An online REINDEX retains the old index during the new build. 2x the old
# index plus a reserve is a deliberately conservative preflight estimate, NOT
# a promise of exact peak disk use. A blocked preflight requires another path.
REINDEX_EXTRA_MULTIPLIER = 2
REINDEX_RESERVE_BYTES = 16 * MIB
REINDEX_PROVIDER_RESERVE_BYTES = 10 * MIB
LOCK_TIMEOUT = "3s"
STATEMENT_TIMEOUT = "15min"

# Explicit allowlist; do not permit user-supplied SQL identifiers.
INDEX_TARGETS = {
    "provenance_identity": ("public", "field_provenances", "uq_field_provenances_identity"),
    "provenance_opportunity": ("public", "field_provenances", "ix_field_provenances_opportunity_id"),
    "opportunity_search": ("public", "opportunities", "ix_opportunities_search_tsv"),
    "evaluation_identity": ("public", "match_evaluations", "uq_match_evaluations_current_opportunity"),
}
LARGE_TABLES = (
    "opportunities", "match_evaluations", "field_provenances", "feed_projection",
    "opportunity_cold_archive",
)


@dataclass(frozen=True)
class ReindexEstimate:
    db_bytes: int
    old_index_bytes: int
    estimated_peak_bytes: int
    limit_bytes: int
    permitted: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return vars(self)


def index_rebuild_estimate(
    db_bytes: int, index_bytes: int, *, read_only: bool = False,
    in_recovery: bool = False, active_jobs: int = 0,
) -> ReindexEstimate:
    if min(db_bytes, index_bytes, active_jobs) < 0:
        raise ValueError("capacity and queue measurements must be nonnegative")
    limit = min(HARD_STOP_BYTES, PROVIDER_LIMIT_BYTES - REINDEX_PROVIDER_RESERVE_BYTES)
    peak = db_bytes + REINDEX_EXTRA_MULTIPLIER * index_bytes + REINDEX_RESERVE_BYTES
    if read_only or in_recovery:
        reason = "database_unwritable"
    elif active_jobs:
        reason = "worker_queue_not_idle"
    elif db_bytes >= BLOCK_BYTES:
        reason = "heavy_work_pause_boundary"
    elif peak >= limit:
        reason = "insufficient_temporary_headroom"
    else:
        reason = "within_preflight_limits"
    return ReindexEstimate(
        db_bytes=db_bytes, old_index_bytes=index_bytes,
        estimated_peak_bytes=peak, limit_bytes=limit,
        permitted=reason == "within_preflight_limits", reason=reason,
    )


def _index_metadata(connection, *, target: str) -> dict[str, Any]:
    schema, table, index = INDEX_TARGETS[target]
    row = connection.execute(text("""
        SELECT i.relname AS index_name, t.relname AS table_name,
               n.nspname AS schema_name, pg_relation_size(i.oid)::bigint AS bytes,
               x.indisvalid AS valid, x.indisready AS ready,
               x.indisunique AS is_unique, pg_get_indexdef(i.oid) AS definition
        FROM pg_class i
        JOIN pg_namespace n ON n.oid = i.relnamespace
        JOIN pg_index x ON x.indexrelid = i.oid
        JOIN pg_class t ON t.oid = x.indrelid
        WHERE n.nspname = :schema AND i.relname = :index_name
    """), {"schema": schema, "index_name": index}).mappings().one_or_none()
    if row is None:
        raise RuntimeError("expected index is missing: " + target)
    row = dict(row)
    if row["table_name"] != table or not row["valid"] or not row["ready"]:
        raise RuntimeError("index relation or validity does not match allowlist")
    return {
        "name": target, "schema": schema, "table": table,
        "index_name": index, "bytes": int(row["bytes"]),
        "valid": bool(row["valid"]), "is_unique": bool(row["is_unique"]),
    }


def _active_job_count(connection) -> int:
    return int(connection.execute(text("""
        SELECT count(*) FROM public.worker_jobs
        WHERE status IN ('PENDING','RETRY','RUNNING')
    """)).scalar_one())


def audit(connection) -> dict[str, Any]:
    if connection.engine.dialect.name != "postgresql":
        raise RuntimeError("storage audit requires PostgreSQL")
    snapshot = inspect_connection(connection)
    active_jobs = _active_job_count(connection)
    relation_rows = connection.execute(text("""
        SELECT c.relname AS name,
               pg_total_relation_size(c.oid)::bigint AS total_bytes,
               pg_relation_size(c.oid)::bigint AS heap_bytes,
               pg_indexes_size(c.oid)::bigint AS index_bytes,
               COALESCE(s.n_live_tup, 0)::bigint AS approx_live_rows,
               COALESCE(s.n_dead_tup, 0)::bigint AS approx_dead_rows
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
        WHERE n.nspname='public' AND c.relname = ANY(:names)
          AND c.relkind='r'
        ORDER BY total_bytes DESC, c.relname
    """), {"names": list(LARGE_TABLES)}).mappings().all()
    targets = []
    for name in INDEX_TARGETS:
        meta = _index_metadata(connection, target=name)
        estimate = index_rebuild_estimate(
            snapshot.database_size_bytes, meta["bytes"],
            read_only=snapshot.read_only, in_recovery=snapshot.in_recovery,
            active_jobs=active_jobs,
        )
        targets.append({**meta, "reindex": estimate.as_dict()})
    return {
        "database_bytes": snapshot.database_size_bytes,
        "status": snapshot.status,
        "active_jobs": active_jobs,
        "warn_bytes": WARN_BYTES, "hard_stop_bytes": HARD_STOP_BYTES,
        "provider_limit_bytes": PROVIDER_LIMIT_BYTES,
        "relations": [dict(row) for row in relation_rows],
        "index_targets": targets,
        "note": "Index rebuilds can reduce bloat but cannot remove live row data; savings are unproven until measured.",
    }


def reindex_one(connection, target: str, *, confirm: bool) -> dict[str, Any]:
    if target not in INDEX_TARGETS:
        raise ValueError("index is not in the explicit maintenance allowlist")
    if not confirm or os.environ.get("OPOS_STORAGE_REINDEX_APPROVED") != "1":
        raise RuntimeError("index maintenance requires --confirm and OPOS_STORAGE_REINDEX_APPROVED=1")
    if connection.engine.dialect.name != "postgresql":
        raise RuntimeError("online REINDEX is PostgreSQL-only")
    if connection.get_isolation_level() != "READ COMMITTED":
        # AUTOCOMMIT may report the default READ COMMITTED isolation level;
        # the CLI sets execution_options(isolation_level='AUTOCOMMIT').
        raise RuntimeError("unexpected isolation level")

    before = audit(connection)
    old = next(row for row in before["index_targets"] if row["name"] == target)
    if not old["reindex"]["permitted"]:
        raise RuntimeError("reindex preflight blocked: " + old["reindex"]["reason"])
    lock = bool(connection.execute(text("SELECT pg_try_advisory_lock(697, 7007)")).scalar_one())
    if not lock:
        raise RuntimeError("a storage reclamation operation is already in progress")
    try:
        # Recheck inside the serialized critical section; never substitute
        # stale audit snapshots for the database's current capacity.
        current = audit(connection)
        selected = next(row for row in current["index_targets"] if row["name"] == target)
        if not selected["reindex"]["permitted"]:
            raise RuntimeError("reindex became unsafe: " + selected["reindex"]["reason"])
        connection.execute(text("SET lock_timeout = '3s'"))
        connection.execute(text("SET statement_timeout = '15min'"))
        schema, _, index = INDEX_TARGETS[target]
        # SQL identifiers come only from the hard-coded allowlist above.
        connection.exec_driver_sql(f'REINDEX INDEX CONCURRENTLY "{schema}"."{index}"')
        after = audit(connection)
        rebuilt = next(row for row in after["index_targets"] if row["name"] == target)
        if not rebuilt["valid"]:
            raise RuntimeError("online index rebuild did not leave a valid index")
        return {
            "target": target, "index_bytes_before": old["bytes"],
            "index_bytes_after": rebuilt["bytes"],
            "database_bytes_before": before["database_bytes"],
            "database_bytes_after": after["database_bytes"],
            "reclaimed_index_bytes": old["bytes"] - rebuilt["bytes"],
            "result": "measured_no_data_rows_changed",
        }
    finally:
        connection.execute(text("RESET lock_timeout"))
        connection.execute(text("RESET statement_timeout"))
        connection.execute(text("SELECT pg_advisory_unlock(697, 7007)"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Capacity-safe storage audit / opt-in index reindex")
    parser.add_argument("--index", choices=sorted(INDEX_TARGETS), help="Run one allowlisted concurrent REINDEX")
    parser.add_argument("--confirm", action="store_true", help="Required with --index")
    parser.add_argument("--dsn-env", default="OPOS_TARGET_DB_URL")
    args = parser.parse_args()
    if args.index and not args.confirm:
        parser.error("--index requires --confirm")
    if not args.index and args.confirm:
        parser.error("--confirm is only used with --index")
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error("missing database URL in selected environment variable")
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        # Concurrent REINDEX cannot run inside a transaction block.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            result = (
                reindex_one(connection, args.index, confirm=args.confirm)
                if args.index else audit(connection)
            )
            print(json.dumps(result, sort_keys=True, default=str))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
