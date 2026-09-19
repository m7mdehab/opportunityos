import tempfile
import unittest

from fastapi.testclient import TestClient

from api.app import create_app
from api.security import hash_founder_password
from api.settings import Settings, load_settings
from storage.engine import get_engine, init_db
from storage.models import FounderAuthEventRecord, FounderSessionRecord


class HostedAuthContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_url = f"sqlite:///{self.tmp.name}/auth.db"
        engine = get_engine(db_url, allow_sqlite=True)
        init_db(engine)
        engine.dispose()
        self.settings = Settings(
            db_url=db_url,
            founder_password="",
            founder_password_hash=hash_founder_password("correct" + " horse battery staple"),
            session_secret="x" * 32,
            public_origin="https://app.example",
            cloud_mode=True,
            force_secure_cookies=True,
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app, base_url="https://testserver")

    def tearDown(self):
        self.client.close()
        self.app.state.engine.dispose()
        self.tmp.cleanup()

    def test_login_durable_session_csrf_and_logout(self):
        headers = {"X-OpportunityOS-CSRF": "1", "Origin": "https://app.example"}
        response = self.client.post("/api/auth/login", json={"password": "correct" + " horse battery staple"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("__Host-oos_session", response.headers.get("set-cookie", ""))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        session = self.app.state.session_factory()
        try:
            row = session.query(FounderSessionRecord).one()
            self.assertNotIn(response.cookies.get("__Host-oos_session"), row.token_digest)
            self.assertEqual(session.query(FounderAuthEventRecord).filter_by(event_type="LOGIN_SUCCESS").count(), 1)
        finally:
            session.close()
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_missing_csrf_is_rejected_for_cloud_mutation(self):
        response = self.client.post("/api/auth/login", json={"password": "correct" + " horse battery staple"})
        self.assertEqual(response.status_code, 403)

    def test_wrong_origin_is_rejected(self):
        response = self.client.post("/api/auth/login", json={"password": "correct" + " horse battery staple"},
                                    headers={"X-OpportunityOS-CSRF": "1", "Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)

    def test_origin_is_required_even_with_csrf_header(self):
        response = self.client.post("/api/auth/login", json={"password": "correct" + " horse battery staple"},
                                    headers={"X-OpportunityOS-CSRF": "1"})
        self.assertEqual(response.status_code, 403)

    def test_logout_all_requires_current_session_and_secure_deletion(self):
        headers = {"X-OpportunityOS-CSRF": "1", "Origin": "https://app.example"}
        unauthenticated = self.client.post("/api/auth/logout-all", headers=headers)
        self.assertEqual(unauthenticated.status_code, 401)
        session = self.app.state.session_factory()
        try:
            self.assertEqual(session.query(FounderSessionRecord).count(), 0)
        finally:
            session.close()
        self.assertEqual(self.client.post("/api/auth/login", json={"password": "correct" + " horse battery staple"}, headers=headers).status_code, 200)
        deleted = self.client.post("/api/auth/logout-all", headers=headers)
        self.assertEqual(deleted.status_code, 200)
        cookie = deleted.headers.get("set-cookie", "").lower()
        self.assertIn("__host-oos_session=", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("path=/", cookie)

    def test_hash_only_non_cloud_keeps_signed_session_mode(self):
        local = Settings(db_url=self.settings.db_url, founder_password="", founder_password_hash=self.settings.founder_password_hash,
                          session_secret="y" * 32, cloud_mode=False)
        app = create_app(local)
        client = TestClient(app, base_url="http://testserver")
        try:
            response = client.post("/api/auth/login", json={"password": "correct" + " horse battery staple"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("oos_session=", response.headers.get("set-cookie", ""))
            self.assertEqual(client.get("/api/auth/me").status_code, 200)
            self.assertEqual(client.post("/api/auth/logout").status_code, 200)
            self.assertEqual(client.get("/api/auth/me").status_code, 401)
        finally:
            client.close()
            app.state.engine.dispose()

    def test_load_settings_normalizes_trailing_origin(self):
        import os
        values = {
            "OPPORTUNITYOS_DB_URL": self.settings.db_url.replace("sqlite", "postgresql", 1),
            "OPPORTUNITYOS_ENVIRONMENT": "cloud",
            "OPPORTUNITYOS_FOUNDER_PASSWORD_HASH": self.settings.founder_password_hash,
            "OPPORTUNITYOS_SESSION_SECRET": "z" * 32,
            "OPPORTUNITYOS_PUBLIC_ORIGIN": "https://App.Example/",
        }
        old = {key: os.environ.get(key) for key in values}
        try:
            os.environ.update(values)
            self.assertEqual(load_settings().public_origin, "https://app.example")
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
