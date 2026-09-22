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

ARCHIVE_VERSION = "v1"


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
        ORDER BY o.id
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
    rows = [dict(row) for row in connection.execute(text(_candidate_sql()), {"truth_pack_hash": truth_pack_hash}).mappings().all()]
    # Build the archive in bounded bulk reads.  The previous per-row path did
    # one provenance query and several writes for every opportunity, which is
    # untenable for a hosted cold-state compaction of tens of thousands of
    # rows.  Payloads are still compressed and checksummed independently.
    provenance_rows = connection.execute(
        text("""
            SELECT opportunity_id, field_name, raw_value, normalized_value,
                   derivation_type, raw_pointer, record_checksum, rule_id
            FROM field_provenances
            WHERE opportunity_id = ANY(:opportunity_ids)
            ORDER BY opportunity_id, id
        """),
        {"opportunity_ids": [row["id"] for row in rows]},
    ).mappings().all() if rows else []
    provenance_by_id: dict[str, list[dict[str, Any]]] = {}
    for item in provenance_rows:
        item = dict(item)
        provenance_by_id.setdefault(item.pop("opportunity_id"), []).append(item)
    archive_rows: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            "opportunity_id": row["id"],
            "content_hash": row["content_hash"],
            "description": row["description"],
            "raw_payload_json": row["raw_payload_json"],
            "provenance": provenance_by_id.get(row["id"], []),
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        compressed = zlib.compress(raw, level=9)
        digest = hashlib.sha256(compressed).hexdigest()
        archive_rows.append({
            "opportunity_id": row["id"], "content_hash": row["content_hash"],
            "payload_zlib": compressed, "payload_sha256": digest,
            "original_size_bytes": len(raw), "archive_version": ARCHIVE_VERSION,
            "archived_at": now,
        })
        archived.append({"opportunity_id": row["id"], "compressed_bytes": len(compressed), "sha256": digest})
    if archive_rows:
        connection.execute(text("""
            INSERT INTO opportunity_cold_archive
                (opportunity_id, content_hash, payload_zlib, payload_sha256,
                 original_size_bytes, archive_version, archived_at)
            VALUES (:opportunity_id, :content_hash, :payload_zlib, :payload_sha256,
                    :original_size_bytes, :archive_version, :archived_at)
            ON CONFLICT (opportunity_id) DO NOTHING
        """), archive_rows)
        ids = [row["id"] for row in rows]
        connection.execute(text("""
            UPDATE opportunities
            SET description = '[archived]', raw_payload_json = NULL, search_tsv = NULL
            WHERE id = ANY(:opportunity_ids)
        """), {"opportunity_ids": ids})
        connection.execute(text("DELETE FROM field_provenances WHERE opportunity_id = ANY(:opportunity_ids)"), {"opportunity_ids": ids})
        connection.execute(text("""
            UPDATE feed_projection
            SET visible = FALSE, visibility_reason = 'cold_ineligible',
                search_text = '', search_tsv = NULL
            WHERE opportunity_id = ANY(:opportunity_ids)
        """), {"opportunity_ids": ids})
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan/apply zero-dollar database footprint maintenance")
    parser.add_argument("operation", choices=("plan", "apply"))
    parser.add_argument("--truth-pack-hash", required=True)
    parser.add_argument("--dsn-env", default="OPOS_TARGET_DB_URL")
    parser.add_argument("--confirm-maintenance", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"missing required environment variable {args.dsn_env}")
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            result = build_plan(connection, truth_pack_hash=args.truth_pack_hash).as_dict() if args.operation == "plan" else apply_maintenance(connection, truth_pack_hash=args.truth_pack_hash, confirm=args.confirm_maintenance)
            print(json.dumps(result, sort_keys=True, default=str))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
