"""Assert Storage V2 migration invariants against a real disposable PostgreSQL."""
from __future__ import annotations

import json
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError


def main() -> None:
    database_url = os.environ.get("OPPORTUNITYOS_DB_URL")
    if not database_url:
        raise SystemExit("OPPORTUNITYOS_DB_URL is required")

    config = Config("alembic.ini")
    heads = ScriptDirectory.from_config(config).get_heads()
    expected_head = "0026_fr008_live_actions"
    if len(heads) != 1 or heads[0] != expected_head:
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
            feed_view = connection.execute(text(
                "SELECT pg_get_viewdef(c.oid, true), c.reloptions "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relname='founder_feed' AND c.relkind='v'"
            )).one()
            if "row_number" in str(feed_view[0]).lower():
                raise AssertionError("founder_feed must use the one-current-projection fast path")
            if "security_invoker=true" not in {str(option).replace(" ", "") for option in (feed_view[1] or [])}:
                raise AssertionError("founder_feed must retain security_invoker behavior")
            rls = connection.execute(text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relname IN "
                "('founder_activity_events','opportunity_archive_orphans','alembic_version')"
            )).all()
            grants = connection.execute(text(
                "SELECT "
                "has_table_privilege('anon','public.alembic_version','SELECT'), "
                "has_table_privilege('anon','public.alembic_version','INSERT'), "
                "has_table_privilege('anon','public.alembic_version','UPDATE'), "
                "has_table_privilege('anon','public.alembic_version','DELETE'), "
                "has_table_privilege('anon','public.alembic_version','TRUNCATE'), "
                "has_table_privilege('anon','public.alembic_version','REFERENCES'), "
                "has_table_privilege('anon','public.alembic_version','TRIGGER'), "
                "has_table_privilege('authenticated','public.alembic_version','SELECT'), "
                "has_table_privilege('authenticated','public.alembic_version','INSERT'), "
                "has_table_privilege('authenticated','public.alembic_version','UPDATE'), "
                "has_table_privilege('authenticated','public.alembic_version','DELETE'), "
                "has_table_privilege('authenticated','public.alembic_version','TRUNCATE'), "
                "has_table_privilege('authenticated','public.alembic_version','REFERENCES'), "
                "has_table_privilege('authenticated','public.alembic_version','TRIGGER')"
            )).one()
            policy_count = connection.execute(text(
                "SELECT count(*) FROM pg_policies "
                "WHERE schemaname='public' AND tablename='alembic_version'"
            )).scalar_one()
            active_rows = connection.execute(text(
                "SELECT count(*) FROM public.feed_projection WHERE truth_pack_hash='active'"
            )).scalar_one()
            projection_rows = connection.execute(text("SELECT count(*) FROM public.feed_projection")).scalar_one()
            # The migration runner is the relation owner/administrator. Verify
            # it can update its version row; roll back the no-op update.
            connection.commit()
            owner_tx = connection.begin()
            owner_revision = connection.execute(text(
                "UPDATE public.alembic_version SET version_num=version_num "
                "WHERE version_num=:revision RETURNING version_num"
            ), {"revision": expected_head}).scalar_one()
            owner_tx.rollback()
            if owner_revision != expected_head:
                raise AssertionError("Alembic owner could not update its version row")

            denied_operations: list[str] = []
            statements = {
                "SELECT": "SELECT version_num FROM public.alembic_version",
                "INSERT": "INSERT INTO public.alembic_version (version_num) VALUES ('browser-probe')",
                "UPDATE": "UPDATE public.alembic_version SET version_num='browser-probe'",
                "DELETE": "DELETE FROM public.alembic_version",
                "TRUNCATE": "TRUNCATE TABLE public.alembic_version",
            }
            for role in ("anon", "authenticated"):
                for operation, statement in statements.items():
                    probe_tx = connection.begin()
                    try:
                        connection.execute(text(f"SET LOCAL ROLE {role}"))
                        connection.execute(text(statement))
                    except DBAPIError as exc:
                        original = getattr(exc, "orig", exc)
                        if getattr(original, "pgcode", None) != "42501":
                            raise AssertionError(
                                f"{role} {operation} probe failed with unexpected SQLSTATE"
                            ) from exc
                        denied_operations.append(f"{role}:{operation}")
                    else:
                        raise AssertionError(f"browser role {role} unexpectedly completed {operation}")
                    finally:
                        probe_tx.rollback()

        if revision != expected_head:
            raise AssertionError(f"database revision is {revision!r}, not {expected_head}")
        if {name for name, enabled in rls if enabled} != {
            "founder_activity_events", "opportunity_archive_orphans", "alembic_version"
        }:
            raise AssertionError(f"RLS is not enabled on required tables: {rls!r}")
        if any(grants):
            raise AssertionError(f"browser roles retain alembic_version privileges: {grants!r}")
        if policy_count:
            raise AssertionError("alembic_version must use revoked privileges and default-deny RLS, not browser policies")
        if len(denied_operations) != 10:
            raise AssertionError(f"not all browser probes were denied: {denied_operations!r}")
        if active_rows or projection_rows:
            raise AssertionError("migration must leave a clean, empty current projection for rebuild")

        print(json.dumps({
            "status": "pass",
            "revision": revision,
            "alembic_heads": heads,
            "alembic_owner_update": "pass",
            "browser_alembic_version_denials": denied_operations,
            "alembic_version_rls_enabled": True,
            "alembic_version_browser_privileges": "revoked",
            "required_tables": sorted(required),
            "feed_projection_rows_after_migration": projection_rows,
            "synthetic_active_rows": active_rows,
            "founder_feed_fast_path": "direct_current_projection",
            "rls_enabled": sorted(name for name, enabled in rls if enabled),
        }, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
