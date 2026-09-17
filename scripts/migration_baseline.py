"""Read-only, allowlisted structural PostgreSQL migration snapshots."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


FORMAT = 1
SAMPLE_SIZE = 32
TABLES = (
    "opportunities", "field_provenances", "match_evaluations",
    "source_poll_runs", "source_states", "sources", "source_occurrences",
    "founder_opportunity_views", "founder_triage_states", "founder_filter_settings",
    "founder_facets", "founder_saved_views", "founder_feedback",
    "outbound_actions", "idempotency_reservations", "inbound_evidence",
    "pipeline_events", "founder_notifications", "inbox_checkpoints",
    "reconciliation_records", "artifact_cache", "worker_jobs",
    "opportunity_families", "feed_projection",
)
HASH = re.compile(r"^[0-9a-fA-F]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
CHECKS = {
    "duplicate_opportunity_ids": ("opportunities", ("id",)),
    "duplicate_source_identity": ("source_occurrences", ("source_id", "source_item_id")),
    "duplicate_evaluations": ("match_evaluations", ("opportunity_id", "truth_pack_hash")),
    "duplicate_action_keys": ("outbound_actions", ("idempotency_key",)),
    "duplicate_reservation_keys": ("idempotency_reservations", ("idempotency_key",)),
    "duplicate_triage": ("founder_triage_states", ("opportunity_id",)),
}
REFERENCES = {
    "orphan_provenances": ("field_provenances", "opportunity_id"),
    "orphan_evaluations": ("match_evaluations", "opportunity_id"),
    "orphan_triage": ("founder_triage_states", "opportunity_id"),
    "orphan_feedback": ("founder_feedback", "opportunity_id"),
    "orphan_feed_projection": ("feed_projection", "opportunity_id"),
}


def _scalar(cursor, sql):
    cursor.execute(sql)
    return cursor.fetchone()[0]


def inspect(connection):
    """Inspect inside one PostgreSQL read-only, repeatable-read transaction."""
    cursor = connection.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("SELECT table_name, column_name FROM information_schema.columns "
                       "WHERE table_schema = current_schema()")
        columns = {}
        for table, column in cursor.fetchall():
            if table in TABLES or table == "alembic_version":
                columns.setdefault(table, set()).add(column)

        result = {"format": FORMAT, "alembic_revision": None, "tables": {},
                  "evaluation_coverage": None, "invariants": {}, "opportunity_sample": []}
        if "version_num" in columns.get("alembic_version", set()):
            cursor.execute("SELECT version_num FROM alembic_version ORDER BY version_num")
            revisions = [row[0] for row in cursor.fetchall()]
            if len(revisions) > 1 or any(not isinstance(x, str) or not IDENT.fullmatch(x) for x in revisions):
                raise ValueError("Invalid Alembic revision metadata")
            result["alembic_revision"] = revisions[0] if revisions else None

        for table in TABLES:
            result["tables"][table] = (int(_scalar(cursor, f'SELECT count(*) FROM "{table}"'))
                                        if table in columns else None)

        if {"truth_pack_hash", "opportunity_id"} <= columns.get("match_evaluations", set()):
            cursor.execute("SELECT truth_pack_hash, count(*), count(DISTINCT opportunity_id) "
                           "FROM match_evaluations GROUP BY truth_pack_hash ORDER BY truth_pack_hash")
            coverage = []
            for value, count, distinct_count in cursor.fetchall():
                if not isinstance(value, str) or not HASH.fullmatch(value):
                    raise ValueError("Invalid truth-pack hash metadata")
                coverage.append({"truth_pack_hash": value.lower(), "evaluations": int(count),
                                 "opportunities": int(distinct_count)})
            result["evaluation_coverage"] = coverage

        for name, (table, keys) in CHECKS.items():
            if set(keys) <= columns.get(table, set()):
                group = ", ".join(f'"{key}"' for key in keys)
                result["invariants"][name] = int(_scalar(
                    cursor, f'SELECT count(*) FROM (SELECT 1 FROM "{table}" '
                            f'GROUP BY {group} HAVING count(*) > 1) AS duplicates'))
            else:
                result["invariants"][name] = None
        for name, (table, key) in REFERENCES.items():
            if key in columns.get(table, set()) and "id" in columns.get("opportunities", set()):
                result["invariants"][name] = int(_scalar(
                    cursor, f'SELECT count(*) FROM "{table}" AS child '
                            f'LEFT JOIN opportunities AS parent ON child."{key}" = parent.id '
                            'WHERE parent.id IS NULL'))
            else:
                result["invariants"][name] = None

        if {"id", "content_hash"} <= columns.get("opportunities", set()):
            cursor.execute(f"SELECT id, content_hash FROM opportunities ORDER BY id LIMIT {SAMPLE_SIZE}")
            for opportunity_id, content_hash in cursor.fetchall():
                if (not isinstance(opportunity_id, str) or not IDENT.fullmatch(opportunity_id)
                        or not isinstance(content_hash, str) or not HASH.fullmatch(content_hash)):
                    raise ValueError("Invalid opportunity identity/hash metadata")
                result["opportunity_sample"].append(
                    {"id": opportunity_id, "content_hash": content_hash.lower()})
        cursor.execute("ROLLBACK")
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def compare(baseline, candidate):
    """Return stable mismatch messages; no implicit count or schema allowances."""
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return ["snapshot structure mismatch"]
    expected = {"format", "alembic_revision", "tables", "evaluation_coverage",
                "invariants", "opportunity_sample"}
    if (set(baseline) != expected or set(candidate) != expected
            or not isinstance(baseline.get("tables"), dict)
            or not isinstance(candidate.get("tables"), dict)
            or set(baseline["tables"]) != set(TABLES)
            or set(candidate["tables"]) != set(TABLES)
            or not isinstance(baseline.get("invariants"), dict)
            or not isinstance(candidate.get("invariants"), dict)
            or set(baseline["invariants"]) != set(CHECKS) | set(REFERENCES)
            or set(candidate["invariants"]) != set(CHECKS) | set(REFERENCES)):
        return ["snapshot structure mismatch"]
    if baseline.get("format") != FORMAT or candidate.get("format") != FORMAT:
        return ["snapshot format mismatch"]
    differences = []
    for key in ("alembic_revision", "tables", "evaluation_coverage", "invariants",
                "opportunity_sample"):
        if baseline.get(key) != candidate.get(key):
            if key == "tables" and isinstance(baseline.get(key), dict) and isinstance(candidate.get(key), dict):
                for table in TABLES:
                    if baseline[key].get(table) != candidate[key].get(table):
                        differences.append(f"tables.{table}: mismatch")
            elif key == "invariants" and isinstance(baseline.get(key), dict) and isinstance(candidate.get(key), dict):
                for name in sorted(set(baseline[key]) | set(candidate[key])):
                    if baseline[key].get(name) != candidate[key].get(name):
                        differences.append(f"invariants.{name}: mismatch")
            else:
                differences.append(f"{key}: mismatch")
    return differences


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("snapshot")
    comparison = sub.add_parser("compare")
    comparison.add_argument("baseline")
    comparison.add_argument("candidate")
    args = parser.parse_args(argv)
    try:
        if args.operation == "snapshot":
            url = os.environ.get("OPPORTUNITYOS_DB_URL")
            if not url:
                raise ValueError("Database configuration is missing")
            try:
                import psycopg2
            except ImportError as exc:
                raise ValueError("PostgreSQL driver psycopg2 is unavailable") from exc
            connection = psycopg2.connect(url)
            try:
                data = inspect(connection)
            finally:
                connection.close()
            print(json.dumps(data, sort_keys=True, separators=(",", ":")))
            return 0
        with open(args.baseline, encoding="utf-8") as stream:
            baseline = json.load(stream)
        with open(args.candidate, encoding="utf-8") as stream:
            candidate = json.load(stream)
        differences = compare(baseline, candidate)
        for difference in differences:
            print(difference)
        if differences:
            return 1
        print("PARITY PASS")
        return 0
    except (Exception, KeyboardInterrupt):
        # Driver exceptions can contain connection strings or server-supplied data.
        print("migration baseline: inspection or input failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
