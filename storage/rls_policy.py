"""Repository-owned browser-deny RLS authority for Founder Alpha."""
from __future__ import annotations

from storage.models import Base
from storage.feed_projection import FeedProjectionRecord  # registers the shared Base table

# Every canonical application relation is browser-denied.  This registry is
# derived from the ORM metadata so a new table cannot silently escape review.
EXCLUDED = {"alembic_version"}
RLS_TABLES = frozenset(name for name in Base.metadata.tables if name not in EXCLUDED)


def registry_coverage() -> tuple[set[str], set[str]]:
    tables = set(Base.metadata.tables)
    return tables - EXCLUDED, set(RLS_TABLES)


def assert_registry_complete() -> None:
    classified, registered = registry_coverage()
    missing = classified - registered
    if missing:
        raise AssertionError("unclassified application tables: " + ", ".join(sorted(missing)))


def apply_postgres_deny_policies(op) -> None:
    """Enable RLS and conditionally deny Supabase-like roles when present."""
    assert_registry_complete()
    for table in sorted(RLS_TABLES):
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


def remove_postgres_deny_policies(op) -> None:
    """Remove only migration 0009 policies and its RLS enablement."""
    assert_registry_complete()
    for table in sorted(RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_browser_deny_anon ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
