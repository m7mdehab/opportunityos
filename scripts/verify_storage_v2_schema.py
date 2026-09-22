"""Assert Storage V2 migration invariants against a real disposable PostgreSQL."""
from __future__ import annotations

import json
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def main() -> None:
    database_url = os.environ.get("OPPORTUNITYOS_DB_URL")
    if not database_url:
        raise SystemExit("OPPORTUNITYOS_DB_URL is required")

    config = Config("alembic.ini")
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1 or heads[0] != "0022_storage_v2_direct_tiering":
        raise AssertionError(f"expected one Storage V2 Alembic head, got {heads!r}")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names(schema="public"))
        required = {
            "opportunities", "opportunity_cold_archive", "opportunity_archive_orphans",
            "field_provenances", "match_evaluations", "feed_projection",
            "founder_activity_events",
        }
        missing = required - tables
        if missing:
            raise AssertionError(f"missing Storage V2 tables: {sorted(missing)}")

        columns = {
            table: {column["name"]: column for column in inspector.get_columns(table, schema="public")}
            for table in required
        }
        if columns["feed_projection"].keys() & {"search_text", "search_tsv", "description"}:
            raise AssertionError("feed_projection contains a duplicate full-text/body field")
        if columns["opportunities"]["description"]["nullable"] is not True:
            raise AssertionError("cold opportunity descriptions must be nullable")
        if not {"lifecycle_tier", "archive_object_key", "archive_sha256"}.issubset(columns["opportunities"]):
            raise AssertionError("opportunities is missing lifecycle/archive state")
        if columns["opportunity_cold_archive"]["payload_zlib"]["nullable"] is not True:
            raise AssertionError("hosted cold archive must not require a PostgreSQL payload")
        if not {"storage_backend", "object_key", "compressed_size_bytes"}.issubset(columns["opportunity_cold_archive"]):
            raise AssertionError("cold archive metadata is incomplete")
        if not {"content_hash", "hard_failure_code"}.issubset(columns["match_evaluations"]):
            raise AssertionError("current evaluation lacks content identity or compact reason")
        if columns["match_evaluations"]["dimension_scores_json"]["nullable"] is not True:
            raise AssertionError("cold evaluations must be allowed to omit verbose dimensions")

        projection_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("feed_projection", schema="public")
        }
        if ("opportunity_id",) not in projection_uniques:
            raise AssertionError("feed_projection must have one current row per opportunity")
        evaluation_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("match_evaluations", schema="public")
        }
        if ("opportunity_id",) not in evaluation_uniques:
            raise AssertionError("match_evaluations must have one current row per opportunity")
        indexes = {
            item["name"]
            for item in inspector.get_indexes("feed_projection", schema="public")
        }
        if any("search" in name for name in indexes):
            raise AssertionError(f"projection retains a duplicate search index: {indexes!r}")

        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            rls = connection.execute(text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relname IN "
                "('founder_activity_events','opportunity_archive_orphans')"
            )).all()
            active_rows = connection.execute(text(
                "SELECT count(*) FROM public.feed_projection WHERE truth_pack_hash='active'"
            )).scalar_one()
            projection_rows = connection.execute(text("SELECT count(*) FROM public.feed_projection")).scalar_one()

        if revision != "0022_storage_v2_direct_tiering":
            raise AssertionError(f"database revision is {revision!r}, not 0022")
        if {name for name, enabled in rls if enabled} != {
            "founder_activity_events", "opportunity_archive_orphans"
        }:
            raise AssertionError(f"RLS is not enabled on required tables: {rls!r}")
        if active_rows or projection_rows:
            raise AssertionError("migration must leave a clean, empty current projection for rebuild")

        print(json.dumps({
            "status": "pass",
            "revision": revision,
            "alembic_heads": heads,
            "required_tables": sorted(required),
            "feed_projection_rows_after_migration": projection_rows,
            "synthetic_active_rows": active_rows,
            "rls_enabled": sorted(name for name, enabled in rls if enabled),
        }, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
