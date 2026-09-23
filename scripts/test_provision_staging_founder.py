from __future__ import annotations

import unittest
import uuid
from typing import Any

from scripts.provision_staging_founder import Config, ProvisionFailure, _bind_identity, _config, provision


FOUNDER_ID = str(uuid.uuid4())
CONFIG = Config(
    supabase_url="https://sunjfepvdzfknglrjwhm.supabase.co",
    service_key="never-print-this-service-key",
    founder_email="founder@example.invalid",
    founder_password="never-print-this-password",
    database_url="postgresql://private.example.invalid/postgres",
)


class FakeCursor:
    def __init__(self, row: tuple[str] | None = None):
        self.row = row
        self.statements: list[tuple[str, tuple[Any, ...] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params: tuple[Any, ...] | None = None):
        self.statements.append((sql, params))

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row: tuple[str] | None = None):
        self.cursor_value = FakeCursor(row)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FounderProvisionTests(unittest.TestCase):
    def test_requires_only_the_replacement_project_origin(self):
        values = {
            "SUPABASE_URL": CONFIG.supabase_url,
            "SUPABASE_SERVICE_ROLE_KEY": CONFIG.service_key,
            "FOUNDER_EMAIL": CONFIG.founder_email,
            "FOUNDER_PASSWORD": CONFIG.founder_password,
            "CLOUD_DATABASE_URL": CONFIG.database_url,
        }
        self.assertEqual(_config(values).supabase_url, CONFIG.supabase_url)
        values["SUPABASE_URL"] = "https://some-other-project.supabase.co"
        with self.assertRaises(ProvisionFailure) as raised:
            _config(values)
        self.assertEqual(str(raised.exception), "project_origin")

    def test_provisions_confirms_password_and_inserts_singleton(self):
        calls: list[tuple[str, str, dict[str, Any] | None]] = []
        connection = FakeConnection()

        def request_json(url: str, *, key: str, method: str = "GET", payload=None):
            self.assertEqual(key, CONFIG.service_key)
            calls.append((url, method, payload))
            if "/admin/users?" in url:
                return {"users": []}
            if method == "POST" and url.endswith("/admin/users"):
                return {"id": FOUNDER_ID}
            if "grant_type=password" in url:
                return {"user": {"id": FOUNDER_ID}, "access_token": "must-not-be-printed"}
            self.fail("unexpected Auth request")

        provision(CONFIG, request_json=request_json, connect=lambda *_a, **_k: connection)
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertEqual(len(connection.cursor_value.statements), 3)
        self.assertEqual(calls[1][2]["password"], CONFIG.founder_password)

    def test_existing_binding_is_idempotent(self):
        connection = FakeConnection((FOUNDER_ID,))
        _bind_identity(CONFIG.database_url, FOUNDER_ID, connect=lambda *_a, **_k: connection)
        self.assertTrue(connection.committed)
        self.assertEqual(len(connection.cursor_value.statements), 2)
        self.assertIn("FOR UPDATE", connection.cursor_value.statements[1][0])

    def test_different_existing_identity_fails_closed_without_commit(self):
        connection = FakeConnection((str(uuid.uuid4()),))
        with self.assertRaises(ProvisionFailure) as raised:
            _bind_identity(CONFIG.database_url, FOUNDER_ID, connect=lambda *_a, **_k: connection)
        self.assertEqual(str(raised.exception), "identity_conflict")
        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)

    def test_auth_failure_is_sanitized(self):
        def request_json(*_args, **_kwargs):
            raise ProvisionFailure("supabase_auth_request")

        with self.assertRaises(ProvisionFailure) as raised:
            provision(CONFIG, request_json=request_json)
        self.assertEqual(str(raised.exception), "supabase_auth_request")
        self.assertNotIn(CONFIG.founder_password, str(raised.exception))
        self.assertNotIn(CONFIG.service_key, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
