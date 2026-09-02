"""Unit tests for opportunity.persistence.persist_batch on injected SQLite.

Follows the existing unit convention in this repo (see e.g. worker/test_worker.py,
storage/test_storage.py): storage.engine.get_engine(..., allow_sqlite=True) against
a temp-file SQLite DB, never the real production database.
"""
import os
import tempfile
import unittest

from opportunity.models import DerivationType, FieldProvenance, Opportunity, Track
from opportunity.persistence import PersistResult, persist_batch
from opportunity.pipeline import IngestionBatch
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import FieldProvenanceRecord, OpportunityRecord
from storage.repository import StorageRepository


def _field_provenance(field_name: str, value: str) -> FieldProvenance:
    return FieldProvenance(
        field_name=field_name,
        raw_value=value,
        normalized_value=value,
        derivation_type=DerivationType.RAW_EXTRACTION.value,
        raw_pointer=f"fixture:{field_name}",
        record_checksum="checksum-fixture",
        rule_id="fixture_rule",
    )


def _make_opportunity(
    *,
    opp_id: str = "fixture:job-1",
    title: str = "Principal Backend Engineer",
    description: str = "Build distributed systems at scale.",
) -> Opportunity:
    return Opportunity(
        id=opp_id,
        track=Track.EMPLOYMENT,
        source="fixture_source",
        source_url="https://example.com/jobs/1",
        source_id="job-1",
        organization="Acme Corp",
        title=title,
        description=description,
        location_raw="Remote",
        posted_date="2026-08-01",
        closing_date="2026-09-01",
        field_provenances=(
            _field_provenance("title", title),
            _field_provenance("organization", "Acme Corp"),
        ),
        canonical_outbound_url="https://example.com/jobs/1",
    )


def _make_batch(opportunities: tuple) -> IngestionBatch:
    return IngestionBatch(
        batch_id="batch-fixture",
        run_id="run-fixture",
        ingested_at="2026-08-01",
        opportunities=opportunities,
        clusters=(),
        health_reports=(),
        total_raw_ingested=len(opportunities),
        total_unique_opportunities=len(opportunities),
        exact_duplicates_removed=0,
        cross_source_duplicates_clustered=0,
        ambiguous_duplicates_count=0,
        track_counts=(),
        eligibility_counts=(),
    )


class PersistBatchTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_persistence.db")
        self.engine = get_engine(f"sqlite:///{self.db_path}", allow_sqlite=True)
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()
        self.repository = StorageRepository(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_fresh_insert_with_provenance(self):
        opp = _make_opportunity()
        batch = _make_batch((opp,))

        result = persist_batch(batch, self.repository)

        self.assertIsInstance(result, PersistResult)
        self.assertEqual(result.inserted_ids, (opp.id,))
        self.assertEqual(result.unchanged_ids, ())
        self.assertEqual(result.updated_ids, ())
        self.assertEqual(result.inserted_count, 1)
        self.assertEqual(result.unchanged_count, 0)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.total_processed, 1)
        self.assertEqual(result.persisted_ids, (opp.id,))

        record = self.session.query(OpportunityRecord).filter_by(id=opp.id).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.title, opp.title)
        self.assertEqual(record.organization, opp.organization)
        self.assertEqual(record.content_hash, opp.content_hash)
        self.assertEqual(record.deadline, opp.closing_date)
        self.assertEqual(record.posted_date, opp.posted_date)
        self.assertFalse(record.is_stale)
        self.assertIsNone(record.reverified_at)

        provenances = (
            self.session.query(FieldProvenanceRecord).filter_by(opportunity_id=opp.id).all()
        )
        self.assertEqual(len(provenances), 2)
        prov_field_names = {p.field_name for p in provenances}
        self.assertEqual(prov_field_names, {"title", "organization"})

    def test_identical_rerun_inserts_nothing(self):
        opp = _make_opportunity()
        batch = _make_batch((opp,))

        first = persist_batch(batch, self.repository)
        second = persist_batch(batch, self.repository)

        self.assertEqual(first.inserted_count, 1)
        self.assertEqual(second.inserted_count, 0)
        self.assertEqual(second.unchanged_count, 1)
        self.assertEqual(second.updated_count, 0)
        self.assertEqual(second.unchanged_ids, (opp.id,))

        row_count = self.session.query(OpportunityRecord).count()
        self.assertEqual(row_count, 1)

        provenance_count = self.session.query(FieldProvenanceRecord).count()
        self.assertEqual(provenance_count, 2)

    def test_changed_content_hash_updates_and_reverifies(self):
        original = _make_opportunity()
        first_batch = _make_batch((original,))
        first = persist_batch(first_batch, self.repository)
        self.assertEqual(first.inserted_count, 1)

        changed = _make_opportunity(
            opp_id=original.id,
            title="Staff Backend Engineer",
            description="Lead distributed systems architecture across the org.",
        )
        self.assertNotEqual(changed.content_hash, original.content_hash)
        second_batch = _make_batch((changed,))

        second = persist_batch(second_batch, self.repository)

        self.assertEqual(second.inserted_count, 0)
        self.assertEqual(second.unchanged_count, 0)
        self.assertEqual(second.updated_count, 1)
        self.assertEqual(second.updated_ids, (changed.id,))
        self.assertEqual(second.persisted_ids, (changed.id,))

        row_count = self.session.query(OpportunityRecord).count()
        self.assertEqual(row_count, 1, "same identity must update in place, not duplicate")

        record = self.session.query(OpportunityRecord).filter_by(id=changed.id).first()
        self.assertEqual(record.title, "Staff Backend Engineer")
        self.assertEqual(record.content_hash, changed.content_hash)
        self.assertFalse(record.is_stale)
        self.assertIsNotNone(record.reverified_at, "a changed posting must set reverified_at")

        provenances = (
            self.session.query(FieldProvenanceRecord).filter_by(opportunity_id=changed.id).all()
        )
        prov_values = {p.field_name: p.normalized_value for p in provenances}
        self.assertEqual(prov_values.get("title"), "Staff Backend Engineer")

    def test_empty_batch_is_noop(self):
        batch = _make_batch(())

        result = persist_batch(batch, self.repository)

        self.assertEqual(result.inserted_count, 0)
        self.assertEqual(result.unchanged_count, 0)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.total_processed, 0)
        self.assertEqual(result.persisted_ids, ())

        row_count = self.session.query(OpportunityRecord).count()
        self.assertEqual(row_count, 0)


if __name__ == "__main__":
    unittest.main()
