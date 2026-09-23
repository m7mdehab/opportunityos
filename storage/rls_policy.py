"""Repository-owned browser-deny RLS authority for Founder Alpha."""
from __future__ import annotations

from sqlalchemy import inspect

from storage.models import Base
from storage.feed_projection import FeedProjectionRecord  # registers the shared Base table

# Every canonical application relation is browser-denied.  This registry is
# derived from the ORM metadata so a new table cannot silently escape review.
EXCLUDED = {"alembic_version"}
RLS_TABLES = frozenset(name for name in Base.metadata.tables if name not in EXCLUDED)
_TABLES_CREATED_AFTER_0009 = frozenset({
    "founder_activity_events",
    "founder_cv_selections",
    "opportunity_archive_orphans",
    "opportunity_cold_archive",
})


def registry_coverage() -> tuple[set[str], set[str]]:
    tables = set(Base.metadata.tables)
    return tables - EXCLUDED, set(RLS_TABLES)


def assert_registry_complete() -> None:
    classified, registered = registry_coverage()
    missing = classified - registered
    if missing:
        raise AssertionError("unclassified application tables: " + ", ".join(sorted(missing)))


def apply_postgres_deny_policies(op, *, excluded: set[str] | None = None) -> None:
    """Enable RLS on relations existing at this migration point.

    The registry describes the final ORM schema, while migrations create some
    registered tables later in the chain. Skip only not-yet-created tables;
    their creating migration must apply the same deny policy explicitly.
    """
    assert_registry_complete()
    excluded_tables = set(excluded or ())
    connection = op.get_bind()
    if op.get_context().as_sql:
        # This helper is called at revision 0009. Offline SQL generation has
        # no reflectable connection, so model the relation set at that exact
        # migration point and exclude tables created later in the chain.
        existing_tables = set(RLS_TABLES - _TABLES_CREATED_AFTER_0009)
    else:
        existing_tables = set(inspect(connection).get_table_names())
    for table in sorted(RLS_TABLES - excluded_tables):
        if table not in existing_tables:
            continue
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            f"EXECUTE 'CREATE POLICY {table}_browser_deny_anon ON {table} FOR ALL TO anon USING (false) WITH CHECK (false)'; "
            "END IF; "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN "
            f"EXECUTE 'CREATE POLICY {table}_browser_deny_authenticated ON {table} FOR ALL TO authenticated USING (false) WITH CHECK (false)'; "
            "END IF; END $$"
        )


def apply_postgres_deny_policy_for_table(op, table: str) -> None:
    """Apply the standard browser deny policy to a table created later."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
        f"EXECUTE 'DROP POLICY IF EXISTS {table}_browser_deny_anon ON {table}'; "
        f"EXECUTE 'CREATE POLICY {table}_browser_deny_anon ON {table} FOR ALL TO anon USING (false) WITH CHECK (false)'; "
        "END IF; "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN "
        f"EXECUTE 'DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON {table}'; "
        f"EXECUTE 'CREATE POLICY {table}_browser_deny_authenticated ON {table} FOR ALL TO authenticated USING (false) WITH CHECK (false)'; "
        "END IF; END $$"
    )


def remove_postgres_deny_policies(op, *, excluded: set[str] | None = None) -> None:
    """Remove migration 0009 policies only from relations present at downgrade time.

    The shared ORM registry also contains tables created by later revisions.
    When 0009 is downgraded from a newer schema, some such relations may
    already have been dropped by their own downgrade; guarding each operation
    keeps historical downgrade paths safe without weakening the live schema.
    """
    assert_registry_complete()
    excluded_tables = set(excluded or ())
    for table in sorted(RLS_TABLES - excluded_tables):
        op.execute(
            f"""DO $$ BEGIN
              IF to_regclass('public.{table}') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS {table}_browser_deny_anon ON public.{table}';
                EXECUTE 'DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON public.{table}';
                EXECUTE 'ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY';
              END IF;
            END $$"""
        )
