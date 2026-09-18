import os
import unittest
from unittest.mock import patch

from scripts.check_cloud_readiness import check_truth_pack
from scripts.cloud_runtime_bridge import plan_runtime_environment
from truth.pack import TruthPackInvalid, _fetch_remote_bytes, load_truth_pack


DB = "postgresql+psycopg2://db.cloud.invalid/opos"


class PrivateTruthPackCloudTests(unittest.TestCase):
    def test_cloud_rejects_signed_or_credential_bearing_uri(self):
        for uri in (
            "https://objects.example/pack.yaml?sig=secret",
            "https://user:password@objects/pack.yaml",
            "https://objects.example/pack.yaml#fragment",
        ):
            with self.subTest(uri=uri), self.assertRaises(TruthPackInvalid):
                load_truth_pack(uri, expected_hash="a" * 64, auth_token="token", cloud_mode=True)

    def test_cloud_requires_private_auth_and_supabase_api_key(self):
        with self.assertRaisesRegex(TruthPackInvalid, "AUTH_TOKEN"):
            load_truth_pack("https://objects.example/pack.yaml", expected_hash="a" * 64, cloud_mode=True)
        with self.assertRaisesRegex(TruthPackInvalid, "both"):
            load_truth_pack("https://project.supabase.co/storage/v1/object/authenticated/truth/pack.yaml",
                            expected_hash="a" * 64, auth_token="token", cloud_mode=True)

    def test_remote_request_uses_headers_without_logging_values(self):
        class Response:
            headers = {"Content-Type": "text/yaml"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"fixture: true"
        with patch("truth.pack.urlopen", return_value=Response()) as opened:
            _fetch_remote_bytes("https://objects.example/pack.yaml", auth_token="auth-secret", api_key="api-secret")
        request = opened.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer auth-secret")
        self.assertEqual(request.headers["Apikey"], "api-secret")
        self.assertNotIn("auth-secret", request.full_url)
        self.assertNotIn("api-secret", request.full_url)

    def test_readiness_distinguishes_private_ready_and_public_blocked(self):
        ready = check_truth_pack({
            "OPPORTUNITYOS_ENVIRONMENT": "cloud",
            "OPPORTUNITYOS_TRUTH_PACK_URI": "https://objects.example/pack.yaml",
            "OPPORTUNITYOS_TRUTH_PACK_HASH": "a" * 64,
            "OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN": "token",
        }, role="worker")
        self.assertEqual(ready.status, "PASS")
        self.assertIn("PRIVATE_REMOTE_READY", ready.message)
        blocked = check_truth_pack({
            "OPPORTUNITYOS_ENVIRONMENT": "cloud",
            "OPPORTUNITYOS_TRUTH_PACK_URI": "https://project.supabase.co/storage/v1/object/public/truth/pack.yaml",
            "OPPORTUNITYOS_TRUTH_PACK_HASH": "a" * 64,
            "OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN": "token",
            "OPPORTUNITYOS_TRUTH_PACK_API_KEY": "key",
        }, role="worker")
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertIn("PUBLIC_OR_UNAUTHENTICATED_REMOTE_BLOCKED", blocked.message)

    def test_cloud_bridge_propagates_private_values_only_to_api_and_worker(self):
        env = {
            "CLOUD_DATABASE_URL": DB,
            "OPPORTUNITYOS_ENVIRONMENT": "cloud",
            "OPPORTUNITYOS_TRUTH_PACK_URI": "https://objects.example/pack.yaml",
            "OPPORTUNITYOS_TRUTH_PACK_HASH": "a" * 64,
            "OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN": "auth-secret",
        }
        api = plan_runtime_environment("api", dict(env, OPPORTUNITYOS_FOUNDER_PASSWORD="pw", OPPORTUNITYOS_SESSION_SECRET="s" * 32))
        worker = plan_runtime_environment("worker", env)
        self.assertEqual(api.aliases["OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN"], "auth-secret")
        self.assertEqual(worker.aliases["OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN"], "auth-secret")
        self.assertNotIn("OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN", plan_runtime_environment("scheduler", {"CLOUD_DATABASE_URL": DB, **{k: v for k, v in env.items() if k != "CLOUD_DATABASE_URL"}}).aliases)


if __name__ == "__main__":
    unittest.main()
