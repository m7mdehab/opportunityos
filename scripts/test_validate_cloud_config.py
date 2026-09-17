"""Synthetic, secret-redacting tests for the cloud deployment preflight."""

import contextlib
import io
import os
import unittest
from unittest.mock import patch

from scripts import validate_cloud_config as config


class CloudConfigTests(unittest.TestCase):
    def setUp(self):
        self.worker = {
            "CLOUD_DATABASE_URL": "postgresql://db.invalid/opos",
            "QUEUE_NAMESPACE": "opos",
            "STORAGE_SERVICE_KEY": "synthetic-storage-secret",
            "STORAGE_PRIVATE_BUCKET": "private-artifacts",
        }

    def test_valid_worker(self):
        self.assertEqual(config.validate("worker", self.worker), [])

    def test_missing_database_url(self):
        values = {key: value for key, value in self.worker.items() if key != "CLOUD_DATABASE_URL"}
        self.assertEqual(config.validate("worker", values), ["CLOUD_DATABASE_URL"])

    def test_api_requires_server_only_auth_and_storage_secrets(self):
        values = {
            "CLOUD_DATABASE_URL": self.worker["CLOUD_DATABASE_URL"],
            "AUTH_JWKS_URL": "https://auth.invalid/keys",
            "AUTH_ISSUER": "https://auth.invalid",
            "AUTH_AUDIENCE": "authenticated",
            "STORAGE_PRIVATE_BUCKET": "private-artifacts",
        }
        self.assertEqual(config.validate("api", values),
                         ["AUTH_SERVICE_KEY", "STORAGE_SERVICE_KEY"])

    def test_web_does_not_require_worker_secrets(self):
        values = {"NEXT_PUBLIC_DATA_API_URL": "https://data.invalid",
                  "NEXT_PUBLIC_DATA_ANON_KEY": "synthetic-publishable-key"}
        self.assertEqual(config.validate("web", values), [])

    def test_failure_output_never_prints_supplied_values(self):
        values = dict(self.worker, STORAGE_SERVICE_KEY="synthetic-secret-DO-NOT-PRINT",
                      CLOUD_DATABASE_URL="postgresql://db.invalid/opos")
        values["QUEUE_NAMESPACE"] = "REPLACE_ME"
        output = io.StringIO()
        with patch.dict(os.environ, values, clear=True), contextlib.redirect_stdout(output):
            self.assertEqual(config.main(["--role", "worker"]), 1)
        self.assertIn("QUEUE_NAMESPACE", output.getvalue())
        self.assertNotIn("synthetic-secret-DO-NOT-PRINT", output.getvalue())
        self.assertNotIn("postgresql://db.invalid/opos", output.getvalue())
        self.assertNotIn("REPLACE_ME", output.getvalue())

    def test_malformed_url_and_template_are_rejected(self):
        values = dict(self.worker, CLOUD_DATABASE_URL="postgresql://REPLACE_ME")
        self.assertEqual(config.validate("worker", values), ["CLOUD_DATABASE_URL"])
        values["CLOUD_DATABASE_URL"] = "not-a-url"
        self.assertEqual(config.validate("worker", values), ["CLOUD_DATABASE_URL"])


if __name__ == "__main__":
    unittest.main()
