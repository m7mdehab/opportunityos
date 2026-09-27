"""Repository-managed, idempotent zero-dollar footprint maintenance.

Only derived/reconstructable duplication is compacted.  Opportunity identity
rows, founder activity, evaluations and source poll history remain.  Cold
payloads are zlib-compressed with a SHA-256 over the stored bytes so a rerun
can verify integrity before changing a hot row.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from storage.cold_storage import ARCHIVE_VERSION, hosted_storage_configured, pack, put



@dataclass(frozen=True)
class MaintenancePlan:
    database_size_bytes: int
    relation_sizes: tuple[dict[str, Any], ...]
    eligible_count: int
    active_projection_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "database_size_bytes": self.database_size_bytes,
            "relation_sizes": list(self.relation_sizes),
            "eligible_count": self.eligible_count,
            "active_projection_count": self.active_projection_count,
        }


def _candidate_sql() -> str:
    return """
        SELECT o.id, o.content_hash, o.description, o.raw_payload_json
        FROM opportunities o
        JOIN match_evaluations e ON e.opportunity_id = o.id
        WHERE e.truth_pack_hash = :truth_pack_hash
          AND lower(e.qualification_decision) = 'ineligible'
          AND NOT EXISTS (SELECT 1 FROM founder_feedback f WHERE f.opportunity_id = o.id)
          AND NOT EXISTS (SELECT 1 FROM founder_triage_states t WHERE t.opportunity_id = o.id)
          AND NOT EXISTS (SELECT 1 FROM founder_opportunity_views v WHERE v.opportunity_id = o.id)
          AND NOT EXISTS (SELECT 1 FROM outbound_actions a WHERE a.opportunity_id = o.id)
          AND NOT EXISTS (SELECT 1 FROM opportunity_cold_archive c WHERE c.opportunity_id = o.id)
    """


def build_plan(connection, *, truth_pack_hash: str) -> MaintenancePlan:
    size = int(connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
    rows = connection.execute(
        text("""
            SELECT relname AS relation, pg_total_relation_size(quote_ident(relname)::regclass) AS bytes
            FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r','m')
            ORDER BY bytes DESC, relname
        """)
    ).mappings().all()
    eligible = int(connection.execute(text(f"SELECT count(*) FROM ({_candidate_sql()}) candidates"), {"truth_pack_hash": truth_pack_hash}).scalar_one())
    active = int(connection.execute(text("SELECT count(*) FROM feed_projection WHERE truth_pack_hash = 'active'")).scalar_one())
    return MaintenancePlan(size, tuple(dict(row) for row in rows), eligible, active)


def archive_payload(connection, row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    provenance = connection.execute(
        text("""
            SELECT field_name, raw_value, normalized_value, derivation_type,
                   raw_pointer, record_checksum, rule_id
            FROM field_provenances WHERE opportunity_id = :opportunity_id ORDER BY id
        """),
        {"opportunity_id": row["id"]},
    ).mappings().all()
    payload = {
        "opportunity_id": row["id"],
        "content_hash": row["content_hash"],
        "description": row["description"],
        "raw_payload_json": row["raw_payload_json"],
        "provenance": [dict(item) for item in provenance],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    digest = hashlib.sha256(compressed).hexdigest()
    connection.execute(
        text("""
            INSERT INTO opportunity_cold_archive
                (opportunity_id, content_hash, payload_zlib, payload_sha256,
                 original_size_bytes, archive_version, archived_at)
            VALUES (:opportunity_id, :content_hash, :payload_zlib, :payload_sha256,
                    :original_size_bytes, :archive_version, :archived_at)
            ON CONFLICT (opportunity_id) DO NOTHING
        """),
        {
            "opportunity_id": row["id"], "content_hash": row["content_hash"],
            "payload_zlib": compressed, "payload_sha256": digest,
            "original_size_bytes": len(raw), "archive_version": ARCHIVE_VERSION,
            "archived_at": now,
        },
    )
    connection.execute(
        text("""
            UPDATE opportunities
            SET description = '[archived]', raw_payload_json = NULL, search_tsv = NULL
            WHERE id = :opportunity_id
        """), {"opportunity_id": row["id"]},
    )
    connection.execute(text("DELETE FROM field_provenances WHERE opportunity_id = :opportunity_id"), {"opportunity_id": row["id"]})
    connection.execute(
        text("""
            UPDATE feed_projection
            SET visible = FALSE, visibility_reason = 'cold_ineligible',
                search_text = '', search_tsv = NULL
            WHERE opportunity_id = :opportunity_id
        """),
        {"opportunity_id": row["id"]},
    )
    return {"opportunity_id": row["id"], "compressed_bytes": len(compressed), "sha256": digest}


def apply_maintenance(connection, *, truth_pack_hash: str, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise ValueError("maintenance requires explicit --confirm-maintenance")
    now = datetime.now(timezone.utc)
    archived: list[dict[str, Any]] = []
    while True:
        rows = [dict(row) for row in connection.execute(
            text(_candidate_sql() + " LIMIT 500"), {"truth_pack_hash": truth_pack_hash}
        ).mappings().all()]
        if not rows:
            break
        ids = [row["id"] for row in rows]
        provenance_rows = connection.execute(text("""
            SELECT opportunity_id, field_name, raw_value, normalized_value,
                   derivation_type, raw_pointer, record_checksum, rule_id
            FROM field_provenances WHERE opportunity_id = ANY(:opportunity_ids)
            ORDER BY opportunity_id, id
        """), {"opportunity_ids": ids}).mappings().all()
        provenance_by_id: dict[str, list[dict[str, Any]]] = {}
        for item in provenance_rows:
            item = dict(item)
            provenance_by_id.setdefault(item.pop("opportunity_id"), []).append(item)
        archive_rows: list[dict[str, Any]] = []
        external = hosted_storage_configured()
        for row in rows:
            payload = {
                "opportunity_id": row["id"], "content_hash": row["content_hash"],
                "description": row["description"], "raw_payload_json": row["raw_payload_json"],
                "provenance": provenance_by_id.get(row["id"], []),
            }
            compressed, digest, original_size = pack(payload)
            object_key = None
            if external:
                object_key, digest, compressed_size = put(compressed, row["content_hash"])
            else:
                compressed_size = len(compressed)
            archive_rows.append({
                "opportunity_id": row["id"], "content_hash": row["content_hash"],
                "payload_zlib": None if external else compressed, "storage_backend": "supabase_storage" if external else "postgres_payload",
                "object_key": object_key, "compressed_size_bytes": compressed_size,
                "payload_sha256": digest,
                "original_size_bytes": original_size, "archive_version": ARCHIVE_VERSION,
                "archived_at": now,
            })
            archived.append({"opportunity_id": row["id"], "compressed_bytes": compressed_size, "sha256": digest, "storage_backend": "supabase_storage" if external else "postgres_payload"})
        insert_stmt = text("""
            INSERT INTO opportunity_cold_archive
                (opportunity_id, content_hash, payload_zlib, payload_sha256,
                 original_size_bytes, archive_version, archived_at, storage_backend,
                 object_key, compressed_size_bytes)
            VALUES (:opportunity_id, :content_hash, :payload_zlib, :payload_sha256,
                    :original_size_bytes, :archive_version, :archived_at, :storage_backend,
                    :object_key, :compressed_size_bytes)
            ON CONFLICT (opportunity_id) DO NOTHING
        """)
        connection.execute(insert_stmt, archive_rows)
        connection.execute(text("""
            UPDATE opportunities
            SET description = '[archived]', raw_payload_json = NULL, search_tsv = NULL
                , archive_state = 'COLD', archive_object_key = c.object_key,
                  archive_sha256 = c.payload_sha256
            FROM opportunity_cold_archive c
            WHERE id = ANY(:opportunity_ids)
              AND c.opportunity_id = opportunities.id
        """), {"opportunity_ids": ids})
        connection.execute(text("DELETE FROM field_provenances WHERE opportunity_id = ANY(:opportunity_ids)"), {"opportunity_ids": ids})
        # Keep only compact current state for terminal cold rows.  The full
        # evaluation detail is already losslessly present in the archive.
        connection.execute(text("""
            UPDATE match_evaluations
            SET dimension_scores_json = '{}', reasons_json = '[]',
                evaluation_detail_json = NULL
            WHERE opportunity_id = ANY(:opportunity_ids)
              AND truth_pack_hash = :truth_pack_hash
        """), {"opportunity_ids": ids, "truth_pack_hash": truth_pack_hash})
        connection.execute(text("""
            UPDATE feed_projection
            SET visible = FALSE, visibility_reason = 'cold_ineligible',
                search_text = '', search_tsv = NULL
            WHERE opportunity_id = ANY(:opportunity_ids)
        """), {"opportunity_ids": ids})
        print(f"maintenance_batch_complete count={len(rows)} total={len(archived)}", flush=True)
    # Synthetic active projections are a derived fallback profile.  Remove only
    # rows with no founder state; the current authoritative profile remains.
    active_result = connection.execute(text("""
        DELETE FROM feed_projection fp
        WHERE fp.truth_pack_hash = 'active'
          AND NOT EXISTS (SELECT 1 FROM founder_feedback f WHERE f.opportunity_id = fp.opportunity_id)
          AND NOT EXISTS (SELECT 1 FROM founder_triage_states t WHERE t.opportunity_id = fp.opportunity_id)
          AND NOT EXISTS (SELECT 1 FROM founder_opportunity_views v WHERE v.opportunity_id = fp.opportunity_id)
          AND NOT EXISTS (SELECT 1 FROM outbound_actions a WHERE a.opportunity_id = fp.opportunity_id)
    """))
    # All remaining projections use the authoritative opportunities search
    # vector; clear the duplicate projection copy and reclaim its GIN index.
    connection.execute(text("UPDATE feed_projection SET search_text = '', search_tsv = NULL"))
    return {"archived_count": len(archived), "active_projection_removed": active_result.rowcount or 0,
            "archive_sha256": hashlib.sha256("".join(item["sha256"] for item in archived).encode()).hexdigest()}


def verify_archive(connection, opportunity_id: str) -> bool:
    row = connection.execute(text("SELECT payload_zlib, payload_sha256 FROM opportunity_cold_archive WHERE opportunity_id = :id"), {"id": opportunity_id}).mappings().first()
    if row is None:
        return False
    compressed = bytes(row["payload_zlib"])
    return hashlib.sha256(compressed).hexdigest() == row["payload_sha256"] and json.loads(zlib.decompress(compressed))['opportunity_id'] == opportunity_id



def hot_dimension_compaction_plan(connection) -> dict[str, Any]:
    """Estimate HOT/PROTECTED dimension compaction without reading job text."""
    row = connection.execute(text("""
        WITH compact AS (
          SELECT
            octet_length(e.dimension_scores_json) AS current_bytes,
            octet_length(
              COALESCE((
                SELECT jsonb_agg(
                  jsonb_strip_nulls(
                    jsonb_build_object(
                      'dimension_name', item->'dimension_name',
                      'raw_score', item->'raw_score',
                      'weight', item->'weight',
                      'weighted_score', item->'weighted_score',
                      'explanation', item->'explanation',
                      'signal_tags', item->'signal_tags'
                    )
                  )
                )::text
                FROM jsonb_array_elements(e.dimension_scores_json::jsonb) item
              ), '[]')
            ) AS compact_bytes
          FROM match_evaluations e
          JOIN opportunities o ON o.id = e.opportunity_id
          WHERE o.lifecycle_tier IN ('hot', 'protected')
            AND e.dimension_scores_json IS NOT NULL
            AND left(e.dimension_scores_json, 1) = '['
        )
        SELECT count(*) AS rows,
               COALESCE(sum(current_bytes), 0) AS current_bytes,
               COALESCE(sum(compact_bytes), 0) AS compact_bytes,
               COALESCE(sum(current_bytes - compact_bytes), 0) AS logical_savings_bytes
        FROM compact
    """)).mappings().one()
    relation_bytes = int(connection.execute(
        text("SELECT pg_total_relation_size('public.match_evaluations'::regclass)")
    ).scalar_one())
    database_bytes = int(connection.execute(
        text("SELECT pg_database_size(current_database())")
    ).scalar_one())
    return {
        **{key: int(value or 0) for key, value in dict(row).items()},
        "relation_bytes": relation_bytes,
        "database_bytes": database_bytes,
    }


def compact_hot_dimension_scores(connection, *, confirm: bool) -> dict[str, Any]:
    """Rewrite only reconstructable dimension duplication for live HOT rows."""
    if not confirm:
        raise ValueError("hot dimension compaction requires explicit --confirm-maintenance")
    before = hot_dimension_compaction_plan(connection)
    result = connection.execute(text("""
        UPDATE match_evaluations e
        SET dimension_scores_json = compact.payload
        FROM opportunities o
        CROSS JOIN LATERAL (
          SELECT COALESCE(
            jsonb_agg(
              jsonb_strip_nulls(
                jsonb_build_object(
                  'dimension_name', item->'dimension_name',
                  'raw_score', item->'raw_score',
                  'weight', item->'weight',
                  'weighted_score', item->'weighted_score',
                  'explanation', item->'explanation',
                  'signal_tags', item->'signal_tags'
                )
              )
            )::text,
            '[]'
          ) AS payload
          FROM jsonb_array_elements(e.dimension_scores_json::jsonb) item
        ) compact
        WHERE o.id = e.opportunity_id
          AND o.lifecycle_tier IN ('hot', 'protected')
          AND e.dimension_scores_json IS NOT NULL
          AND left(e.dimension_scores_json, 1) = '['
          AND e.dimension_scores_json IS DISTINCT FROM compact.payload
    """))
    after_logical = hot_dimension_compaction_plan(connection)
    return {
        "rows_rewritten": int(result.rowcount or 0),
        "before": before,
        "after_logical": after_logical,
    }


def reclaim_match_evaluation_space(engine) -> dict[str, int]:
    """Physically reclaim the compacted relation outside a transaction."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        before_relation = int(connection.execute(
            text("SELECT pg_total_relation_size('public.match_evaluations'::regclass)")
        ).scalar_one())
        before_database = int(connection.execute(
            text("SELECT pg_database_size(current_database())")
        ).scalar_one())
        connection.execute(text("VACUUM (FULL, ANALYZE) public.match_evaluations"))
        after_relation = int(connection.execute(
            text("SELECT pg_total_relation_size('public.match_evaluations'::regclass)")
        ).scalar_one())
        after_database = int(connection.execute(
            text("SELECT pg_database_size(current_database())")
        ).scalar_one())
    return {
        "before_relation_bytes": before_relation,
        "after_relation_bytes": after_relation,
        "relation_reclaimed_bytes": max(0, before_relation - after_relation),
        "before_database_bytes": before_database,
        "after_database_bytes": after_database,
        "database_reclaimed_bytes": max(0, before_database - after_database),
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Plan/apply zero-dollar database footprint maintenance")
    parser.add_argument("operation", choices=("plan", "apply", "hot-dimensions-plan", "hot-dimensions-apply"))
    parser.add_argument("--truth-pack-hash")
    parser.add_argument("--dsn-env", default="OPOS_TARGET_DB_URL")
    parser.add_argument("--confirm-maintenance", action="store_true")
    args = parser.parse_args()
    if args.operation in {"plan", "apply"} and not args.truth_pack_hash:
        parser.error("--truth-pack-hash is required for cold maintenance")
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"missing required environment variable {args.dsn_env}")
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        if args.operation == "hot-dimensions-plan":
            with engine.connect() as connection:
                result = hot_dimension_compaction_plan(connection)
        elif args.operation == "hot-dimensions-apply":
            with engine.begin() as connection:
                result = compact_hot_dimension_scores(
                    connection,
                    confirm=args.confirm_maintenance,
                )
            result["physical_reclaim"] = reclaim_match_evaluation_space(engine)
        else:
            with engine.begin() as connection:
                result = (
                    build_plan(connection, truth_pack_hash=args.truth_pack_hash).as_dict()
                    if args.operation == "plan"
                    else apply_maintenance(
                        connection,
                        truth_pack_hash=args.truth_pack_hash,
                        confirm=args.confirm_maintenance,
                    )
                )
        print(json.dumps(result, sort_keys=True, default=str))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
