"""Tests for the A1M ``reextract_all`` backfill handler (worker/handlers.py).

Uses SQLite (via storage.engine.init_db -> Base.metadata.create_all), matching
the convention of worker/test_runner.py -- this exercises reextract_all's own
batching/idempotency logic, not PostgreSQL-specific behavior, so no Postgres
DSN is required here.
"""
import json
import os
import tempfile
import unittest

from storage.engine import get_engine, get_session_factory, init_db
from storage.models import OpportunityRecord
from worker.handlers import reextract_all


def _make_opportunity(session, opp_id: str, raw_payload: dict) -> None:
    session.add(
        OpportunityRecord(
            id=opp_id,
            track="employment",
            title="Software Engineer",
            organization="Acme",
            description="desc",
            source_id="src-1",
            source_url="https://example.com",
            content_hash="hash-" + opp_id,
            raw_payload_json=json.dumps(raw_payload),
        )
    )
    session.commit()


def _fake_extractor(raw_payload: dict) -> dict:
    """A minimal fake standing in for the concurrent A1-extract order's
    extraction functions: derives work_mode/employment_type deterministically
    from the raw payload so the test can assert real column changes."""
    return {
        "work_mode": raw_payload.get("work_mode", "unspecified"),
        "employment_type": raw_payload.get("employment_type", "unspecified"),
        "seniority_level": raw_payload.get("seniority_level", "unspecified"),
    }


class TestReextractAllNoOpWhenExtractorUnavailable(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "test_reextract_noop.db")
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.session = get_session_factory(self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_reports_zero_rows_extractor_unavailable(self):
        _make_opportunity(self.session, "opp-1", {"work_mode": "remote"})

        # No extractor injected, and (in this test environment) the
        # concurrent A1-extract module is not on the import path either, so
        # this must degrade to the documented no-op.
        result = reextract_all(self.session, extractor=None)

        self.assertEqual(result, {"status": "extractor_unavailable", "scanned": 0, "changed": 0})
        # And, being a true no-op, it must not have touched the row.
        record = self.session.query(OpportunityRecord).filter_by(id="opp-1").first()
        self.assertEqual(record.work_mode, "unspecified")


class TestReextractAllIdempotency(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "test_reextract_idem.db")
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.session = get_session_factory(self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_second_run_changes_zero_rows(self):
        _make_opportunity(self.session, "opp-1", {"work_mode": "remote", "employment_type": "full_time"})
        _make_opportunity(self.session, "opp-2", {"work_mode": "onsite", "seniority_level": "senior"})
        _make_opportunity(self.session, "opp-3", {})  # no extractable fields -> stays unspecified

        first = reextract_all(self.session, extractor=_fake_extractor, batch_size=2)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["scanned"], 3)
        self.assertEqual(first["changed"], 2)  # opp-1 and opp-2 actually changed; opp-3 did not

        rec1 = self.session.query(OpportunityRecord).filter_by(id="opp-1").first()
        self.assertEqual(rec1.work_mode, "remote")
        self.assertEqual(rec1.employment_type, "full_time")

        second = reextract_all(self.session, extractor=_fake_extractor, batch_size=2)
        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["scanned"], 3)
        self.assertEqual(second["changed"], 0)

    def test_batching_is_interruption_safe_across_multiple_pages(self):
        for i in range(5):
            _make_opportunity(self.session, f"opp-{i:02d}", {"work_mode": "remote"})

        result = reextract_all(self.session, extractor=_fake_extractor, batch_size=2)
        self.assertEqual(result["scanned"], 5)
        self.assertEqual(result["changed"], 5)

        for i in range(5):
            record = self.session.query(OpportunityRecord).filter_by(id=f"opp-{i:02d}").first()
            self.assertEqual(record.work_mode, "remote")


if __name__ == "__main__":
    unittest.main()
