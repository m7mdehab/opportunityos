import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import artifact_cache as ac
from scripts import artifact_integrity as integrity
from scripts import check_cloud_readiness
from storage.models import ArtifactCacheRecord, Base


class FakeTransport:
    def __init__(self):
        self.objects = {}
        self.uploads = []
        self.deletes = []
        self.fail_upload = False
        self.bucket_public = False

    def bucket_info(self):
        return {"id": "private-artifacts", "public": self.bucket_public}

    def post(self, key, body):
        if self.fail_upload:
            raise RuntimeError("transport failure with service key")
        if key in self.objects:
            raise ac.ArtifactObjectExists("already exists")
        self.uploads.append(key)
        self.objects[key] = bytes(body)
        return b""

    def get(self, key, body=None):
        if key not in self.objects:
            raise RuntimeError("missing")
        return self.objects[key]

    def delete(self, key, body=None):
        self.deletes.append(key)
        self.objects.pop(key, None)
        return b""


class ArtifactStorageTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        ArtifactCacheRecord.__table__.create(engine)
        self.session = sessionmaker(bind=engine)()
        self.env = {
            "OPPORTUNITYOS_ARTIFACT_STORAGE_BACKEND": "supabase_storage",
            "SUPABASE_STORAGE_URL": "https://project.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
            "OPPORTUNITYOS_ARTIFACT_BUCKET": "private-artifacts",
        }
        self.transport = FakeTransport()
        self.client = ac.SupabaseStorageClient(transport=self.transport, **{
            "base_url": self.env["SUPABASE_STORAGE_URL"],
            "service_key": self.env["SUPABASE_SERVICE_ROLE_KEY"],
            "bucket": self.env["OPPORTUNITYOS_ARTIFACT_BUCKET"],
        })

    def tearDown(self):
        self.session.close()

    def _store(self, truth="truth-a", body=b"private artifact bytes"):
        with patch.dict(os.environ, self.env, clear=False):
            ac.store(self.session, "opp-1", truth, "classic", "cv", "application/octet-stream", body,
                     storage_client=self.client)
        return ac.cache_key("opp-1", truth, "classic", "cv")

    def test_postgres_payload_compatibility_and_old_row_read(self):
        with patch.dict(os.environ, {}, clear=True):
            ac.store(self.session, "opp-1", "truth", "classic", "cv", "application/octet-stream", b"old")
            self.assertEqual(ac.get(self.session, "opp-1", "truth", "classic", "cv")[1], b"old")

    def test_private_upload_metadata_and_idempotent_retry(self):
        key = self._store()
        self.assertEqual(self.transport.uploads, [f"artifacts/{key}"])
        row = self.session.get(ArtifactCacheRecord, key)
        self.assertEqual(row.storage_backend, "supabase_storage")
        self.assertEqual(row.object_key, f"artifacts/{key}")
        self.assertEqual(row.payload_sha256, hashlib.sha256(b"private artifact bytes").hexdigest())
        self._store()
        self.assertEqual(len(self.transport.uploads), 1)

    def test_metadata_binding_is_verified_before_serving_cached_body(self):
        key = self._store()
        row = self.session.get(ArtifactCacheRecord, key)
        row.generation_version = "stale-generator"
        self.session.commit()
        with self.assertRaisesRegex(ac.ArtifactStorageError, "binding mismatch"):
            ac.get(self.session, "opp-1", "truth-a", "classic", "cv", storage_client=self.client)

    def test_metadata_binding_is_verified_before_idempotent_store(self):
        key = self._store()
        row = self.session.get(ArtifactCacheRecord, key)
        row.truth_pack_hash = "wrong-truth"
        self.session.commit()
        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaisesRegex(ac.ArtifactStorageError, "binding mismatch"):
                ac.store(
                    self.session, "opp-1", "truth-a", "classic", "cv",
                    "application/octet-stream", b"private artifact bytes", storage_client=self.client,
                )

    def test_matching_orphan_is_recovered_without_duplicate_upload(self):
        key = ac.cache_key("opp-1", "truth-a", "classic", "cv")
        object_key = f"artifacts/{key}"
        self.transport.objects[object_key] = b"private artifact bytes"
        with patch.dict(os.environ, self.env, clear=False):
            ac.store(
                self.session,
                "opp-1",
                "truth-a",
                "classic",
                "cv",
                "application/octet-stream",
                b"private artifact bytes",
                storage_client=self.client,
            )
        self.assertEqual(self.transport.uploads, [])
        row = self.session.get(ArtifactCacheRecord, key)
        self.assertIsNotNone(row)
        self.assertEqual(row.object_key, object_key)

    def test_conflicting_orphan_fails_closed_without_metadata(self):
        key = ac.cache_key("opp-1", "truth-a", "classic", "cv")
        self.transport.objects[f"artifacts/{key}"] = b"different bytes"
        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaisesRegex(ac.ArtifactStorageError, "conflicts"):
                ac.store(
                    self.session,
                    "opp-1",
                    "truth-a",
                    "classic",
                    "cv",
                    "application/octet-stream",
                    b"private artifact bytes",
                    storage_client=self.client,
                )
        self.assertIsNone(self.session.get(ArtifactCacheRecord, key))

    def test_supabase_delete_uses_remove_api_contract(self):
        client = ac.SupabaseStorageClient(
            base_url=self.env["SUPABASE_STORAGE_URL"],
            service_key=self.env["SUPABASE_SERVICE_ROLE_KEY"],
            bucket=self.env["OPPORTUNITYOS_ARTIFACT_BUCKET"],
        )
        client._private_bucket_verified = True

        response = MagicMock()
        response.read.return_value = b"[]"
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False

        with patch("api.artifact_cache.urlopen", return_value=context) as mocked:
            client.delete("artifacts/" + "a" * 64)

        request = mocked.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://project.supabase.co/storage/v1/object/private-artifacts",
        )
        self.assertEqual(request.get_method(), "DELETE")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"prefixes": ["artifacts/" + "a" * 64]},
        )
        self.assertEqual(request.headers.get("Content-type"), "application/json")

    def test_public_bucket_is_rejected_before_write(self):
        self.transport.bucket_public = True
        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaisesRegex(ac.ArtifactStorageError, "must exist and be private"):
                ac.store(
                    self.session,
                    "opp-1",
                    "truth-a",
                    "classic",
                    "cv",
                    "application/octet-stream",
                    b"private artifact bytes",
                    storage_client=self.client,
                )
        self.assertEqual(self.transport.uploads, [])
        self.assertEqual(self.session.query(ArtifactCacheRecord).count(), 0)

    def test_external_cache_hit_and_checksum_mismatch_fail_closed(self):
        key = self._store()
        self.assertEqual(ac.get(self.session, "opp-1", "truth-a", "classic", "cv", storage_client=self.client)[1], b"private artifact bytes")
        self.transport.objects[f"artifacts/{key}"] = b"corrupted"
        with self.assertRaisesRegex(ac.ArtifactStorageError, "checksum"):
            ac.get(self.session, "opp-1", "truth-a", "classic", "cv", storage_client=self.client)

    def test_upload_failure_creates_no_metadata_and_does_not_leak_key(self):
        self.transport.fail_upload = True
        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaises(ac.ArtifactStorageError) as caught:
                ac.store(self.session, "opp-1", "truth", "classic", "cv", "application/octet-stream", b"x",
                         storage_client=self.client)
        self.assertNotIn(self.env["SUPABASE_SERVICE_ROLE_KEY"], str(caught.exception))
        self.assertEqual(self.session.query(ArtifactCacheRecord).count(), 0)

    def test_metadata_failure_attempts_compensating_delete(self):
        fake_session = MagicMock()
        fake_session.query.return_value.filter_by.return_value.first.return_value = None
        fake_session.query.return_value.filter.return_value.all.return_value = []
        fake_session.commit.side_effect = RuntimeError("database unavailable")
        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaisesRegex(ac.ArtifactStorageError, "metadata persistence"):
                ac.store(fake_session, "opp-1", "truth", "classic", "cv", "application/octet-stream", b"x",
                         storage_client=self.client)
        self.assertEqual(self.transport.deletes, ["artifacts/" + ac.cache_key("opp-1", "truth", "classic", "cv")])

    def test_stale_truth_eviction_removes_object(self):
        old_key = self._store("truth-old")
        self._store("truth-new")
        self.assertIn(f"artifacts/{old_key}", self.transport.deletes)
        self.assertIsNone(self.session.get(ArtifactCacheRecord, old_key))

    def test_global_eviction_removes_external_body(self):
        first_key = self._store("truth-a", b"first")
        with patch.object(ac, "MAX_CACHE_ROWS", 1), patch.dict(os.environ, self.env, clear=False):
            ac.store(
                self.session,
                "opp-2",
                "truth-b",
                "classic",
                "cv",
                "application/octet-stream",
                b"second",
                storage_client=self.client,
            )
        self.assertIn(f"artifacts/{first_key}", self.transport.deletes)
        self.assertIsNone(self.session.get(ArtifactCacheRecord, first_key))

    def test_backend_switch_cleans_external_stale_body_before_metadata(self):
        old_key = self._store("truth-old")
        postgres_env = {"OPPORTUNITYOS_ARTIFACT_STORAGE_BACKEND": "postgres_payload"}
        with patch.dict(os.environ, postgres_env, clear=True):
            ac.store(
                self.session,
                "opp-1",
                "truth-new",
                "classic",
                "cv",
                "application/octet-stream",
                b"replacement",
                storage_client=self.client,
            )
        self.assertIn(f"artifacts/{old_key}", self.transport.deletes)
        self.assertIsNone(self.session.get(ArtifactCacheRecord, old_key))

    def test_object_key_contains_no_founder_content(self):
        key = ac.cache_key("opp-founder-private-description", "truth-founder-private", "classic", "cv")
        self.assertEqual(ac.object_key_for(key), f"artifacts/{key}")
        self.assertNotIn("founder-private", ac.object_key_for(key))

    def test_cloud_config_requires_explicit_private_backend(self):
        self.assertTrue(ac.validate_storage_config({"OPPORTUNITYOS_ENVIRONMENT": "cloud"}))
        self.assertTrue(ac.validate_storage_config({"OPPORTUNITYOS_ENVIRONMENT": "cloud",
                                                    "OPPORTUNITYOS_ARTIFACT_STORAGE_BACKEND": "supabase_storage"}))
        self.assertEqual(ac.validate_storage_config({"OPPORTUNITYOS_ENVIRONMENT": "cloud",
                                                     "OPPORTUNITYOS_ARTIFACT_STORAGE_BACKEND": "supabase_storage",
                                                     **self.env}), [])

    def test_cloud_readiness_distinguishes_compatibility_backend(self):
        result = check_cloud_readiness.check_artifact_storage({"OPPORTUNITYOS_ENVIRONMENT": "cloud",
                                                               "OPPORTUNITYOS_ARTIFACT_STORAGE_BACKEND": "postgres_payload"})
        self.assertEqual(result.status, "BLOCKED")

    def test_cloud_readiness_accepts_complete_supabase_static_config(self):
        result = check_cloud_readiness.check_artifact_storage({"OPPORTUNITYOS_ENVIRONMENT": "cloud", **self.env})
        self.assertEqual(result.status, "PASS")

    def test_external_integrity_manifest_reports_retrieval_state(self):
        key = "a" * 64
        row = {"cache_key": key, "storage_backend": "supabase_storage", "object_key": "artifacts/" + key,
               "sha256": hashlib.sha256(b"body").hexdigest(), "size_bytes": 4,
               "expected_sha256": hashlib.sha256(b"body").hexdigest(), "expected_size_bytes": 4,
               "body_status": "retrievable"}
        source = integrity.manifest(type("Reader", (), {"backend": "supabase_storage", "inventory": lambda self: [row]})())
        self.assertEqual(source["backend"], "supabase_storage")
        self.assertEqual(integrity.verify(source, type("Reader", (), {"inventory": lambda self: [row]})())["retrievable"], 1)
        mismatch = dict(row, body_status="checksum_mismatch", sha256="b" * 64)
        self.assertEqual(integrity.verify(source, type("Reader", (), {"inventory": lambda self: [mismatch]})())["checksum_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
