import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base, OpportunityArchiveOrphanRecord, OpportunityColdArchiveRecord
from storage.repository import StorageRepository


class ArchiveOrphanCleanupConcurrencyTests(unittest.TestCase):
    def test_concurrent_cleanup_can_remove_later_ledger_row(self) -> None:
        fd, path = tempfile.mkstemp(prefix="opos-orphan-cleanup-", suffix=".sqlite3")
        os.close(fd)
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(
            engine,
            tables=[
                OpportunityColdArchiveRecord.__table__,
                OpportunityArchiveOrphanRecord.__table__,
            ],
        )
        Session = sessionmaker(bind=engine)
        first = Session()
        second = Session()
        try:
            first.add_all(
                [
                    OpportunityArchiveOrphanRecord(
                        object_key="cold-opportunities/a.json.zlib",
                        payload_sha256="a" * 64,
                        compressed_size_bytes=10,
                        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    ),
                    OpportunityArchiveOrphanRecord(
                        object_key="cold-opportunities/b.json.zlib",
                        payload_sha256="b" * 64,
                        compressed_size_bytes=20,
                        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                    ),
                ]
            )
            first.commit()

            deleted_objects: list[str] = []

            def concurrent_delete(object_key: str, *, client=None) -> None:
                deleted_objects.append(object_key)
                if object_key == "cold-opportunities/a.json.zlib":
                    second.query(OpportunityArchiveOrphanRecord).filter_by(
                        object_key="cold-opportunities/b.json.zlib"
                    ).delete(synchronize_session=False)
                    second.commit()

            repository = StorageRepository(first, cold_storage_client=object())
            with patch("storage.repository.delete_cold_object", side_effect=concurrent_delete):
                removed = repository.cleanup_archive_orphans(limit=20)

            self.assertEqual(removed, 1)
            self.assertEqual(deleted_objects, ["cold-opportunities/a.json.zlib"])
            self.assertEqual(first.query(OpportunityArchiveOrphanRecord).count(), 0)
        finally:
            first.close()
            second.close()
            engine.dispose()
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
