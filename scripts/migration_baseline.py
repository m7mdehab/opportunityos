"""Read-only, allowlisted structural PostgreSQL migration snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys


FORMAT = 2
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
NULL_FIELDS = {
    "opportunities": ("content_hash", "source_id", "is_stale", "location_country", "remote_scope"),
    "match_evaluations": ("truth_pack_hash", "qualification_decision", "policy_version"),
    "founder_triage_states": ("state",),
    "artifact_cache": ("truth_pack_hash", "payload"),
    "feed_projection": ("opportunity_content_hash", "truth_pack_hash", "qualification_decision"),
}
DECISIONS = ("qualified", "uncertain", "ineligible")
CHECKS.update({
    "duplicate_provenance_identity": ("field_provenances", ("opportunity_id", "field_name", "record_checksum")),
    "duplicate_feed_projection_identity": ("feed_projection", ("opportunity_id", "truth_pack_hash", "projection_version")),
    "duplicate_saved_view_names": ("founder_saved_views", ("name",)),
})
REFERENCES.update({
    "orphan_views": ("founder_opportunity_views", "opportunity_id"),
    "orphan_artifact_metadata": ("artifact_cache", "opportunity_id"),
    "orphan_outbound_actions": ("outbound_actions", "opportunity_id"),
})
UNIQUE_CONSTRAINTS = {
    "field_provenances": "uq_field_provenances_identity",
    "match_evaluations": "uq_match_evaluations_opportunity_truth_pack",
    "feed_projection": "uq_feed_projection_opportunity_truth_pack",
}


def _scalar(cursor, sql):
    cursor.execute(sql)
    return cursor.fetchone()[0]


def inspect(connection):
    """Inspect inside one PostgreSQL read-only, repeatable-read transaction."""
    cursor = connection.cursor()
    try:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("SELECT table_name, column_name FROM information_schema.columns "
                       "WHERE table_schema = 'public'")
        columns = {}
        for table, column in cursor.fetchall():
            if table in TABLES or table == "alembic_version":
                columns.setdefault(table, set()).add(column)

        result = {"format": FORMAT, "alembic_revision": None, "tables": {},
                  "evaluation_coverage": None, "invariants": {}, "opportunity_sample": [],
                  "identity_digests": {"opportunities": None, "evaluation_bindings": None},
                  "decision_distributions": {}, "state_distributions": {},
                  "null_counts": {}, "unique_constraints": {}}
        if "version_num" in columns.get("alembic_version", set()):
            cursor.execute("SELECT version_num FROM public.alembic_version ORDER BY version_num")
            revisions = [row[0] for row in cursor.fetchall()]
            if len(revisions) > 1 or any(not isinstance(x, str) or not IDENT.fullmatch(x) for x in revisions):
                raise ValueError("Invalid Alembic revision metadata")
            result["alembic_revision"] = revisions[0] if revisions else None

        for table in TABLES:
            result["tables"][table] = (int(_scalar(cursor, f'SELECT count(*) FROM public."{table}"'))
                                        if table in columns else None)
        cursor.execute("SELECT table_name, constraint_name FROM information_schema.table_constraints "
                       "WHERE table_schema = 'public' AND constraint_type = 'UNIQUE'")
        present_constraints = set(cursor.fetchall())
        for table, name in UNIQUE_CONSTRAINTS.items():
            result["unique_constraints"][name] = ((table, name) in present_constraints
                                                  if table in columns else None)

        for table, fields in NULL_FIELDS.items():
            for field in fields:
                key = f"{table}.{field}"
                result["null_counts"][key] = (
                    int(_scalar(cursor, f'SELECT count(*) FROM public."{table}" WHERE "{field}" IS NULL'))
                    if field in columns.get(table, set()) else None)

        for table in ("match_evaluations", "feed_projection"):
            field = "qualification_decision"
            if field not in columns.get(table, set()):
                result["decision_distributions"][table] = None
                continue
            cursor.execute(f'SELECT CASE WHEN "{field}" IN '
                           "('qualified','uncertain','ineligible') THEN "
                           f'"{field}" ELSE \'__unexpected__\' END, count(*) '
                           f'FROM public."{table}" GROUP BY 1 ORDER BY 1')
            result["decision_distributions"][table] = {key: int(count) for key, count in cursor.fetchall()}
        if "state" in columns.get("founder_triage_states", set()):
            cursor.execute("SELECT CASE WHEN state IN ('dismissed','snoozed') THEN state "
                           "ELSE '__unexpected__' END, count(*) "
                           "FROM public.founder_triage_states GROUP BY 1 ORDER BY 1")
            result["state_distributions"]["founder_triage_states"] = {
                key: int(count) for key, count in cursor.fetchall()}
        else:
            result["state_distributions"]["founder_triage_states"] = None

        def digest_rows(sql, validators):
            cursor.execute(sql)
            digest = hashlib.sha256()
            while True:
                rows = cursor.fetchmany(1024)
                if not rows:
                    break
                for row in rows:
                    if len(row) != len(validators) or any(not valid(value) for valid, value in zip(validators, row)):
                        raise ValueError("Invalid canonical identity metadata")
                    digest.update(json.dumps(row, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
                    digest.update(b"\n")
            return digest.hexdigest()

        valid_id = lambda value: isinstance(value, str) and bool(IDENT.fullmatch(value))
        valid_hash = lambda value: isinstance(value, str) and bool(HASH.fullmatch(value))
        valid_decision = lambda value: value in DECISIONS
        if {"id", "content_hash"} <= columns.get("opportunities", set()):
            result["identity_digests"]["opportunities"] = digest_rows(
                "SELECT id, content_hash FROM public.opportunities ORDER BY id", (valid_id, valid_hash))
        if {"opportunity_id", "truth_pack_hash", "qualification_decision"} <= columns.get("match_evaluations", set()):
            result["identity_digests"]["evaluation_bindings"] = digest_rows(
                "SELECT opportunity_id, truth_pack_hash, qualification_decision "
                "FROM public.match_evaluations ORDER BY opportunity_id, truth_pack_hash",
                (valid_id, valid_hash, valid_decision))

        if {"truth_pack_hash", "opportunity_id"} <= columns.get("match_evaluations", set()):
            cursor.execute("SELECT truth_pack_hash, count(*), count(DISTINCT opportunity_id) "
                           "FROM public.match_evaluations GROUP BY truth_pack_hash ORDER BY truth_pack_hash")
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
                    cursor, f'SELECT count(*) FROM (SELECT 1 FROM public."{table}" '
                            f'GROUP BY {group} HAVING count(*) > 1) AS duplicates'))
            else:
                result["invariants"][name] = None
        for name, (table, key) in REFERENCES.items():
            if key in columns.get(table, set()) and "id" in columns.get("opportunities", set()):
                result["invariants"][name] = int(_scalar(
                    cursor, f'SELECT count(*) FROM public."{table}" AS child '
                            f'LEFT JOIN public.opportunities AS parent ON child."{key}" = parent.id '
                            'WHERE parent.id IS NULL'))
            else:
                result["invariants"][name] = None

        if {"id", "content_hash"} <= columns.get("opportunities", set()):
            cursor.execute(f"SELECT id, content_hash FROM public.opportunities ORDER BY id LIMIT {SAMPLE_SIZE}")
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
                "invariants", "opportunity_sample", "identity_digests",
                "decision_distributions", "state_distributions", "null_counts", "unique_constraints"}
    if (set(baseline) != expected or set(candidate) != expected
            or not isinstance(baseline.get("tables"), dict)
            or not isinstance(candidate.get("tables"), dict)
            or set(baseline["tables"]) != set(TABLES)
            or set(candidate["tables"]) != set(TABLES)
            or not isinstance(baseline.get("invariants"), dict)
            or not isinstance(candidate.get("invariants"), dict)
            or set(baseline["invariants"]) != set(CHECKS) | set(REFERENCES)
            or set(candidate["invariants"]) != set(CHECKS) | set(REFERENCES)
            or not isinstance(baseline.get("unique_constraints"), dict)
            or not isinstance(candidate.get("unique_constraints"), dict)
            or set(baseline["unique_constraints"]) != set(UNIQUE_CONSTRAINTS.values())
            or set(candidate["unique_constraints"]) != set(UNIQUE_CONSTRAINTS.values())):
        return ["snapshot structure mismatch"]
    if baseline.get("format") != FORMAT or candidate.get("format") != FORMAT:
        return ["snapshot format mismatch"]
    differences = []
    for key in ("alembic_revision", "tables", "evaluation_coverage", "invariants",
                "opportunity_sample", "identity_digests", "decision_distributions", "null_counts",
                "unique_constraints", "state_distributions"):
        if baseline.get(key) != candidate.get(key):
            if key == "tables" and isinstance(baseline.get(key), dict) and isinstance(candidate.get(key), dict):
                for table in TABLES:
                    if baseline[key].get(table) != candidate[key].get(table):
                        differences.append(f"tables.{table}: mismatch")
            elif key in ("invariants", "identity_digests", "decision_distributions", "state_distributions", "null_counts", "unique_constraints") and isinstance(baseline.get(key), dict) and isinstance(candidate.get(key), dict):
                for name in sorted(set(baseline[key]) | set(candidate[key])):
                    if baseline[key].get(name) != candidate[key].get(name):
                        differences.append(f"{key}.{name}: mismatch")
            else:
                differences.append(f"{key}: mismatch")
    for label, snapshot in (("baseline", baseline), ("candidate", candidate)):
        for name, count in sorted(snapshot["invariants"].items()):
            if count is not None and count != 0:
                differences.append(f"{label}.invariants.{name}: nonzero")
        for name, present in sorted(snapshot["unique_constraints"].items()):
            if present is False:
                differences.append(f"{label}.unique_constraints.{name}: absent")
        for table, distribution in sorted(snapshot["decision_distributions"].items()):
            if isinstance(distribution, dict) and distribution.get("__unexpected__", 0):
                differences.append(f"{label}.decision_distributions.{table}: unexpected value")
        for table, distribution in sorted(snapshot["state_distributions"].items()):
            if isinstance(distribution, dict) and distribution.get("__unexpected__", 0):
                differences.append(f"{label}.state_distributions.{table}: unexpected value")
    return differences


def unsupported(snapshot):
    """Structural concepts unavailable in this schema, distinct from parity."""
    names = []
    for group in ("tables", "invariants", "null_counts", "unique_constraints",
                  "decision_distributions", "state_distributions", "identity_digests"):
        values = snapshot.get(group, {})
        if isinstance(values, dict):
            names.extend(f"{group}.{key}" for key, value in values.items() if value is None)
    if snapshot.get("evaluation_coverage") is None:
        names.append("evaluation_coverage")
    if snapshot.get("alembic_revision") is None:
        names.append("alembic_revision")
    return sorted(names)


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
            connection = psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://", 1))
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
        gaps = sorted(set(unsupported(baseline)) | set(unsupported(candidate)))
        if gaps:
            print(json.dumps({"status": "partial", "unsupported": gaps}, sort_keys=True))
            return 3
        print("PARITY PASS")
        return 0
    except (Exception, KeyboardInterrupt):
        # Driver exceptions can contain connection strings or server-supplied data.
        print("migration baseline: inspection or input failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
