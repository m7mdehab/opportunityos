"""Real PostgreSQL failure drills; all databases and rows are disposable."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlsplit, urlunsplit

from psycopg2 import sql

from scripts import db_migration_restore as db
from scripts import migration_acceptance as acceptance


def db_url(url, name):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, ""))


@unittest.skipUnless(os.environ.get("OPOS_LIVE_PROOF_TEST") == "1", "dedicated disposable PostgreSQL job only")
class AcceptancePostgresDrills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_url = os.environ[db.SOURCE]
        cls.admin = db.config("source")
        cls.databases = ["accept_source"]
        cls._create("accept_source")
        cls.source_url = db_url(cls.base_url, "accept_source")
        with mock.patch.dict(os.environ, {db.SOURCE: cls.source_url}):
            cls.source = db.config("source")
            db.migrate(cls.source)
            connection = db.connect(cls.source)
            try:
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO public.opportunities "
                    "(id,track,title,organization,description,source_id,source_url,content_hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    ("accept_opp", "employment", "Synthetic role", "Fixture organization",
                     "Synthetic fixture only", "fixture_source", "https://example.invalid/fixture", "a" * 64))
                cursor.execute(
                    "INSERT INTO public.match_evaluations "
                    "(id,opportunity_id,truth_pack_hash,qualification_decision,fit_score,"
                    "dimension_scores_json,reasons_json,policy_version,evaluated_at,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                    ("accept_eval", "accept_opp", "b" * 64, "uncertain", 0.5, "{}", "[]", "fixture-v1"))
                cursor.execute(
                    "INSERT INTO public.artifact_cache "
                    "(cache_key,opportunity_id,truth_pack_hash,template_id,artifact_kind,content_type,payload,storage_backend) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    ("c" * 64, "accept_opp", "b" * 64, "fixture", "pdf", "application/pdf",
                     b"synthetic acceptance artifact", "postgres_payload"))
                connection.commit()
            finally:
                connection.close()

    @classmethod
    def tearDownClass(cls):
        for name in reversed(getattr(cls, "databases", [])):
            connection = db.connect(cls.admin)
            try:
                connection.autocommit = True
                cursor = connection.cursor()
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            finally:
                connection.close()

    @classmethod
    def _create(cls, name):
        connection = db.connect(cls.admin)
        try:
            connection.autocommit = True
            cursor = connection.cursor()
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        finally:
            connection.close()

    @contextmanager
    def target(self):
        name = "accept_target_" + self._testMethodName.split("test_", 1)[-1][:45]
        self._create(name)
        self.databases.append(name)
        url = db_url(self.base_url, name)
        with mock.patch.dict(os.environ, {db.SOURCE: self.source_url, db.TARGET: url}):
            yield db.target_config()

    def execute(self, *, hook=None):
        with tempfile.TemporaryDirectory(prefix="opos-accept-drill-") as directory:
            report = acceptance.run(directory, connection_mode="direct", confirm_restore=True,
                                    source_writes_paused=True, target_writes_disabled=True,
                                    allow_insecure_local=True, _test_hook=hook)
            self.assertEqual(report["decision"], "REJECT")
            self.assertFalse(report["traffic_cutover_authorized"])
            self.assertNotIn(os.environ[db.SOURCE], str(report))
            self.assertNotIn(os.environ[db.TARGET], str(report))
            return report

    def test_partially_migrated_target_blocks_before_backup(self):
        with self.target() as target:
            db.migrate(target)
            result = self.execute()
            self.assertEqual(result["stages"]["fresh_target_validation"], "BLOCKED")
            self.assertEqual(result["stages"]["backup"], "NOT_RUN")

    def test_clean_restore_reports_all_machine_evidence_without_claiming_acceptance(self):
        with self.target():
            result = self.execute()
            for name in ("backup", "manifest_checksum", "fresh_target_validation",
                         "restore_import", "revision_verification", "evaluation_parity",
                         "feed_projection_parity", "triage_state_parity", "artifact_metadata",
                         "artifact_body"):
                self.assertEqual(result["stages"][name], "PASS", name)
            self.assertEqual(result["stages"]["structural_parity"], "PARTIAL")
            self.assertEqual(result["table_parity"]["opportunities"]["count_status"], "PASS")
            self.assertEqual(result["identity_parity"]["opportunities"], "PASS")
            self.assertEqual(result["evaluation_distributions"]["target"], {"uncertain": 1})
            self.assertEqual(result["projection_counts"], {"source": 0, "target": 0})
            self.assertEqual(len(result["backup_sha256"]), 64)
            self.assertEqual(len(result["source_fingerprint"]), 24)
            self.assertIn("tables.source_states", result["unsupported_concepts"])
            self.assertEqual(result["gates"]["A-9"]["status"], "PARTIAL")

    def test_interrupted_restore_isolates_partial_target(self):
        with self.target() as target:
            def interrupted(settings, archive, **kwargs):
                connection = db.connect(settings)
                try:
                    cursor = connection.cursor()
                    cursor.execute("CREATE TABLE public.interrupted_fixture (id integer)")
                    connection.commit()
                finally:
                    connection.close()
                raise db.HarnessError("simulated restore interruption")
            with mock.patch.object(db, "restore", side_effect=interrupted):
                result = self.execute()
            self.assertEqual(result["stages"]["restore_import"], "FAIL")
            self.assertEqual(result["stages"]["revision_verification"], "NOT_RUN")
            self.assertGreater(db.inspect(target)["table_count"], 0)

    def test_corrupt_archive_fails_checksum_before_restore(self):
        with self.target() as target:
            def corrupt(stage, source, target, archive):
                if stage == "before_restore":
                    with Path(archive).open("ab") as stream:
                        stream.write(b"corrupt")
            result = self.execute(hook=corrupt)
            self.assertEqual(result["stages"]["restore_import"], "FAIL")
            self.assertEqual(db.inspect(target)["table_count"], 0)

    def test_parity_mismatch_rejects(self):
        with self.target():
            def mismatch(stage, source, target, archive):
                if stage == "before_parity":
                    self.sql(target, "UPDATE public.opportunities SET content_hash = %s", ("d" * 64,))
            result = self.execute(hook=mismatch)
            self.assertEqual(result["stages"]["structural_parity"], "FAIL")
            self.assertEqual(result["table_parity"]["opportunities"]["count_status"], "PASS")
            self.assertEqual(result["identity_parity"]["opportunities"], "FAIL")
            self.assertEqual(result["gates"]["A-9"]["status"], "FAIL")

    def test_stale_alembic_revision_rejects(self):
        with self.target():
            def stale(stage, source, target, archive):
                if stage == "after_migration":
                    self.sql(target, "UPDATE public.alembic_version SET version_num = %s",
                             ("0005_widen_location_region",))
            result = self.execute(hook=stale)
            self.assertEqual(result["stages"]["revision_verification"], "FAIL")
            self.assertEqual(result["stages"]["structural_parity"], "NOT_RUN")

    def test_duplicate_canonical_identity_rejects(self):
        with self.target():
            def duplicate(stage, source, target, archive):
                if stage == "before_parity":
                    self.sql(target, "ALTER TABLE public.opportunities DROP CONSTRAINT opportunities_pkey CASCADE")
                    self.sql(target, "INSERT INTO public.opportunities SELECT * FROM public.opportunities WHERE id='accept_opp'")
            result = self.execute(hook=duplicate)
            self.assertEqual(result["stages"]["structural_parity"], "FAIL")
            self.assertTrue(any("duplicate_opportunity_ids" in item for item in
                                result["stage_details"]["structural_parity"]["difference_paths"]))

    def test_feed_projection_mismatch_rejects(self):
        with self.target():
            def projection(stage, source, target, archive):
                if stage == "before_parity":
                    self.sql(target,
                        "INSERT INTO public.feed_projection "
                        "(id,opportunity_id,opportunity_content_hash,truth_pack_hash,projection_version,"
                        "title,organization,source_id,source_url,track,seniority_level,work_mode,"
                        "remote_scope,employment_type,evaluated_at,projected_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                        ("feed_fixture", "accept_opp", "a" * 64, "b" * 64, "fixture-v1",
                         "Synthetic role", "Fixture organization", "fixture_source", "https://example.invalid/fixture",
                         "employment", "unknown", "unknown", "unknown", "unknown"))
            result = self.execute(hook=projection)
            self.assertEqual(result["stages"]["feed_projection_parity"], "FAIL")
            self.assertEqual(result["gates"]["A-9"]["status"], "FAIL")

    def test_artifact_body_unavailable_rejects(self):
        with self.target():
            def missing(stage, source, target, archive):
                if stage == "before_artifact":
                    self.sql(target, "UPDATE public.artifact_cache SET payload = NULL")
            result = self.execute(hook=missing)
            self.assertEqual(result["stages"]["artifact_metadata"], "PASS")
            self.assertEqual(result["stages"]["artifact_body"], "FAIL")
            self.assertEqual(result["artifact_results"]["artifact_body"]["missing"], 1)

    def test_dry_run_keeps_target_empty(self):
        with self.target() as target:
            with tempfile.TemporaryDirectory(prefix="opos-accept-dry-") as directory:
                result = acceptance.run(directory, dry_run=True, connection_mode="direct",
                                        allow_insecure_local=True)
            self.assertEqual(result["decision"], "REJECT")
            self.assertEqual(result["stages"]["restore_import"], "NOT_RUN")
            self.assertEqual(db.inspect(target)["table_count"], 0)

    @staticmethod
    def sql(settings, statement, params=None):
        connection = db.connect(settings)
        try:
            cursor = connection.cursor()
            cursor.execute(statement, params)
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
