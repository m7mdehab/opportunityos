from __future__ import annotations

import hashlib
import json
import unittest
import zlib
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.cold_storage import pack
from storage.models import Base, OpportunityColdArchiveRecord, OpportunityRecord
from storage.repository import StorageRepository
from worker.handlers import _reconstruct_opportunity


class ColdArchiveHydrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.session.add(
            OpportunityRecord(
                id="cold-1", track="employment", title="Cold", organization="Org",
                description=None, source_id="src", source_url="https://example.invalid/cold",
                content_hash="h1", work_mode="remote", remote_scope="worldwide",
                employment_type="full_time", seniority_level="mid", lifecycle_tier="cold",
            )
        )
        payload = {
            "schema_version": 2,
            "opportunity_id": "cold-1",
            "source_id": "src",
            "content_hash": "h1",
            "source_url": "https://example.invalid/cold",
            "original_source_payload": '{"source":true}',
            "canonical_description": "authoritative text",
            "provenance": [],
            "opportunity": {
                "id": "cold-1", "track": "employment", "title": "Cold",
                "organization": "Org", "description": "authoritative text",
                "source_id": "src", "source_url": "https://example.invalid/cold",
                "content_hash": "h1", "raw_payload_json": '{"source":true}',
                "work_mode": "remote", "remote_scope": "worldwide",
                "employment_type": "full_time", "seniority_level": "mid",
                "record_checksum": "",
            },
        }
        compressed, digest, raw_size = pack(payload)
        self.session.add(OpportunityColdArchiveRecord(
            opportunity_id="cold-1", content_hash="h1", payload_zlib=compressed,
            storage_backend="postgres_fallback", payload_sha256=digest,
            original_size_bytes=raw_size, compressed_size_bytes=len(compressed),
            archive_version="v2", archived_at=datetime.now(timezone.utc),
        ))
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_persistent_hydration_is_prohibited(self):
        with self.assertRaisesRegex(RuntimeError, "persistent cold rehydration is prohibited"):
            StorageRepository(self.session).hydrate_cold_opportunity("cold-1")

    def test_corrupt_archive_fails_closed(self):
        row = self.session.get(OpportunityColdArchiveRecord, "cold-1")
        row.payload_zlib = b"corrupt"
        self.session.commit()
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            StorageRepository(self.session).load_cold_opportunity_payload("cold-1")

    def test_read_only_archive_hydration_keeps_hot_row_cold(self):
        repository = StorageRepository(self.session)
        record = self.session.get(OpportunityRecord, "cold-1")
        payload = repository.load_cold_opportunity_payload("cold-1", record=record)

        # Matching receives authoritative source truth in memory, while the
        # compact identity row remains the durable representation.
        reconstructed = _reconstruct_opportunity(
            self.session, record, archive_payload=payload
        )
        self.assertEqual(reconstructed.description, "authoritative text")
        self.session.expire_all()
        persisted = self.session.get(OpportunityRecord, "cold-1")
        self.assertIsNone(persisted.description)
        self.assertEqual(persisted.lifecycle_tier, "cold")
        self.assertIsNone(persisted.raw_payload_json)
        self.assertEqual(
            self.session.query(OpportunityColdArchiveRecord).filter_by(opportunity_id="cold-1").count(),
            1,
        )


if __name__ == "__main__":
    unittest.main()
