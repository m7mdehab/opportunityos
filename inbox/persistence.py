"""Durable SQLite Persistence Layer with Explicit Processing Lifecycle (FETCHED -> PROCESSED)."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Sequence
from matching.models import Track
from .models import (
    DerivedOpportunityState,
    ExtractedDeadline,
    FounderNotificationRecord,
    InboundMessageEvidence,
    InboundSignal,
    OpportunityStage,
    PipelineEvent,
    SignalCategory,
    SignalPriority,
)

DEFAULT_INBOX_DB_PATH = Path("private/inbox_store.db")


class DurableInboxStore:
    """Thread-safe and process-durable SQLite persistence store for inbox subsystem."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or DEFAULT_INBOX_DB_PATH)
        self._lock = threading.Lock()
        self._memory_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
            self._memory_conn.row_factory = sqlite3.Row
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS inbound_evidence (
                        message_content_hash TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        provider_message_id TEXT NOT NULL,
                        thread_id TEXT NOT NULL,
                        sender_email TEXT NOT NULL,
                        sender_name TEXT NOT NULL,
                        recipient_email TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        snippet TEXT NOT NULL,
                        body_text TEXT NOT NULL,
                        body_html TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        headers_json TEXT NOT NULL,
                        attachment_names_json TEXT NOT NULL,
                        processing_status TEXT NOT NULL DEFAULT 'FETCHED',
                        processed_at TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pipeline_events (
                        event_id TEXT PRIMARY KEY,
                        opportunity_id TEXT NOT NULL,
                        signal_id TEXT NOT NULL,
                        previous_stage TEXT NOT NULL,
                        new_stage TEXT NOT NULL,
                        track TEXT NOT NULL,
                        trigger_category TEXT NOT NULL,
                        message_content_hash TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        notes TEXT NOT NULL,
                        UNIQUE(signal_id, opportunity_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS founder_notifications (
                        notification_key TEXT PRIMARY KEY,
                        notification_id TEXT NOT NULL,
                        opportunity_id TEXT,
                        signal_id TEXT NOT NULL,
                        priority TEXT NOT NULL,
                        category TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        action_required INTEGER NOT NULL,
                        deadline TEXT,
                        created_at TEXT NOT NULL,
                        acknowledged INTEGER NOT NULL,
                        acknowledged_at TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS inbox_checkpoints (
                        checkpoint_key TEXT PRIMARY KEY,
                        cursor_value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS reconciliation_records (
                        reconciliation_id TEXT PRIMARY KEY,
                        outbound_action_id TEXT NOT NULL,
                        opportunity_id TEXT NOT NULL,
                        signal_id TEXT NOT NULL,
                        inbound_content_hash TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        resolved INTEGER NOT NULL,
                        resolved_at TEXT
                    )
                """)
            finally:
                if self._memory_conn is None:
                    conn.close()

    def store_evidence(self, msg: InboundMessageEvidence, status: str = "FETCHED") -> bool:
        """Store immutable inbound message evidence durably."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO inbound_evidence (
                        message_content_hash, provider, provider_message_id, thread_id,
                        sender_email, sender_name, recipient_email, subject, snippet,
                        body_text, body_html, received_at, headers_json, attachment_names_json,
                        processing_status, processed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        msg.message_content_hash, msg.provider, msg.provider_message_id, msg.thread_id,
                        msg.sender_email, msg.sender_name, msg.recipient_email, msg.subject, msg.snippet,
                        msg.body_text, msg.body_html, msg.received_at,
                        json.dumps(msg.headers), json.dumps(msg.attachment_names),
                        status,
                    ),
                )
                return cur.rowcount > 0
            finally:
                if self._memory_conn is None:
                    conn.close()

    def mark_evidence_processed(self, content_hash: str, processed_at: str) -> None:
        """Mark evidence as fully processed (all events/notifications/reconciliations committed)."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE inbound_evidence SET processing_status = 'PROCESSED', processed_at = ? WHERE message_content_hash = ?",
                    (processed_at, content_hash),
                )
            finally:
                if self._memory_conn is None:
                    conn.close()

    def is_evidence_processed(self, content_hash: str) -> bool:
        """Check if message has already completed full processing."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT processing_status FROM inbound_evidence WHERE message_content_hash = ?", (content_hash,))
                row = cur.fetchone()
                return bool(row and row["processing_status"] == "PROCESSED")
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_evidence(self, content_hash: str) -> InboundMessageEvidence | None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM inbound_evidence WHERE message_content_hash = ?", (content_hash,))
                row = cur.fetchone()
                if not row:
                    return None
                return InboundMessageEvidence(
                    provider=row["provider"], provider_message_id=row["provider_message_id"],
                    thread_id=row["thread_id"], sender_email=row["sender_email"],
                    sender_name=row["sender_name"], recipient_email=row["recipient_email"],
                    subject=row["subject"], snippet=row["snippet"],
                    body_text=row["body_text"], body_html=row["body_html"],
                    received_at=row["received_at"],
                    headers=tuple([tuple(h) for h in json.loads(row["headers_json"])]),
                    attachment_names=tuple(json.loads(row["attachment_names_json"])),
                    message_content_hash=row["message_content_hash"],
                )
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_all_evidence(self) -> tuple[InboundMessageEvidence, ...]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM inbound_evidence ORDER BY received_at ASC")
                evs = []
                for row in cur.fetchall():
                    evs.append(InboundMessageEvidence(
                        provider=row["provider"], provider_message_id=row["provider_message_id"],
                        thread_id=row["thread_id"], sender_email=row["sender_email"],
                        sender_name=row["sender_name"], recipient_email=row["recipient_email"],
                        subject=row["subject"], snippet=row["snippet"],
                        body_text=row["body_text"], body_html=row["body_html"],
                        received_at=row["received_at"],
                        headers=tuple([tuple(h) for h in json.loads(row["headers_json"])]),
                        attachment_names=tuple(json.loads(row["attachment_names_json"])),
                        message_content_hash=row["message_content_hash"],
                    ))
                return tuple(evs)
            finally:
                if self._memory_conn is None:
                    conn.close()

    def store_pipeline_event(self, event: PipelineEvent) -> bool:
        """Store pipeline event with (signal_id, opportunity_id) uniqueness."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO pipeline_events (
                        event_id, opportunity_id, signal_id, previous_stage, new_stage,
                        track, trigger_category, message_content_hash, occurred_at,
                        recorded_at, actor, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id, event.opportunity_id, event.signal_id,
                        event.previous_stage.value, event.new_stage.value,
                        event.track.value, event.trigger_category.value,
                        event.message_content_hash, event.occurred_at,
                        event.recorded_at, event.actor, event.notes,
                    ),
                )
                return cur.rowcount > 0
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_events_for_opportunity(self, opportunity_id: str) -> tuple[PipelineEvent, ...]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM pipeline_events WHERE opportunity_id = ? ORDER BY occurred_at ASC, recorded_at ASC, event_id ASC", (opportunity_id,))
                events = []
                for row in cur.fetchall():
                    events.append(PipelineEvent(
                        event_id=row["event_id"], opportunity_id=row["opportunity_id"],
                        signal_id=row["signal_id"], previous_stage=OpportunityStage(row["previous_stage"]),
                        new_stage=OpportunityStage(row["new_stage"]), track=Track(row["track"]),
                        trigger_category=SignalCategory(row["trigger_category"]),
                        message_content_hash=row["message_content_hash"], occurred_at=row["occurred_at"],
                        recorded_at=row["recorded_at"], actor=row["actor"], notes=row["notes"],
                    ))
                return tuple(events)
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_all_pipeline_events(self) -> tuple[PipelineEvent, ...]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM pipeline_events ORDER BY occurred_at ASC, recorded_at ASC, event_id ASC")
                events = []
                for row in cur.fetchall():
                    events.append(PipelineEvent(
                        event_id=row["event_id"], opportunity_id=row["opportunity_id"],
                        signal_id=row["signal_id"], previous_stage=OpportunityStage(row["previous_stage"]),
                        new_stage=OpportunityStage(row["new_stage"]), track=Track(row["track"]),
                        trigger_category=SignalCategory(row["trigger_category"]),
                        message_content_hash=row["message_content_hash"], occurred_at=row["occurred_at"],
                        recorded_at=row["recorded_at"], actor=row["actor"], notes=row["notes"],
                    ))
                return tuple(events)
            finally:
                if self._memory_conn is None:
                    conn.close()

    def store_notification(self, notif: FounderNotificationRecord) -> bool:
        """Store notification record keyed by notification_key."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO founder_notifications (
                        notification_key, notification_id, opportunity_id, signal_id,
                        priority, category, title, message, action_required,
                        deadline, created_at, acknowledged, acknowledged_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        notif.notification_key, notif.notification_id, notif.opportunity_id,
                        notif.signal_id, notif.priority.value, notif.category.value,
                        notif.title, notif.message, 1 if notif.action_required else 0,
                        notif.deadline, notif.created_at, 1 if notif.acknowledged else 0,
                        notif.acknowledged_at,
                    ),
                )
                return cur.rowcount > 0
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_all_notifications(self) -> tuple[FounderNotificationRecord, ...]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM founder_notifications ORDER BY created_at ASC, notification_id ASC")
                notifs = []
                for row in cur.fetchall():
                    notifs.append(FounderNotificationRecord(
                        notification_id=row["notification_id"], notification_key=row["notification_key"],
                        opportunity_id=row["opportunity_id"], signal_id=row["signal_id"],
                        priority=SignalPriority(row["priority"]), category=SignalCategory(row["category"]),
                        title=row["title"], message=row["message"],
                        action_required=bool(row["action_required"]), deadline=row["deadline"],
                        created_at=row["created_at"], acknowledged=bool(row["acknowledged"]),
                        acknowledged_at=row["acknowledged_at"],
                    ))
                return tuple(notifs)
            finally:
                if self._memory_conn is None:
                    conn.close()

    def acknowledge_notification(self, notification_key: str, acknowledged_at: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "UPDATE founder_notifications SET acknowledged = 1, acknowledged_at = ? WHERE notification_key = ?",
                    (acknowledged_at, notification_key),
                )
                return cur.rowcount > 0
            finally:
                if self._memory_conn is None:
                    conn.close()

    def save_checkpoint(self, checkpoint_key: str, cursor_value: str, updated_at: str) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO inbox_checkpoints (checkpoint_key, cursor_value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(checkpoint_key) DO UPDATE SET cursor_value = excluded.cursor_value, updated_at = excluded.updated_at
                    """,
                    (checkpoint_key, cursor_value, updated_at),
                )
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_checkpoint(self, checkpoint_key: str) -> str | None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT cursor_value FROM inbox_checkpoints WHERE checkpoint_key = ?", (checkpoint_key,))
                row = cur.fetchone()
                return row["cursor_value"] if row else None
            finally:
                if self._memory_conn is None:
                    conn.close()

    def record_reconciliation(
        self,
        reconciliation_id: str,
        outbound_action_id: str,
        opportunity_id: str,
        signal_id: str,
        inbound_content_hash: str,
        reason: str,
        created_at: str,
    ) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO reconciliation_records (
                        reconciliation_id, outbound_action_id, opportunity_id,
                        signal_id, inbound_content_hash, reason, created_at, resolved, resolved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
                    """,
                    (reconciliation_id, outbound_action_id, opportunity_id, signal_id, inbound_content_hash, reason, created_at),
                )
                return cur.rowcount > 0
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_unresolved_reconciliations(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM reconciliation_records WHERE resolved = 0")
                return tuple([dict(r) for r in cur.fetchall()])
            finally:
                if self._memory_conn is None:
                    conn.close()
