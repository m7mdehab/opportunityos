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
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", cls.db_url.replace("%", "%%"))
        command.upgrade(config, "head")

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

    def test_fr008_query_fast_paths_migrate_with_founder_contract(self):
        with self.engine.begin() as conn:
            fixture_savepoint = conn.begin_nested()
            index_exists = conn.execute(sa.text(
                "SELECT to_regclass('public.ix_opportunities_created_at') IS NOT NULL"
            )).scalar_one()
            conn.exec_driver_sql("SET LOCAL enable_seqscan = off")
            index_plan = " ".join(conn.execute(sa.text(
                "EXPLAIN (COSTS OFF) SELECT id FROM public.opportunities "
                "WHERE created_at >= current_date - 1 AND created_at < current_date + 1"
            )).scalars().all())
            conn.exec_driver_sql("SET LOCAL enable_seqscan = on")
            view_sql = conn.execute(sa.text(
                "SELECT pg_get_viewdef('public.founder_feed_fr008'::regclass, true)"
            )).scalar_one().lower()
            columns = conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='founder_feed_fr008' "
                "ORDER BY ordinal_position"
            )).scalars().all()
            dashboard_sql = conn.execute(sa.text(
                "SELECT pg_get_functiondef('public.founder_dashboard_daily(integer,double precision)'::regprocedure)"
            )).scalar_one().lower()
            founder_id = conn.execute(sa.text(
                "SELECT supabase_user_id FROM public.founder_identity WHERE id='singleton'"
            )).scalar_one_or_none()
            if founder_id is None:
                founder_id = "00000000-0000-0000-0000-000000000029"
                conn.execute(sa.text(
                    "INSERT INTO public.founder_identity(id,supabase_user_id) "
                    "VALUES ('singleton',:founder_id)"
                ), {"founder_id": founder_id})
            conn.execute(sa.text(
                "SELECT set_config('request.jwt.claim.sub',:founder_id,true)"
            ), {"founder_id": founder_id})
            conn.exec_driver_sql("SET LOCAL ROLE authenticated")
            today = conn.execute(sa.text(
                "SELECT * FROM public.founder_dashboard_daily(1,80)"
            )).mappings().one()
            all_time = conn.execute(sa.text(
                "SELECT * FROM public.founder_dashboard_daily(0,80) ORDER BY date DESC"
            )).mappings().all()
            two_days = conn.execute(sa.text(
                "SELECT * FROM public.founder_dashboard_daily(2,80) ORDER BY date DESC"
            )).mappings().all()
            fixture_savepoint.rollback()

        self.assertIn("founder_feed f", view_sql)
        self.assertTrue(index_exists)
        self.assertIn("ix_opportunities_created_at", index_plan)
        self.assertNotIn("founder_activity_state", view_sql)
        self.assertNotIn("founder_feed_activity", view_sql)
        self.assertLess(columns.index("action_state"), columns.index("role_relevance_class"))
        self.assertLess(columns.index("has_activity"), columns.index("remote_rank"))
        self.assertIn("p_days = 0", dashboard_sql)
        self.assertIn("filter (where", dashboard_sql)
        self.assertIn("generate_series", dashboard_sql)
        self.assertIn("jsonb_array_elements_text", dashboard_sql)
        self.assertEqual(today["date"], all_time[0]["date"])
        self.assertEqual(len(all_time), 1)
        self.assertEqual(len(two_days), 2)
        for metric in ("fetched", "unique_new", "qualified", "high_fit", "opened", "labelled", "applied", "hidden_by_filters"):
            self.assertGreaterEqual(all_time[0][metric], today[metric])


if __name__ == "__main__":
    unittest.main()
