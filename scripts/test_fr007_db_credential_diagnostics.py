from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.fr007_db_credential_diagnostics import classify_database_exception


class DatabaseCredentialDiagnosticsTests(unittest.TestCase):
    def test_sqlstate_28p01_is_authentication_rejection(self):
        error = SimpleNamespace(orig=SimpleNamespace(pgcode="28P01"))
        self.assertEqual(classify_database_exception(error), ("authentication-rejected", "28P01"))

    def test_dns_failure_is_sanitized_without_driver_message(self):
        secretish_message = "could not translate host name 'private-host' to address"
        category, sqlstate = classify_database_exception(RuntimeError(secretish_message))
        self.assertEqual((category, sqlstate), ("dns-resolution", None))
        self.assertNotIn("private-host", category)

    def test_connection_timeout_is_distinguished(self):
        error = SimpleNamespace(orig=OSError("connection timed out"))
        self.assertEqual(classify_database_exception(error), ("connection-timeout", None))

    def test_ssl_failure_is_distinguished(self):
        self.assertEqual(
            classify_database_exception(RuntimeError("SSL certificate verify failed")),
            ("ssl-failure", None),
        )

    def test_unknown_failure_returns_only_exception_class_and_sqlstate(self):
        category, sqlstate = classify_database_exception(RuntimeError("sensitive driver detail"))
        self.assertEqual((category, sqlstate), ("RuntimeError", None))
        self.assertNotIn("sensitive driver detail", category)


if __name__ == "__main__":
    unittest.main()
