"""Low-egress Storage V2 representative-source measurements and archive proof.

All database reads are bounded aggregates or metadata-only rows scoped to the
requested source. The verifier downloads only that source's current cold
objects, with hard object-count and byte ceilings; it never exports the corpus.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from storage.cold_storage import client_from_env, get as get_cold_object, unpack
from storage.engine import get_engine, get_production_db_url, get_session_factory

MAX_ARCHIVE_OBJECTS = 50
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
HISTORICAL_CORPUS_SIZE = 26_000
DATABASE_HARD_BUDGET = 200 * 1024 * 1024


def _scalar(connection, sql: str, params: dict[str, Any] | None = None) -> Any:
    return connection.execute(text(sql), params or {}).scalar_one()


def snapshot(connection, *, source_id: str) -> dict[str, Any]:
    """Return compact aggregate measurements without reading source bodies."""
    db_bytes = int(_scalar(connection, "SELECT pg_database_size(current_database())"))
    revision = _scalar(connection, "SELECT version_num FROM public.alembic_version LIMIT 1")
    relation_rows = connection.execute(text("""
        SELECT n.nspname AS schema_name,
               c.relname AS relation,
               pg_total_relation_size(c.oid)::bigint AS total_bytes,
               pg_relation_size(c.oid)::bigint AS heap_bytes,
               pg_indexes_size(c.oid)::bigint AS index_bytes,
               COALESCE(s.n_live_tup, 0)::bigint AS estimated_live_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        WHERE n.nspname IN ('public', 'storage') AND c.relkind IN ('r', 'm')
        ORDER BY pg_total_relation_size(c.oid) DESC, c.relname
        LIMIT 20
    """)).mappings().all()
    index_rows = connection.execute(text("""
        SELECT n.nspname AS index_schema,
               idx.relname AS index_name,
               n.nspname AS table_schema,
               tbl.relname AS table_name,
               pg_relation_size(idx.oid)::bigint AS bytes
        FROM pg_index i
        JOIN pg_class idx ON idx.oid = i.indexrelid
        JOIN pg_class tbl ON tbl.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = tbl.relnamespace
        WHERE n.nspname IN ('public', 'storage')
        ORDER BY pg_relation_size(idx.oid) DESC, idx.relname
        LIMIT 20
    """)).mappings().all()

    row = connection.execute(text("""
        SELECT
          (SELECT count(*) FROM public.opportunities) AS opportunities,
          (SELECT count(*) FROM public.opportunities WHERE lifecycle_tier='hot') AS hot_opportunities,
          (SELECT count(*) FROM public.opportunities WHERE lifecycle_tier='cold') AS cold_opportunities,
          (SELECT count(*) FROM public.opportunities WHERE lifecycle_tier='protected') AS protected_opportunities,
          (SELECT count(*) FROM public.opportunities WHERE source_id=:source_id) AS source_opportunities,
          (SELECT count(*) FROM public.opportunities WHERE source_id=:source_id AND lifecycle_tier='hot') AS source_hot,
          (SELECT count(*) FROM public.opportunities WHERE source_id=:source_id AND lifecycle_tier='cold') AS source_cold,
          (SELECT count(*) FROM public.opportunities WHERE source_id=:source_id AND lifecycle_tier='protected') AS source_protected,
          (SELECT count(*) FROM public.feed_projection) AS feed_rows,
          (SELECT count(*) FROM public.feed_projection f JOIN public.opportunities o ON o.id=f.opportunity_id WHERE o.source_id=:source_id) AS source_feed_rows,
          (SELECT count(*) FROM public.feed_projection WHERE truth_pack_hash='active') AS synthetic_active_feed_rows,
          (SELECT COALESCE(max(n),0) FROM (SELECT count(*) AS n FROM public.feed_projection GROUP BY opportunity_id) d) AS max_projections_per_opportunity,
          (SELECT count(*) FROM public.match_evaluations) AS evaluation_rows,
          (SELECT count(*) FROM public.match_evaluations e JOIN public.opportunities o ON o.id=e.opportunity_id WHERE o.source_id=:source_id) AS source_evaluation_rows,
          (SELECT COALESCE(max(n),0) FROM (SELECT count(*) AS n FROM public.match_evaluations GROUP BY opportunity_id) d) AS max_evaluations_per_opportunity,
          (SELECT count(*) FROM public.field_provenances) AS provenance_rows,
          (SELECT count(*) FROM public.field_provenances p JOIN public.opportunities o ON o.id=p.opportunity_id WHERE o.source_id=:source_id) AS source_provenance_rows,
          (SELECT count(*) FROM public.opportunity_cold_archive) AS cold_archive_rows,
          (SELECT count(*) FROM public.opportunity_cold_archive a JOIN public.opportunities o ON o.id=a.opportunity_id WHERE o.source_id=:source_id AND o.lifecycle_tier='cold') AS source_cold_archive_rows,
          (SELECT COALESCE(sum(compressed_size_bytes),0) FROM public.opportunity_cold_archive) AS compressed_archive_bytes,
          (SELECT COALESCE(sum(a.compressed_size_bytes),0) FROM public.opportunity_cold_archive a JOIN public.opportunities o ON o.id=a.opportunity_id WHERE o.source_id=:source_id AND o.lifecycle_tier='cold') AS source_compressed_archive_bytes,
          (SELECT count(*) FROM public.opportunities o WHERE o.lifecycle_tier='cold' AND o.description IS NOT NULL) AS cold_description_rows,
          (SELECT count(*) FROM public.opportunities o WHERE o.lifecycle_tier='cold' AND o.raw_payload_json IS NOT NULL) AS cold_raw_payload_rows,
          (SELECT count(*) FROM public.opportunities o WHERE o.source_id=:source_id AND o.lifecycle_tier='cold' AND (o.description IS NOT NULL OR o.raw_payload_json IS NOT NULL)) AS source_cold_body_rows,
          (SELECT count(*) FROM public.field_provenances p JOIN public.opportunities o ON o.id=p.opportunity_id WHERE o.lifecycle_tier='cold') AS cold_provenance_rows,
          (SELECT count(*) FROM public.field_provenances p JOIN public.opportunities o ON o.id=p.opportunity_id WHERE o.source_id=:source_id AND o.lifecycle_tier='cold') AS source_cold_provenance_rows,
          (SELECT count(*) FROM public.match_evaluations e JOIN public.opportunities o ON o.id=e.opportunity_id WHERE o.lifecycle_tier='cold' AND (e.dimension_scores_json IS NOT NULL OR e.evaluation_detail_json IS NOT NULL)) AS cold_verbose_evaluation_rows,
          (SELECT count(*) FROM public.match_evaluations e JOIN public.opportunities o ON o.id=e.opportunity_id WHERE o.source_id=:source_id AND o.lifecycle_tier='cold' AND (e.dimension_scores_json IS NOT NULL OR e.evaluation_detail_json IS NOT NULL)) AS source_cold_verbose_evaluation_rows,
          (SELECT COALESCE(sum(length(e.reasons_json)),0) FROM public.match_evaluations e JOIN public.opportunities o ON o.id=e.opportunity_id WHERE o.lifecycle_tier='cold') AS cold_reason_bytes,
          (SELECT COALESCE(max(length(e.reasons_json)),0) FROM public.match_evaluations e JOIN public.opportunities o ON o.id=e.opportunity_id WHERE o.lifecycle_tier='cold') AS cold_max_reason_bytes,
          (SELECT COALESCE(max(length(e.reasons_json)),0) FROM public.match_evaluations e JOIN public.opportunities o ON o.id=e.opportunity_id WHERE o.source_id=:source_id AND o.lifecycle_tier='cold') AS source_cold_max_reason_bytes,
          (SELECT count(*) FROM public.founder_activity_events) AS founder_activity_rows,
          (SELECT count(*) FROM public.founder_feedback) AS founder_feedback_rows,
          (SELECT count(*) FROM public.founder_triage_states) AS founder_triage_rows,
          (SELECT count(*) FROM public.founder_opportunity_views) AS founder_view_rows,
          (SELECT count(*) FROM public.source_poll_runs WHERE source_id=:source_id) AS source_poll_run_count,
          (SELECT count(*) FROM public.source_schedules) AS source_schedules,
          (SELECT count(*) FROM public.worker_jobs) AS worker_jobs_total
    """), {"source_id": source_id}).mappings().one()
    source_poll = connection.execute(text("""
        SELECT status, raw_ingested, unique_opportunities, inserted, unchanged, updated,
               finished_at
        FROM public.source_poll_runs
        WHERE source_id=:source_id
        ORDER BY started_at DESC
        LIMIT 1
    """), {"source_id": source_id}).mappings().first()
    source_poll_statuses = connection.execute(text("""
        SELECT status, count(*)::bigint AS count
        FROM public.source_poll_runs
        GROUP BY status
        ORDER BY status
    """)).mappings().all()
    source_coverage = int(_scalar(connection, """
        SELECT count(*) FROM (
          SELECT DISTINCT ON (source_id) source_id, status
          FROM public.source_poll_runs
          ORDER BY source_id, started_at DESC
        ) latest
        WHERE status='ok'
    """))
    dead_letter_error_classes = connection.execute(text("""
        SELECT CASE
                 WHEN error_message ~* 'EMAXCONNSESSION' THEN 'EMAXCONNSESSION'
                 WHEN error_message ~* 'UniqueViolation' THEN 'UniqueViolation'
                 WHEN error_message ~* 'ReadOnlySqlTransaction' THEN 'ReadOnlySqlTransaction'
                 WHEN error_message ~* 'OperationalError' THEN 'OperationalError'
                 WHEN error_message ~* 'Timeout|timed out' THEN 'Timeout'
                 WHEN error_message IS NULL OR btrim(error_message)='' THEN 'NoErrorText'
                 ELSE 'Other'
               END AS error_class,
               count(*)::bigint AS count
        FROM public.worker_jobs
        WHERE status='DEAD_LETTER'
        GROUP BY 1
        ORDER BY 1
    """)).mappings().all()
    queue = connection.execute(text("""
        SELECT count(*) FILTER (WHERE status='PENDING') AS pending,
               count(*) FILTER (WHERE status='RETRY') AS retry,
               count(*) FILTER (WHERE status='RUNNING') AS running,
               count(*) FILTER (WHERE status='RUNNING' AND lease_expires_at < now()) AS expired_leases,
               count(*) FILTER (WHERE status='DEAD_LETTER') AS dead_letter,
               EXTRACT(epoch FROM (now() - (min(run_after) FILTER (
                 WHERE status IN ('PENDING','RETRY') AND run_after <= now()
               ))))::bigint AS oldest_due_age_seconds
        FROM public.worker_jobs
    """)).mappings().one()
    has_storage_objects = bool(_scalar(connection, "SELECT to_regclass('storage.objects') IS NOT NULL"))
    storage = connection.execute(text("""
        SELECT bucket_id,
               count(*)::bigint AS object_count,
               COALESCE(sum(CASE WHEN metadata->>'size' ~ '^[0-9]+$' THEN (metadata->>'size')::bigint ELSE 0 END),0)::bigint AS object_bytes
        FROM storage.objects
        WHERE bucket_id IN ('opportunity-artifacts','founder-cv-portfolio')
        GROUP BY bucket_id
        ORDER BY bucket_id
    """)).mappings().all() if has_storage_objects else []
    relation_bytes = int(_scalar(connection, """
        SELECT COALESCE(sum(pg_total_relation_size(c.oid)),0)::bigint
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','m')
    """))
    application_relation_bytes = int(_scalar(connection, """
        SELECT COALESCE(sum(pg_total_relation_size(c.oid)),0)::bigint
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname IN ('public','storage') AND c.relkind IN ('r','m')
    """))

    return {
        "source_id": source_id,
        "database_revision": str(revision) if revision is not None else None,
        "database_bytes": db_bytes,
        "public_relation_total_bytes": relation_bytes,
        "application_relation_total_bytes": application_relation_bytes,
        "top_relations": [dict(item) for item in relation_rows],
        "top_indexes": [dict(item) for item in index_rows],
        "counts": dict(row),
        "latest_source_poll": dict(source_poll) if source_poll is not None else None,
        "source_poll_status_counts": {item["status"]: int(item["count"]) for item in source_poll_statuses},
        "successful_source_coverage": source_coverage,
        "dead_letter_error_class_counts": {
            item["error_class"]: int(item["count"]) for item in dead_letter_error_classes
        },
        "queue": dict(queue),
        "storage_buckets": {item["bucket_id"]: {
            "object_count": int(item["object_count"]),
            "object_bytes": int(item["object_bytes"]),
        } for item in storage},
    }


def verify_source_archives(connection, *, source_id: str) -> dict[str, Any]:
    """Download and checksum only this source's current cold archive objects."""
    records = connection.execute(text("""
        SELECT o.id AS opportunity_id, o.content_hash,
               a.object_key, a.payload_sha256, a.compressed_size_bytes,
               a.storage_backend
        FROM public.opportunities o
        JOIN public.opportunity_cold_archive a ON a.opportunity_id=o.id
        WHERE o.source_id=:source_id AND o.lifecycle_tier='cold'
        ORDER BY o.id
        LIMIT :max_objects_plus_one
    """), {"source_id": source_id, "max_objects_plus_one": MAX_ARCHIVE_OBJECTS + 1}).mappings().all()
    if len(records) > MAX_ARCHIVE_OBJECTS:
        raise RuntimeError("representative archive count exceeds the bounded verifier limit")
    advertised_bytes = sum(int(row["compressed_size_bytes"] or 0) for row in records)
    if advertised_bytes > MAX_ARCHIVE_BYTES:
        raise RuntimeError("representative archive bytes exceed the bounded verifier limit")
    if any(row["storage_backend"] != "supabase_storage" or not row["object_key"] for row in records):
        raise RuntimeError("cold source row is not backed by a private Storage object")

    client = client_from_env()
    client.ensure_private_bucket()
    verified_bytes = 0
    for row in records:
        compressed = get_cold_object(row["object_key"], row["payload_sha256"], client=client)
        if len(compressed) != int(row["compressed_size_bytes"]):
            raise RuntimeError("cold archive object byte count does not match database metadata")
        payload = unpack(
            compressed,
            row["payload_sha256"],
            opportunity_id=row["opportunity_id"],
            content_hash=row["content_hash"],
        )
        description = str(payload.get("canonical_description") or "").strip().casefold()
        if description == "[archived]":
            raise RuntimeError("cold archive contains a forbidden placeholder description")
        verified_bytes += len(compressed)
    return {
        "source_id": source_id,
        "archive_objects_verified": len(records),
        "compressed_bytes_downloaded": verified_bytes,
        "sha256_identity_verified": True,
        "download_scope": "source-scoped-cold-archives-only",
    }


def compare_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
    archive_proof: dict[str, Any],
    capacity_benchmark: dict[str, Any],
) -> dict[str, Any]:
    """Apply direct-tier checks and the physical 26k-row benchmark gate."""
    if before.get("source_id") != after.get("source_id") or before.get("source_id") != archive_proof.get("source_id"):
        raise ValueError("representative-source evidence scopes do not match")
    source_id = before["source_id"]
    b = before["counts"]
    a = after["counts"]
    poll = after.get("latest_source_poll") or {}
    unique = int(poll.get("unique_opportunities") or 0)
    raw = int(poll.get("raw_ingested") or 0)
    if poll.get("status") != "ok" or raw < 1 or unique < 1:
        raise RuntimeError("representative poll did not produce a successful non-empty unique source sample")

    archive_objects = max(0, int(a["source_cold_archive_rows"]) - int(b["source_cold_archive_rows"]))
    archive_bytes = max(0, int(a["source_compressed_archive_bytes"]) - int(b["source_compressed_archive_bytes"]))
    hot = int(a["source_hot"])
    cold = int(a["source_cold"])
    protected = int(a["source_protected"])
    db_growth = max(
        0,
        int(after["database_bytes"]) - int(before["database_bytes"]),
        int(after["public_relation_total_bytes"]) - int(before["public_relation_total_bytes"]),
    )
    bytes_per_unique = db_growth / unique
    naive_linear_projection = int(before["database_bytes"] + bytes_per_unique * HISTORICAL_CORPUS_SIZE)
    benchmark_population = int(capacity_benchmark.get("population_opportunities") or 0)
    benchmark_increment = int(capacity_benchmark.get("benchmark_growth_bytes") or 0)
    projected_bytes = int(after["database_bytes"]) + benchmark_increment
    benchmark_checks = capacity_benchmark.get("checks") or {}
    checks = {
        "no_synthetic_active_feed": int(a["synthetic_active_feed_rows"]) == 0,
        "at_most_one_current_projection": int(a["max_projections_per_opportunity"]) <= 1,
        "at_most_one_current_evaluation": int(a["max_evaluations_per_opportunity"]) <= 1,
        "cold_relational_bodies_absent": int(a["cold_description_rows"]) == 0 and int(a["cold_raw_payload_rows"]) == 0,
        "cold_relational_provenance_absent": int(a["cold_provenance_rows"]) == 0,
        "cold_verbose_evaluation_absent": int(a["cold_verbose_evaluation_rows"]) == 0,
        "cold_reason_representation_compact": int(a["cold_max_reason_bytes"]) <= 512,
        "source_cold_reason_representation_compact": int(a["source_cold_max_reason_bytes"]) <= 512,
        "source_cold_relational_bodies_absent": int(a["source_cold_body_rows"]) == 0,
        "source_cold_provenance_absent": int(a["source_cold_provenance_rows"]) == 0,
        "source_cold_verbose_evaluation_absent": int(a["source_cold_verbose_evaluation_rows"]) == 0,
        "archive_checksum_and_identity_verified": archive_proof.get("sha256_identity_verified") is True,
        "archive_download_source_scoped": archive_proof.get("download_scope") == "source-scoped-cold-archives-only",
        "physical_database_within_hard_budget": int(after["database_bytes"]) <= DATABASE_HARD_BUDGET,
        "physical_26k_benchmark_passed": (
            capacity_benchmark.get("status") == "PASS"
            and benchmark_population == HISTORICAL_CORPUS_SIZE
            and capacity_benchmark.get("source_id") == source_id
            and int(capacity_benchmark.get("sample_unique_opportunities") or 0) == unique
            and int(capacity_benchmark.get("benchmark_growth_bytes") or 0) > 0
            and int(capacity_benchmark.get("database_bytes_after_population") or 0)
                > int(capacity_benchmark.get("benchmark_database_bytes_empty_schema") or 0)
            and bool(benchmark_checks)
            and all(value is True for value in benchmark_checks.values())
        ),
        "projected_database_within_hard_budget": projected_bytes <= DATABASE_HARD_BUDGET,
        "benchmark_schema_matches_live_head": (
            capacity_benchmark.get("database_revision") == after.get("database_revision")
            and capacity_benchmark.get("database_revision") == "0023_alembic_access"
        ),
    }
    if int(archive_proof.get("archive_objects_verified") or 0) < archive_objects:
        checks["all_new_cold_archives_verified"] = False
    else:
        checks["all_new_cold_archives_verified"] = True
    report = {
        "source_id": source_id,
        "status": "PASS" if all(checks.values()) else "STOP_FOR_ARCHITECTURE_REVIEW",
        "before_database_bytes": int(before["database_bytes"]),
        "after_database_bytes": int(after["database_bytes"]),
        "before_public_relation_bytes": int(before["public_relation_total_bytes"]),
        "after_public_relation_bytes": int(after["public_relation_total_bytes"]),
        "database_growth_bytes": db_growth,
        "raw_opportunities_received": raw,
        "unique_opportunities": unique,
        "source_opportunities_after": int(a["source_opportunities"]),
        "hot_opportunities_after": hot,
        "cold_opportunities_after": cold,
        "protected_opportunities_after": protected,
        "feed_visible_opportunities_after": int(a["source_feed_rows"]),
        "current_evaluations_after": int(a["source_evaluation_rows"]),
        "cold_archive_objects_created": archive_objects,
        "compressed_archive_bytes_created": archive_bytes,
        "source_cold_archive_objects_after": int(a["source_cold_archive_rows"]),
        "source_cold_archive_bytes_after": int(a["source_compressed_archive_bytes"]),
        "average_compressed_bytes_per_unique_received": round(archive_bytes / unique, 2),
        "average_compressed_bytes_per_cold_archived": round(archive_bytes / archive_objects, 2) if archive_objects else 0,
        "archive_bytes_downloaded_for_verification": int(archive_proof.get("compressed_bytes_downloaded") or 0),
        "extrapolation_corpus_opportunities": HISTORICAL_CORPUS_SIZE,
        "naive_small_sample_linear_projection_bytes": naive_linear_projection,
        "capacity_benchmark_growth_bytes": benchmark_increment,
        "capacity_benchmark_database_bytes_after_population": capacity_benchmark.get("database_bytes_after_population"),
        "capacity_benchmark_application_relation_bytes": capacity_benchmark.get("benchmark_application_relation_bytes"),
        "projected_cold_archive_storage_bytes": capacity_benchmark.get("projected_cold_archive_storage_bytes"),
        "projected_database_preferred_budget_pass": projected_bytes <= 150 * 1024 * 1024,
        "projected_database_bytes": projected_bytes,
        "projected_database_mib": round(projected_bytes / (1024 * 1024), 2),
        "capacity_benchmark_top_relations": capacity_benchmark.get("top_relations", []),
        "capacity_benchmark_top_indexes": capacity_benchmark.get("top_indexes", []),
        "capacity_benchmark_checks": benchmark_checks,
        "capacity_window_review": (
            "preferred<=150MiB"
            if projected_bytes <= 150 * 1024 * 1024
            else "inspected measured relation/index profile; hard ceiling<=200MiB"
            if projected_bytes <= DATABASE_HARD_BUDGET
            else "stop before full bootstrap"
        ),
        "checks": checks,
        "full_registry_enqueue_performed": False,
        "corpus_wide_storage_download_performed": False,
        "placeholder_input_scoring": "blocked by persist_evaluated_batch guard; regression-tested",
    }
    return report


def _connect():
    raw = os.environ.get("OPOS_TARGET_DB_URL") or os.environ.get("CLOUD_DATABASE_URL")
    if not raw:
        raise RuntimeError("database URL secret is unavailable")
    engine = get_engine(
        get_production_db_url(raw),
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        application_name="opportunityos-fr007-source-gate",
    )
    return engine, get_session_factory(engine)()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("snapshot", "verify-archives", "compare"))
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--archive-proof", type=Path)
    parser.add_argument("--capacity-benchmark", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "compare":
        if not all((args.before, args.after, args.archive_proof, args.capacity_benchmark)):
            parser.error("compare requires --before, --after, --archive-proof, and --capacity-benchmark")
        result = compare_snapshots(
            json.loads(args.before.read_text(encoding="utf-8")),
            json.loads(args.after.read_text(encoding="utf-8")),
            json.loads(args.archive_proof.read_text(encoding="utf-8")),
            json.loads(args.capacity_benchmark.read_text(encoding="utf-8")),
        )
        encoded = json.dumps(result, sort_keys=True, default=str)
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        if result["status"] != "PASS":
            raise SystemExit("representative-source economics or invariant gate did not pass")
        return 0

    engine = None
    session = None
    try:
        engine, session = _connect()
        if args.mode == "snapshot":
            result = snapshot(session.connection(), source_id=args.source_id)
        else:
            result = verify_source_archives(session.connection(), source_id=args.source_id)
    except Exception as exc:
        raise SystemExit(f"source-gate operation failed ({type(exc).__name__}); sensitive values suppressed") from None
    finally:
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()

    encoded = json.dumps(result, sort_keys=True, default=str)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
