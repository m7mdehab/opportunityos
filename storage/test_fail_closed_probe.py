"""A-0 fail-closed probe (BRIEF-FR-003 §7).

The independent audit's seven-class fail-closed probe, extracted from
storage/test_postgres_integration.py::test_case_p_no_implicit_production_sqlite_fallback
into its own permanent CI file so it runs on every build, with or without a
PostgreSQL backend available.

Two test classes:

- FailClosedProbeMisconfigurationTest: the seven misconfiguration classes.
  These run WITHOUT PostgreSQL — they are never skipped for lack of a DSN,
  because they assert exactly that a missing/wrong DSN fails closed.
- FailClosedProbeValidDsnTest: the five valid-DSN constructions. This class
  is skipped only when no PostgreSQL DSN is available, and FAILS (does not
  skip) when CI is truthy, matching the fail-loud convention used by
  storage/test_postgres_integration.py.

Every test saves and restores os.environ["OPPORTUNITYOS_DB_URL"] in a
`finally` block so this probe cannot leak environment state into any other
test in the same `python -m unittest discover` process — the full suite
runs in one process, and this file is designed to be safe to run alongside
it in any order.

Case P in storage/test_postgres_integration.py is the existing model for
this structure and is left untouched; this probe is an additional,
standalone file, not a replacement.
"""
import os
import unittest

from storage.engine import (
    ProductionDatabaseConfigurationError,
    get_engine,
    get_production_db_url,
)
from outbound.browser_engine import OutboundBrowserEngine
from outbound.postgres_idempotency import PostgresIdempotencyLedger
from inbox.postgres_persistence import PostgresInboxStore
from inbox.pipeline import PipelineEventStore
from inbox.notifications import NotificationEngine
from inbox.ingestion import InboundIngestionService, MockMailTransport
from inbox.orchestrator import ProductionOperationalOrchestrator


def _save_env():
    return os.environ.get("OPPORTUNITYOS_DB_URL")


def _restore_env(saved):
    if saved is not None:
        os.environ["OPPORTUNITYOS_DB_URL"] = saved
    elif "OPPORTUNITYOS_DB_URL" in os.environ:
        del os.environ["OPPORTUNITYOS_DB_URL"]


class FailClosedProbeMisconfigurationTest(unittest.TestCase):
    """The seven misconfiguration classes, each raising
    ProductionDatabaseConfigurationError. Runs WITHOUT PostgreSQL."""

    def test_class_1_get_production_db_url_raises_when_env_unset(self):
        saved = _save_env()
        try:
            if "OPPORTUNITYOS_DB_URL" in os.environ:
                del os.environ["OPPORTUNITYOS_DB_URL"]
            with self.assertRaises(ProductionDatabaseConfigurationError):
                get_production_db_url()
        finally:
            _restore_env(saved)

    def test_class_2_get_engine_default_constructor_raises_when_env_unset(self):
        saved = _save_env()
        try:
            if "OPPORTUNITYOS_DB_URL" in os.environ:
                del os.environ["OPPORTUNITYOS_DB_URL"]
            with self.assertRaises(ProductionDatabaseConfigurationError):
                get_engine()  # default production constructor
        finally:
            _restore_env(saved)

    def test_class_3_get_production_db_url_raises_for_sqlite_env(self):
        saved = _save_env()
        try:
            os.environ["OPPORTUNITYOS_DB_URL"] = "sqlite:///x.db"
            with self.assertRaises(ProductionDatabaseConfigurationError):
                get_production_db_url()
        finally:
            _restore_env(saved)

    def test_class_4_production_components_raise_when_env_unset(self):
        saved = _save_env()
        try:
            if "OPPORTUNITYOS_DB_URL" in os.environ:
                del os.environ["OPPORTUNITYOS_DB_URL"]

            with self.subTest(component="OutboundBrowserEngine"):
                with self.assertRaises(ProductionDatabaseConfigurationError):
                    OutboundBrowserEngine()

            with self.subTest(component="InboundIngestionService"):
                with self.assertRaises(ProductionDatabaseConfigurationError):
                    InboundIngestionService(MockMailTransport())

            with self.subTest(component="PipelineEventStore"):
                with self.assertRaises(ProductionDatabaseConfigurationError):
                    PipelineEventStore()

            with self.subTest(component="NotificationEngine"):
                with self.assertRaises(ProductionDatabaseConfigurationError):
                    NotificationEngine()
        finally:
            _restore_env(saved)

    def test_class_5_postgres_inbox_store_raises_for_explicit_sqlite_arg(self):
        saved = _save_env()
        try:
            with self.assertRaises(ProductionDatabaseConfigurationError):
                PostgresInboxStore(db_url="sqlite:///x.db")
        finally:
            _restore_env(saved)

    def test_class_6_postgres_idempotency_ledger_raises_for_explicit_sqlite_arg(self):
        saved = _save_env()
        try:
            with self.assertRaises(ProductionDatabaseConfigurationError):
                PostgresIdempotencyLedger(db_url="sqlite:///x.db")
        finally:
            _restore_env(saved)

    def test_class_7_orchestrator_raises_for_store_none(self):
        saved = _save_env()
        try:
            # store=None with no store on the ingestion service falls back to
            # PostgresInboxStore()'s default constructor, which only fails
            # closed when OPPORTUNITYOS_DB_URL is unset/non-PostgreSQL — so
            # this class exercises the unset case explicitly, same as the
            # other misconfiguration classes above.
            if "OPPORTUNITYOS_DB_URL" in os.environ:
                del os.environ["OPPORTUNITYOS_DB_URL"]

            class IngestionWithoutStore:
                pass

            with self.subTest(form="ingestion_service_without_store"):
                with self.assertRaises(ProductionDatabaseConfigurationError):
                    ProductionOperationalOrchestrator(
                        ingestion_service=IngestionWithoutStore(), store=None
                    )

            with self.subTest(form="ingestion_service_none"):
                with self.assertRaises(ProductionDatabaseConfigurationError):
                    ProductionOperationalOrchestrator(ingestion_service=None, store=None)
        finally:
            _restore_env(saved)


class FailClosedProbeValidDsnTest(unittest.TestCase):
    """The five valid-DSN constructions. Skipped only when no PostgreSQL DSN
    is available; FAILS (not skipped) when CI is truthy."""

    @classmethod
    def setUpClass(cls):
        db_url = os.environ.get("OPPORTUNITYOS_DB_URL")
        if not db_url or not db_url.startswith("postgresql"):
            if os.environ.get("CI"):
                raise AssertionError(
                    "CI is set but OPPORTUNITYOS_DB_URL is missing or not a "
                    "PostgreSQL URL (postgresql+psycopg2://...). The "
                    "fail-closed probe's valid-DSN class must fail rather "
                    f"than skip in CI. Got: {db_url!r}."
                )
            raise unittest.SkipTest(
                "FailClosedProbeValidDsnTest requires a PostgreSQL "
                f"OPPORTUNITYOS_DB_URL to construct real PostgreSQL-backed "
                f"stores/ledgers; got {db_url!r}. Skipping outside CI."
            )
        cls.db_url = db_url

    def test_valid_dsn_1_outbound_browser_engine_carries_postgres_ledger(self):
        saved = _save_env()
        try:
            os.environ["OPPORTUNITYOS_DB_URL"] = self.db_url
            engine = OutboundBrowserEngine()
            self.assertIsInstance(engine.ledger, PostgresIdempotencyLedger)
        finally:
            _restore_env(saved)

    def test_valid_dsn_2_inbound_ingestion_service_carries_postgres_store(self):
        saved = _save_env()
        try:
            os.environ["OPPORTUNITYOS_DB_URL"] = self.db_url
            ingest = InboundIngestionService(MockMailTransport())
            self.assertIsInstance(ingest.store, PostgresInboxStore)
        finally:
            _restore_env(saved)

    def test_valid_dsn_3_pipeline_event_store_carries_postgres_store(self):
        saved = _save_env()
        try:
            os.environ["OPPORTUNITYOS_DB_URL"] = self.db_url
            pipe = PipelineEventStore()
            self.assertIsInstance(pipe.store, PostgresInboxStore)
        finally:
            _restore_env(saved)

    def test_valid_dsn_4_notification_engine_carries_postgres_store(self):
        saved = _save_env()
        try:
            os.environ["OPPORTUNITYOS_DB_URL"] = self.db_url
            notif = NotificationEngine()
            self.assertIsInstance(notif.store, PostgresInboxStore)
        finally:
            _restore_env(saved)

    def test_valid_dsn_5_production_operational_orchestrator_carries_postgres_store(self):
        saved = _save_env()
        try:
            os.environ["OPPORTUNITYOS_DB_URL"] = self.db_url
            ingest = InboundIngestionService(MockMailTransport())
            orch = ProductionOperationalOrchestrator(ingestion_service=ingest)
            self.assertIsInstance(orch.store, PostgresInboxStore)
        finally:
            _restore_env(saved)


if __name__ == "__main__":
    unittest.main()
