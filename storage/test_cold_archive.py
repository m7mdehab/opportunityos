from __future__ import annotations

import hashlib
import json
import unittest
import zlib
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base, OpportunityColdArchiveRecord, OpportunityRecord
from storage.repository import StorageRepository


class ColdArchiveHydrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.session.add(
            OpportunityRecord(
                id="cold-1", track="employment", title="Cold", organization="Org",
                description="[archived]", source_id="src", source_url="https://example.invalid/cold",
                content_hash="h1", work_mode="remote", remote_scope="worldwide",
                employment_type="full_time", seniority_level="mid",
            )
        )
        payload = {"opportunity_id": "cold-1", "content_hash": "h1", "description": "authoritative text", "raw_payload_json": '{"source":true}', "provenance": []}
        compressed = zlib.compress(json.dumps(payload, separators=(",", ":")).encode())
        self.session.add(OpportunityColdArchiveRecord(
            opportunity_id="cold-1", content_hash="h1", payload_zlib=compressed,
            payload_sha256=hashlib.sha256(compressed).hexdigest(), original_size_bytes=len(compressed),
            archive_version="v1", archived_at=datetime.now(timezone.utc),
        ))
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_hydrates_only_after_checksum_and_identity_verification(self):
        record = StorageRepository(self.session).hydrate_cold_opportunity("cold-1")
        self.assertEqual(record.description, "authoritative text")
        self.assertEqual(record.raw_payload_json, '{"source":true}')

    def test_corrupt_archive_fails_closed(self):
        row = self.session.get(OpportunityColdArchiveRecord, "cold-1")
        row.payload_zlib = b"corrupt"
        self.session.commit()
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            StorageRepository(self.session).hydrate_cold_opportunity("cold-1")


if __name__ == "__main__":
    unittest.main()
