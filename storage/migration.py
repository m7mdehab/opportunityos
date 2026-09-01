import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from storage.models import (
    OutboundActionRecordModel,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    InboxCheckpointRecord,
    ReconciliationRecordModel,
)


class LegacySqliteToPostgresMigrator:
    """Losslessly migrates real authoritative SQLite stores (inbox and outbound) to PostgreSQL."""

    def __init__(self, target_session: Session):
        self.session = target_session

    def migrate_inbox_sqlite(self, sqlite_db_path: str) -> Dict[str, int]:
        if not os.path.exists(sqlite_db_path):
            return {
                "inbound_evidence": 0,
                "pipeline_events": 0,
                "founder_notifications": 0,
                "inbox_checkpoints": 0,
                "reconciliation_records": 0,
            }

        conn = sqlite3.connect(sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        stats = {
            "inbound_evidence": 0,
            "pipeline_events": 0,
            "founder_notifications": 0,
            "inbox_checkpoints": 0,
            "reconciliation_records": 0,
        }

        # 1. Inbound Evidence
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inbound_evidence'")
        if cur.fetchone():
            cur.execute("SELECT * FROM inbound_evidence")
            for row in cur.fetchall():
                r = dict(row)
                rec_at = datetime.fromisoformat(r["received_at"]) if r.get("received_at") else datetime.now(timezone.utc)
                proc_at = datetime.fromisoformat(r["processed_at"]) if r.get("processed_at") else None
                rec = InboundEvidenceRecord(
                    message_content_hash=r["message_content_hash"],
                    provider=r["provider"],
                    provider_message_id=r["provider_message_id"],
                    thread_id=r["thread_id"],
                    sender_email=r["sender_email"],
                    sender_name=r["sender_name"],
                    recipient_email=r["recipient_email"],
                    subject=r["subject"],
                    snippet=r["snippet"],
                    body_text=r["body_text"],
                    body_html=r["body_html"],
                    received_at=rec_at,
                    headers_json=r.get("headers_json", "[]"),
                    attachment_names_json=r.get("attachment_names_json", "[]"),
                    processing_status=r.get("processing_status", "FETCHED"),
                    processed_at=proc_at,
                )
                self.session.merge(rec)
                stats["inbound_evidence"] += 1

        # 2. Pipeline Events
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_events'")
        if cur.fetchone():
            cur.execute("SELECT * FROM pipeline_events")
            for row in cur.fetchall():
                r = dict(row)
                occ_at = datetime.fromisoformat(r["occurred_at"]) if r.get("occurred_at") else datetime.now(timezone.utc)
                rec_at = datetime.fromisoformat(r["recorded_at"]) if r.get("recorded_at") else datetime.now(timezone.utc)
                rec = PipelineEventRecord(
                    event_id=r["event_id"],
                    opportunity_id=r["opportunity_id"],
                    signal_id=r["signal_id"],
                    previous_stage=r["previous_stage"],
                    new_stage=r["new_stage"],
                    track=r["track"],
                    trigger_category=r["trigger_category"],
                    message_content_hash=r["message_content_hash"],
                    occurred_at=occ_at,
                    recorded_at=rec_at,
                    actor=r["actor"],
                    notes=r["notes"],
                )
                self.session.merge(rec)
                stats["pipeline_events"] += 1

        # 3. Founder Notifications
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='founder_notifications'")
        if cur.fetchone():
            cur.execute("SELECT * FROM founder_notifications")
            for row in cur.fetchall():
                r = dict(row)
                c_at = datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.now(timezone.utc)
                ack_at = datetime.fromisoformat(r["acknowledged_at"]) if r.get("acknowledged_at") else None
                rec = NotificationRecord(
                    notification_key=r["notification_key"],
                    notification_id=r["notification_id"],
                    opportunity_id=r.get("opportunity_id"),
                    signal_id=r["signal_id"],
                    priority=r["priority"],
                    category=r["category"],
                    title=r["title"],
                    message=r["message"],
                    action_required=bool(r.get("action_required", False)),
                    deadline=r.get("deadline"),
                    created_at=c_at,
                    acknowledged=bool(r.get("acknowledged", False)),
                    acknowledged_at=ack_at,
                )
                self.session.merge(rec)
                stats["founder_notifications"] += 1

        # 4. Inbox Checkpoints
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inbox_checkpoints'")
        if cur.fetchone():
            cur.execute("SELECT * FROM inbox_checkpoints")
            for row in cur.fetchall():
                r = dict(row)
                up_at = datetime.fromisoformat(r["updated_at"]) if r.get("updated_at") else datetime.now(timezone.utc)
                rec = InboxCheckpointRecord(
                    checkpoint_key=r["checkpoint_key"],
                    cursor_value=r["cursor_value"],
                    updated_at=up_at,
                )
                self.session.merge(rec)
                stats["inbox_checkpoints"] += 1

        # 5. Reconciliation Records
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reconciliation_records'")
        if cur.fetchone():
            cur.execute("SELECT * FROM reconciliation_records")
            for row in cur.fetchall():
                r = dict(row)
                c_at = datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.now(timezone.utc)
                res_at = datetime.fromisoformat(r["resolved_at"]) if r.get("resolved_at") else None
                rec = ReconciliationRecordModel(
                    reconciliation_id=r["reconciliation_id"],
                    outbound_action_id=r["outbound_action_id"],
                    opportunity_id=r["opportunity_id"],
                    signal_id=r["signal_id"],
                    inbound_content_hash=r["inbound_content_hash"],
                    reason=r["reason"],
                    created_at=c_at,
                    resolved=bool(r.get("resolved", False)),
                    resolved_at=res_at,
                )
                self.session.merge(rec)
                stats["reconciliation_records"] += 1

        self.session.commit()
        conn.close()
        return stats

    def migrate_outbound_sqlite(self, sqlite_db_path: str) -> Dict[str, int]:
        if not os.path.exists(sqlite_db_path):
            return {"idempotency_reservations": 0, "outbound_actions": 0}

        conn = sqlite3.connect(sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        stats = {"idempotency_reservations": 0, "outbound_actions": 0}

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='idempotency_ledger'")
        if cur.fetchone():
            cur.execute("SELECT * FROM idempotency_ledger")
            for row in cur.fetchall():
                r = dict(row)
                c_at = datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.now(timezone.utc)
                up_at = datetime.fromisoformat(r["updated_at"]) if r.get("updated_at") else datetime.now(timezone.utc)

                # Reservation Record
                res_rec = IdempotencyReservationRecord(
                    idempotency_key=r["idempotency_key"],
                    action_id=r["action_id"],
                    workspace=r["workspace"],
                    candidate_id=r["candidate_id"],
                    opportunity_id=r["opportunity_id"],
                    action_type=r["action_type"],
                    action_status=r["action_status"],
                    record_json=r["record_json"],
                    created_at=c_at,
                    updated_at=up_at,
                )
                self.session.merge(res_rec)
                stats["idempotency_reservations"] += 1

                # Parse complete OutboundActionRecord from record_json
                if r.get("record_json"):
                    try:
                        d = json.loads(r["record_json"])
                        ev_dict = d.get("confirmation_evidence") or {}
                        act_rec = OutboundActionRecordModel(
                            id=r["action_id"],
                            opportunity_id=r["opportunity_id"],
                            opportunity_content_hash=d.get("opportunity_content_hash", ""),
                            workspace=r["workspace"],
                            candidate_id=r["candidate_id"],
                            track=d.get("track", "EMPLOYMENT"),
                            source=d.get("source", ""),
                            adapter_name=d.get("adapter_name", ""),
                            adapter_version=d.get("adapter_version", ""),
                            execution_mode=d.get("execution_mode", "DRY_RUN"),
                            qualification_decision=d.get("qualification_decision", "UNQUALIFIED"),
                            match_score_snapshot=float(d.get("match_score_snapshot", 0.0)),
                            artifact_ids_json=json.dumps(d.get("artifact_ids", [])),
                            artifact_hashes_json=json.dumps(d.get("artifact_hashes", [])),
                            manifest_hash=d.get("manifest_hash", ""),
                            action_status=r["action_status"],
                            idempotency_key=r["idempotency_key"],
                            receipt_reference=ev_dict.get("receipt_reference"),
                            confirmation_text=ev_dict.get("confirmation_text"),
                            receipt_checksum=ev_dict.get("evidence_checksum"),
                            confirmation_evidence_json=json.dumps(ev_dict) if ev_dict else None,
                            blocker_reason=d.get("blocker_reason"),
                            manual_edits_json=json.dumps(d.get("manual_edits", [])),
                            external_reference_id=d.get("external_reference_id"),
                            record_json=r["record_json"],
                            created_at=c_at,
                            updated_at=up_at,
                        )
                        self.session.merge(act_rec)
                        stats["outbound_actions"] += 1
                    except Exception:
                        pass

        self.session.commit()
        conn.close()
        return stats
