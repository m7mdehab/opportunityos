"""Hosted W22.7 capacity/migration closure entrypoint.

All output is sanitized.  Live write mode is explicit and uses one direct
session so the Supabase temporary read-write override applies to migration,
compaction and physical reclaim on the same connection.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

# When invoked as ``python scripts/fr007_capacity_closure.py`` Python places
# only ``scripts/`` on sys.path.  Keep repository-owned ``scripts.*`` imports
# resolvable in hosted runners just as they are from ``python -m``.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.db_capacity_guard import inspect_connection
from scripts.db_capacity_maintenance import apply_maintenance, build_plan


def snapshot(connection, truth_pack_hash: str | None = None) -> dict:
    revision = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    size = inspect_connection(connection)
    relations = connection.execute(text("""
        SELECT relname AS relation, pg_total_relation_size(c.oid)::bigint AS bytes
        FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace
          AND c.relkind IN ('r','m') ORDER BY bytes DESC, relname
    """)).mappings().all()
    current_hash = truth_pack_hash or connection.execute(text("""
        SELECT truth_pack_hash FROM match_evaluations
        GROUP BY truth_pack_hash ORDER BY count(*) DESC, truth_pack_hash LIMIT 1
    """)).scalar()
    queue = connection.execute(text("""
        SELECT count(*) FILTER (WHERE status IN ('PENDING','RETRY') AND coalesce(run_after,created_at) <= now()) AS due_runnable,
               count(*) FILTER (WHERE status='RUNNING') AS running,
               count(*) FILTER (WHERE status='RUNNING' AND lease_expires_at < now()) AS expired,
               count(*) FILTER (WHERE status='DEAD_LETTER') AS dead_letter
        FROM worker_jobs
    """)).mappings().one()
    return {
        "revision": str(revision) if revision is not None else None,
        "database_size_bytes": size.database_size_bytes,
        "capacity_status": size.status,
        "read_only": size.read_only,
        "in_recovery": size.in_recovery,
        "truth_pack_hash": current_hash,
        "relations": [dict(row) for row in relations[:12]],
        "queue": dict(queue),
    }


def run_migration_on_connection(connection) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    # Alembic's env.py receives the already-open connection; this URL is only
    # a sanitized dialect hint and is never printed or used to connect.
    config.set_main_option(
        "sqlalchemy.url",
        connection.engine.url.render_as_string(hide_password=True),
    )
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
    expected_head = ScriptDirectory.from_config(config).get_current_head()
    actual_head = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    if actual_head != expected_head:
        raise RuntimeError(
            f"migration did not reach repository head: expected={expected_head!r} actual={actual_head!r}"
        )


def live_maintenance(dsn: str, truth_pack_hash: str | None) -> dict:
    engine = create_engine(dsn, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            before = snapshot(connection, truth_pack_hash)
            # Supabase's documented temporary quota maintenance override.
            connection.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE"))
            run_migration_on_connection(connection)
            # Alembic and the preflight statements may leave SQLAlchemy's
            # autobegin marker active even with AUTOCOMMIT isolation.  End it
            # explicitly before opening the bounded maintenance transaction.
            connection.commit()
            print("migration_head_verified", flush=True)
            selected_hash = truth_pack_hash or before["truth_pack_hash"]
            if not selected_hash:
                raise RuntimeError("current truth-pack hash unavailable")
            plan = build_plan(connection, truth_pack_hash=selected_hash)
            connection.commit()
            print(f"maintenance_plan_ready eligible={plan.eligible_count} active_projection={plan.active_projection_count}", flush=True)
            # Reclaim the largest derived projection footprint before writing
            # lossless cold payloads.  On a near-quota database PostgreSQL
            # cannot stage a second copy of the GIN/index pages needed by the
            # archive insert unless this derived state is compacted first.
            # Drop only rebuildable GIN indexes first; a full database cannot
            # stage their update tuples.  They are recreated over the compact
            # NULL vectors after archival.
            connection.execute(text("DROP INDEX IF EXISTS ix_feed_projection_search_tsv"))
            connection.execute(text("DROP INDEX IF EXISTS ix_opportunities_search_tsv"))
            # feed_projection is fully derived and rebuilt by the durable
            # worker/evaluation path.  Truncating it is the only bounded,
            # zero-copy way to recover a database that cannot stage even an
            # UPDATE tuple at the provider quota.
            connection.execute(text("TRUNCATE TABLE feed_projection"))
            connection.execute(text("UPDATE opportunities SET search_tsv = NULL WHERE search_tsv IS NOT NULL"))
            connection.commit()
            connection.execute(text("SET lock_timeout = '5min'"))
            print("vacuum_full_start relation=feed_projection_prearchive", flush=True)
            connection.execute(text("VACUUM (FULL, ANALYZE) public.feed_projection"))
            print("vacuum_full_done relation=feed_projection_prearchive", flush=True)
            with connection.begin():
                result = apply_maintenance(connection, truth_pack_hash=selected_hash, confirm=True)
            # Physical reclaim must run outside a transaction.  These are the
            # measured heavy relations, never arbitrary product tables.
            connection.execute(text("SET lock_timeout = '5min'"))
            for relation in ("feed_projection", "field_provenances", "opportunities", "match_evaluations"):
                print(f"vacuum_full_start relation={relation}", flush=True)
                connection.execute(text(f"VACUUM (FULL, ANALYZE) public.{relation}"))
                print(f"vacuum_full_done relation={relation}", flush=True)
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_opportunities_search_tsv ON opportunities USING gin (search_tsv)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_feed_projection_search_tsv ON feed_projection USING gin (search_tsv)"))
            after = snapshot(connection, selected_hash)
            if after["database_size_bytes"] > 400 * 1024 * 1024:
                raise RuntimeError("capacity maintenance completed below logical target")
            return {"before": before, "plan": plan.as_dict(), "maintenance": result, "after": after}
    finally:
        engine.dispose()


def fresh_write_proof(dsn: str) -> dict:
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            state = inspect_connection(connection)
            if state.read_only or state.in_recovery or state.database_size_bytes > 400 * 1024 * 1024:
                raise RuntimeError("fresh application connection is not writable/within capacity")
            transaction = connection.begin()
            try:
                connection.execute(text("CREATE TEMP TABLE opos_w227_write_probe (ok integer) ON COMMIT DROP"))
                connection.execute(text("INSERT INTO opos_w227_write_probe VALUES (1)"))
                transaction.rollback()
            except Exception:
                transaction.rollback()
                raise
            return {"status": "PASS", **state.as_dict()}
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "live-maintenance", "fresh-write"))
    parser.add_argument("--dsn-env", default="OPOS_TARGET_DB_URL")
    parser.add_argument("--truth-pack-hash")
    args = parser.parse_args()
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"missing required environment variable {args.dsn_env}")
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        if args.mode == "preflight":
            with engine.connect() as connection:
                result = snapshot(connection, args.truth_pack_hash)
        elif args.mode == "fresh-write":
            result = fresh_write_proof(dsn)
        else:
            result = live_maintenance(dsn, args.truth_pack_hash)
    finally:
        engine.dispose()
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
