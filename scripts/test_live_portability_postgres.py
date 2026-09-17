"""Disposable real-PostgreSQL proof; enabled only in the dedicated CI job."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import artifact_integrity as artifacts
from scripts import db_migration_restore as db
from scripts import live_portability_proof as proof
from scripts import portability_bundle as bundle


@unittest.skipUnless(os.environ.get("OPOS_LIVE_PROOF_TEST") == "1", "dedicated disposable PostgreSQL job only")
class LivePostgresPortabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = db.config("source")
        cls.target = db.target_config()
        if db.inspect(cls.source)["table_count"] or db.inspect(cls.target)["table_count"]:
            raise AssertionError("disposable source and target must start empty")
        db.migrate(cls.source)
        connection = db.connect(cls.source)
        try:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO public.opportunities "
                "(id,track,title,organization,description,source_id,source_url,content_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                ("opp_fixture_1", "employment", "Synthetic role", "Fixture organization",
                 "Synthetic fixture only", "fixture_source", "https://example.invalid/fixture", "a" * 64))
            cursor.execute(
                "INSERT INTO public.match_evaluations "
                "(id,opportunity_id,truth_pack_hash,qualification_decision,fit_score,"
                "dimension_scores_json,reasons_json,policy_version,evaluated_at,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                ("eval_fixture_1", "opp_fixture_1", "b" * 64, "uncertain", 0.5, "{}", "[]", "fixture-v1"))
            cursor.execute(
                "INSERT INTO public.founder_triage_states "
                "(opportunity_id,state,created_at,updated_at) "
                "VALUES (%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                ("opp_fixture_1", "dismissed"))
            cursor.execute(
                "INSERT INTO public.artifact_cache "
                "(cache_key,opportunity_id,truth_pack_hash,template_id,artifact_kind,content_type,payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s,%s,%s)",
                ("c" * 64, "opp_fixture_1", "b" * 64, "fixture", "pdf", "application/pdf",
                 b"synthetic artifact bytes", "d" * 64, "opp_fixture_1", "b" * 64,
                 "fixture", "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", None))
            connection.commit()
        finally:
            connection.close()
        cls.temp = tempfile.TemporaryDirectory(prefix="opos-live-proof-")
        cls.workspace = Path(cls.temp.name)
        result = subprocess.run(
            [sys.executable, str(db.ROOT / "scripts" / "live_portability_proof.py"),
             "--output-dir", str(cls.workspace), "--confirm-target-restore", "--allow-partial"],
            cwd=db.ROOT, capture_output=True, text=True, check=False, shell=False)
        if result.returncode:
            raise AssertionError("live proof runner failed; sanitized output=" + result.stdout[-4000:])
        cls.report = json.loads(result.stdout)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def test_actual_postgres_flow_and_independent_states(self):
        stages = self.report["stages"]
        for name in ("backup_creation", "manifest_creation", "checksum_verification",
                     "restore", "migration_revision", "artifact_metadata", "provider_exit_bundle"):
            self.assertEqual(stages[name], "PASS", name)
        self.assertEqual(stages["structural_parity"], "PARTIAL")
        self.assertEqual(stages["artifact_body"], "PARTIAL")
        self.assertIn("tables.source_states", self.report["details"]["structural_parity"]["unsupported"])
        self.assertEqual(self.report["details"]["artifact_body"]["retrievable"], 1)
        self.assertEqual(self.report["details"]["artifact_body"]["metadata_only"], 1)
        self.assertEqual(self.report["status"], "PARTIAL")
        self.assertNotIn("synthetic artifact bytes", json.dumps(self.report))

    def test_corrupted_archive_and_mismatched_checksum_fail_before_restore(self):
        archive = self.workspace / "database.dump"
        manifest = self.workspace / "database.dump.manifest.json"
        with tempfile.TemporaryDirectory() as temp:
            damaged = Path(temp) / "damaged.dump"
            data = bytearray(archive.read_bytes())
            data[-1] ^= 1
            damaged.write_bytes(data)
            with self.assertRaisesRegex(db.HarnessError, "integrity mismatch"):
                db.restore(self.target, damaged, manifest=manifest, confirmed=True)
            bad_manifest = Path(temp) / "wrong.manifest.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["sha256"] = "0" * 64
            bad_manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(db.HarnessError, "integrity mismatch"):
                db.restore(self.target, archive, manifest=bad_manifest, confirmed=True)

    def test_source_target_identity_and_nonempty_target_fail_closed(self):
        with self.assertRaisesRegex(db.HarnessError, "distinct"):
            db.target_config({db.SOURCE: os.environ[db.SOURCE], db.TARGET: os.environ[db.SOURCE]})
        with self.assertRaisesRegex(db.HarnessError, "not empty"):
            db.restore(self.target, self.workspace / "database.dump",
                       manifest=self.workspace / "database.dump.manifest.json", confirmed=True)
        with self.assertRaisesRegex(db.HarnessError, "manifest required"):
            db.restore(self.target, self.workspace / "database.dump", confirmed=True)

    def test_unsupported_parity_is_not_pass(self):
        result = db.parity_live(self.source, self.target)
        self.assertEqual(result["differences"], [])
        self.assertIn("tables.source_states", result["unsupported"])

    def test_artifact_retrievable_missing_metadata_only_and_checksum_mismatch(self):
        manifest = json.loads((self.workspace / "artifacts.json").read_text(encoding="utf-8"))
        actual = artifacts.verify(manifest, artifacts.PostgresPayloadReader(self.target))
        self.assertEqual((actual["retrievable"], actual["metadata_only"]), (1, 1))
        missing = copy.deepcopy(manifest)
        missing["artifacts"][0]["cache_key"] = "e" * 64
        self.assertEqual(artifacts.verify(missing, artifacts.PostgresPayloadReader(self.target))["missing"], 1)
        mismatch = copy.deepcopy(manifest)
        mismatch["artifacts"][0]["sha256"] = "0" * 64
        self.assertEqual(artifacts.verify(mismatch, artifacts.PostgresPayloadReader(self.target))["checksum_mismatch"], 1)
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(artifacts.main(["manifest", "--role", "source", "--output", "unused.json",
                                             "--backend", "unconfigured_object_store"]), 3)
        self.assertIn("unsupported", stderr.getvalue())

    def test_malformed_dsn_and_secret_redaction(self):
        with self.assertRaises(db.HarnessError):
            db.config("source", {db.SOURCE: "not-a-postgresql-dsn"})
        marker = "fixture_secret_marker"
        previous = os.environ[db.SOURCE]
        os.environ[db.SOURCE] = "postgresql://" + marker + ":" + marker + "@invalid"
        try:
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(db.main(["inspect"]), 2)
            self.assertNotIn(marker, output.getvalue())
        finally:
            os.environ[db.SOURCE] = previous

    def test_provider_exit_bundle_integrity(self):
        path = self.workspace / "provider-exit.json"
        verified = bundle.verify(path)
        self.assertEqual(verified["schema"], "public")
        self.assertNotIn("OPOS_SOURCE_DB_URL", json.dumps(verified))
        self.assertNotIn(os.environ[db.SOURCE], json.dumps(verified))
        self.assertNotIn(os.environ[db.TARGET], json.dumps(verified))


if __name__ == "__main__":
    unittest.main()
