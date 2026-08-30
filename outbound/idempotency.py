"""Durable SQLite Idempotency & Duplicate Prevention Ledger."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from matching.models import QualificationDecision, Track
from .models import (
    ActionStatus,
    ConfirmationEvidence,
    ExecutionMode,
    OutboundActionRecord,
)


class DuplicateSubmissionError(ValueError):
    """Raised when duplicate submission is attempted."""


class UnknownOutcomeFrozenError(ValueError):
    """Raised when an attempt is made to execute an action with unresolved UNKNOWN_OUTCOME."""


class IdempotencyLedger:
    """Thread-safe and process-durable submission ledger preventing duplicate side effects."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._memory_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", timeout=30.0, check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS idempotency_ledger (
                            idempotency_key TEXT PRIMARY KEY,
                            action_id TEXT NOT NULL,
                            workspace TEXT NOT NULL,
                            candidate_id TEXT NOT NULL,
                            opportunity_id TEXT NOT NULL,
                            action_type TEXT NOT NULL,
                            action_status TEXT NOT NULL,
                            record_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                    """)
            finally:
                if self._memory_conn is None:
                    conn.close()

    @classmethod
    def compute_idempotency_key(
        cls,
        workspace: str,
        candidate_id: str,
        opportunity_id: str,
        action_type: str,
    ) -> str:
        payload = f"{workspace}:{candidate_id}:{opportunity_id}:{action_type}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _record_to_json(self, record: OutboundActionRecord) -> str:
        evidence_dict = None
        if record.confirmation_evidence:
            evidence_dict = {
                "confirmed": record.confirmation_evidence.confirmed,
                "confirmation_text": record.confirmation_evidence.confirmation_text,
                "application_id": record.confirmation_evidence.application_id,
                "receipt_reference": record.confirmation_evidence.receipt_reference,
                "final_url": record.confirmation_evidence.final_url,
                "detected_at": record.confirmation_evidence.detected_at,
                "evidence_checksum": record.confirmation_evidence.evidence_checksum,
            }

        data = {
            "action_id": record.action_id,
            "opportunity_id": record.opportunity_id,
            "opportunity_content_hash": record.opportunity_content_hash,
            "workspace": record.workspace,
            "candidate_id": record.candidate_id,
            "track": record.track.value,
            "source": record.source,
            "adapter_name": record.adapter_name,
            "adapter_version": record.adapter_version,
            "execution_mode": record.execution_mode.value,
            "qualification_decision": record.qualification_decision.value,
            "match_score_snapshot": record.match_score_snapshot,
            "artifact_ids": list(record.artifact_ids),
            "artifact_hashes": list(record.artifact_hashes),
            "manifest_hash": record.manifest_hash,
            "action_status": record.action_status.value,
            "idempotency_key": record.idempotency_key,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "confirmation_evidence": evidence_dict,
            "blocker_reason": record.blocker_reason,
            "manual_edits": list(record.manual_edits),
            "external_reference_id": record.external_reference_id,
        }
        return json.dumps(data)

    def _json_to_record(self, data_str: str) -> OutboundActionRecord:
        d = json.loads(data_str)
        ev = None
        if d.get("confirmation_evidence"):
            ev_data = d["confirmation_evidence"]
            ev = ConfirmationEvidence(
                confirmed=ev_data["confirmed"],
                confirmation_text=ev_data["confirmation_text"],
                application_id=ev_data.get("application_id", ""),
                receipt_reference=ev_data.get("receipt_reference", ""),
                final_url=ev_data.get("final_url", ""),
                detected_at=ev_data.get("detected_at", ""),
                evidence_checksum=ev_data.get("evidence_checksum", ""),
            )

        return OutboundActionRecord(
            action_id=d["action_id"],
            opportunity_id=d["opportunity_id"],
            opportunity_content_hash=d["opportunity_content_hash"],
            workspace=d.get("workspace", "default"),
            candidate_id=d.get("candidate_id", "founder"),
            track=Track(d["track"]),
            source=d["source"],
            adapter_name=d["adapter_name"],
            adapter_version=d["adapter_version"],
            execution_mode=ExecutionMode(d["execution_mode"]),
            qualification_decision=QualificationDecision(d["qualification_decision"]),
            match_score_snapshot=d["match_score_snapshot"],
            artifact_ids=tuple(d["artifact_ids"]),
            artifact_hashes=tuple(d["artifact_hashes"]),
            manifest_hash=d["manifest_hash"],
            action_status=ActionStatus(d["action_status"]),
            idempotency_key=d["idempotency_key"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            confirmation_evidence=ev,
            blocker_reason=d.get("blocker_reason", ""),
            manual_edits=tuple(d.get("manual_edits", ())),
            external_reference_id=d.get("external_reference_id", ""),
        )

    def reserve_submission(self, record: OutboundActionRecord) -> None:
        """Atomically reserve submission intent. Blocks duplicates and frozen outcomes."""
        key = record.idempotency_key
        submitting_record = dataclasses.replace(record, action_status=ActionStatus.SUBMITTING)
        record_json = self._record_to_json(submitting_record)

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute("SELECT action_status FROM idempotency_ledger WHERE idempotency_key = ?", (key,))
                    row = cur.fetchone()
                    if row is not None:
                        status = row["action_status"]
                        if status == ActionStatus.UNKNOWN_OUTCOME.value:
                            raise UnknownOutcomeFrozenError(
                                f"Submission permanently blocked: action '{key}' resulted in UNKNOWN_OUTCOME and requires explicit manual reconciliation before retry."
                            )
                        if status in (ActionStatus.SUBMITTING.value, ActionStatus.SUBMITTED.value, ActionStatus.CONFIRMED.value):
                            raise DuplicateSubmissionError(
                                f"Duplicate submission blocked for idempotency key '{key}' (current status: {status})"
                            )

                    cur.execute("""
                        INSERT INTO idempotency_ledger (
                            idempotency_key, action_id, workspace, candidate_id, opportunity_id,
                            action_type, action_status, record_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(idempotency_key) DO UPDATE SET
                            action_status = excluded.action_status,
                            record_json = excluded.record_json,
                            updated_at = excluded.updated_at
                    """, (
                        key, submitting_record.action_id, submitting_record.workspace, submitting_record.candidate_id,
                        submitting_record.opportunity_id, "application", ActionStatus.SUBMITTING.value,
                        record_json, submitting_record.created_at, submitting_record.updated_at,
                    ))
            finally:
                if self._memory_conn is None:
                    conn.close()

    def transition_status(
        self,
        idempotency_key: str,
        new_status: ActionStatus,
        evidence: ConfirmationEvidence | None = None,
        blocker_reason: str = "",
        external_reference_id: str = "",
    ) -> OutboundActionRecord:
        """Transition action record state."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute("SELECT record_json FROM idempotency_ledger WHERE idempotency_key = ?", (idempotency_key,))
                    row = cur.fetchone()
                    if row is None:
                        raise KeyError(f"No record found for idempotency key '{idempotency_key}'")

                    existing = self._json_to_record(row["record_json"])
                    updated = OutboundActionRecord(
                        action_id=existing.action_id,
                        opportunity_id=existing.opportunity_id,
                        opportunity_content_hash=existing.opportunity_content_hash,
                        workspace=existing.workspace,
                        candidate_id=existing.candidate_id,
                        track=existing.track,
                        source=existing.source,
                        adapter_name=existing.adapter_name,
                        adapter_version=existing.adapter_version,
                        execution_mode=existing.execution_mode,
                        qualification_decision=existing.qualification_decision,
                        match_score_snapshot=existing.match_score_snapshot,
                        artifact_ids=existing.artifact_ids,
                        artifact_hashes=existing.artifact_hashes,
                        manifest_hash=existing.manifest_hash,
                        action_status=new_status,
                        idempotency_key=existing.idempotency_key,
                        created_at=existing.created_at,
                        updated_at="2026-08-30T00:00:00Z",
                        confirmation_evidence=evidence if evidence is not None else existing.confirmation_evidence,
                        blocker_reason=blocker_reason or existing.blocker_reason,
                        manual_edits=existing.manual_edits,
                        external_reference_id=external_reference_id or existing.external_reference_id,
                    )
                    updated_json = self._record_to_json(updated)
                    cur.execute("""
                        UPDATE idempotency_ledger SET
                            action_status = ?,
                            record_json = ?,
                            updated_at = ?
                        WHERE idempotency_key = ?
                    """, (new_status.value, updated_json, updated.updated_at, idempotency_key))
                    return updated
            finally:
                if self._memory_conn is None:
                    conn.close()

    def is_duplicate(self, workspace: str, candidate_id: str, opportunity_id: str, action_type: str) -> bool:
        key = self.compute_idempotency_key(workspace, candidate_id, opportunity_id, action_type)
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT action_status FROM idempotency_ledger WHERE idempotency_key = ?", (key,))
                row = cur.fetchone()
                if row is None:
                    return False
                status = row["action_status"]
                return status in (
                    ActionStatus.SUBMITTING.value,
                    ActionStatus.SUBMITTED.value,
                    ActionStatus.CONFIRMED.value,
                    ActionStatus.UNKNOWN_OUTCOME.value,
                )
            finally:
                if self._memory_conn is None:
                    conn.close()

    def get_record(self, idempotency_key: str) -> OutboundActionRecord | None:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT record_json FROM idempotency_ledger WHERE idempotency_key = ?", (idempotency_key,))
                row = cur.fetchone()
                if row is None:
                    return None
                return self._json_to_record(row["record_json"])
            finally:
                if self._memory_conn is None:
                    conn.close()

    def reconcile_unknown_outcome(
        self,
        idempotency_key: str,
        new_status: ActionStatus,
        reason: str = "manual reconciliation",
    ) -> OutboundActionRecord:
        """Explicit founder reconciliation allowing recovery from UNKNOWN_OUTCOME."""
        return self.transition_status(
            idempotency_key=idempotency_key,
            new_status=new_status,
            blocker_reason=reason,
        )
