import unittest

from storage.models import Base
from storage.rls_policy import RLS_TABLES, assert_registry_complete


class RlsRegistryTest(unittest.TestCase):
    def test_every_application_model_table_is_classified(self):
        assert_registry_complete()
        self.assertEqual(set(Base.metadata.tables) - {"alembic_version"}, set(RLS_TABLES))

    def test_auth_tables_are_browser_denied_classifications(self):
        self.assertTrue({"founder_sessions", "founder_auth_rate_limit", "founder_auth_events"} <= set(RLS_TABLES))


if __name__ == "__main__":
    unittest.main()
