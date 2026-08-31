import sqlite3
import os
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from storage.models import (
    OutboundActionRecord,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
)

class LegacySqliteToPostgresMigrator:
    def __init__(self, target_session: Session):
        self.session = target_session

    def migrate_inbox_sqlite(self, sqlite_db_path: str) -> Dict[str, int]:
        if not os.path.exists(sqlite_db_path):
            return {"evidence": 0, "events": 0, "notifications": 0}
        
        conn = sqlite3.connect(sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        stats = {"evidence": 0, "events": 0, "notifications": 0}

        # 1. Inbound evidence
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inbound_evidence'")
        if cur.fetchone():
            cur.execute("SELECT * FROM inbound_evidence")
            for row in cur.fetchall():
                row_dict = dict(row)
                rec_at = datetime.fromisoformat(row_dict["received_at"]) if "received_at" in row_dict and row_dict["received_at"] else datetime.now(timezone.utc)
                proc_at = datetime.fromisoformat(row_dict["processed_at"]) if "processed_at" in row_dict and row_dict["processed_at"] else None
                rec = InboundEvidenceRecord(
                    id=row_dict.get("id") or row_dict.get("signal_id") or row_dict.get("message_id"),
                    message_id=row_dict["message_id"],
                    source_provider=row_dict["source_provider"],
                    sender=row_dict["sender"],
                    subject=row_dict["subject"],
                    body_hash=row_dict.get("body_hash", ""),
                    received_at=rec_at,
                    processing_status=row_dict.get("processing_status", "FETCHED"),
                    processed_at=proc_at,
                    raw_headers_json=row_dict.get("raw_headers_json"),
                )
                self.session.merge(rec)
                stats["evidence"] += 1

        # 2. Pipeline events
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_events'")
        if cur.fetchone():
            cur.execute("SELECT * FROM pipeline_events")
            for row in cur.fetchall():
                row_dict = dict(row)
                src_time = datetime.fromisoformat(row_dict["source_timestamp"]) if "source_timestamp" in row_dict and row_dict["source_timestamp"] else datetime.now(timezone.utc)
                created_at = datetime.fromisoformat(row_dict["created_at"]) if "created_at" in row_dict and row_dict["created_at"] else datetime.now(timezone.utc)
                rec = PipelineEventRecord(
                    id=row_dict["id"],
                    opportunity_id=row_dict["opportunity_id"],
                    signal_id=row_dict["signal_id"],
                    signal_category=row_dict["signal_category"],
                    source_timestamp=src_time,
                    confidence=float(row_dict.get("confidence", 1.0)),
                    provenance_hash=row_dict.get("provenance_hash", ""),
                    event_metadata_json=row_dict.get("event_metadata_json"),
                    created_at=created_at,
                )
                self.session.merge(rec)
                stats["events"] += 1

        # 3. Notifications
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'")
        if cur.fetchone():
            cur.execute("SELECT * FROM notifications")
            for row in cur.fetchall():
                row_dict = dict(row)
                created_at = datetime.fromisoformat(row_dict["created_at"]) if "created_at" in row_dict and row_dict["created_at"] else datetime.now(timezone.utc)
                rec = NotificationRecord(
                    id=row_dict["id"],
                    notification_key=row_dict["notification_key"],
                    opportunity_id=row_dict["opportunity_id"],
                    priority=row_dict["priority"],
                    headline=row_dict["headline"],
                    body=row_dict["body"],
                    action_required=bool(row_dict.get("action_required", False)),
                    deadline=row_dict.get("deadline"),
                    created_at=created_at,
                )
                self.session.merge(rec)
                stats["notifications"] += 1

        self.session.commit()
        conn.close()
        return stats

    def migrate_outbound_sqlite(self, sqlite_db_path: str) -> Dict[str, int]:
        if not os.path.exists(sqlite_db_path):
            return {"reservations": 0, "actions": 0}

        conn = sqlite3.connect(sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        stats = {"reservations": 0, "actions": 0}

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='idempotency_reservations'")
        if cur.fetchone():
            cur.execute("SELECT * FROM idempotency_reservations")
            for row in cur.fetchall():
                row_dict = dict(row)
                created_at = datetime.fromisoformat(row_dict["created_at"]) if "created_at" in row_dict and row_dict["created_at"] else datetime.now(timezone.utc)
                rec = IdempotencyReservationRecord(
                    idempotency_key=row_dict["idempotency_key"],
                    action_id=row_dict["action_id"],
                    opportunity_id=row_dict["opportunity_id"],
                    status=row_dict.get("status", "RESERVED"),
                    created_at=created_at,
                )
                self.session.merge(rec)
                stats["reservations"] += 1

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='outbound_actions'")
        if cur.fetchone():
            cur.execute("SELECT * FROM outbound_actions")
            for row in cur.fetchall():
                row_dict = dict(row)
                created_at = datetime.fromisoformat(row_dict["created_at"]) if "created_at" in row_dict and row_dict["created_at"] else datetime.now(timezone.utc)
                updated_at = datetime.fromisoformat(row_dict["updated_at"]) if "updated_at" in row_dict and row_dict["updated_at"] else datetime.now(timezone.utc)
                rec = OutboundActionRecord(
                    id=row_dict["id"],
                    opportunity_id=row_dict["opportunity_id"],
                    execution_mode=row_dict["execution_mode"],
                    action_status=row_dict["action_status"],
                    idempotency_key=row_dict["idempotency_key"],
                    prepared_manifest_hash=row_dict.get("prepared_manifest_hash"),
                    receipt_reference=row_dict.get("receipt_reference"),
                    confirmation_text=row_dict.get("confirmation_text"),
                    receipt_checksum=row_dict.get("receipt_checksum"),
                    error_message=row_dict.get("error_message"),
                    created_at=created_at,
                    updated_at=updated_at,
                )
                self.session.merge(rec)
                stats["actions"] += 1

        self.session.commit()
        conn.close()
        return stats
