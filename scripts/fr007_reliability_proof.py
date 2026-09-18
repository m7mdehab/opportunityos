"""FR-007 W13C reliability proof runner.

The runner is deliberately small and provider neutral.  It observes the real
PostgreSQL read model and persistence invariants; it never fabricates a PASS
when PostgreSQL, a worker, or an artifact backend is unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STATES = ("PASS", "FAIL", "BLOCKED")
SCENARIOS = ("A4", "A5", "A6")
_SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _result(scenario: str, state: str, **details: Any) -> dict[str, Any]:
    if scenario not in SCENARIOS or state not in STATES:
        raise ValueError("invalid proof result")
    return {"scenario": scenario, "state": state, "details": details}


def _table_exists(connection: Any, table: str) -> bool:
    if not _SAFE_IDENTIFIER.fullmatch(table):
        raise ValueError("unsafe table name")
    from sqlalchemy import text
    return connection.execute(text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table}"}).fetchone()[0] is not None


def _count(connection: Any, table: str) -> int | None:
    from sqlalchemy import text
    return None if not _table_exists(connection, table) else int(connection.execute(text(f"SELECT count(*) FROM {table}")).fetchone()[0])


def _connect(dsn: str):
    if not dsn or "postgresql" not in dsn.lower():
        raise ValueError("OPPORTUNITYOS_DB_URL must be a PostgreSQL DSN")
    from sqlalchemy import create_engine
    return create_engine(dsn, future=True).connect()


def prove_a4(connection: Any) -> dict[str, Any]:
    """Prove read availability from persisted rows while workers are absent."""
    required = ("opportunities", "feed_projection")
    missing = [name for name in required if not _table_exists(connection, name)]
    if missing:
        return _result("A4", "BLOCKED", reason="required_read_tables_missing", missing=missing)
    try:
        counts = {name: _count(connection, name) for name in ("opportunities", "feed_projection", "match_evaluations", "worker_jobs")}
        # The exact feed query used by storage.feed_query is projection-only.
        from sqlalchemy import text
        connection.execute(text("SELECT opportunity_id, truth_pack_hash FROM feed_projection ORDER BY opportunity_id, truth_pack_hash LIMIT 25")).fetchall()
        connection.execute(text("SELECT id FROM opportunities ORDER BY id LIMIT 25")).fetchall()
        failed_jobs = int(connection.execute(text("SELECT count(*) FROM worker_jobs WHERE status IN ('FAILED','RUNNING')")).fetchone()[0]) if counts["worker_jobs"] is not None else None
        return _result("A4", "PASS", read_model="persisted_sql_only", counts=counts, failed_or_stuck_jobs=failed_jobs, worker_started=False)
    except Exception:
        return _result("A4", "FAIL", reason="persisted_read_probe_failed")


def prove_a5(connection: Any, *, source_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check source isolation and durable failure visibility.

    ``source_probe`` is the injected real handler/runner seam in integration
    tests.  Without it, a live database cannot prove source execution occurred.
    """
    if source_probe is None:
        return _result("A5", "BLOCKED", reason="real_poll_handler_probe_not_supplied")
    try:
        observed = source_probe()
        if observed.get("bad_failed") and observed.get("good_persisted") and observed.get("runner_continued"):
            return _result("A5", "PASS", **{k: observed[k] for k in sorted(observed)})
        return _result("A5", "FAIL", reason="source_isolation_invariant_failed")
    except Exception:
        return _result("A5", "FAIL", reason="source_isolation_probe_failed")


def prove_a6(connection: Any, *, idempotency_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check repeat-poll identity/content invariants through an injected seam."""
    if idempotency_probe is None:
        return _result("A6", "BLOCKED", reason="real_persist_batch_probe_not_supplied")
    try:
        observed = idempotency_probe()
        required = ("stable_identity", "stable_provenance", "changed_content_reverified", "no_duplicate_identity")
        if all(observed.get(key) for key in required):
            return _result("A6", "PASS", **{k: observed[k] for k in sorted(observed)})
        return _result("A6", "FAIL", reason="poll_idempotency_invariant_failed", observed=observed)
    except Exception:
        return _result("A6", "FAIL", reason="poll_idempotency_probe_failed")


def run(dsn: str | None = None, *, source_probe=None, idempotency_probe=None) -> dict[str, Any]:
    """Run all scenarios; connection and probe failures remain explicit."""
    dsn = dsn or os.environ.get("OPPORTUNITYOS_DB_URL")
    if not dsn:
        return {"format": 1, "scenarios": [_result(name, "BLOCKED", reason="postgres_dsn_missing") for name in SCENARIOS], "status": "BLOCKED"}
    connection = None
    try:
        connection = _connect(dsn)
        results = [prove_a4(connection), prove_a5(connection, source_probe=source_probe), prove_a6(connection, idempotency_probe=idempotency_probe)]
    except Exception:
        results = [_result(name, "BLOCKED", reason="postgres_connection_unavailable") for name in SCENARIOS]
    finally:
        if connection is not None:
            connection.close()
    states = {item["state"] for item in results}
    status = "FAIL" if "FAIL" in states else "BLOCKED" if "BLOCKED" in states else "PASS"
    return {"format": 1, "scenarios": results, "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-env", default="OPPORTUNITYOS_DB_URL")
    args = parser.parse_args(argv)
    report = run(os.environ.get(args.dsn_env))
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
