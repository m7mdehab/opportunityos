"""Bounded, encrypted-backup input for irreplaceable Founder state.

Only the allowlisted Founder/configuration tables are read. Opportunity rows
are fetched only for Founder-protected or Founder-referenced IDs; the source
corpus is never scanned or exported wholesale by the daily backup path.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

from sqlalchemy import MetaData, Text, create_engine, func, select, text, union
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.db_migration_restore import config
from scripts.encrypted_backup import decrypted_backup


STATE_TABLES = (
    "founder_activity_events",
    "founder_feedback",
    "founder_triage_states",
    "founder_opportunity_views",
    "founder_cv_selections",
    "founder_filter_settings",
    "founder_facets",
    "founder_saved_views",
    "founder_notifications",
    "outbound_actions",
    "idempotency_reservations",
    "pipeline_events",
    "inbox_checkpoints",
    "inbound_evidence",
)
SNAPSHOT_TABLES = ("opportunities", *STATE_TABLES)
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_PROTECTED_OPPORTUNITIES = 10_000
FORMAT_NAME = "opportunityos-founder-state"


class FounderStateBackupError(Exception):
    """Safe, redacted backup/restore failure."""


def _json_default(value):
    if isinstance(value, datetime):
        return {"__opos_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__opos_type__": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__opos_type__": "decimal", "value": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__opos_type__": "bytes", "value": base64.b64encode(bytes(value)).decode("ascii")}
    raise TypeError(f"unsupported Founder-state value type: {type(value).__name__}")


def _json_object_hook(value):
    kind = value.get("__opos_type__")
    raw = value.get("value")
    if kind == "datetime" and len(value) == 2:
        return datetime.fromisoformat(raw)
    if kind == "date" and len(value) == 2:
        return date.fromisoformat(raw)
    if kind == "decimal" and len(value) == 2:
        return Decimal(raw)
    if kind == "bytes" and len(value) == 2:
        return base64.b64decode(raw, validate=True)
    return value


def _table(metadata: MetaData, dialect: str, name: str):
    key = f"public.{name}" if dialect == "postgresql" else name
    try:
        return metadata.tables[key]
    except KeyError as exc:
        raise FounderStateBackupError("Founder-state schema is incomplete") from exc


def export_snapshot(engine, destination: str | Path) -> dict:
    output = Path(destination).expanduser().resolve()
    if output.exists() or not output.parent.is_dir():
        raise FounderStateBackupError("snapshot destination must be a new file in an existing directory")
    dialect = engine.dialect.name
    metadata = MetaData()
    schema = "public" if dialect == "postgresql" else None
    try:
        metadata.reflect(bind=engine, schema=schema, only=list(SNAPSHOT_TABLES))
        with engine.connect() as conn:
            with conn.begin():
                if dialect == "postgresql":
                    conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    revisions = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
                else:
                    revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
                if len(revisions) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", revisions[0]):
                    raise FounderStateBackupError("exactly one valid schema revision is required")

                tables = {name: _table(metadata, dialect, name) for name in SNAPSHOT_TABLES}
                opportunity = tables["opportunities"]
                id_queries = [select(opportunity.c.id).where(opportunity.c.lifecycle_tier == "protected")]
                for name in STATE_TABLES:
                    table = tables[name]
                    if "opportunity_id" in table.c:
                        id_queries.append(select(table.c.opportunity_id).where(table.c.opportunity_id.is_not(None)))
                id_union = union(*id_queries).limit(MAX_PROTECTED_OPPORTUNITIES + 1)
                opportunity_ids = sorted(str(row[0]) for row in conn.execute(id_union).all())
                if len(opportunity_ids) > MAX_PROTECTED_OPPORTUNITIES:
                    raise FounderStateBackupError("Founder-protected opportunity count exceeds backup safety cap")

                # Measure serialized row bodies server-side before retrieving
                # them. pg_column_size(table) can omit out-of-line TOAST data,
                # so use the JSON representation and a conservative expansion
                # allowance for Python's tagged date/byte encoding.
                estimated_encoded_bytes = 0
                if dialect == "postgresql":
                    for name in SNAPSHOT_TABLES:
                        table = tables[name]
                        if name == "opportunities" and not opportunity_ids:
                            continue
                        size_source = table.alias("backup_source_row")
                        size_query = select(
                            func.coalesce(func.sum(func.octet_length(
                                func.to_jsonb(size_source.table_valued()).cast(Text)
                            )), 0),
                            func.count(),
                        ).select_from(size_source)
                        if name == "opportunities":
                            size_query = size_query.where(size_source.c.id.in_(opportunity_ids))
                        json_row_bytes, row_count = conn.execute(size_query).one()
                        estimated_encoded_bytes += 2 * int(json_row_bytes) + 128 * int(row_count)
                        if estimated_encoded_bytes > MAX_SNAPSHOT_BYTES:
                            raise FounderStateBackupError("Founder-state source rows exceed the 8 MiB egress safety cap")

                rows_by_table = {}
                for name in SNAPSHOT_TABLES:
                    table = tables[name]
                    statement = select(table)
                    if name == "opportunities":
                        statement = statement.where(table.c.id.in_(sorted(opportunity_ids))) if opportunity_ids else None
                    rows = [] if statement is None else [
                        {key: value for key, value in row._mapping.items()}
                        for row in conn.execute(statement)
                    ]
                    rows_by_table[name] = rows

        payload = {
            "format": FORMAT_NAME,
            "version": 1,
            "backup_class": "founder_state",
            "source_revision": revisions[0],
            "created_at": datetime.now(timezone.utc),
            "table_rows": rows_by_table,
            "protected_opportunity_count": len(rows_by_table["opportunities"]),
        }
        encoded = json.dumps(payload, default=_json_default, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > MAX_SNAPSHOT_BYTES:
            raise FounderStateBackupError("Founder-state snapshot exceeds the 8 MiB egress safety cap")
        compressed = gzip.compress(encoded, compresslevel=6, mtime=0)
        with output.open("xb") as stream:
            stream.write(compressed)
        return {
            "status": "PASS",
            "backup_class": "founder_state",
            "source_revision": revisions[0],
            "protected_opportunities": len(rows_by_table["opportunities"]),
            "row_counts": {name: len(rows) for name, rows in rows_by_table.items()},
            "source_json_bytes": len(encoded),
            "compressed_bytes": len(compressed),
            "sha256": hashlib.sha256(compressed).hexdigest(),
        }
    except FounderStateBackupError:
        output.unlink(missing_ok=True)
        raise
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise FounderStateBackupError(f"Founder-state export failed ({type(exc).__name__})") from None


def load_snapshot(path: str | Path) -> dict:
    try:
        with gzip.open(path, "rb") as stream:
            encoded = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(encoded) > MAX_SNAPSHOT_BYTES:
            raise FounderStateBackupError("Founder-state snapshot exceeds the 8 MiB safety cap")
        payload = json.loads(encoded, object_hook=_json_object_hook)
    except FounderStateBackupError:
        raise
    except Exception as exc:
        raise FounderStateBackupError(f"Founder-state snapshot invalid ({type(exc).__name__})") from None
    if (not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME
            or payload.get("version") != 1 or payload.get("backup_class") != "founder_state"
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", str(payload.get("source_revision", "")))
            or not isinstance(payload.get("table_rows"), dict)
            or set(payload["table_rows"]) != set(SNAPSHOT_TABLES)
            or any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
                   for rows in payload["table_rows"].values())):
        raise FounderStateBackupError("Founder-state snapshot contract mismatch")
    if len(payload["table_rows"]["opportunities"]) > MAX_PROTECTED_OPPORTUNITIES:
        raise FounderStateBackupError("Founder-protected opportunity count exceeds restore safety cap")
    return payload


def restore_snapshot(engine, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else load_snapshot(payload)
    # Revalidate callers that pass an in-memory payload rather than a file.
    if (payload.get("format") != FORMAT_NAME or payload.get("version") != 1
            or payload.get("backup_class") != "founder_state"
            or set(payload.get("table_rows", {})) != set(SNAPSHOT_TABLES)):
        raise FounderStateBackupError("Founder-state snapshot contract mismatch")
    dialect = engine.dialect.name
    metadata = MetaData()
    schema = "public" if dialect == "postgresql" else None
    try:
        metadata.reflect(bind=engine, schema=schema, only=list(SNAPSHOT_TABLES))
        restored_counts = {}
        with engine.begin() as conn:
            # Opportunity parents are inserted if absent but never overwritten:
            # a newer source poll remains authoritative for existing IDs.
            for name in SNAPSHOT_TABLES:
                rows = payload["table_rows"][name]
                if not rows:
                    restored_counts[name] = 0
                    continue
                table = _table(metadata, dialect, name)
                allowed_columns = set(table.c.keys())
                if any(set(row) - allowed_columns for row in rows):
                    raise FounderStateBackupError("snapshot columns do not match the migrated schema")
                if dialect not in ("postgresql", "sqlite"):
                    raise FounderStateBackupError("unsupported restore database dialect")
                primary_keys = [column.name for column in table.primary_key.columns]
                if not primary_keys:
                    raise FounderStateBackupError("Founder-state table has no primary key")
                restored_counts[name] = len(rows)
                for start in range(0, len(rows), 100):
                    batch = rows[start:start + 100]
                    statement = (pg_insert(table) if dialect == "postgresql" else sqlite_insert(table)).values(batch)
                    if name == "opportunities":
                        statement = statement.on_conflict_do_nothing(index_elements=[table.c[key] for key in primary_keys])
                    else:
                        updates = {
                            column.name: getattr(statement.excluded, column.name)
                            for column in table.columns if column.name not in primary_keys
                        }
                        if updates:
                            statement = statement.on_conflict_do_update(
                                index_elements=[table.c[key] for key in primary_keys], set_=updates
                            )
                        else:
                            statement = statement.on_conflict_do_nothing(index_elements=[table.c[key] for key in primary_keys])
                    conn.execute(statement)
        return {"status": "PASS", "backup_class": "founder_state", "restored_rows": restored_counts}
    except FounderStateBackupError:
        raise
    except Exception as exc:
        raise FounderStateBackupError(f"Founder-state restore failed ({type(exc).__name__})") from None


def _engine(role: str):
    settings = config(role)
    return create_engine(settings["dsn"], future=True, pool_size=1, max_overflow=0, pool_pre_ping=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    export = sub.add_parser("export")
    export.add_argument("--output", required=True)
    restore = sub.add_parser("restore-encrypted")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--encrypted-manifest", required=True)
    restore.add_argument("--confirm-target-restore", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.operation == "export":
            engine = _engine("source")
            try:
                result = export_snapshot(engine, args.output)
            finally:
                engine.dispose()
        else:
            if not args.confirm_target_restore:
                raise FounderStateBackupError("explicit Founder-state restore confirmation required")
            with Path(args.encrypted_manifest).open(encoding="utf-8") as stream:
                encrypted_manifest = json.load(stream)
            if encrypted_manifest.get("backup_class") != "founder_state":
                raise FounderStateBackupError("encrypted artifact is not a Founder-state backup")
            engine = _engine("target")
            try:
                with decrypted_backup(args.archive, encrypted_manifest) as plaintext:
                    result = restore_snapshot(engine, load_snapshot(plaintext))
            finally:
                engine.dispose()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error_class": type(exc).__name__, "details": "suppressed"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
