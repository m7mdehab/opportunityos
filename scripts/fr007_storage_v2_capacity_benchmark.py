"""Measure a disposable PostgreSQL 26k-row Storage V2 corpus from live aggregates.

The live database contributes only row counts and field-length aggregates. All
benchmark records are deterministic placeholders inserted into an isolated
PostgreSQL service; no synthetic rows are written to the Supabase project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import ARRAY, Boolean, Column, DateTime, MetaData, String, Table, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from opportunity.registry import SourceRegistry
from storage.cold_storage import ARCHIVE_VERSION, archive_key
from storage.engine import get_production_db_url
from storage.feed_projection import FeedProjectionRecord
from storage.models import (
    FieldProvenanceRecord,
    MatchEvaluationRecord,
    OpportunityColdArchiveRecord,
    OpportunityRecord,
    SourcePollRunRecord,
    SourceScheduleRecord,
    WorkerJobRecord,
)

POPULATION = 26_000
DATABASE_HARD_BUDGET = 200 * 1024 * 1024
EXPECTED_HEAD = "0023_alembic_access"
SUCCESSFUL_CORPUS_SOURCE_ID = "__successful_corpus__"
INSERT_BATCH_SIZE = 1000
_benchmark_metadata = MetaData()
STORAGE_OBJECTS = Table(
    "objects",
    _benchmark_metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("bucket_id", String),
    Column("name", String),
    Column("owner", UUID(as_uuid=False)),
    Column("owner_id", String),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    Column("last_accessed_at", DateTime(timezone=True)),
    Column("metadata", JSONB),
    Column("path_tokens", ARRAY(String)),
    Column("version", String),
    Column("user_metadata", JSONB),
    Column("archived_at", DateTime(timezone=True)),
    Column("is_delete_marker", Boolean, nullable=False),
    Column("is_versioned", Boolean, nullable=False),
    schema="storage",
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _alpha_token(value: int) -> str:
    """Return an alphabetic token so PostgreSQL's text search sees variation."""
    output = ""
    current = value + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        output = chr(ord("a") + remainder) + output
    return output or "a"


def _fit(value: str, length: int | None, *, filler: str = "x") -> str:
    target = max(0, int(length or 0))
    if target <= len(value):
        return value[:target]
    return value + filler * (target - len(value))


def _json_of_length(key: str, length: int | None) -> str:
    target = max(2, int(length or 2))
    prefix = json.dumps({key: ""}, separators=(",", ":"))
    overhead = len(prefix)
    if target < overhead:
        return prefix
    return json.dumps({key: "x" * (target - overhead)}, separators=(",", ":"))


def _insert_rows(connection, table, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= INSERT_BATCH_SIZE:
            connection.execute(table.insert(), batch)
            count += len(batch)
            batch.clear()
    if batch:
        connection.execute(table.insert(), batch)
        count += len(batch)
    return count


def _source_scope(source_id: str, alias: str | None = None) -> str:
    column = f"{alias}.source_id" if alias else "source_id"
    if source_id == SUCCESSFUL_CORPUS_SOURCE_ID:
        return f"{column} IN (SELECT DISTINCT source_id FROM public.source_poll_runs WHERE status='ok')"
    return f"{column}=:source_id"


def _source_params(source_id: str) -> dict[str, str]:
    return {} if source_id == SUCCESSFUL_CORPUS_SOURCE_ID else {"source_id": source_id}


def _remaining_capacity_projection(
    *, live_database_bytes: int, benchmark_growth_bytes: int,
    source_growth_bytes: int, current_opportunities: int,
    current_sources: int, target_opportunities: int, target_sources: int,
) -> dict[str, int]:
    if (
        min(live_database_bytes, benchmark_growth_bytes, source_growth_bytes,
            current_opportunities, current_sources) < 0
        or target_opportunities <= 0 or target_sources <= 0
        or source_growth_bytes >= benchmark_growth_bytes
    ):
        raise ValueError("capacity projection has invalid measured population bounds")
    remaining_sources = max(0, target_sources - current_sources)
    remaining_opportunities = max(
        0,
        target_opportunities - current_opportunities,
        math.ceil(target_opportunities * remaining_sources / target_sources),
    )
    non_source_growth = benchmark_growth_bytes - source_growth_bytes
    reserve = 1.01
    remaining_bytes = math.ceil(
        non_source_growth * min(1.0, remaining_opportunities / target_opportunities) * reserve
    ) + math.ceil(source_growth_bytes * remaining_sources / target_sources * reserve)
    return {
        "remaining_sources": remaining_sources,
        "remaining_opportunities": remaining_opportunities,
        "remaining_projected_bytes": remaining_bytes,
        "projected_final_database_bytes": live_database_bytes + remaining_bytes,
    }


def _shape(connection, source_id: str) -> dict[str, Any]:
    corpus_scope = source_id == SUCCESSFUL_CORPUS_SOURCE_ID
    source_filter = _source_scope(source_id)
    successful_source_count_sql = (
        "(SELECT count(DISTINCT source_id) FROM public.source_poll_runs WHERE status='ok')"
        if corpus_scope else
        "(SELECT count(DISTINCT source_id) FROM public.source_poll_runs WHERE source_id=:source_id AND status='ok')"
    )
    poll_status_sql = (
        "'ok'" if corpus_scope else
        "(SELECT status FROM public.source_poll_runs WHERE source_id=:source_id ORDER BY started_at DESC LIMIT 1)"
    )
    poll_unique_sql = (
        f"(SELECT count(*) FROM public.opportunities WHERE {source_filter})" if corpus_scope else
        "(SELECT unique_opportunities FROM public.source_poll_runs WHERE source_id=:source_id ORDER BY started_at DESC LIMIT 1)"
    )
    params = _source_params(source_id)
    state = connection.execute(text(f"""
        SELECT current_database() AS database_name,
               current_user AS database_role,
               current_setting('transaction_read_only') AS transaction_read_only,
               pg_is_in_recovery() AS in_recovery,
               (SELECT version_num FROM public.alembic_version LIMIT 1) AS revision,
               (SELECT count(*) FROM public.opportunities WHERE {source_filter}) AS opportunities,
               (SELECT count(*) FROM public.opportunities WHERE {source_filter} AND lifecycle_tier='hot') AS hot,
               (SELECT count(*) FROM public.opportunities WHERE {source_filter} AND lifecycle_tier='cold') AS cold,
               (SELECT count(*) FROM public.opportunities WHERE {source_filter} AND lifecycle_tier='protected') AS protected,
               {successful_source_count_sql} AS successful_source_count,
               {poll_status_sql} AS poll_status,
               {poll_unique_sql} AS poll_unique
    """), params).mappings().one()
    source_count = int(state["successful_source_count"] or 0)
    minimum_sample_opportunities = 100 if corpus_scope else 20
    if (
        state["database_role"] != "postgres"
        or state["transaction_read_only"] != "off"
        or state["in_recovery"]
        or state["revision"] != EXPECTED_HEAD
        or state["poll_status"] != "ok"
        or source_count < (3 if corpus_scope else 1)
        or int(state["poll_unique"] or 0) < minimum_sample_opportunities
        or int(state["opportunities"] or 0) < minimum_sample_opportunities
        or int(state["hot"] or 0) < 1
        or int(state["cold"] or 0) < 1
    ):
        raise RuntimeError("live sample corpus or schema does not satisfy the benchmark preconditions")

    opp = connection.execute(text(f"""
        SELECT
          count(*) FILTER (WHERE lifecycle_tier='hot') AS hot,
          count(*) FILTER (WHERE lifecycle_tier='cold') AS cold,
          count(*) FILTER (WHERE lifecycle_tier='protected') AS protected,
          round(avg(length(title)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_title,
          round(avg(length(organization)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_org,
          round(avg(length(source_url)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_url,
          round(avg(length(description)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_description,
          round(avg(length(raw_payload_json)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_raw,
          round(avg(length(location_city)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_city,
          round(avg(length(location_region)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_region,
          round(avg(length(remote_scope_regions)) FILTER (WHERE lifecycle_tier IN ('hot','protected')))::int AS hot_remote_regions,
          round(avg(length(title)) FILTER (WHERE lifecycle_tier='cold'))::int AS cold_title,
          round(avg(length(organization)) FILTER (WHERE lifecycle_tier='cold'))::int AS cold_org,
          round(avg(length(source_url)) FILTER (WHERE lifecycle_tier='cold'))::int AS cold_url,
          round(avg(length(location_city)) FILTER (WHERE lifecycle_tier='cold'))::int AS cold_city,
          round(avg(length(location_region)) FILTER (WHERE lifecycle_tier='cold'))::int AS cold_region,
          round(avg(length(remote_scope_regions)) FILTER (WHERE lifecycle_tier='cold'))::int AS cold_remote_regions
        FROM public.opportunities WHERE {source_filter}
    """), params).mappings().one()
    evaluation = connection.execute(text(f"""
        SELECT
          round(avg(length(e.reasons_json)) FILTER (WHERE o.lifecycle_tier IN ('hot','protected')))::int AS hot_reasons,
          round(avg(length(e.dimension_scores_json)) FILTER (WHERE o.lifecycle_tier IN ('hot','protected')))::int AS hot_dimensions,
          round(avg(length(e.evaluation_detail_json)) FILTER (WHERE o.lifecycle_tier IN ('hot','protected')))::int AS hot_detail,
          round(avg(length(e.reasons_json)) FILTER (WHERE o.lifecycle_tier='cold'))::int AS cold_reasons
        FROM public.match_evaluations e
        JOIN public.opportunities o ON o.id=e.opportunity_id
        WHERE {_source_scope(source_id, 'o')}
    """), params).mappings().one()
    provenance = connection.execute(text(f"""
        SELECT count(*) AS rows,
               round(avg(length(p.raw_value)))::int AS raw_value,
               round(avg(length(p.normalized_value)))::int AS normalized_value,
               round(avg(length(p.raw_pointer)))::int AS raw_pointer,
               round(avg(length(p.rule_id)))::int AS rule_id
        FROM public.field_provenances p
        JOIN public.opportunities o ON o.id=p.opportunity_id
        WHERE {_source_scope(source_id, 'o')} AND o.lifecycle_tier IN ('hot','protected')
    """), params).mappings().one()
    archive = connection.execute(text(f"""
        SELECT count(*) AS rows,
               round(avg(compressed_size_bytes))::int AS compressed_bytes,
               round(avg(original_size_bytes))::int AS original_bytes,
               round(avg(length(object_key)))::int AS object_key_length
        FROM public.opportunity_cold_archive a
        JOIN public.opportunities o ON o.id=a.opportunity_id
        WHERE {_source_scope(source_id, 'o')} AND o.lifecycle_tier='cold'
    """), params).mappings().one()
    storage_objects = connection.execute(text("""
        SELECT count(*) AS rows,
               round(avg(pg_column_size(o)))::int AS tuple_bytes,
               round(avg(pg_column_size(metadata)))::int AS metadata_bytes,
               round(avg(length(name)))::int AS object_key_length,
               round(avg(cardinality(path_tokens)))::int AS path_segments,
               round(avg(length(version)))::int AS version_length
        FROM storage.objects o
        WHERE bucket_id='opportunity-artifacts' AND archived_at IS NULL
    """)).mappings().one()
    poll_filter = (
        "source_id IN (SELECT DISTINCT source_id FROM public.source_poll_runs WHERE status='ok') AND status='ok'"
        if corpus_scope else "source_id=:source_id"
    )
    poll = connection.execute(text(f"""
        SELECT round(avg(raw_ingested))::int AS raw_ingested,
               round(avg(unique_opportunities))::int AS unique_opportunities
        FROM public.source_poll_runs WHERE {poll_filter}
    """), params).mappings().one()
    return {
        "live_database_revision": state["revision"],
        "sample_opportunities": int(state["opportunities"]),
        "sample_unique_opportunities": int(state["poll_unique"]),
        "sample_source_count": source_count,
        "sample_scope": "successful-source-corpus" if corpus_scope else "single-source",
        "sample_hot": int(state["hot"]),
        "sample_cold": int(state["cold"]),
        "sample_protected": int(state["protected"]),
        "opportunity_lengths": dict(opp),
        "evaluation_lengths": dict(evaluation),
        "provenance_shape": dict(provenance),
        "archive_shape": dict(archive),
        "storage_object_shape": dict(storage_objects),
        "poll_shape": dict(poll),
    }


def _create_storage_metadata_benchmark(connection) -> None:
    """Mirror the verified live storage.objects columns and index contract."""
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS storage"))
    connection.execute(text("""
        CREATE TABLE storage.objects (
            id uuid NOT NULL,
            bucket_id text,
            name text,
            owner uuid,
            owner_id text,
            created_at timestamp with time zone,
            updated_at timestamp with time zone,
            last_accessed_at timestamp with time zone,
            metadata jsonb,
            path_tokens text[],
            version text,
            user_metadata jsonb,
            archived_at timestamp with time zone,
            is_delete_marker boolean NOT NULL,
            is_versioned boolean NOT NULL,
            CONSTRAINT objects_pkey PRIMARY KEY (id)
        )
    """))
    connection.execute(text('CREATE INDEX idx_objects_bucket_id_name ON storage.objects USING btree (bucket_id, name COLLATE "C")'))
    connection.execute(text('CREATE INDEX idx_objects_bucket_id_name_lower ON storage.objects USING btree (bucket_id, lower(name) COLLATE "C")'))
    connection.execute(text('CREATE UNIQUE INDEX idx_objects_current_version ON storage.objects USING btree (bucket_id, name COLLATE "C") WHERE (archived_at IS NULL)'))
    connection.execute(text('CREATE INDEX idx_objects_delete_markers ON storage.objects USING btree (bucket_id, name COLLATE "C") WHERE is_delete_marker'))
    connection.execute(text('CREATE UNIQUE INDEX idx_objects_null_version ON storage.objects USING btree (bucket_id, name COLLATE "C") WHERE (NOT is_versioned)'))
    connection.execute(text('CREATE INDEX name_prefix_search ON storage.objects USING btree (name text_pattern_ops)'))
    connection.execute(text('CREATE UNIQUE INDEX objects_bucket_id_name_version_key ON storage.objects USING btree (bucket_id, name COLLATE "C", version) NULLS NOT DISTINCT'))


def _storage_object_metadata(size_bytes: int, etag: str, now: datetime) -> dict[str, Any]:
    return {
        "cacheControl": "no-cache",
        "contentLength": size_bytes,
        "eTag": etag[:36],
        "httpStatusCode": 200,
        "lastModified": now.replace(tzinfo=timezone.utc).isoformat(timespec="seconds"),
        "mimetype": "application/octet-stream",
        "size": size_bytes,
    }


def _table_snapshot(connection, *, require_empty: bool = False) -> dict[str, Any]:
    revision = connection.execute(text("SELECT version_num FROM public.alembic_version LIMIT 1")).scalar_one()
    counts = connection.execute(text("""
        SELECT
          (SELECT count(*) FROM public.opportunities) AS opportunities,
          (SELECT count(*) FROM public.opportunities WHERE lifecycle_tier='hot') AS hot,
          (SELECT count(*) FROM public.opportunities WHERE lifecycle_tier='cold') AS cold,
          (SELECT count(*) FROM public.opportunities WHERE lifecycle_tier='protected') AS protected,
          (SELECT count(*) FROM public.feed_projection) AS feed,
          (SELECT count(*) FROM public.match_evaluations) AS evaluations,
          (SELECT count(*) FROM public.field_provenances) AS provenance,
          (SELECT count(*) FROM public.opportunity_cold_archive) AS archives,
          (SELECT count(*) FROM public.source_poll_runs) AS source_polls,
          (SELECT count(*) FROM public.source_schedules) AS schedules,
          (SELECT count(*) FROM public.worker_jobs) AS jobs,
          (SELECT count(*) FROM storage.objects) AS storage_objects
    """)).mappings().one()
    tier_checks = connection.execute(text("""
        SELECT
          (SELECT count(*) FROM public.opportunities
            WHERE lifecycle_tier='cold' AND (description IS NOT NULL OR raw_payload_json IS NOT NULL)) AS cold_bodies,
          (SELECT count(*) FROM public.field_provenances p JOIN public.opportunities o ON o.id=p.opportunity_id
            WHERE o.lifecycle_tier='cold') AS cold_provenance,
          (SELECT count(*) FROM public.match_evaluations e JOIN public.opportunities o ON o.id=e.opportunity_id
            WHERE o.lifecycle_tier='cold' AND (e.dimension_scores_json IS NOT NULL OR e.evaluation_detail_json IS NOT NULL)) AS cold_verbose_evaluations,
          (SELECT count(*) FROM public.opportunity_cold_archive
            WHERE payload_zlib IS NOT NULL OR storage_backend <> 'supabase_storage' OR object_key IS NULL) AS invalid_archives,
          (SELECT count(*) FROM public.opportunity_cold_archive a JOIN public.opportunities o ON o.id=a.opportunity_id
            WHERE o.archive_object_key IS DISTINCT FROM a.object_key
              OR o.archive_sha256 IS DISTINCT FROM a.payload_sha256
              OR o.content_hash IS DISTINCT FROM a.content_hash) AS archive_identity_mismatches,
          (SELECT COALESCE(max(n),0) FROM
            (SELECT count(*) AS n FROM public.feed_projection GROUP BY opportunity_id) q) AS max_projections_per_opportunity,
          (SELECT COALESCE(max(n),0) FROM
            (SELECT count(*) AS n FROM public.match_evaluations GROUP BY opportunity_id) q) AS max_evaluations_per_opportunity,
          (SELECT COALESCE(max(length(reasons_json)),0) FROM public.match_evaluations e
            JOIN public.opportunities o ON o.id=e.opportunity_id WHERE o.lifecycle_tier='cold') AS max_cold_reason_bytes,
          (SELECT count(*) FROM storage.objects WHERE bucket_id='opportunity-artifacts') AS storage_objects,
          (SELECT round(avg(pg_column_size(o)))::int FROM storage.objects o
            WHERE bucket_id='opportunity-artifacts') AS storage_object_tuple_bytes,
          (SELECT round(avg(pg_column_size(metadata)))::int FROM storage.objects o
            WHERE bucket_id='opportunity-artifacts') AS storage_object_metadata_bytes,
          (SELECT round(avg(length(name)))::int FROM storage.objects o
            WHERE bucket_id='opportunity-artifacts') AS storage_object_key_length,
          (SELECT round(avg(cardinality(path_tokens)))::int FROM storage.objects o
            WHERE bucket_id='opportunity-artifacts') AS storage_object_path_segments,
          (SELECT round(avg(length(version)))::int FROM storage.objects o
            WHERE bucket_id='opportunity-artifacts') AS storage_object_version_length
    """)).mappings().one()
    if require_empty and int(counts["opportunities"]) != 0:
        raise RuntimeError("disposable benchmark database must have no product rows before seeding")
    db_bytes = int(connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
    return {
        "revision": str(revision),
        "database_bytes": db_bytes,
        "product_counts": dict(counts),
        "tier_checks": dict(tier_checks),
    }


def _relation_profile(connection) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    relations = connection.execute(text("""
        SELECT n.nspname AS schema_name,
               c.relname AS relation,
               pg_total_relation_size(c.oid)::bigint AS total_bytes,
               pg_relation_size(c.oid)::bigint AS heap_bytes,
               pg_indexes_size(c.oid)::bigint AS index_bytes,
               COALESCE(s.n_live_tup,0)::bigint AS estimated_live_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
        WHERE n.nspname IN ('public','storage') AND c.relkind IN ('r','m')
        ORDER BY pg_total_relation_size(c.oid) DESC, c.relname
        LIMIT 25
    """)).mappings().all()
    indexes = connection.execute(text("""
        SELECT idx.relname AS index_name, tbl.relname AS table_name,
               pg_relation_size(idx.oid)::bigint AS bytes
        FROM pg_index i
        JOIN pg_class idx ON idx.oid=i.indexrelid
        JOIN pg_class tbl ON tbl.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=tbl.relnamespace
        WHERE n.nspname IN ('public','storage')
        ORDER BY pg_relation_size(idx.oid) DESC, idx.relname
        LIMIT 25
    """)).mappings().all()
    public_bytes = int(connection.execute(text("""
        SELECT COALESCE(sum(pg_total_relation_size(c.oid)),0)::bigint
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname IN ('public','storage') AND c.relkind IN ('r','m')
    """)).scalar_one())
    return [dict(row) for row in relations], [dict(row) for row in indexes], public_bytes


def _source_overhead_profile(connection) -> dict[str, int]:
    rows = connection.execute(text("""
        SELECT c.relname AS relation,
               pg_total_relation_size(c.oid)::bigint AS total_bytes
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public'
          AND c.relname IN ('worker_jobs','source_poll_runs','source_schedules')
          AND c.relkind='r'
    """)).mappings().all()
    profile = {f"public.{row['relation']}": int(row['total_bytes']) for row in rows}
    for relation in ("public.worker_jobs", "public.source_poll_runs", "public.source_schedules"):
        profile.setdefault(relation, 0)
    profile["total"] = sum(profile.values())
    return profile


def _benchmark_rows(connection, shape: dict[str, Any], source_ids: list[str]) -> dict[str, int]:
    opp_shape = shape["opportunity_lengths"]
    eval_shape = shape["evaluation_lengths"]
    provenance_shape = shape["provenance_shape"]
    archive_shape = shape["archive_shape"]
    current_source_count = max(1, shape["sample_hot"] + shape["sample_cold"] + shape["sample_protected"])
    hot_share = (shape["sample_hot"] + shape["sample_protected"]) / current_source_count
    protected_share = shape["sample_protected"] / current_source_count
    hot_and_protected_count = min(POPULATION, max(1, round(POPULATION * hot_share)))
    protected_count = min(hot_and_protected_count, round(POPULATION * protected_share))
    hot_count = hot_and_protected_count - protected_count
    cold_count = POPULATION - hot_and_protected_count
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    registry_id = lambda i: source_ids[i % len(source_ids)]
    opportunity_ids = [f"b{i:063x}" for i in range(POPULATION)]
    content_hashes = [_digest(f"fr007-capacity-content-{i}") for i in range(POPULATION)]
    payload_hashes = [_digest(f"cold-payload-{value}") for value in content_hashes]
    cold_compressed = int(archive_shape["compressed_bytes"] or 0)
    cold_original = int(archive_shape["original_bytes"] or 0)
    tiers = ["hot"] * hot_count + ["protected"] * protected_count + ["cold"] * cold_count

    def opportunity_rows():
        for i, opportunity_id in enumerate(opportunity_ids):
            tier = tiers[i]
            is_cold = tier == "cold"
            src = registry_id(i)
            token = _alpha_token(i)
            title_length = opp_shape["cold_title"] if is_cold else opp_shape["hot_title"]
            org_length = opp_shape["cold_org"] if is_cold else opp_shape["hot_org"]
            url_length = opp_shape["cold_url"] if is_cold else opp_shape["hot_url"]
            title = _fit(f"Senior {token} Software Engineer", title_length, filler=" ")
            organization = _fit(f"Org {token}", org_length, filler=" ")
            source_url = _fit(f"https://jobs.example.test/j/{token}", url_length)
            content_hash = content_hashes[i]
            object_key = archive_key(content_hash, opportunity_id) if is_cold else None
            description = None if is_cold else _fit(
                "This role owns software design delivery and systems collaboration. ",
                opp_shape["hot_description"], filler=" "
            )
            raw_json = None if is_cold else _json_of_length("source", opp_shape["hot_raw"])
            yield {
                "id": opportunity_id,
                "track": "engineering",
                "title": title,
                "organization": organization,
                "description": description,
                "source_id": src,
                "source_url": source_url,
                "content_hash": content_hash,
                "country": "Germany",
                "region": "Berlin",
                "geographic_scope": None,
                "posted_date": "2026-09-01",
                "deadline": None,
                "is_stale": False,
                "reverified_at": None,
                "raw_payload_json": raw_json,
                "created_at": now,
                "work_mode": "unspecified",
                "work_mode_source": None,
                "location_country": "DE",
                "location_city": _fit("Berlin", opp_shape["cold_city"] if is_cold else opp_shape["hot_city"], filler=" "),
                "location_region": _fit("Berlin Region", opp_shape["cold_region"] if is_cold else opp_shape["hot_region"], filler=" ") or None,
                "remote_scope": "unspecified",
                "remote_scope_regions": _fit("Europe", opp_shape["cold_remote_regions"] if is_cold else opp_shape["hot_remote_regions"], filler=" ") or None,
                "employment_type": "unspecified",
                "seniority_level": "unspecified",
                "compensation_min": None,
                "compensation_max": None,
                "compensation_currency": None,
                "compensation_period": None,
                "title_family": "engineering",
                "title_level": None,
                "family_key": None,
                "search_tsv": None,
                "archive_object_key": object_key,
                "archive_sha256": payload_hashes[i] if is_cold else None,
                "archive_state": "verified" if is_cold else None,
                "lifecycle_tier": tier,
            }

    opp_inserted = _insert_rows(connection, OpportunityRecord.__table__, opportunity_rows())

    def evaluation_rows():
        for i, opportunity_id in enumerate(opportunity_ids):
            is_hot = tiers[i] != "cold"
            yield {
                "id": f"e{i:063x}",
                "opportunity_id": opportunity_id,
                "truth_pack_hash": _digest("fr007-capacity-truth-pack"),
                "content_hash": content_hashes[i],
                "qualification_decision": "eligible" if is_hot else "ineligible",
                "fit_score": 70.0 if is_hot else 5.0,
                "dimension_scores_json": _json_of_length("scores", eval_shape["hot_dimensions"]) if is_hot else None,
                "reasons_json": _json_of_length("reasons", eval_shape["cold_reasons"] if not is_hot else eval_shape["hot_reasons"]),
                "hard_failure_code": None if is_hot else "benchmark_terminal",
                "evaluation_detail_json": _json_of_length("detail", eval_shape["hot_detail"]) if is_hot else None,
                "policy_version": "fr007-capacity-benchmark",
                "evaluated_at": now,
                "created_at": now,
            }

    eval_inserted = _insert_rows(connection, MatchEvaluationRecord.__table__, evaluation_rows())

    def provenance_rows():
        average_rows = float(provenance_shape["rows"]) / max(1, shape["sample_hot"] + shape["sample_protected"])
        rows_per_hot = max(1, round(average_rows))
        for i in range(hot_and_protected_count):
            opportunity_id = opportunity_ids[i]
            for field_index in range(rows_per_hot):
                field = f"field_{field_index:02d}"
                checksum = _digest(f"{opportunity_id}:{field}")
                yield {
                    "opportunity_id": opportunity_id,
                    "field_name": field,
                    "raw_value": _fit("source value", provenance_shape["raw_value"]),
                    "normalized_value": _fit("normalized value", provenance_shape["normalized_value"]),
                    "derivation_type": "source_native",
                    "raw_pointer": _fit(f"$.fields.{field}", provenance_shape["raw_pointer"]),
                    "record_checksum": checksum,
                    "rule_id": _fit("source_rule", provenance_shape["rule_id"]) or None,
                }

    provenance_inserted = _insert_rows(connection, FieldProvenanceRecord.__table__, provenance_rows())

    def feed_rows():
        for i in range(hot_and_protected_count):
            opportunity_id = opportunity_ids[i]
            src = registry_id(i)
            token = _alpha_token(i)
            is_protected = tiers[i] == "protected"
            yield {
                "id": opportunity_id,
                "opportunity_id": opportunity_id,
                "opportunity_content_hash": content_hashes[i],
                "truth_pack_hash": _digest("fr007-capacity-truth-pack"),
                "projection_version": "storage-v2",
                "title": _fit(f"Senior {token} Software Engineer", opp_shape["hot_title"], filler=" "),
                "organization": _fit(f"Org {token}", opp_shape["hot_org"], filler=" "),
                "source_id": src,
                "source_url": _fit(f"https://jobs.example.test/j/{token}", opp_shape["hot_url"]),
                "posted_date": "2026-09-01",
                "track": "engineering",
                "opportunity_type": "role",
                "title_family": "engineering",
                "seniority_level": "unspecified",
                "work_mode": "unspecified",
                "location_country": "DE",
                "location_city": _fit("Berlin", opp_shape["hot_city"], filler=" "),
                "location_region": _fit("Berlin Region", opp_shape["hot_region"], filler=" ") or None,
                "remote_scope": "unspecified",
                "remote_scope_regions": _fit("Europe", opp_shape["hot_remote_regions"], filler=" ") or None,
                "employment_type": "unspecified",
                "qualification_decision": "eligible",
                "fit_score": 70.0,
                "priority_score": 70.0,
                "reasons_json": _json_of_length("reasons", eval_shape["hot_reasons"]),
                "red_line_match": False,
                "excluded_industry_match": False,
                "visible": not is_protected,
                "visibility_reason": "founder_protected" if is_protected else None,
                "evaluated_at": now,
                "projected_at": now,
            }

    feed_inserted = _insert_rows(connection, FeedProjectionRecord.__table__, feed_rows())

    def archive_rows():
        for i in range(hot_and_protected_count, POPULATION):
            opportunity_id = opportunity_ids[i]
            content_hash = content_hashes[i]
            object_key = archive_key(content_hash, opportunity_id)
            yield {
                "opportunity_id": opportunity_id,
                "content_hash": content_hash,
                "payload_zlib": None,
                "storage_backend": "supabase_storage",
                "object_key": object_key,
                "compressed_size_bytes": cold_compressed,
                "payload_sha256": payload_hashes[i],
                "original_size_bytes": cold_original,
                "archive_version": ARCHIVE_VERSION,
                "archived_at": now.replace(tzinfo=timezone.utc),
            }

    archives_inserted = _insert_rows(connection, OpportunityColdArchiveRecord.__table__, archive_rows())

    def storage_object_rows():
        for i in range(hot_and_protected_count, POPULATION):
            opportunity_id = opportunity_ids[i]
            object_name = archive_key(content_hashes[i], opportunity_id)
            size_bytes = cold_compressed
            yield {
                "id": str(uuid.UUID(int=i + 1)),
                "bucket_id": "opportunity-artifacts",
                "name": object_name,
                "owner": None,
                "owner_id": None,
                "created_at": now.replace(tzinfo=timezone.utc),
                "updated_at": now.replace(tzinfo=timezone.utc),
                "last_accessed_at": None,
                "metadata": _storage_object_metadata(size_bytes, payload_hashes[i], now),
                "path_tokens": object_name.split("/"),
                "version": str(uuid.UUID(int=POPULATION + i + 1)),
                "user_metadata": None,
                "archived_at": None,
                "is_delete_marker": False,
                "is_versioned": False,
            }

    storage_objects_inserted = _insert_rows(connection, STORAGE_OBJECTS, storage_object_rows())

    read_allowed_sources = len(source_ids)
    opp_per_source = [0] * read_allowed_sources
    for i in range(POPULATION):
        opp_per_source[i % read_allowed_sources] += 1

    def source_poll_rows():
        for i, source_id in enumerate(source_ids):
            source_opportunities = opp_per_source[i]
            poll_id = f"p{i:063x}"
            yield {
                "id": poll_id,
                "source_id": source_id,
                "job_id": f"j{i:063x}",
                "started_at": now,
                "finished_at": now + timedelta(seconds=1),
                "status": "ok",
                "refusal_reason": None,
                "raw_ingested": source_opportunities,
                "unique_opportunities": source_opportunities,
                "inserted": source_opportunities,
                "unchanged": 0,
                "updated": 0,
                "error_message": None,
            }

    polls_inserted = _insert_rows(connection, SourcePollRunRecord.__table__, source_poll_rows())

    def source_schedule_rows():
        for source_id in source_ids:
            yield {
                "source_id": source_id,
                "cadence_hours": 6.0,
                "last_attempt_at": now,
                "last_success_at": now,
                "next_due_at": now + timedelta(hours=6),
                "cooldown_until": None,
                "consecutive_failures": 0,
                "last_status": "ok",
                "error_message": None,
                "created_at": now,
                "updated_at": now,
            }

    schedules_inserted = _insert_rows(connection, SourceScheduleRecord.__table__, source_schedule_rows())

    def worker_rows():
        for i, source_id in enumerate(source_ids):
            yield {
                "id": f"w{i:063x}", "job_type": "poll_source",
                "payload_json": json.dumps({"source_id": source_id}, separators=(",", ":")),
                "status": "COMPLETED", "run_after": now, "retry_count": 0, "max_retries": 3,
                "lease_owner": None, "lease_expires_at": None, "error_message": None,
                "created_at": now, "updated_at": now,
            }
            yield {
                "id": f"x{i:063x}", "job_type": "evaluate_new", "payload_json": "{}",
                "status": "COMPLETED", "run_after": now, "retry_count": 0, "max_retries": 3,
                "lease_owner": None, "lease_expires_at": None, "error_message": None,
                "created_at": now, "updated_at": now,
            }

    jobs_inserted = _insert_rows(connection, WorkerJobRecord.__table__, worker_rows())

    # Keep one compact searchable tsvector per opportunity, matching the
    # direct-tier representation. Unique alphabetic title tokens ensure the
    # measured GIN index does not benefit from an unrealistically tiny lexicon.
    connection.execute(text("""
        UPDATE public.opportunities
        SET search_tsv=to_tsvector('english', concat_ws(' ', title, organization,
            location_country, location_city, location_region, track, title_family, family_key))
        WHERE search_tsv IS NULL
        """))
    connection.execute(text("ANALYZE"))
    return {
        "opportunities_inserted": opp_inserted,
        "evaluations_inserted": eval_inserted,
        "provenance_inserted": provenance_inserted,
        "feed_inserted": feed_inserted,
        "archives_inserted": archives_inserted,
        "storage_objects_inserted": storage_objects_inserted,
        "source_polls_inserted": polls_inserted,
        "source_schedules_inserted": schedules_inserted,
        "worker_jobs_inserted": jobs_inserted,
        "hot_opportunities": hot_count,
        "cold_opportunities": cold_count,
        "protected_opportunities": protected_count,
        "projected_cold_archive_storage_bytes": cold_count * cold_compressed,
        "sample_archive_bytes_per_cold_opportunity": cold_compressed,
        "source_count": read_allowed_sources,
    }


def run_benchmark(source_id: str) -> dict[str, Any]:
    live_raw = os.environ.get("OPOS_TARGET_DB_URL") or os.environ.get("CLOUD_DATABASE_URL")
    benchmark_raw = os.environ.get("FR007_BENCHMARK_DB_URL")
    if not live_raw or not benchmark_raw:
        raise RuntimeError("one or more required database endpoints are unavailable")
    live_engine = create_engine(get_production_db_url(live_raw), pool_size=1, max_overflow=0, pool_pre_ping=True)
    benchmark_engine = create_engine(get_production_db_url(benchmark_raw), pool_size=1, max_overflow=0, pool_pre_ping=True)
    try:
        with live_engine.connect() as live_connection:
            shape = _shape(live_connection, source_id)
        registry = SourceRegistry()
        source_ids = [sid for sid in registry._sources if registry.is_read_allowed(sid)]
        if not source_ids:
            raise RuntimeError("read-allowed source registry is empty")
        with benchmark_engine.begin() as benchmark_connection:
            _create_storage_metadata_benchmark(benchmark_connection)
            empty = _table_snapshot(benchmark_connection, require_empty=True)
            if empty["revision"] != EXPECTED_HEAD:
                raise RuntimeError("disposable benchmark schema is not at the required Alembic head")
            inserted = _benchmark_rows(benchmark_connection, shape, source_ids)
        with benchmark_engine.connect() as benchmark_connection:
            populated = _table_snapshot(benchmark_connection)
            top_relations, top_indexes, public_relation_bytes = _relation_profile(benchmark_connection)
            source_overhead = _source_overhead_profile(benchmark_connection)
        growth = max(0, int(populated["database_bytes"]) - int(empty["database_bytes"]))
        with live_engine.connect() as live_connection:
            live_database_bytes = int(live_connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
        if source_id == SUCCESSFUL_CORPUS_SOURCE_ID:
            remaining_projection = _remaining_capacity_projection(
                live_database_bytes=live_database_bytes,
                benchmark_growth_bytes=growth,
                source_growth_bytes=source_overhead["total"],
                current_opportunities=int(shape["sample_opportunities"]),
                current_sources=int(shape["sample_source_count"]),
                target_opportunities=POPULATION,
                target_sources=len(source_ids),
            )
            projected = remaining_projection["projected_final_database_bytes"]
        else:
            remaining_projection = None
            projected = live_database_bytes + growth
        checks = {
            "live_and_benchmark_schema_at_expected_head": (
                shape["live_database_revision"] == EXPECTED_HEAD and populated["revision"] == EXPECTED_HEAD
            ),
            "exact_physical_benchmark_population": int(inserted["opportunities_inserted"]) == POPULATION,
            "one_current_evaluation_per_opportunity": int(inserted["evaluations_inserted"]) == POPULATION,
            "one_compact_archive_per_cold_opportunity": int(inserted["archives_inserted"]) == inserted["cold_opportunities"],
            "bounded_current_feed_population": int(inserted["feed_inserted"]) == inserted["hot_opportunities"] + inserted["protected_opportunities"],
            "registry_scale_is_represented": int(inserted["source_count"]) == len(source_ids) and int(inserted["source_polls_inserted"]) == len(source_ids),
            "benchmark_cold_rows_have_no_relational_bodies_or_provenance": (
                int(populated["tier_checks"]["cold_bodies"]) == 0
                and int(populated["tier_checks"]["cold_provenance"]) == 0
                and int(populated["tier_checks"]["cold_verbose_evaluations"]) == 0
                and int(populated["tier_checks"]["max_cold_reason_bytes"]) <= 512
            ),
            "benchmark_has_complete_archive_metadata_and_single_current_rows": (
                int(populated["tier_checks"]["invalid_archives"]) == 0
                and int(populated["tier_checks"]["archive_identity_mismatches"]) == 0
                and int(populated["tier_checks"]["max_projections_per_opportunity"]) <= 1
                and int(populated["tier_checks"]["max_evaluations_per_opportunity"]) <= 1
            ),
            "storage_metadata_row_per_cold_archive": int(inserted["storage_objects_inserted"]) == inserted["cold_opportunities"],
            "storage_metadata_shape_matches_live_tier": (
                int(populated["tier_checks"]["storage_objects"]) == inserted["cold_opportunities"]
                and abs(int(populated["tier_checks"]["storage_object_metadata_bytes"]) - int(shape["storage_object_shape"]["metadata_bytes"]))
                    <= max(16, int(shape["storage_object_shape"]["metadata_bytes"]) // 5)
                and int(populated["tier_checks"]["storage_object_key_length"]) == int(shape["storage_object_shape"]["object_key_length"])
                and int(populated["tier_checks"]["storage_object_path_segments"]) == int(shape["storage_object_shape"]["path_segments"])
                and int(populated["tier_checks"]["storage_object_version_length"]) == int(shape["storage_object_shape"]["version_length"])
            ),
            "all_physical_measurements_are_post_population": int(populated["database_bytes"]) > int(empty["database_bytes"]),
            "projected_database_within_hard_budget": projected <= DATABASE_HARD_BUDGET,
        }
        largest_relations = {
            f"{row['schema_name']}.{row['relation']}": int(row["total_bytes"])
            for row in top_relations
        }
        capacity_model = {
            "schema": "fr007-storage-v2-capacity-model-v2",
            "representative_workflow_run_id": (
                int(os.environ["GITHUB_RUN_ID"]) if source_id != SUCCESSFUL_CORPUS_SOURCE_ID and os.environ.get("GITHUB_RUN_ID") else None
            ),
            "capacity_benchmark_workflow_run_id": (
                int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None
            ),
            "source_id": source_id,
            "source_sample_opportunities": shape["sample_opportunities"],
            "source_sample_successful_identities": shape["sample_source_count"],
            "live_database_bytes_at_benchmark": live_database_bytes,
            "benchmark_database_bytes_empty_schema": empty["database_bytes"],
            "benchmark_database_bytes_after_population": populated["database_bytes"],
            "benchmark_growth_bytes": growth,
            "target_opportunities": POPULATION,
            "target_read_allowed_sources": len(source_ids),
            "hard_database_budget_bytes": DATABASE_HARD_BUDGET,
            "projected_final_database_bytes": projected,
            "projected_final_database_mib": round(projected / (1024 * 1024), 2),
            "projected_database_bytes_at_gate": projected,
            "projected_database_mib_at_gate": round(projected / (1024 * 1024), 2),
            "projected_cold_archive_storage_bytes": inserted["projected_cold_archive_storage_bytes"],
            "source_overhead_relation_bytes": source_overhead,
            "population": {
                "opportunities": POPULATION,
                "hot": inserted["hot_opportunities"],
                "cold": inserted["cold_opportunities"],
                "protected": inserted["protected_opportunities"],
                "feed_projections": inserted["feed_inserted"],
                "evaluations": inserted["evaluations_inserted"],
                "provenance": inserted["provenance_inserted"],
                "archives": inserted["archives_inserted"],
                "storage_objects": inserted["storage_objects_inserted"],
                "source_polls": inserted["source_polls_inserted"],
                "source_schedules": inserted["source_schedules_inserted"],
                "worker_jobs": inserted["worker_jobs_inserted"],
            },
            "largest_relations_bytes": largest_relations,
            "measurement_contract": {
                "benchmark_engine": "isolated PostgreSQL 17 disposable service",
                "live_database_writes": 0,
                "live_payload_text_read": False,
                "physical_database_measurement": "pg_database_size",
                "projection": "current live physical bytes plus physically measured remaining population growth",
                "safety_reserve_fraction_for_incremental_projection": 0.01,
                "remaining_projection": remaining_projection,
            },
        }
        return {
            "status": "PASS" if all(checks.values()) else "STOP_FOR_ARCHITECTURE_REVIEW",
            "source_id": source_id,
            "database_revision": populated["revision"],
            "population_opportunities": POPULATION,
            "sample_unique_opportunities": shape["sample_unique_opportunities"],
            "sample_opportunities": shape["sample_opportunities"],
            "sample_source_count": shape["sample_source_count"],
            "sample_scope": shape["sample_scope"],
            "sample_tier_counts": {
                "hot": shape["sample_hot"], "cold": shape["sample_cold"], "protected": shape["sample_protected"]
            },
            "population_tier_counts": {
                "hot": inserted["hot_opportunities"], "cold": inserted["cold_opportunities"],
                "protected": inserted["protected_opportunities"]
            },
            "live_database_bytes_at_benchmark": live_database_bytes,
            "benchmark_database_bytes_empty_schema": empty["database_bytes"],
            "database_bytes_after_population": populated["database_bytes"],
            "benchmark_growth_bytes": growth,
            "projected_database_bytes": projected,
            "projected_database_mib": round(projected / (1024 * 1024), 2),
            "remaining_capacity_projection": remaining_projection,
            "source_overhead_relation_bytes": source_overhead,
            "projected_cold_archive_storage_bytes": inserted["projected_cold_archive_storage_bytes"],
            "benchmark_application_relation_bytes": public_relation_bytes,
            "benchmark_product_counts": populated["product_counts"],
            "benchmark_tier_checks": populated["tier_checks"],
            "top_relations": top_relations,
            "top_indexes": top_indexes,
            "sample_shape": {
                "opportunity_lengths": shape["opportunity_lengths"],
                "evaluation_lengths": shape["evaluation_lengths"],
                "provenance_shape": shape["provenance_shape"],
                "archive_shape": shape["archive_shape"],
                "storage_object_shape": shape["storage_object_shape"],
                "poll_shape": shape["poll_shape"],
            },
            "inserted": inserted,
            "capacity_model": capacity_model,
            "checks": checks,
            "synthetic_data_location": "disposable-postgresql-only",
            "live_database_writes": 0,
            "payload_text_read_from_live": False,
        }
    finally:
        live_engine.dispose()
        benchmark_engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(args.source_id)
    except Exception as exc:
        raise SystemExit(f"capacity benchmark failed ({type(exc).__name__}); sensitive values suppressed") from None
    encoded = json.dumps(report, sort_keys=True, default=str)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.model_output:
        args.model_output.write_text(
            json.dumps(report["capacity_model"], sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(encoded)
    if report["status"] != "PASS":
        raise SystemExit("physical 26k capacity benchmark or hard-budget gate did not pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
