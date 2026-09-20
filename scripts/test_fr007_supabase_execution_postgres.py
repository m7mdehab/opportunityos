"""Execute the committed provider SQL bundle on disposable PostgreSQL."""
from __future__ import annotations

import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit, urlunsplit

from psycopg2 import sql

from scripts import db_migration_restore as db


@unittest.skipUnless(os.environ.get("OPOS_LIVE_PROOF_TEST") == "1", "disposable PostgreSQL bundle job only")
class SupabaseBundlePostgresProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_url = os.environ[db.SOURCE]
        cls.admin = db.config("source")
        cls.database = "bundle_exec_" + str(os.getpid())
        admin = db.connect(cls.admin)
        try:
            admin.autocommit = True
            cur = admin.cursor()
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.database)))
        finally:
            admin.close()
        parts = urlsplit(cls.base_url)
        cls.target_url = urlunsplit((parts.scheme, parts.netloc, "/" + cls.database, parts.query, ""))

    @classmethod
    def tearDownClass(cls):
        admin = db.connect(cls.admin)
        try:
            admin.autocommit = True
            admin.cursor().execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(cls.database)))
        finally:
            admin.close()

    def test_generated_bundle_applies_and_enforces_rls(self):
        connection = db.connect(db.config("source", {db.SOURCE: self.target_url}))
        try:
            with connection.cursor() as cur:
                cur.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF; END $$")
                cur.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF; END $$")
                connection.commit()
                root = Path(__file__).parents[1] / "reports" / "evidence" / "FR-007" / "provider-execution"
                for path in sorted((root / "migrations").glob("*.sql")):
                    cur.execute(path.read_text(encoding="utf-8"))
                cur.execute((root / "provider-security.sql").read_text(encoding="utf-8"))
                cur.execute("SELECT version_num FROM alembic_version")
                self.assertEqual(cur.fetchone()[0], "0015_hosted_founder_surface")
                cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass('public.alembic_version')")
                self.assertTrue(cur.fetchone()[0])
                for role in ("anon", "authenticated"):
                    cur.execute("SELECT has_table_privilege(%s, 'public.founder_sessions', 'TRUNCATE')", (role,))
                    self.assertFalse(cur.fetchone()[0])
                cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass('public.founder_sessions')")
                self.assertTrue(cur.fetchone()[0])
                cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='founder_sessions'")
                self.assertGreaterEqual(cur.fetchone()[0], 2)
                # W23 D3: two truth-pack projections collapse to one feed row,
                # with a scored projection winning over an unscored historical row.
                cur.execute("""
                    INSERT INTO public.opportunities
                      (id, track, title, organization, description, source_id, source_url, content_hash)
                    VALUES ('w23-feed-opportunity', 'employment', 'Synthetic feed role', 'Synthetic org',
                            'fixture only', 'reddit:manual', 'https://example.invalid/w23', %s)
                """, ('c' * 64,))
                for projection_id, truth_hash, score in (
                    ('w23-feed-a', 'a' * 64, None), ('w23-feed-b', 'b' * 64, 91.0)
                ):
                    cur.execute("""
                        INSERT INTO public.feed_projection
                          (id, opportunity_id, opportunity_content_hash, truth_pack_hash,
                           projection_version, title, organization, source_id, source_url,
                           track, seniority_level, work_mode, remote_scope, employment_type,
                           qualification_decision, fit_score, evaluated_at, projected_at)
                        VALUES (%s, 'w23-feed-opportunity', %s, %s, 'w23', 'Synthetic feed role',
                                'Synthetic org', 'reddit:manual', 'https://example.invalid/w23',
                                'employment', 'unknown', 'remote', 'global', 'full_time',
                                'qualified', %s, now(), now())
                    """, (projection_id, 'c' * 64, truth_hash, score))
                cur.execute("SELECT count(*), max(fit_score), max(source_family) FROM public.founder_feed WHERE opportunity_id='w23-feed-opportunity'")
                self.assertEqual(cur.fetchone(), (1, 91.0, 'reddit'))
                cur.execute("GRANT SELECT ON founder_sessions TO anon, authenticated")
                cur.execute("INSERT INTO founder_sessions (id, token_digest, created_at, expires_at, auth_version) VALUES ('bundle-proof', %s, now(), now()+interval '1 hour', 'v1')", ("b" * 64,))
                connection.commit()
            for role in ("anon", "authenticated"):
                with connection.cursor() as cur:
                    cur.execute("BEGIN")
                    cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                    cur.execute("SELECT count(*) FROM founder_sessions")
                    self.assertEqual(cur.fetchone()[0], 0)
                    cur.execute("ROLLBACK")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
