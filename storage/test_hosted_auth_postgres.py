"""Disposable PostgreSQL proof for migration 0009 RLS effects.

This test is executed by the repository's PostgreSQL CI service.  It is not a
hosted Supabase acceptance test; without a PostgreSQL DSN it remains visibly
unexecuted rather than manufacturing a local PASS.
"""
from __future__ import annotations

import os
import unittest

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


class HostedAuthPostgresAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_url = os.environ.get("OPPORTUNITYOS_DB_URL")
        if not cls.db_url or not cls.db_url.startswith("postgresql"):
            raise unittest.SkipTest("real PostgreSQL DSN required; hosted-auth RLS proof not executed")
        cls.engine = sa.create_engine(cls.db_url)
        with cls.engine.begin() as conn:
            conn.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF; END $$")
            conn.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF; END $$")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def _alembic(self, revision: str) -> None:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", self.db_url.replace("%", "%%"))
        command.downgrade(config, revision) if revision == "0008_artifact_storage" else command.upgrade(config, revision)

    def _state(self, table: str) -> tuple[bool, int]:
        with self.engine.connect() as conn:
            enabled = conn.execute(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:table)"), {"table": table}).scalar()
            policies = conn.execute(sa.text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=:table AND policyname LIKE '%_browser_deny_%'"), {"table": table}).scalar()
            return bool(enabled), int(policies)

    def test_upgrade_downgrade_upgrade_rls_and_owner_path(self):
        # CI migrates the shared disposable database to head before running the
        # suite. Rewind first so 0009 actually executes after the Supabase-like
        # roles exist; otherwise an upgrade-to-0009 call is a no-op.
        self._alembic("0008_artifact_storage")
        self._alembic("0009_hosted_founder_auth")

        enabled, policies = self._state("opportunities")
        self.assertTrue(enabled)
        self.assertGreaterEqual(policies, 2)

        # Prove the backend/owner path remains usable and the browser roles are
        # denied by RLS even when SELECT is explicitly granted.
        with self.engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO founder_sessions "
                "(id, token_digest, created_at, expires_at, auth_version) "
                "VALUES ('rls-proof', :digest, now(), now() + interval '1 hour', 'v1')"
            ), {"digest": "a" * 64})
            owner_count = conn.execute(sa.text(
                "SELECT count(*) FROM founder_sessions WHERE id='rls-proof'"
            )).scalar_one()
            self.assertEqual(owner_count, 1)
            conn.exec_driver_sql("GRANT SELECT ON founder_sessions TO anon, authenticated")

        for role in ("anon", "authenticated"):
            with self.engine.begin() as conn:
                conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
                visible = conn.execute(sa.text(
                    "SELECT count(*) FROM founder_sessions WHERE id='rls-proof'"
                )).scalar_one()
                self.assertEqual(visible, 0, f"{role} must be denied by RLS")

        self._alembic("0008_artifact_storage")
        enabled, policies = self._state("opportunities")
        self.assertFalse(enabled)
        self.assertEqual(policies, 0)

        self._alembic("head")
        enabled, policies = self._state("opportunities")
        self.assertTrue(enabled)
        # At hosted head, anon remains fail-closed while authenticated access
        # is deliberately replaced by the Founder-only read policy from 0011.
        self.assertEqual(policies, 1)
        with self.engine.connect() as conn:
            founder_policy = conn.execute(sa.text(
                "SELECT count(*) FROM pg_policies "
                "WHERE schemaname='public' AND tablename='opportunities' "
                "AND policyname='opportunities_founder_authenticated_read'"
            )).scalar_one()
        self.assertEqual(founder_policy, 1)


if __name__ == "__main__":
    unittest.main()
