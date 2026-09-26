from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine, delete, insert, select, text
from sqlalchemy.orm import Session

from scripts import founder_state_backup as backup
from storage.models import OpportunityRecord


def _test_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata = MetaData()
    Table(
        "opportunities", metadata,
        Column("id", String, primary_key=True),
        Column("lifecycle_tier", String, nullable=False),
        Column("title", String, nullable=False),
    )
    for name in backup.STATE_TABLES:
        Table(name, metadata,
              Column("id", String, primary_key=True),
              Column("opportunity_id", String, nullable=True),
              Column("action_text", String, nullable=True),
              Column("created_at", DateTime, nullable=True))
    Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(metadata.tables["alembic_version"]), {"version_num": "0026_fr008_live_actions"})
    return engine


class FounderStateBackupTests(unittest.TestCase):
    def test_snapshot_exports_only_protected_opportunity_rows_and_restore_is_idempotent(self):
        source = _test_engine()
        source_meta = MetaData()
        source_meta.reflect(bind=source)
        with source.begin() as conn:
            opportunities = source_meta.tables["opportunities"]
            conn.execute(insert(opportunities), [
                {"id": "founder-protected", "lifecycle_tier": "protected", "title": "Protected"},
                {"id": "cold-only", "lifecycle_tier": "cold", "title": "Not exported"},
            ])
            activity = source_meta.tables["founder_activity_events"]
            conn.execute(insert(activity), {
                "id": "activity-1", "opportunity_id": "founder-protected",
                "action_text": "mark_applied",
            })
            filters = source_meta.tables["founder_filter_settings"]
            conn.execute(insert(filters), {"id": "custom-filter", "action_text": "enabled"})

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "founder-state.json.gz"
            metrics = backup.export_snapshot(source, archive)
            payload = backup.load_snapshot(archive)
            self.assertEqual(metrics["backup_class"], "founder_state")
            self.assertEqual(payload["source_revision"], "0026_fr008_live_actions")
            self.assertEqual([row["id"] for row in payload["table_rows"]["opportunities"]], ["founder-protected"])
            self.assertEqual(metrics["source_json_bytes"] <= backup.MAX_SNAPSHOT_BYTES, True)

            target = _test_engine()
            target_meta = MetaData()
            target_meta.reflect(bind=target)
            with target.begin() as conn:
                conn.execute(insert(target_meta.tables["opportunities"]), {
                    "id": "founder-protected", "lifecycle_tier": "protected", "title": "Newer source truth",
                })
            result = backup.restore_snapshot(target, payload)
            backup.restore_snapshot(target, payload)
            with target.connect() as conn:
                title = conn.execute(select(target_meta.tables["opportunities"].c.title).where(
                    target_meta.tables["opportunities"].c.id == "founder-protected"
                )).scalar_one()
                activity_count = conn.execute(text("select count(*) from founder_activity_events")).scalar_one()
                filter_count = conn.execute(text("select count(*) from founder_filter_settings")).scalar_one()
                cold_count = conn.execute(select(target_meta.tables["opportunities"].c.id).where(
                    target_meta.tables["opportunities"].c.id == "cold-only"
                )).all()
            self.assertEqual(title, "Newer source truth")
            self.assertEqual(activity_count, 1)
            self.assertEqual(filter_count, 1)
            self.assertEqual(cold_count, [])
            self.assertEqual(result["restored_rows"]["founder_activity_events"], 1)
            target.dispose()
        source.dispose()

    def test_snapshot_enforces_egress_cap_and_rejects_corrupt_payload(self):
        engine = _test_engine()
        metadata = MetaData()
        metadata.reflect(bind=engine)
        with engine.begin() as conn:
            conn.execute(insert(metadata.tables["founder_activity_events"]), {
                "id": "large-activity", "action_text": "x" * 4096,
            })
        with tempfile.TemporaryDirectory() as temp:
            too_small = Path(temp) / "too-small.json.gz"
            with patch.object(backup, "MAX_SNAPSHOT_BYTES", 100):
                with self.assertRaisesRegex(backup.FounderStateBackupError, "8 MiB egress safety cap"):
                    backup.export_snapshot(engine, too_small)
            self.assertFalse(too_small.exists())
            corrupt = Path(temp) / "corrupt.json.gz"
            corrupt.write_bytes(b"not gzip")
            with self.assertRaisesRegex(backup.FounderStateBackupError, "snapshot invalid"):
                backup.load_snapshot(corrupt)
        engine.dispose()

    def test_postgresql_export_runs_against_the_migrated_disposable_schema(self):
        if os.environ.get("FR007_POSTGRES_BACKUP_TEST") != "1":
            self.skipTest("dedicated PostgreSQL backup acceptance is not enabled")
        url = os.environ.get("OPPORTUNITYOS_DB_URL", "")
        if not url.startswith("postgresql"):
            self.fail("PostgreSQL backup acceptance requires OPPORTUNITYOS_DB_URL")
        engine = create_engine(url, future=True, pool_size=1, max_overflow=0)
        try:
            with tempfile.TemporaryDirectory() as temp:
                metrics = backup.export_snapshot(engine, Path(temp) / "founder-state.json.gz")
                self.assertEqual(metrics["status"], "PASS")
                self.assertEqual(metrics["backup_class"], "founder_state")
                self.assertLessEqual(metrics["source_json_bytes"], backup.MAX_SNAPSHOT_BYTES)
                self.assertEqual(backup.load_snapshot(Path(temp) / "founder-state.json.gz")["source_revision"],
                                 "0026_fr008_live_actions")
        finally:
            engine.dispose()

    def test_postgresql_preflight_counts_large_toasted_opportunity_body(self):
        if os.environ.get("FR007_POSTGRES_BACKUP_TEST") != "1":
            self.skipTest("dedicated PostgreSQL backup acceptance is not enabled")
        url = os.environ.get("OPPORTUNITYOS_DB_URL", "")
        if not url.startswith("postgresql"):
            self.fail("PostgreSQL backup acceptance requires OPPORTUNITYOS_DB_URL")
        engine = create_engine(url, future=True, pool_size=1, max_overflow=0)
        opportunity_id = f"backup-toasted-{uuid4().hex}"
        record = OpportunityRecord(
            id=opportunity_id,
            track="employment",
            title="Bounded backup preflight fixture",
            organization="FR-007 disposable test",
            description="x" * (512 * 1024),
            source_id="fr007-backup-test",
            source_url="https://example.invalid/fr007-backup-test",
            content_hash="a" * 64,
            lifecycle_tier="protected",
        )
        with Session(engine) as session:
            session.add(record)
            session.commit()
        try:
            with tempfile.TemporaryDirectory() as temp:
                archive = Path(temp) / "must-not-be-written.json.gz"
                with patch.object(backup, "MAX_SNAPSHOT_BYTES", 256 * 1024):
                    with self.assertRaisesRegex(backup.FounderStateBackupError,
                                                "source rows exceed the 8 MiB egress safety cap"):
                        backup.export_snapshot(engine, archive)
                self.assertFalse(archive.exists())
        finally:
            with engine.begin() as conn:
                conn.execute(delete(OpportunityRecord).where(OpportunityRecord.id == opportunity_id))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
